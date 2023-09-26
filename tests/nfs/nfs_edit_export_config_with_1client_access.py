from time import sleep

from nfs_operations import cleanup_cluster, setup_nfs_cluster

from cli.ceph.ceph import Ceph
from cli.exceptions import ConfigError, OperationFailedError
from cli.utilities.filesys import Mount
from utility.log import Log

log = Log(__name__)


def update_export_conf(
    client, nfs_name, nfs_export_client, original_clients_value, new_clients_values
):
    try:
        out = Ceph(client).nfs.export.get(nfs_name, nfs_export_client)
        client.exec_command(sudo=True, cmd=f"echo '{out}' > export.conf")
        client.exec_command(
            sudo=True,
            cmd=f"sed -i 's/{original_clients_value}/{new_clients_values}/' export.conf",
        )
        Ceph(client).nfs.export.apply(nfs_name, "export.conf")
    except Exception:
        raise OperationFailedError("failed to edit clients in export conf file")


def run(ceph_cluster, **kw):
    """Verify readdir ops
    Args:
        **kw: Key/value pairs of configuration information to be used in the test.
    """
    config = kw.get("config")
    nfs_nodes = ceph_cluster.get_nodes("nfs")
    clients = ceph_cluster.get_nodes("client")
    port = config.get("port", "2049")
    version = config.get("nfs_version", "4.0")
    no_clients = int(config.get("clients", "2"))
    # If the setup doesn't have required number of clients, exit.
    if no_clients > len(clients):
        raise ConfigError("The test requires more clients than available")

    clients = clients[:no_clients]  # Select only the required number of clients
    nfs_node = nfs_nodes[0]
    fs_name = "cephfs"
    nfs_name = "cephfs-nfs"
    nfs_export = "/export"
    nfs_mount = "/mnt/nfs"
    nfs_server_name = nfs_node.hostname

    # Export Conf Parameter
    nfs_export_client = "/export_client_access"
    nfs_client_mount = "/mnt/nfs_client_mount"
    original_clients_value = "client_address"
    new_clients_values = f"{clients[0].hostname}"

    try:
        # Setup nfs cluster
        setup_nfs_cluster(
            clients,
            nfs_server_name,
            port,
            version,
            nfs_name,
            nfs_mount,
            fs_name,
            nfs_export,
            fs_name,
        )

        # Create export
        Ceph(clients).nfs.export.create(
            fs_name=fs_name,
            nfs_name=nfs_name,
            nfs_export=nfs_export_client,
            fs=fs_name,
            client_addr="client_address",
        )

        # Edit the export config to mount with client 1 access value
        update_export_conf(
            clients[0],
            nfs_name,
            nfs_export_client,
            original_clients_value,
            new_clients_values,
        )

        # Mount the export on client1 which is unauthorized.Mount should fail
        clients[1].create_dirs(dir_path=nfs_client_mount, sudo=True)
        cmd = (
            f"mount -t nfs -o vers={version},port={port} "
            f"{nfs_server_name}:{nfs_export_client} {nfs_client_mount}"
        )
        _, rc = clients[1].exec_command(cmd=cmd, sudo=True, check_ec=False)
        if "No such file or directory" in str(rc):
            log.info("As expected, Mount on unauthorized client failed")
            pass
        else:
            log.error(f"Mount passed on unauthorized client: {clients[0].hostname}")

        # Mount the export on client0 which is authorized.Mount should pass
        clients[0].create_dirs(dir_path=nfs_client_mount, sudo=True)
        if Mount(clients[0]).nfs(
            mount=nfs_client_mount,
            version=version,
            port=port,
            server=nfs_server_name,
            export=nfs_export_client,
        ):
            raise OperationFailedError(f"Failed to mount nfs on {clients[0].hostname}")
        log.info("Mount succeeded on client0")

    except Exception as e:
        log.error(f"Error : {e}")
        return 1
    finally:
        log.info("Cleaning up")
        sleep(30)
        cleanup_cluster(clients, nfs_mount, nfs_name, nfs_export)
        cleanup_cluster(clients, nfs_client_mount, nfs_name, nfs_export_client)
        log.info("Cleaning up successfull")
    return 0
