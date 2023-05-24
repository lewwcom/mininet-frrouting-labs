import ctypes
import os

CLONE_NEWNET = 0x40000000
libc = ctypes.CDLL("libc.so.6", use_errno=True)
root_fd = os.open("/proc/self/ns/net", os.O_RDONLY)


def ns(fd: int):
    """Make the current process jump to other network namespace.

    From: https://medium.com/opsops/how-to-traverse-network-namespaces-8290abe45707

    :param fd: file descriptor of the network namespace
    :type fd: int
    """

    libc.setns(fd, CLONE_NEWNET)
