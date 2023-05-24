import json
import os
import time
from typing import Any, Callable, Union, cast

import requests
from netns_traverse import ns, root_fd

from mininet.node import Node


class ZeroTierNode(Node):
    """A node running ZeroTier One.

    :param name: name of node
    :type name: str
    :param inNamespace: in network namespace?, defaults to True
    :type inNamespace: bool, optional
    :param trustedPath: a list that contain trusted paths (dict has 2 keys:
        `net_addr` and `trusted_path_id`), default to None
    :type trustedPath: list[dict[str, Any]], optional
    """

    _HOME_FOLDER = "/var/lib/zerotier-one"

    def __init__(self, name, inNamespace=True, **params):
        privateDirs = params.pop("privateDirs", [])
        super().__init__(
            name,
            inNamespace=inNamespace,
            privateDirs=(ZeroTierNode._HOME_FOLDER, *privateDirs),
            **params,
        )

    def config(self, mac=None, ip=None, defaultRoute=None, lo="up", **_params):
        super().config(mac, ip, defaultRoute, lo, **_params)

        trustedPaths = _params.get("trustedPaths")
        if trustedPaths is not None:
            self._configTrustedPath(trustedPaths)

        self.startZeroTier()

        node_id = self.cmd("zerotier-cli info | cut -d ' ' -f 3")
        assert isinstance(node_id, str)
        self.node_id = node_id.strip()

        auth_token = self.cmd(f"cat {ZeroTierNode._HOME_FOLDER}/authtoken.secret")
        assert isinstance(auth_token, str)
        self.auth_token = auth_token.strip()
        self.auth_header = {"X-ZT1-AUTH": self.auth_token}

    def _configTrustedPath(self, trustedPaths: list[dict[str, Any]]):
        """Generate local.conf with trusted paths info.

        See: https://docs.zerotier.com/zerotier/zerotier.conf#local-configuration-options

        :param trustedPaths: a list that contain trusted paths (dict has 2 keys:
            `net_addr` and `trusted_path_id`), default to None
        :type trustedPaths: list[dict[str, Any]]
        """

        localConf = {
            "physical": {
                path.get("net_addr"): {"trustedPathId": path.get("trusted_path_id")}
                for path in trustedPaths
            }
        }
        self.cmd(
            f"echo '{json.dumps(localConf, indent=2)}' > {ZeroTierNode._HOME_FOLDER}/local.conf"
        )

    def joinNetwork(self, network_id: str):
        """Make ZeroTier One join a network.

        :param network_id: ID of the network to join.
        :type network_id: str
        """

        self.cmd(f"zerotier-cli join {network_id}")

    def startZeroTier(self):
        """Start ZeroTier daemon."""

        self.cmd("zerotier-one -d")

        # It takes time for ZeroTier to start and populate home folder
        time.sleep(2)

        # Get rid of "sendto: Network is unreachable" when run zerotier commands
        # the first time
        self.cmd("zerotier-cli info")

    def stopZeroTier(self):
        """Stop ZeroTier daemon."""

        self.cmd(f"kill -KILL {self.getPID()}")

    def restartZeroTier(self):
        """Restart ZeroTier daemon."""

        self.stopZeroTier()
        self.startZeroTier()

    def getPID(self) -> str:
        """Get PID of ZeroTier daemon.

        :return: PID of ZeroTier daemon
        :rtype: str
        """

        return cast(str, self.cmd(f"cat {ZeroTierNode._HOME_FOLDER}/zerotier-one.pid"))

    def callServiceAPI(
        self,
        method: str,
        path: str,
        headers: Union[dict[str, str], None] = None,
        json: Union[dict[str, Any], None] = None,
        verbose: bool = False,
    ) -> Union[dict[str, Any], list[Any]]:
        """Call ZeroTier service API.

        See: https://docs.zerotier.com/service/v1/

        :param method: HTTP method
        :type method: str
        :param path: path of API
        :type path: str
        :param headers: HTTP headers, defaults to None
        :type headers: Union[dict[str, str], None], optional
        :param json: JSON payload, defaults to None
        :type json: Union[dict[str, Any], None], optional
        :param verbose: print request and response?, defaults to False
        :type verbose: bool, optional
        :return: JSON payload of response
        :rtype: Union[dict[str, Any], list[Any]]
        """

        if headers is None:
            headers = {}
        headers.update(self.auth_header)

        def callServiceAPI():
            response = requests.request(
                method=method,
                url=f"http://localhost:9993/{path}",
                headers=headers,
                json=json,
            )
            if verbose:
                print(
                    response.request.path_url,
                    response.request.headers,
                    response.request.body,
                )
                print(response.headers, response.content)
            return response.json()

        return self._runInNetNS(callServiceAPI)

    def _runInNetNS(self, func: Callable) -> Any:
        """Run the given function inside network namespace linked to the node.

        :param func: function to run
        :type func: Callable
        :return: result returned by the function
        :rtype: Any
        """

        netns_fd = os.open(f"/proc/{self.getPID()}/ns/net", os.O_RDONLY)

        ns(netns_fd)
        result = func()
        ns(root_fd)

        os.close(netns_fd)

        return result


class ZeroTierRoot(ZeroTierNode):
    def config(self, mac=None, ip=None, defaultRoute=None, lo="up", **_params):
        self.cmd(f"rm -rf {ZeroTierNode._HOME_FOLDER}/moons.d/*")

        super().config(mac, ip, defaultRoute, lo, **_params)
        self._genMoon()

        # Restart ZeroTier
        self.stopZeroTier()
        self.startZeroTier()

    def _genMoon(self):
        """Generate Moon.

        See: https://docs.zerotier.com/zerotier/moons/
        """

        json_path = f"{ZeroTierNode._HOME_FOLDER}/moon.json"
        moons_dir = f"{ZeroTierNode._HOME_FOLDER}/moons.d"

        self.cmd(
            f"zerotier-idtool initmoon {ZeroTierNode._HOME_FOLDER}/identity.public > {json_path}"
        )
        # The home folder of ZeroTier is a tmpfs mounted privately for node, so
        # the Python script cannot see it and directly open files inside it.
        moon_json = self.cmd(f"cat {json_path}")
        assert isinstance(moon_json, str)
        moon = json.loads(moon_json)

        stable_endpoints = [f"{i.ip}/9993" for i in self.intfList()]
        moon["roots"][0]["stableEndpoints"] = stable_endpoints
        self.cmd(f"echo '{json.dumps(moon, indent=2)}' > {json_path}")

        self.cmd(f'bash -c "cd {moons_dir} && zerotier-idtool genmoon {json_path}"')

    def terminate(self):
        self.stopZeroTier()
        super().terminate()


class ZeroTierController(ZeroTierNode):
    def getNetworks(self, verbose: bool = False) -> list[str]:
        """Get networks managed by this controller.

        :param verbose: print request and response?, defaults to False
        :type verbose: bool, optional
        :return: list of networks managed by this controller
        :rtype: list[str]
        """

        return cast(
            list[str],
            self.callServiceAPI(
                method="get", path="controller/network", verbose=verbose
            ),
        )

    def createNetwork(self, net_addr: str, verbose: bool = False) -> dict[str, Any]:
        """Create a public network to be managed by controller.

        See: https://docs.zerotier.com/self-hosting/network-controllers

        :param net_addr: network address (x.y.z.t), prefix length will always be
            24
        :type net_addr: str
        :param verbose: print request and response?, defaults to False
        :type verbose: bool, optional
        :return: JSON payload of the response from controller
        :rtype: dict[str, Any]
        """

        net_addr = ".".join(net_addr.split(".")[:3])
        return cast(
            dict[str, Any],
            self.callServiceAPI(
                method="post",
                path=f"controller/network/{self.node_id}______",
                json={
                    "ipAssignmentPools": [
                        {
                            "ipRangeStart": f"{net_addr}.1",
                            "ipRangeEnd": f"{net_addr}.254",
                        }
                    ],
                    "routes": [{"target": f"{net_addr}.0/24", "via": None}],
                    "v4AssignMode": "zt",
                    "private": False,
                },
                verbose=verbose,
            ),
        )
