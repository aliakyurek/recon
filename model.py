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
import util
logger = logging.getLogger(__name__)

strList = list[str]


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
        logger.debug(msg)
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

        # deploy the public key to the remote host
        command = f'echo {key_name} {key} > C:\\Users\\{self.current_host.username}\\.ssh\\authorized_keys'
        out, err, code = self.execute_command(command)

    def bind(self, event, handler):
        """Bind an event to a handler function."""
        self._event_handlers[event] = handler

    def start(self):
        # this doesn't do anything yet, but it's a good practice to have a start method
        self._call_handler("initialized")

    def connect(self, host, username, password):
        """Connect to a host using SSH."""
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
            self._call_handler("host_establishment", is_ok=True)
            return True, None

        except (AuthenticationException, TimeoutError, socket.error) as e:
            # Return a tuple indicating unsuccessful connection (False) and the raised exception
            return False, e

        except Exception as e:
            type, msg, traceback = sys.exc_info()
            logger.debug(f"{type} occured @ {traceback.tb_next.tb_frame}. {msg}")
            return False, e

    def execute_command(self, command):
        """Run the command on the connected host and return the output, error, and exit code."""
        # SSH command execution code
        logger.debug(f"Sending command via SSH: {command}")
        stdin, stdout, stderr = self._ssh_client.exec_command(command)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        exit_code = stdout.channel.recv_exit_status()
        logger.debug(f"Response: {output}")
        return output, error, exit_code

    def clear_consoles(self):
        """Clear console list"""
        self.current_host.consoles.clear()

    def enumerate_consoles(self):
        """Enumerate the available serial consoles on the host."""
        if not self.current_host.consoles:
            self._activity(f"Enumerating consoles...")
            output, _, _ = self.execute_command("wmic path Win32_SerialPort get Caption")
            self.current_host.consoles.extend(com.strip() for com in output.splitlines()[1:] if com)
            self._save_host_data()
        self._call_handler("consoles_loaded", consoles=self.current_host.consoles)

    def clear_local_networks(self):
        """Clear local network list"""
        self.current_host.networks.clear()

    def enumerate_local_networks(self):
        """Enumerate the available local networks on the host."""
        if not self.current_host.networks:
            self._activity(f"Enumerating local networks...")
            output, _, _ = self.execute_command("ipconfig")
            pattern = r"IPv4 Address\D+(\d+\.\d+\.\d+\.\d+)\r\s+Subnet Mask\D+(\d+\.\d+\.\d+\.\d+)"
            matches = re.findall(pattern, output)

            for ip,subnet_mask in matches:
                # Filter out loopback addresses and return the IP addresses of up interfaces
                ipn = IPv4Network(f"{ip}/{subnet_mask}", False)
                if ipn.is_private and not(ipn.is_loopback):
                    self.current_host.networks.append(ipn)
            self._save_host_data()
        self._call_handler("local_networks_loaded", networks=[str(network) for network in self.current_host.networks])

    def clear_nodes(self):
        """Clear node list"""
        self.current_host.nodes.clear()

    def enumerate_nodes(self):
        """Enumerate the available IP reachable nodes on the host."""
        if not self.current_host.nodes:
            for host in self.current_host.networks[0].hosts():
                host = str(host)
                self._activity(f"Querying... {host}")
                output, err, exit_code = self.execute_command(f"ping -n 1 -w 25 {host}")
                if exit_code == 0:
                    self._call_handler("node_found", node=host)
                    self.current_host.nodes.append(host)
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
            self._ssh_tunnel_proc = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
            self._call_handler("tunnel_established", port_mapping=port_mapping)
        else:
            self._activity(f"Closing tunnel...")
            self._ssh_tunnel_proc.terminate()
            self._ssh_tunnel_proc = None
            self._call_handler("tunnel_closed")

    def spawn_console(self, console):
        """Spawn a console for the specified console name like 'USB to UART Bridge (COM6)'"""
        match = re.search(r"(COM\d+)", console)
        title = f"ReConSole serial {match.group()} on {self.current_host.address}"
        
        # our remote command is actually a powershell command that sets the window title and color and then runs the plink command
        # this is the plink command that connects to the serial port
        post_post_ssh_cmd = f"plink -serial {match.group()} -sercfg 115200 8,n,1,X"
        fcolor = "darkcyan"

        # this is the powershell command and used as post connection command for ssh.
        # this way we can set the window title and color before running the plink command
        post_ssh_cmd = f'powershell -Command "$Host.UI.RawUI.WindowTitle = \'{title}\'; $Host.UI.RawUI.ForegroundColor = \'{fcolor}\'; {post_post_ssh_cmd}"'
        start_cmd = f"ssh -t -i {self._key_file} {self.current_host.username}@{self.current_host.address} {post_ssh_cmd}"

        # run this command in a new local shell window
        os.system(f'start {start_cmd}')

    def spawn_shell(self):
        title = f"ReConSole powershell on {self.current_host.address}"
        fcolor = "green"

        # this is the powershell command and used as post connection command for ssh.
        # this way we can set the window title and color before running the shell
        # by providing -NoExit, the shell will not exit after a command is executed
        post_ssh_cmd = f'powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = \'{title}\'; $Host.UI.RawUI.ForegroundColor = \'{fcolor}\';"'
        start_cmd = f"ssh -t -i {self._key_file} {self.current_host.username}@{self.current_host.address} {post_ssh_cmd}"
        
        # run this command in a new local shell window
        os.system(f'start {start_cmd}')

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
        connected, err = self.connect(host, username, password)
        if not connected:
            self._call_handler("host_establishment", is_ok=False, error = err)
            return
        self.enumerate_consoles()
        self.enumerate_local_networks()
        if self.current_host.nodes:
            self.enumerate_nodes()
        return

