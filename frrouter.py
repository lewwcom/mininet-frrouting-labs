from random import randint
from subprocess import call
from typing import cast

from mininet.node import Node


class FRRouter(Node):
    """A Node with IP forwarding enabled and running FRRouting daemons.

    :param name: name of node
    :type name: str
    :param inNamespace: in network namespace?, defaults to True
    :type inNamespace: bool, optional
    :param name: name of node
    :type name: str
    :param daemons: daemons to be enabled, default to None
    :type daemons: tuple[str,...], optional
    :param commands: commands to be executed in vtysh, default to None
    :type commands: tuple[str,...], optional
    :param vrfs: vrf and list of enslaved interfaces, default to None
    :type vrfs: dict[str, list[str]], optional
    """

    _BASE_PATHSPACE = "/etc/frr"

    def __init__(self, name: str, inNamespace=True, **params):
        super().__init__(name, inNamespace, **params)
        self.daemons = cast(tuple[str, ...], params.get("daemons", ()))
        self.netns = f"{name}-{randint(0, 1000):03}"
        self.vrfs = cast(dict[str, list[str]], params.get("vrfs", {}))

    def config(self, **params):
        # This method will be called while Mininet is being initiated.

        # The super.config() call setIP(), setMAC() and setDefaultRoute() if
        # `params` has these value. super.config() also brings loopback intf up.
        super().config(**params)

        # Enable forwarding on the router
        self.cmd("sysctl net.ipv4.ip_forward=1")

        # Ethernet frames only carry 1500 bytes at most (Maximum Transmission
        # Unit). Therefore, TCP payload can be 1460 bytes (Maximum Segment
        # Size). It, combines with TCP headers and IP headers, adds up to 1500
        # bytes. Labels, 4 bytes each, also are parts of Ethernet frames
        # payload. So, we need MTU to be larger or TCP MSS to be smaller in
        # order to transmit labeled packages.
        for intf in self.intfNames():
            self.cmd(f"ip link set dev {intf} mtu 1600")

        # Create VRFs and enslave interfaces
        for table_id, vrf in enumerate(self.vrfs, 1):
            self.cmd(f"ip link add {vrf} type vrf table {table_id}")
            self.cmd(f"ip link set dev {vrf} up")
            for intf in self.vrfs[vrf]:
                self.cmd(f"ip link set dev {intf} master {vrf}")

        # Enable MPLS Label processing on all interfaces
        if self.daemons.count("ldpd"):
            self.cmd("sysctl net.mpls.platform_labels=100000")
            self.cmd("sysctl net.mpls.conf.lo.input=1")
            for intf in self.intfNames():
                self.cmd(f"sysctl net.mpls.conf.{intf}.input=1")

        # Start and config FRRouting
        self._startFRRouting()
        vtysh_commands = params.get("commands")
        if vtysh_commands is not None:
            self.vtysh(*vtysh_commands)

    def terminate(self):
        self._stopFRRouting()

        self.cmd("sysctl net.ipv4.ip_forward=0")

        # TODO: Remove VRFs?

        if self.daemons.count("ldpd"):
            self.cmd("sysctl net.mpls.platform_labels=0")
            self.cmd("sysctl net.mpls.conf.lo.input=0")
            for intf in self.intfList():
                self.cmd(f"sysctl net.mpls.conf.{intf}.input=0")

        super().terminate()

    def vtysh(self, *commands: str):
        """Call this method in Mininet CLI to enter vtysh or execute commands in
        vtysh.

        Usage in Mininet cli: `py frrouter_instance.vtysh()`

        Example for calling this method with params::

            r1.vtysh(
                "configure terminal",
                "router ospf",
                "network 192.168.0.0/16 area 1"
            )

        :param commands: commands to be executed, default to None
        :type commands: tuple[str,...], optional
        """

        vtysh_command = f"vtysh --pathspace {self.netns}"
        options = ""
        if commands:
            commands += ("end", "write integrated")
            options = " -c " + " -c ".join([f"'{command}'" for command in commands])
        call(vtysh_command + options, shell=True)

    def _startFRRouting(self):
        """Start FRRouting daemons.

        See: https://dlqs.dev/frr-local-netns-setup.html
        """

        self._setupFRRoutingPathspace()
        self._configFRRouting()
        self.cmdPrint(f"/usr/lib/frr/frrinit.sh start {self.netns}")

    def _setupFRRoutingPathspace(self):
        """Create pathspace and copy config files.

        :param netns: network namespace name
        :type netns: str
        """

        self.cmd(f"mkdir {FRRouter._BASE_PATHSPACE}/{self.netns}")
        self.cmd(
            f"find {FRRouter._BASE_PATHSPACE} -maxdepth 1 -type f"
            f"    -execdir cp {{}} {FRRouter._BASE_PATHSPACE}/{self.netns} ';'"
        )

    def _configFRRouting(self):
        """Enable watchfrr_options, daemons and config hostname for vtysh."""

        # Create link of network namespace in /var/run/netns so it can be seen
        # by `ip` utility and FRRouting
        self.cmd("mkdir --parents /var/run/netns/")
        self.cmd(
            f"ln --symbolic --no-target-directory"
            f"    /proc/$$/ns/net /var/run/netns/{self.netns}"
        )

        self.cmd(
            f"echo 'watchfrr_options=\"--netns={self.netns}\"'"
            f"    >> {FRRouter._BASE_PATHSPACE}/{self.netns}/daemons"
        )

        for daemon in self.daemons:
            self.cmd(
                f"sed --in-place 's/{daemon}=no/{daemon}=yes/'"
                f"    {FRRouter._BASE_PATHSPACE}/{self.netns}/daemons"
            )

        self.cmd(
            f"echo 'hostname {self.name}'"
            f"    >> {FRRouter._BASE_PATHSPACE}/{self.netns}/vtysh.conf"
        )

    def _stopFRRouting(self):
        """Stop FRRouting daemons and cleanup."""

        self.cmd(
            f"ps aux | grep {self.netns} | awk '!/grep/ {{print $2}}' - |"
            f"    xargs --max-args 1 --no-run-if-empty kill -KILL"
        )
        self.cmd(
            f"rm --recursive"
            f"    /var/run/netns/{self.netns}"
            f"    {FRRouter._BASE_PATHSPACE}/{self.netns}/"
        )
