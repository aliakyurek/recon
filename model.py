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
import time
import util
from dataclasses import dataclass
logger = logging.getLogger(__name__)


class ReCon:
    HOST_DATA_PATH = util.get_path("user/hosts.dat")

    class HostInfo:
        def __init__(self, address, username):
            self.address = address
            self.username = username
            self.active = True
            self.consoles = []
            self.networks = []
            self.nodes = []

    def __init__(self):
        self.event_handlers = {}
        self.config = None
        self.config_path = None
        self.ssh_client = None
        self.ssh_tunnel_proc = None
        self.key_file = None

        self.host_pool = {}
        self.current_host = None
        self.restore_host_data()

    def restore_host_data(self):
        if not os.path.isfile(self.HOST_DATA_PATH):
            return
        with open(self.HOST_DATA_PATH, 'rb') as file:
            # Deserialize and retrieve the variable from the file
            self.host_pool = pickle.load(file)
            if self.host_pool:
                for host in self.host_pool:
                    if self.host_pool[host].active:
                        self.current_host = self.host_pool[host]
                        break

    def save_host_data(self):
        os.makedirs(util.get_path("user/"), exist_ok=True)
        # Open the file in binary mode
        with open(self.HOST_DATA_PATH, 'wb') as file:
            # Serialize and write the variable to the file
            pickle.dump(self.host_pool, file)

    def bind(self, event, handler):
        self.event_handlers[event] = handler

    def call_handler(self, handler, **kwargs):
        if handler in self.event_handlers:
            self.event_handlers[handler](**kwargs)

    def start(self):
        self.call_handler("initialized")

    def connect(self, host, username, password):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.activity(f"Connecting to {host}...")

            self.ssh_client.connect(host, 22, username, password,
                                   timeout=3, look_for_keys=False)

            if self.current_host and self.current_host.address != host:
                self.current_host.active = False
            if host not in self.host_pool:
                self.current_host = self.host_pool[host] = self.HostInfo(address=host, username=username)
            self.save_host_data()

            self.activity(f"Checking prompt...")
            self.fill_prompt()

            self.activity(f"Deploying key...")
            self.deploy_key()
            self.call_handler("host_establishment", is_ok=True)
            return True, None

        except (AuthenticationException, TimeoutError, socket.error) as e:
            # Return a tuple indicating unsuccessful connection (False) and the raised exception
            return False, e

        except Exception as e:
            type, msg, traceback = sys.exc_info()
            logger.debug(f"{type} occured @ {traceback.tb_next.tb_frame}. {msg}")
            return False, e


    def activity(self, msg):
        logger.debug(msg)
        self.call_handler("activity", msg=msg)

    def fill_prompt(self):
        # Open a session on the SSH channel
        channel = self.ssh_client.get_transport().open_session()
        channel.settimeout(2)
        prompt = ""
        # Read the initial data if available
        try:
            prompt = channel.recv(1024).decode('utf-8')
        except socket.timeout:
            pass
        channel.close()
        self.prompt = prompt

    def execute_command(self, command):
        """Implement SSH command execution logic here."""
        # SSH command execution code
        logger.debug(f"Sending command via SSH: {command}")
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        exit_code = stdout.channel.recv_exit_status()
        logger.debug(f"Response: {output}")
        return output, error, exit_code

    def clear_consoles(self):
        self.current_host.consoles.clear()

    def enumerate_consoles(self):
        if not self.current_host.consoles:
            self.activity(f"Enumerating consoles...")
            output, _, _ = self.execute_command("wmic path Win32_SerialPort get Caption")
            self.current_host.consoles.extend(com.strip() for com in output.splitlines()[1:] if com)
            self.save_host_data()
        self.call_handler("consoles_loaded", consoles=self.current_host.consoles)

    def clear_local_networks(self):
        self.current_host.networks.clear()

    def enumerate_local_networks(self):
        if not self.current_host.networks:
            self.activity(f"Enumerating local networks...")
            output, _, _ = self.execute_command("ipconfig")
            pattern = r"IPv4 Address\D+(\d+\.\d+\.\d+\.\d+)\r\s+Subnet Mask\D+(\d+\.\d+\.\d+\.\d+)"
            matches = re.findall(pattern, output)

            for ip,subnet_mask in matches:
                # Filter out loopback addresses and return the IP addresses of up interfaces
                ipn = IPv4Network(f"{ip}/{subnet_mask}", False)
                if ipn.is_private and not(ipn.is_loopback):
                    self.current_host.networks.append(ipn)
            self.save_host_data()
        self.call_handler("local_networks_loaded", networks=[str(network) for network in self.current_host.networks])

    def clear_nodes(self):
        self.current_host.nodes.clear()

    def enumerate_nodes(self):
        if not self.current_host.nodes:
            for host in self.current_host.networks[0].hosts():
                host = str(host)
                self.activity(f"Querying... {host}")
                output, err, exit_code = self.execute_command(f"ping -n 1 -w 25 {host}")
                if exit_code == 0:
                    self.call_handler("node_found", node=host)
                    self.current_host.nodes.append(host)
            self.save_host_data()
        else:
            for host in self.current_host.nodes:
                self.call_handler("node_found", node=host)
        self.call_handler("nodes_loaded")

    def toggle_https_tunnel(self):
        if self.ssh_tunnel_proc is None:
            port_mapping = {}
            self.activity(f"Establishing tunnel...")
            args = ["ssh","-N","-i",self.key_file,f"{self.current_host.username}@{self.current_host.address}"]
            for node in self.current_host.nodes:
                args.append("-L")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                    server_socket.bind(("127.0.0.1", 0))
                    _, local_port = server_socket.getsockname()
                args.append(f"{local_port}:{node}:443")
                port_mapping[node] = local_port
            self.ssh_tunnel_proc = subprocess.Popen(args)
            self.call_handler("tunnel_established", port_mapping=port_mapping)
        else:
            self.activity(f"Closing tunnel...")
            self.ssh_tunnel_proc.terminate()
            self.ssh_tunnel_proc = None
            self.call_handler("tunnel_closed")


    def deploy_key(self):
        self.rsa_key = rsa_key = paramiko.RSAKey.generate(bits=2048)
        # self.addKeyToServer(rsa_key)
        key_name= rsa_key.get_name()
        key = rsa_key.get_base64()
        # Write the key to a file
        key_fd, self.key_file = tempfile.mkstemp()
        os.close(key_fd)
        rsa_key.write_private_key_file(self.key_file)

        command = f'echo {key_name} {key} > C:\\Users\\{self.current_host.username}\\.ssh\\authorized_keys'
        out, err, code = self.execute_command(command)

    def spawn_console(self, console):
        match = re.search(r"(COM\d+)", console)
        title = f"ReConSole serial {match.group()} on {self.current_host.address}"
        post_post_ssh_cmd = f"plink -serial {match.group()} -sercfg 115200 8,n,1,X"
        fcolor = "darkcyan"
        post_ssh_cmd = f'powershell -Command "$Host.UI.RawUI.WindowTitle = \'{title}\'; $Host.UI.RawUI.ForegroundColor = \'{fcolor}\'; {post_post_ssh_cmd}"'
        start_cmd = f"ssh -t -i {self.key_file} {self.current_host.username}@{self.current_host.address} {post_ssh_cmd}"
        os.system(f'start {start_cmd}')

    def spawn_shell(self):
        title = f"ReConSole powershell on {self.current_host.address}"
        fcolor = "green"
        post_ssh_cmd = f'powershell -NoExit -Command "$Host.UI.RawUI.WindowTitle = \'{title}\'; $Host.UI.RawUI.ForegroundColor = \'{fcolor}\';"'
        start_cmd = f"ssh -t -i {self.key_file} {self.current_host.username}@{self.current_host.address} {post_ssh_cmd}"
        os.system(f'start {start_cmd}')

    def stop(self):
        if self.ssh_client:
            self.ssh_client.close()
        if self.ssh_tunnel_proc:
            self.ssh_tunnel_proc.terminate()
        if self.key_file:
            os.remove(self.key_file)
        # kill spawned ssh and serial consoles
        subprocess.run(['taskkill', '/f', '/fi', "WINDOWTITLE eq ReConSole*"])


    def setup(self, host, username, password):
        connected, err = self.connect(host, username, password)
        if not connected:
            self.call_handler("host_establishment", is_ok=False, error = err)
            return
        self.enumerate_consoles()
        self.enumerate_local_networks()
        if self.current_host.nodes:
            self.enumerate_nodes()
        return

