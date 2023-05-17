import itertools
import json
import random
import string
import traceback

from ceph.ceph import CommandFailed
from ceph.parallel import parallel
from tests.cephfs.cephfs_utilsV1 import FsUtils
from utility.log import Log

log = Log(__name__)


def run(ceph_cluster, **kw):
    """
    Pre-requisite:
    1. get-or-create the client with permission
    Steps:
    1. caps the client permission
    2. check if the correct daemons have expected permission
    """
    try:
        tc = "CEPH-83574328"
        log.info(f"Running CephFS tests for -{tc}")
        fs_util = FsUtils(ceph_cluster)
        config = kw.get("config")
        clients = ceph_cluster.get_ceph_objects("client")
        build = config.get("build", config.get("rhbuild"))
        fs_util.prepare_clients(clients, build)
        fs_util.auth_list(clients)
        client1 = clients[0]
        fs_details = fs_util.get_fs_info(client1)
        if not fs_details:
            fs_util.create_fs(client1, "cephfs")
        rand_name = "".join(
            random.choice(string.ascii_lowercase + string.digits)
            for _ in list(range(5))
        )
        create_cmd = f"ceph auth get-or-create client.{rand_name} mon 'allow r' osd 'allow rw pool=mypool'"
        client1.exec_command(sudo=True, cmd=create_cmd)
        daemon_list = ["mon", "mds", "osd"]
        permission_list = [
            "'allow r'",
            "'allow rw'",
            "'allow rx'",
            "'allow w'",
            "'allow wx'",
            "'allow rwx'",
            "'allow *'",
        ]
        mounting_dir = "".join(
            random.choice(string.ascii_lowercase + string.digits)
            for _ in list(range(10))
        )
        kernel_mounting_dir_1 = f"/mnt/cephfs_kernel{mounting_dir}_1/"
        mon_node_ips = fs_util.get_mon_node_ips()
        fs_util.kernel_mount(
            [client1],
            kernel_mounting_dir_1,
            ",".join(mon_node_ips),
        )
        with parallel() as p:
            p.spawn(fs_util.run_ios, clients[0], kernel_mounting_dir_1)
        for daemon in daemon_list:
            for perm in permission_list:
                if daemon == "mds" and "x" in perm:
                    continue
                elif daemon == "mds" and "w" in perm:
                    continue
                else:
                    client1.exec_command(
                        sudo=True,
                        cmd=f"ceph auth caps client.{rand_name} {daemon} {perm}",
                    )
                    out1, _ = client1.exec_command(
                        sudo=True,
                        cmd=f"ceph auth get client.{rand_name} -f json-pretty",
                    )
                    output1 = json.loads(out1)[0]
                    if output1["caps"][daemon] != perm.strip("'"):
                        raise CommandFailed(
                            f"Not Expected permission for {daemon}, it should be {perm}"
                        )

        combs_daemon = list(itertools.combinations(daemon_list, 2))
        for daemon1, daemon2 in combs_daemon:
            combs_perm = list(itertools.combinations(permission_list, 2))
            for perm1, perm2 in combs_perm:
                if daemon1 == "mds" and "x" in perm1:
                    continue
                elif daemon2 == "mds" and "x" in perm2:
                    continue
                elif daemon1 == "mds" and "w" in perm1:
                    continue
                elif daemon2 == "mds" and "w" in perm2:
                    continue
                else:
                    client1.exec_command(
                        sudo=True,
                        cmd=f"ceph auth caps client.{rand_name} {daemon1} {perm1} {daemon2} {perm2}",
                    )
                    out2, _ = client1.exec_command(
                        sudo=True,
                        cmd=f"ceph auth get client.{rand_name} -f json-pretty",
                    )
                    output2 = json.loads(out2)[0]
                    if output2["caps"][daemon1] != perm1.strip("'"):
                        raise CommandFailed(
                            f"Not Expected permission for {daemon1}, it should be {perm1}"
                        )
                    if output2["caps"][daemon2] != perm2.strip("'"):
                        raise CommandFailed(
                            f"Not Expected permission for {daemon2}, it should be {perm2}"
                        )

        combs_daemon = list(itertools.combinations(daemon_list, 3))
        for daemon1, daemon2, daemon3 in combs_daemon:
            combs_perm = list(itertools.combinations(permission_list, 3))
            for perm1, perm2, perm3 in combs_perm:
                if daemon1 == "mds" and "x" in perm1:
                    continue
                elif daemon2 == "mds" and "x" in perm2:
                    continue
                elif daemon3 == "mds" and "x" in perm3:
                    continue
                elif daemon1 == "mds" and "w" in perm1:
                    continue
                elif daemon2 == "mds" and "w" in perm2:
                    continue
                elif daemon3 == "mds" and "w" in perm3:
                    continue
                else:
                    client1.exec_command(
                        sudo=True,
                        cmd=f"ceph auth caps client.{rand_name} {daemon1} {perm1} {daemon2} {perm2} {daemon3} {perm3}",
                    )
                    out3, _ = client1.exec_command(
                        sudo=True,
                        cmd=f"ceph auth get client.{rand_name} -f json-pretty",
                    )
                    output3 = json.loads(out3)[0]
                    print((daemon1, daemon2, daemon3), (perm1, perm2, perm3))
                    if output3["caps"][daemon1] != perm1.strip("'"):
                        raise CommandFailed(
                            f"Not Expected permission for {daemon1}, it should be {perm1}"
                        )
                    if output3["caps"][daemon2] != perm2.strip("'"):
                        raise CommandFailed(
                            f"Not Expected permission for {daemon2}, it should be {perm2}"
                        )
                    if output3["caps"][daemon3] != perm3.strip("'"):
                        raise CommandFailed(
                            f"Not Expected permission for {daemon3}, it should be {perm3}"
                        )
        return 0
    except Exception as e:
        log.error(e)
        log.error(traceback.format_exc())
        return 1
    finally:
        log.info("Cleaning up")
        fs_util.client_clean_up(
            "umount", fuse_clients=[clients[0]], mounting_dir=kernel_mounting_dir_1
        )
