import time

from base_topo import TopoWithPostAction, TopoWithRealisticLink, TopoWithRouter
from zerotier import ZeroTierController, ZeroTierNode, ZeroTierRoot

from mininet.net import Mininet
from mininet.node import OVSSwitch


class OSPFTopo(TopoWithRouter):
    """OSPF topology.

    Two directly connected routers plus a host for each router:

        `h1 --192.168.0.0/24-- r1 --192.168.1.0/24-- r2 --192.168.2.0/24-- h2`

    Two routers use OSPF to exchange routing data and build routing tables.
    """

    def build(self):
        """Create custom topo."""

        ospf_setup_commands = (
            "configure terminal",
            "router ospf",
            "network 192.168.0.0/16 area 1",
        )

        # Add hosts and routers
        r1 = self.buildRouterAndHost(
            router_name="r1",
            host_name="h1",
            net_addr="192.168.0.0",
            daemons=("ospfd",),
            commands=ospf_setup_commands,
        )

        r2 = self.buildRouterAndHost(
            router_name="r2",
            host_name="h2",
            net_addr="192.168.2.0",
            daemons=("ospfd",),
            commands=ospf_setup_commands,
        )

        # Add links
        self.addLink(
            r1,
            r2,  # , intfName1="r1-eth1", intfName2="r2-eth1"
            params1={"ip": "192.168.1.1/24"},
            params2={"ip": "192.168.1.2/24"},
        )


class MPLSTopo(TopoWithRouter):
    """MPLS topology.

    Three directly connected routers plus a host for each outer router:

        `h1 --- r1 --- r2 --- r3 --- h2`

    Three routers use OSPF to exchange routing data and build routing tables and
    use LDP to exchange labels. Packets are switched by MPLS.
    """

    def build(self):
        """Create custom topo."""

        daemons = ("ospfd", "ldpd")

        ospf_setup_commands = (
            "configure terminal",
            "router ospf",
            "network 192.168.0.0/16 area 1",
            "mpls ldp-sync",
        )

        # Add hosts and routers
        r1 = self.buildRouterAndHost(
            router_name="r1",
            host_name="h1",
            net_addr="192.168.0.0",
            daemons=daemons,
            commands=ospf_setup_commands,
        )

        r2 = self.addRouter(
            "r2", ip="192.168.2.1/24", daemons=daemons, commands=ospf_setup_commands
        )

        r3 = self.buildRouterAndHost(
            router_name="r3",
            host_name="h2",
            net_addr="192.168.3.0",
            daemons=daemons,
            commands=ospf_setup_commands,
        )

        # Add links
        # Link r2 and r3 first to use r2 default interface
        self.addLink(r2, r3, params2={"ip": "192.168.2.2/24"})
        self.addLink(
            r1, r2, params1={"ip": "192.168.1.1/24"}, params2={"ip": "192.168.1.2/24"}
        )


class BGPTopo(TopoWithRouter):
    """BGP topology.

    Four directly connected routers plus a host for each outer router:

        `h1 --- r1 --- r2 --- r3 --- r4 --- h2`

    r1 and r4 are in two different ASs. r2 and r3 together are in another AS
    which use OSPF as it's IGP. BGP is used for exchanging routing data between
    ASs. r1 and r4 will advertise their local networks to the AS that contains
    r2 and r3.
    """

    def build(self):
        """Create custom topo."""

        # AS 1
        r1 = self.buildAS(
            router_name="r1",
            host_name="h1",
            net_addr="192.168.0.0",
            as_number=1,
            peer="192.168.1.2",
            peer_as=2,
        )

        # AS 3
        r4 = self.buildAS(
            router_name="r4",
            host_name="h2",
            net_addr="192.168.4.0",
            as_number=3,
            peer="192.168.3.1",
            peer_as=2,
        )

        # AS 2
        ospf_bgp_setup_commands = (
            "configure terminal",
            "router ospf",
            "network 192.168.0.0/16 area 1",
            "end",
            "configure terminal",
            "router bgp 2",
            "no bgp ebgp-requires-policy",
        )

        # Add routers
        r2 = self.addRouter(
            "r2",
            ip="192.168.2.1/24",
            daemons=("ospfd", "bgpd"),
            commands=(
                *ospf_bgp_setup_commands,
                "neighbor 192.168.1.1 remote-as 1",
                "neighbor 192.168.2.2 remote-as 2",
            ),
        )

        r3 = self.addRouter(
            "r3",
            ip="192.168.3.1/24",
            daemons=("ospfd", "bgpd"),
            commands=(
                *ospf_bgp_setup_commands,
                "neighbor 192.168.3.2 remote-as 3",
                "neighbor 192.168.2.1 remote-as 2",
            ),
        )

        # Add Links

        # Keep this order of links creation for Mininet to set the correct IP
        # for interfaces
        self.addLink(r3, r4, params2={"ip": "192.168.3.2/24"})
        self.addLink(r2, r3, params2={"ip": "192.168.2.2/24"})
        self.addLink(
            r1, r2, params1={"ip": "192.168.1.1/24"}, params2={"ip": "192.168.1.2/24"}
        )

    def buildAS(
        self,
        router_name: str,
        host_name: str,
        net_addr: str,
        as_number: int,
        peer: str,
        peer_as: int,
    ) -> str:
        """Build a AS consist one router that connects with a host.

        This AS advertises its local network to the AS `peer_as`.

        :param router_name: name of router
        :type router_name: str
        :param host_name: name of host
        :type host_name: str
        :param net_addr: network address (x.y.z.t) of router and host, prefix
            length will always be 24.
        :type net_addr: str
        :param as_number: AS number
        :type as_number: int
        :param peer: peer's address (x.y.z.t)
        :type peer: str
        :param peer_as: AS number of peer
        :type peer_as: int
        :return: name of router
        :rtype: str
        """

        net_addr = ".".join(net_addr.split(".")[:3])

        bgp_setup_commands = (
            "configure terminal",
            f"router bgp {as_number}",
            "no bgp ebgp-requires-policy",
            f"neighbor {peer} remote-as {peer_as}",
            f"network {net_addr}.0/24",
        )

        return self.buildRouterAndHost(
            router_name=router_name,
            host_name=host_name,
            net_addr=net_addr,
            daemons=("bgpd",),
            commands=bgp_setup_commands,
        )


class MPLSVPNTopo(MPLSTopo):
    """MPLS-VPN Topology.

    Four directly connected routers plus a host for each outer router::

        h1---ce1---pe1---p---pe2---ce2---h2
                    |         |
                    +---------+

    ce1 and ce2 are edge routers of customer's sites. pe1 and pe2 are provider
    edges. pe1, pe2 are in the same AS. pe1 and pe2 have vrf instances
    associated with the site that connects with the router. Routes are
    distributed by OSPF between ce1, customer vrf of pe1, between pe1, p, pe2
    and between ce2 and customer vrf of pe2.

    IPv4 routes from customer vrf will be exported to default vrf as VPN-IPv4
    routes and then these routes will be distributed to other routers in AS by
    internal BGP. Received VPN-IPv4 routes will then be imported to receiver's
    customer VRF.
    """

    def build(self):
        """Create custom topo."""

        ce1, ce2 = self.buildCustomerSites(
            ce1_name="ce1",
            ce2_name="ce2",
            h1_name="h1",
            h2_name="h2",
            site1_net_addr="192.168.0.0",
            site2_net_addr="192.168.3.0",
            ospf_network_command="network 192.168.0.0/16 area 1",
        )

        ospf_setup_commands = (
            "configure terminal",
            "router ospf",
            "network 10.0.0.0/16 area 2",
            "network 1.1.1.1/32 area 2",
            "network 2.2.2.2/32 area 2",
            "mpls ldp-sync",
            "end",
        )

        vrf_setup_commands = (
            "configure terminal",
            "vrf customer",
            "end",
            "configure terminal",
            "router ospf vrf customer",
            "network 192.168.0.0/16 area 1",
            "redistribute bgp",
            "end",
            "configure terminal",
            "router bgp 1 vrf customer",
            "address-family ipv4",
            "rt vpn both 1:1",
            "rd vpn export 1:1",
            "label vpn export auto",
            "import vpn",
            "export vpn",
            "redistribute ospf",
            "end",
        )

        pe1 = self.addRouter(
            "pe1",
            ip="10.0.0.1/24",
            daemons=("ospfd", "bgpd", "ldpd"),
            vrfs={"customer": ["pe1-eth2"]},
            commands=(
                *ospf_setup_commands,
                *self.buildMPLSBGPSetupCommands("1.1.1.1", "2.2.2.2"),
                *vrf_setup_commands,
            ),
        )

        p = self.addRouter(
            "p",
            ip="10.0.1.1/24",
            daemons=("ospfd", "bgpd", "ldpd"),
            commands=ospf_setup_commands,
        )

        pe2 = self.addRouter(
            "pe2",
            ip="10.0.1.2/24",
            daemons=("ospfd", "bgpd", "ldpd"),
            vrfs={"customer": ["pe2-eth2"]},
            commands=(
                *ospf_setup_commands,
                *self.buildMPLSBGPSetupCommands("2.2.2.2", "1.1.1.1"),
                *vrf_setup_commands,
            ),
        )

        # Add links
        self.addLink(p, pe2)
        self.addLink(pe1, p, params2={"ip": "10.0.0.2/24"})
        self.addLink(
            pe1, pe2, params1={"ip": "10.0.2.1/24"}, params2={"ip": "10.0.2.2/24"}
        )

        self.addLink(
            pe1,
            ce1,
            intfName1="pe1-eth2",
            params1={"ip": "192.168.1.1/24"},
            params2={"ip": "192.168.1.2/24"},
        )
        self.addLink(
            pe2,
            ce2,
            intfName1="pe2-eth2",
            params1={"ip": "192.168.2.1/24"},
            params2={"ip": "192.168.2.2/24"},
        )

    def buildMPLSBGPSetupCommands(
        self, local_lo_ip: str, peer_lo_ip: str
    ) -> tuple[str, ...]:
        """Generate setup commands to set up MPLS and BGP for PEs.

        :param local_lo_ip: IP address that assigned to loopback interface
        :type local_lo_ip: str
        :param peer_lo_ip: IP address that is used to connect to neighbor
        :type peer_lo_ip: str
        :return: setup commands to set up MPLS and BGP
        :rtype: tuple[str, ...]
        """
        return (
            "configure terminal",
            "interface lo",
            f"ip address {local_lo_ip}/32",
            "end",
            "configure terminal",
            "mpls ldp",
            f"router-id {local_lo_ip}",
            "address-family ipv4",
            f"discovery transport-address {local_lo_ip}",
            "end",
            "configure terminal",
            "router bgp 1",
            f"bgp router-id {local_lo_ip}",
            "no bgp ebgp-requires-policy",
            f"neighbor {peer_lo_ip} remote-as 1",
            f"neighbor {peer_lo_ip} update-source lo",
            "address-family ipv4 vpn",
            f"neighbor {peer_lo_ip} activate",
            f"neighbor {peer_lo_ip} next-hop-self",
            f"neighbor {peer_lo_ip} send-community both",
            "end",
        )

    def buildCustomerSites(
        self,
        ce1_name: str,
        ce2_name: str,
        h1_name: str,
        h2_name: str,
        site1_net_addr: str,
        site2_net_addr: str,
        ospf_network_command: str,
    ) -> tuple[str, str]:
        """Build 2 sites of customer network.

        :param ce1_name: name of ce router in site 1
        :type ce1_name: str
        :param ce2_name: name of ce router in site 2
        :type ce2_name: str
        :param h1_name: name of host in site 1
        :type h1_name: str
        :param h2_name: name of host in site 2
        :type h2_name: str
        :param site1_net_addr: network address (x.y.z.t) of router and host,
            prefix length will always be 24. IP address of router and host are
            x.y.z.1 and x.y.z.2 respectively
        :type site1_net_addr: str
        :param site2_net_addr: network address (x.y.z.t) of router and host,
            prefix length will always be 24. IP address of router and host are
            x.y.z.1 and x.y.z.2 respectively
        :type site2_net_addr: str
        :param ospf_network_command: network command for configuring ospf in
            both 2 ce routers. The network address should cover 2 sites network.
        :type ospf_network_command: str
        :return: name of 2 ce routers
        :rtype: tuple[str, str]
        """
        ospf_setup_commands = (
            "configure terminal",
            "router ospf",
            ospf_network_command,
        )

        ce1 = self.buildRouterAndHost(
            router_name=ce1_name,
            host_name=h1_name,
            net_addr=site1_net_addr,
            daemons=("ospfd",),
            commands=ospf_setup_commands,
        )

        ce2 = self.buildRouterAndHost(
            router_name=ce2_name,
            host_name=h2_name,
            net_addr=site2_net_addr,
            daemons=("ospfd",),
            commands=ospf_setup_commands,
        )

        return ce1, ce2


class ZeroTierTopoSDN(TopoWithPostAction, TopoWithRealisticLink):
    def build(self):
        aroot, controller, h1, h2 = self._genZeroTierNodes()

        # Why OpenFlow14: https://groups.google.com/a/onosproject.org/g/onos-discuss/c/bFnACrQ6Zj8/m/ZjFicCCmAAAJ
        s1 = self.addSwitch("s1", cls=OVSSwitch, protocols="OpenFlow14")
        s2 = self.addSwitch("s2", cls=OVSSwitch, protocols="OpenFlow14")
        s3 = self.addSwitch("s3", cls=OVSSwitch, protocols="OpenFlow14")

        self.addLink(s1, s2)
        self.addLink(s2, s3)
        self.addLink(s3, s1)

        self.addLink(aroot, s3)
        self.addLink(controller, s3)

        self.addLink(h1, s1)
        self.addLink(h2, s2)

    def _genZeroTierNodes(self, **configures) -> tuple[str, str, str, str]:
        """Generate ZeroTier root, ZeroTier controller and 2 ZeroTier leaf nodes.

        :return: tuple of name of ZeroTier nodes
        :rtype: tuple[str, str, str, str]
        """

        # Mount moon directory to all nodes make them automatically orbit the
        # moon created by root.
        privateDirs = (("/var/lib/zerotier-one/moons.d", "./moons.d"),)

        # Mininet configures host follow alphabetical order and Root should
        # start and create moon first, hence the name "aroot".
        aroot = self.addNode(
            "aroot",
            cls=ZeroTierRoot,
            privateDirs=privateDirs,
            **configures.get("aroot", {}),
        )
        controller = self.addNode(
            "controller",
            cls=ZeroTierController,
            privateDirs=privateDirs,
            **configures.get("controller", {}),
        )
        h1 = self.addNode(
            "h1", cls=ZeroTierNode, privateDirs=privateDirs, **configures.get("h1", {})
        )
        h2 = self.addNode(
            "h2", cls=ZeroTierNode, privateDirs=privateDirs, **configures.get("h2", {})
        )

        return aroot, controller, h1, h2

    @classmethod
    def postAction(cls, net: Mininet):
        """Create ZeroTier network and join all nodes.

        :param net: a Mininet instance built from a :class:`ZeroTierTopo` topo
        :type net: Mininet
        """

        assert isinstance(net.topo, cls)
        controller, h1, h2 = net.getNodeByName("controller", "h1", "h2")

        assert (
            isinstance(controller, ZeroTierController)
            and isinstance(h1, ZeroTierNode)
            and isinstance(h2, ZeroTierNode)
        )

        count = 0
        while net.pingAll() > 0:
            if count > 0:
                print(f"*** Waiting for {5 * count} seconds")
            time.sleep(5 * count)
            count += 1

        # Restart nodes when connection between node and root is available to
        # orbit them to root.
        print("*** Restarting leaf ZeroTier node")
        for node in (h1, h2, controller):
            print(node.name, end=" ")
            node.restartZeroTier()
        print()

        print("*** Creating virtual network")
        print(controller.createNetwork("192.168.0.0"))
        print("*** Making nodes to join the network")
        h1.joinNetwork(controller.getNetworks()[0])
        h2.joinNetwork(controller.getNetworks()[0])


class ZeroTierTopoRouter(ZeroTierTopoSDN, TopoWithRouter):
    def build(self):
        aroot, controller, h1, h2 = self._genZeroTierNodes(
            aroot={"ip": "10.0.5.2/24", "defaultRoute": "via 10.0.5.1"},
            controller={"ip": "10.0.6.2/24", "defaultRoute": "via 10.0.6.1"},
            h1={"ip": "10.0.0.2/24", "defaultRoute": "via 10.0.0.1"},
            h2={"ip": "10.0.4.2/24", "defaultRoute": "via 10.0.4.1"},
        )

        ospf_setup_commands = (
            "configure terminal",
            "router ospf",
            "network 10.0.0.0/16 area 1",
        )

        r1 = self.addRouter(
            "r1", ip="10.0.0.1/24", daemons=("ospfd",), commands=ospf_setup_commands
        )
        r2 = self.addRouter(
            "r2", ip="10.0.4.1/24", daemons=("ospfd",), commands=ospf_setup_commands
        )
        r3 = self.addRouter(
            "r3", ip="10.0.2.1/24", daemons=("ospfd",), commands=ospf_setup_commands
        )

        self.addLink(r1, h1)
        self.addLink(r2, h2)
        self.addLink(r3, r2, params2={"ip": "10.0.2.2/24"})
        self.addLink(
            r1, r3, params1={"ip": "10.0.1.1/24"}, params2={"ip": "10.0.1.2/24"}
        )
        self.addLink(
            r1, r2, params1={"ip": "10.0.3.1/24"}, params2={"ip": "10.0.3.2/24"}
        )
        self.addLink(r3, aroot, params1={"ip": "10.0.5.1/24"})
        self.addLink(r3, controller, params1={"ip": "10.0.6.1/24"})


# Topology enables one to pass in `--topo=ospf` from the command line.
# Run `py net.topo.postAction(net)` if needed.
topos = {
    "ospf": {"constructor": (lambda: OSPFTopo()), "require_controller": False},
    "mpls": {"constructor": (lambda: MPLSTopo()), "require_controller": False},
    "bgp": {"constructor": (lambda: BGPTopo()), "require_controller": False},
    "mpls-vpn": {"constructor": (lambda: MPLSVPNTopo()), "require_controller": False},
    "zerotier-sdn": {
        "constructor": (lambda: ZeroTierTopoSDN()),
        "require_controller": True,
    },
    "zerotier-router": {
        "constructor": (lambda: ZeroTierTopoRouter()),
        "require_controller": False,
    },
}
