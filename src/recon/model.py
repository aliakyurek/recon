import paramiko
from paramiko.ssh_exception import *
import logging
import sys
import socket
from ipaddress import IPv4Network
import re
import subprocess
import tempfile
import os
import pickle
from . import util

logger = logging.getLogger("recon.model")
# paramiko log level can be set to DEBUG for more detailed logging, otherwise it'll follow the root logger level
# logging.getLogger("paramiko").setLevel(logging.DEBUG)

strList = list[str]


class ReConError(Exception):
    """Base exception for ReCon errors."""

class ReConSSHError(ReConError):
    """SSH connection or transport error."""

class ReConAuthenticationError(ReConSSHError):
    """Authentication failed (bad username/password)."""

class ReConNetworkError(ReConSSHError):
    """Network/socket error (host unreachable, DNS, etc.)."""

class ReConCommandError(ReConError):
    """Remote command execution error."""
    def __init__(self, command, exit_code, output, error):
        super().__init__(f"Command '{command}' failed with exit code {exit_code}")
        self.command = command
        self.exit_code = exit_code
        self.output = output
        self.error = error


class ReCon:
    """
    The ReCon class represents a tool for remote reconnaissance and management of hosts.
    Attributes:
        HOST_DATA_PATH (str): The file path to store the host data.
    Methods:
        __init__(): Initializes a new instance of the ReCon class.
        restore_host_data(): Restores the host data from the file.
        save_host_data(): Saves the host data to the file.
        bind(event, handler): Binds an event to a handler function.
        call_handler(handler, **kwargs): Calls the specified handler function with the given arguments.
        start(): Starts the ReCon tool.
        connect(host, username, password): Connects to a host using SSH.
        activity(msg): Logs an activity message.
        fill_prompt(): Fills the prompt with initial data from the SSH channel.
        execute_command(command): Executes a command on the connected host.
        clear_consoles(): Clears the list of consoles.
        enumerate_consoles(): Enumerates the available consoles on the host.
        clear_local_networks(): Clears the list of local networks.
        enumerate_local_networks(): Enumerates the available local networks on the host.
        clear_nodes(): Clears the list of nodes.
        enumerate_nodes(): Enumerates the available nodes on the host.
        toggle_https_tunnel(): Toggles the HTTPS tunnel for the nodes.
        deploy_key(): Deploys the RSA key to the host.
        spawn_console(console): Spawns a console for the specified console name.
        spawn_shell(): Spawns a shell console.
        stop(): Stops the ReCon tool and closes connections.
        setup(host, username, password): Sets up the ReCon tool for the specified host.
    """
    
    HOST_DATA_PATH = util.get_dyn_path("user/hosts.dat")

    class HostInfo:
        """
        Represents information about a host.
        This class instances will be added to host_pool and saved to the disk.
        Attributes:
            address (str): The address of the host.
            username (str): The username associated with the host.
            active (bool): Indicates if the host is active.
            consoles (list): A list of consoles associated with the host.
            networks (list): A list of networks associated with the host.
            nodes (list): A list of nodes associated with the host.
        """
        def __init__(self, address: str, username: str):
            self.address: str = address
            self.username: str = username
            self.active: bool = True
            self.consoles: strList = []
            self.networks: strList = []
            self.nodes: strList = []

    def __init__(self):
        # For some of SSH connections we'll use paramiko and for some we'll use subprocess and ssh util.
        self._ssh_client = paramiko.SSHClient()
        self._sftp_client = None
        self._ssh_tunnel_proc = None

        # After connecting to a host using credentials, we'll generate a key and deploy it to the host for the further operations. 
        self._key_file: str = None

        # event handlers are stored in a dictionary with event names as keys and handler functions as values
        self._event_handlers: dict[str, callable] = {}

        # we'll save each host info to the disk and restore it when the tool is started again.
        # this way, recent host connections will be loaded automatically.
        # A host is added to the host_pool when it is connected successfully.
        self.host_pool: dict[str,self.HostInfo] = {}

        # as there may be muliple hosts in the pool, we'll keep track of the current host.
        self.current_host = None

        # try to restore host data from the disk if exists
        self._restore_host_data()

        # prompt is to ensure that we're connected to the right host
        self._prompt = ""

    def _restore_host_data(self):
        """Restore the host data from the pickled file."""
        if not os.path.isfile(self.HOST_DATA_PATH):
            return
        with open(self.HOST_DATA_PATH, 'rb') as file:
            # Deserialize and retrieve the variable from the file
            self.host_pool = pickle.load(file)

    def _save_host_data(self):
        """Save the host data to the pickle file."""
        os.makedirs(os.path.dirname(self.HOST_DATA_PATH), exist_ok=True)
        # Open the file in binary mode
        with open(self.HOST_DATA_PATH, 'wb') as file:
            # Serialize and write the variable to the file
            pickle.dump(self.host_pool, file)

    def _call_handler(self, handler, **kwargs):
        """Call the specified handler function with the given arguments."""
        if handler in self._event_handlers:
            self._event_handlers[handler](**kwargs)

    def _activity(self, msg):
        """Log an activity message and call the activity handler."""
        logger.info(msg)
        self._call_handler("activity", msg=msg)

    def _fill_prompt(self):
        # open a session on the SSH channel
        channel = self._ssh_client.get_transport().open_session()
        channel.settimeout(2)
        prompt = ""

        # read the initial data if available. This will be prompt
        try:
            prompt = channel.recv(1024).decode('utf-8')
        except socket.timeout:
            pass
        channel.close()
        self._prompt = prompt          

    def _deploy_key(self):
        """
        Generate and deploy a RSA key to the host. The public part of the key will be
        saved to the remote host authorized_keys file.
        """

        # generate a RSA key
        self.rsa_key = rsa_key = paramiko.RSAKey.generate(bits=2048)
        key_name= rsa_key.get_name()

        # get the base64 encoded public key
        key = rsa_key.get_base64()

        # create a temporary file and dump the private key to it
        key_fd, self._key_file = tempfile.mkstemp()
        os.close(key_fd)
        rsa_key.write_private_key_file(self._key_file)

        # make sure directory exists
        ssh_dir = os.path.join(os.path.expanduser(f"C:\\Users\\{self.current_host.username}"), ".ssh")
        if not os.path.exists(ssh_dir):
            try:
                os.makedirs(ssh_dir)
            except OSError as e:
                logger.error(f"Failed to create .ssh directory: {e}")
                self._call_handler("fatal_error", msg="Failed to create .ssh directory. Most features will not work.", error=e)
                return

        # deploy the public key to the remote host
        command = f'echo {key_name} {key} > C:\\Users\\{self.current_host.username}\\.ssh\\authorized_keys'
        try:
            out, err, code = self.execute_command(command)
        except (ReConSSHError, ReConCommandError) as e:
            logger.error(f"Failed to deploy public key: {e}")
            self._call_handler("fatal_error", msg="Failed to deploy SSH key. Most features will not work.", error=e)

    def bind(self, event, handler):
        """Bind an event to a handler function."""
        self._event_handlers[event] = handler

    def start(self):
        # this doesn't do anything yet, but it's a good practice to have a start method
        self._call_handler("initialized")

    def _connect(self, host, username, password):
        """Connect to a host using SSH. Raises exceptions on failure."""

        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._activity(f"Connecting to {host}...")
            self._ssh_client.connect(host, 22, username, password,
                                   timeout=3, look_for_keys=False)

            # Create a new HostInfo object and add it to the host pool or update the existing one
            self.host_pool.setdefault(host, self.HostInfo(address=host, username=username))
            self.current_host = self.host_pool[host]
            self._save_host_data()

            self._activity(f"Checking prompt...")
            self._fill_prompt()

            self._activity(f"Deploying key...")
            self._deploy_key()

        except AuthenticationException as e:
            logger.error(f"SSH authentication failed: {e}")
            raise ReConAuthenticationError(str(e)) from e
        
        except (TimeoutError, socket.error) as e:
            logger.error(f"SSH network/socket error: {e}")
            raise ReConNetworkError(str(e)) from e
        
        except SSHException as e:
            logger.error(f"SSH connection error: {e}")
            raise ReConSSHError(str(e)) from e


    def execute_command(self, command):
        try:
            logger.info(f"Sending command via SSH: {command}")
            stdin, stdout, stderr = self._ssh_client.exec_command(command)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            logger.info(f"Command completed with exit code {exit_code}")
        except (paramiko.SSHException, socket.error) as e:
            logger.error(f"SSH error: {e}")
            raise ReConSSHError(str(e)) from e
        if exit_code != 0:
            logger.warning(f"Command '{command}' failed: {error}")
            raise ReConCommandError(command, exit_code, output, error)
        return output, error, exit_code

    def clear_consoles(self):
        """Clear console list"""
        if self.current_host is not None and hasattr(self.current_host, 'consoles'):
            self.current_host.consoles.clear()

    def enumerate_consoles(self):
        """Enumerate the available serial consoles on the host."""
        if not self.current_host.consoles:
            self._activity("Enumerating consoles...")
            try:
                output, _, _ = self.execute_command("wmic path Win32_SerialPort get Caption")
                lines = [com.strip() for com in output.splitlines()[1:] if com.strip()]
                self.current_host.consoles.extend(lines)
                if lines:
                    self._activity(f"Found {len(lines)} serial console(s)")
                else:
                    self._activity("No serial consoles found")
                self._save_host_data()
            except (ReConSSHError, ReConCommandError) as e:
                self._activity(f"Console enumeration failed: {e}")
        self._call_handler("consoles_loaded", consoles=self.current_host.consoles)

    def clear_local_networks(self):
        """Clear local network list"""
        if self.current_host is not None and hasattr(self.current_host, 'networks'):
            self.current_host.networks.clear()

    def enumerate_local_networks(self):
        """Enumerate the available local networks on the host."""
        if not self.current_host.networks:
            self._activity(f"Enumerating local networks...")
            try:
                output, _, _ = self.execute_command("ipconfig")
                pattern = r"IPv4 Address\D+(\d+\.\d+\.\d+\.\d+)\r\s+Subnet Mask\D+(\d+\.\d+\.\d+\.\d+)"
                matches = re.findall(pattern, output)

                for ip,subnet_mask in matches:
                    # Filter out loopback addresses and return the IP addresses of up interfaces
                    ipn = IPv4Network(f"{ip}/{subnet_mask}", False)
                    if ipn.is_private and not(ipn.is_loopback):
                        self.current_host.networks.append(ipn)
                self._save_host_data()
            except (ReConSSHError, ReConCommandError) as e:
                self._activity(f"Local network enumeration failed: {e}")
        self._call_handler("local_networks_loaded", networks=[str(network) for network in self.current_host.networks])

    def clear_nodes(self):
        """Clear node list"""
        if self.current_host is not None and hasattr(self.current_host, 'nodes'):
            self.current_host.nodes.clear()

    def enumerate_nodes(self):
        """Enumerate the available IP reachable nodes on the host."""
        if not self.current_host.nodes:
            if not self.current_host.networks:
                self._activity("No networks available to enumerate nodes.")
                self._call_handler("nodes_loaded")
                return
            for host in self.current_host.networks[0].hosts():
                host = str(host)
                self._activity(f"Querying... {host}")
                try:
                    output, err, exit_code = self.execute_command(f"ping -n 1 -w 25 {host}")
                    self._call_handler("node_found", node=host)
                    self.current_host.nodes.append(host)
                except ReConCommandError as e:
                    # command fail is expected we are scanning for reachable hosts
                    pass
                except ReConSSHError as e:
                    self._activity(f"Node enumeration failed: {e}")
            self._save_host_data()
        else:
            for host in self.current_host.nodes:
                self._call_handler("node_found", node=host)
        self._call_handler("nodes_loaded")

    def toggle_https_tunnel(self):
        """Toggle the HTTPS tunnel for the nodes."""
        if self._ssh_tunnel_proc is None:
            port_mapping = {}
            self._activity(f"Establishing tunnel...")
            # use deployed key to establish a tunnel. -N flag is used to not execute a remote command
            args = ["ssh","-N","-i",self._key_file,f"{self.current_host.username}@{self.current_host.address}"]

            # for each node, find a local port and map it to the node's 443 port.
            # add -L localport:node:443 to the args list
            for node in self.current_host.nodes:
                args.append("-L")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                    server_socket.bind(("127.0.0.1", 0))
                    _, local_port = server_socket.getsockname()
                args.append(f"{local_port}:{node}:443")
                port_mapping[node] = local_port

            # execute ssh subprocess for tunneling                
            self._ssh_tunnel_proc = subprocess.Popen(args)
            self._call_handler("tunnel_established", port_mapping=port_mapping)
        else:
            self._activity(f"Closing tunnel...")
            self._ssh_tunnel_proc.terminate()
            self._ssh_tunnel_proc = None
            self._call_handler("tunnel_closed")

    def spawn_console(self, console):
        """Spawn a console for the specified console name like 'USB to UART Bridge (COM6)'"""

        # grab the COMx part from the console name
        match = re.search(r"(COM\d+)", console)
        if not match:
            self._activity("No COM port found in console name.")
            return
        title = f"[ReCon]sole serial {match.group()} on {self.current_host.address}"
        
        # this is the plink command that connects to the serial port
        powershell_post_cmd = f"plink -serial {match.group()} -sercfg 115200 8,n,1,X"
        fcolor = "darkcyan"

        args = [
            # local
            "ssh",
            "-o StrictHostKeyChecking=no", "-t", "-i" , self._key_file, f"{self.current_host.username}@{self.current_host.address}",
            # remote
            # by using powershell as remote command we can set the window title and color before running the actual serial console utility
             f'powershell -Command "$Host.UI.RawUI.WindowTitle = \'{title}\'; $Host.UI.RawUI.ForegroundColor = \'{fcolor}\'; {powershell_post_cmd}"'
        ]
        subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def spawn_shell(self):
        """Spawn a shell console on the current host using powershell."""
        title = f"[ReCon]sole powershell on {self.current_host.address}"
        fcolor = "green"

        args = [
            # local
            "ssh",
            "-o StrictHostKeyChecking=no", "-t", "-i" , self._key_file, f"{self.current_host.username}@{self.current_host.address}",
            # remote
            # by using powershell as remote command we can set the window title and color before running the shell
            # by providing -NoExit, powershell will not exit and wait for user input
            f'powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = \'{title}\'; $Host.UI.RawUI.ForegroundColor = \'{fcolor}\';"'
        ]
        subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        
    def stop(self):
        if self._ssh_client:
            self._ssh_client.close()
        if self._ssh_tunnel_proc:
            self._ssh_tunnel_proc.terminate()
        if self._key_file:
            os.remove(self._key_file)
        # kill spawned ssh and serial consoles before exiting
        subprocess.run(['taskkill', '/f', '/fi', "WINDOWTITLE eq ReConSole*"])

    def setup(self, host, username, password):
        try:
            self._connect(host, username, password)
        except ReConAuthenticationError as err:
            self._activity(f"Authentication failed: {err}")
            self._call_handler("host_establishment", is_ok=False, error=err, error_type="authentication")
            return
        except ReConNetworkError as err:
            self._activity(f"Network error connecting: {err}")
            self._call_handler("host_establishment", is_ok=False, error=err, error_type="network")
            return
        except ReConSSHError as err:
            self._activity(f"SSH error connecting: {err}")
            self._call_handler("host_establishment", is_ok=False, error=err, error_type="ssh")
            return
        except Exception as err:
            self._activity(f"Unexpected error connecting: {err}")
            self._call_handler("host_establishment", is_ok=False, error=err, error_type="unknown")
            return
        
        self._call_handler("host_establishment", is_ok=True)
        self.enumerate_consoles()
        self.enumerate_local_networks()
        if self.current_host and self.current_host.nodes:
            self.enumerate_nodes()
        return


