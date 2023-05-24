from itertools import chain

from frrouter import FRRouter

from mininet.net import Mininet
from mininet.node import Node
from mininet.topo import Topo


class TopoWithPostAction(Topo):
    """Topo class that has post action that need to trigger after :method::`Mininet.start()`."""

    @classmethod
    def postAction(cls, net: Mininet):
        """Configure topo after :method::`Mininet.start()`.

        :param net: a Mininet instance built from a :class:`TopoWithPostAction`
            topo
        :type net: Mininet
        """
        pass


class TopoWithRealisticLink(Topo):
    """Topo class that enforces bandwidth limit on link."""

    def addLink(self, node1, node2, port1=None, port2=None, key=None, **opts):
        opts.pop("bw", 0)

        # Maximum bandwidth supported is 1 Gbps. AT&T Business offers max 4.7
        # Gbps depend on location. Viettel Solutions offer 300 Mbps.
        #
        # See:
        # - https://www.business.att.com/products/business-fiber-internet.html
        # - https://solutions.viettel.vn/en/telecommunication/ftth-optical-fiber-internet.html
        return super().addLink(node1, node2, port1, port2, key, bw=1000, **opts)


class TopoWithRouter(TopoWithPostAction, TopoWithRealisticLink):
    """Topo class with helper methods to work with :class:`FRRouter`."""

    def addRouter(self, name: str, **options) -> str:
        """Add router to graph.

        :param name: router name
        :type name: str
        :return: router name
        :rtype: str
        """

        return self.addNode(name, cls=FRRouter, **options)

    def routers(self) -> list[str]:
        """Return list of router names.

        :return: list of router names
        :rtype: list[str]
        """

        nodes = self.nodes()
        assert isinstance(nodes, list)
        return [node for node in nodes if self.isRouter(node)]

    def isRouter(self, node_name: str) -> bool:
        """Check if node is a :class::`FRRouter`.

        :param node_name: name of node
        :type node_name: str
        :return: `True` if node is a :class::`FRRouter`, `False` otherwise
        :rtype: bool
        """

        return self.nodeInfo(node_name).get("cls", Node) == FRRouter

    def buildRouterAndHost(
        self,
        router_name: str,
        host_name: str,
        net_addr: str,
        daemons: tuple[str, ...],
        commands: tuple[str, ...],
    ) -> str:
        """Build a network consist one router that connects with a host.

        :param router_name: name of router
        :type router_name: str
        :param host_name: name of host
        :type host_name: str
        :param net_addr: network address (x.y.z.t) of router and host, prefix
            length will always be 24. IP address of router and host are x.y.z.1
            and x.y.z.2 respectively
        :type net_addr: str
        :param daemons: daemons to be enabled on router, default to None
        :type daemons: tuple[str,...], optional
        :param commands: commands to be executed in vtysh, default to None
        :type commands: tuple[str], optional
        :return: name of router
        :rtype: str
        """

        net_addr = ".".join(net_addr.split(".")[:3])

        r = self.addRouter(
            router_name, ip=f"{net_addr}.1/24", daemons=daemons, commands=commands
        )
        h = self.addHost(
            host_name, ip=f"{net_addr}.2/24", defaultRoute=f"via {net_addr}.1"
        )

        self.addLink(r, h)

        return r

    # See https://stackoverflow.com/a/33533514 for how to use classname
    # (TopoWithRouter) here.
    #
    # This method is supposed to be used after the Mininet instance is built,
    # when names of every interfaces are known.
    #
    # To build MPLS configuration commands in `build()` method, consider
    # explicit declare `intfName` in `addLink()` and use these values. Mininet
    # will create links (pairs of veth) first before configuring hosts.
    #
    # The default naming scheme of interfaces is "hostname-eth<port_number>".
    # Port number starts at 0.
    @classmethod
    def postAction(cls, net: Mininet):
        """Configure MPLS for all :class:`FRRouter` that enable ldpd daemon.

        :param net: a Mininet instance built from a :class:`TopoWithRouter` topo
        :type net: Mininet
        """

        assert isinstance(net.topo, cls)
        mpls_routers = filter(
            lambda r: isinstance(r, FRRouter) and r.daemons.count("ldpd"),
            net.getNodeByName(*net.topo.routers()),
        )

        print("*** Configuring MPLS for applicable routers")
        for router in mpls_routers:
            print(router.name, end=" ")
            router.vtysh(
                "configure terminal",
                "mpls ldp",
                "address-family ipv4",
                f"discovery transport-address {router.defaultIntf().IP()}",
                *chain.from_iterable(
                    [[f"interface {name}", "exit"] for name in router.intfNames()]
                ),
            )
        print()
