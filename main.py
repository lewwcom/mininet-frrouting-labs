from typing import Any, Callable, Union, cast

from cli_parser import parser
from topo import TopoWithPostAction, topos

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSController, RemoteController
from mininet.nodelib import LinuxBridge


def main(
    topo_name: str,
    controller_ip: Union[str, None] = None,
    controller_port: Union[str, None] = None,
):
    """Create a network from topo.

    :param topo_name: topo name
    :type topo_name: str
    :param controller_ip: SDN controller IP, defaults to None
    :type controller_ip: Union[str, None], optional
    :param controller_port: Listening port of SDN controller, defaults to None
    :type controller_port: Union[str, None], optional
    """

    topo = cast(dict[str, Any], topos.get(topo_name))

    controller = (
        (lambda name: RemoteController(name, controller_ip, controller_port))
        if controller_ip is not None
        else OVSController
        if topo.get("require_controller", False)
        else None
    )

    topo_constructor = cast(Callable, topo.get("constructor"))
    net = Mininet(topo=topo_constructor(), switch=LinuxBridge, controller=controller, link=TCLink)  # type: ignore
    net.start()

    if isinstance(net.topo, TopoWithPostAction):
        net.topo.postAction(net)

    CLI(net)
    net.stop()


if __name__ == "__main__":
    args = parser.parse_args()
    setLogLevel("debug" if args.verbose else "info")
    main(args.topo_name, args.controller_ip, args.controller_port)
