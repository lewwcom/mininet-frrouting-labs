from argparse import ArgumentParser, MetavarTypeHelpFormatter

from topo import topos

description = "create a network from topo name."
parser = ArgumentParser(
    description=description, formatter_class=MetavarTypeHelpFormatter
)

parser.add_argument(
    "topo_name",
    type=str,
    choices=topos.keys(),
    help=f"topology to create: {[*topos.keys()]}",
    metavar="topo_name",
)
parser.add_argument(
    "-v", "--verbose", action="store_true", help="emit Mininet debug output"
)
parser.add_argument("--controller-ip", type=str, help="IP of remote controller")
parser.add_argument(
    "--controller-port",
    type=int,
    help="listening port of remote controller",
)
