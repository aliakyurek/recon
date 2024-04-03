from threading import Thread
from ui import RcUI
from model import ReCon
from CTkMessagebox import CTkMessagebox
import webbrowser
import os


class App:
    def __init__(self):
        # read config
        self.logic = None
        self.ui = None
        self.init_logic()
        self.init_ui()

    def init_logic(self):
        # init model
        self.logic = ReCon()
        self.logic.bind("activity", self.on_model_activity)
        self.logic.bind("initialized", self.on_model_initialize)
        self.logic.bind("host_establishment", self.on_model_host_establishment)
        self.logic.bind("consoles_loaded", self.on_model_consoles_loaded)
        self.logic.bind("local_networks_loaded", self.on_model_local_networks_loaded)
        self.logic.bind("node_found", self.on_model_node_found)
        self.logic.bind("nodes_loaded", self.on_model_nodes_loaded)
        self.logic.bind("tunnel_established", self.on_model_tunnel_established)
        self.logic.bind("tunnel_closed", self.on_model_tunnel_closed)

    def init_ui(self):
        # init ui
        self.ui = RcUI(title="ReCon")
        self.ui.frames["login"].cmbx_sshosts.configure(command=self.on_ui_cmbx_sshosts_change)
        self.ui.frames["login"].txt_password.bind("<KeyRelease>", self.on_ui_txt_password_keyrelease)
        self.ui.frames["login"].btn_connect.configure(command=self.on_ui_btn_connect_click)
        self.ui.frames["devices"].btn_spawn_shell.configure(command=self.on_ui_btn_spawn_shell)
        self.ui.frames["devices"].btn_consoles_refresh.configure(command=self.on_ui_btn_consoles_refresh)
        self.ui.frames["devices"].btn_spawn_console.configure(command=self.on_ui_btn_spawn_console)
        self.ui.frames["devices"].btn_nics_refresh.configure(command=self.on_ui_btn_nics_refresh)
        self.ui.frames["devices"].btn_nodes_refresh.configure(command=self.on_ui_btn_nodes_refresh)
        self.ui.frames["devices"].btn_tunnel_https.configure(command=self.on_ui_btn_node_tunnel_https)

    def start(self):
        self.logic.start()
        self.ui.start()  # doesn't return while UI running

    # Event handlers
    # app
    def on_stop(self):
        self.logic.stop()

    # model
    def on_model_initialize(self):
        if len(self.logic.host_pool):
            values = tuple(h for h in self.logic.host_pool)
            self.ui.frames["login"].cmbx_sshosts.configure(values=values)
        if self.logic.current_host:
            self.ui.frames["login"].txt_username.insert(0, self.logic.current_host.username)
            self.ui.frames["login"].cmbx_sshosts.set(self.logic.current_host.address)
        else:
            self.ui.frames["login"].txt_username.insert(0, os.getlogin())
        self.ui.set_status("Ready!")
        self.ui.show("login")

    def on_model_activity(self, msg):
        self.ui.set_status(msg)

    def on_model_host_establishment(self, is_ok, error=None):
        if is_ok:
            self.ui.set_connection_info_at_title(self.logic.current_host.username, self.logic.current_host.address)
            self.ui.set_status("Connection established!")
            self.ui.show("devices")
        else:
            self.ui.set_status(f"Can't connect! ({error})", True)
            self.ui.frames["login"].set_accessibility("normal")


    def on_model_consoles_loaded(self, consoles):
        self.ui.set_status("Consoles loaded.")
        self.ui.frames["devices"].cmbx_consoles.configure(values=consoles)
        self.ui.frames["devices"].cmbx_consoles.set(consoles[0])
        self.ui.frames["devices"].btn_spawn_console.configure(state="normal")
        self.ui.frames["devices"].btn_consoles_refresh.configure(state="normal")

    def on_model_local_networks_loaded(self, networks):
        self.ui.set_status("Local networks loaded.")
        self.ui.frames["devices"].cmbx_nics.configure(values=networks)
        self.ui.frames["devices"].cmbx_nics.set(networks[0])
        self.ui.frames["devices"].btn_nics_refresh.configure(state="normal")
        if not self.logic.current_host.nodes:
            msg = CTkMessagebox(title="Proceed?",
                                message="No previously found nodes available. Selected network will be scanned."
                                        "Do you want to proceed?",
                                icon="question", option_1="No", option_2="Yes")
            if msg.get() == "Yes":
                Thread(target=self.logic.enumerate_nodes).start()

    def on_model_node_found(self, node):
        self.ui.frames["devices"].add_lbx_node(node)

    def on_model_nodes_loaded(self):
        self.ui.set_status(f"Nodes loaded.")
        self.ui.frames["devices"].btn_nodes_refresh.configure(state="normal")
        self.ui.frames["devices"].btn_tunnel_https.configure(state="normal")

    def on_model_tunnel_established(self, port_mapping):
        self.ui.frames["devices"].extend_lbx_nodes(port_mapping, handler=self.on_ui_lbx_node_double_click)
        self.ui.frames["devices"].btn_tunnel_https.configure(text="Close tunnel")
        self.ui.set_status(f"Tunnel established!")

    def on_model_tunnel_closed(self):
        self.ui.frames["devices"].btn_tunnel_https.configure(text="Tunnel HTTPS")
        self.ui.set_status(f"Tunnel closed!")

    # ui
    def on_ui_cmbx_sshosts_change(self, arg):
        prev_username = self.ui.frames["login"].txt_username.get()
        if prev_username:
            self.ui.frames["login"].txt_username.delete(0,len(prev_username))
        self.ui.frames["login"].txt_username.insert(0, self.logic.host_pool[arg].username)

    def on_ui_txt_password_keyrelease(self, arg):
        if arg.keycode == 13 and arg.widget.winfo_ismapped():
            self.on_ui_btn_connect_click()

    def on_ui_btn_connect_click(self):
        host = self.ui.frames["login"].cmbx_sshosts.get()
        username = self.ui.frames["login"].txt_username.get()
        password = self.ui.frames["login"].txt_password.get()
        if not(host and username and password):
            self.ui.set_status("Missing fields!", True)
            return
        self.ui.frames["login"].set_accessibility("disabled")
        Thread(target=self.logic.setup, args=(host, username, password)).start()

    def on_ui_btn_spawn_shell(self):
        self.logic.spawn_shell()

    def on_ui_btn_consoles_refresh(self):
        self.logic.clear_consoles()
        self.logic.enumerate_consoles()

    def on_ui_btn_spawn_console(self):
        console = self.ui.frames["devices"].cmbx_consoles.get()
        self.logic.spawn_console(console)

    def on_ui_btn_nics_refresh(self):
        self.logic.clear_local_networks()
        self.logic.enumerate_local_networks()

    def on_ui_lbx_node_double_click(self, arg):
        port = self.ui.frames["devices"].get_selected_lbx_node_port()
        url = f"https://127.0.0.1:{port}"
        webbrowser.open_new_tab(url)

    def on_ui_btn_nodes_refresh(self):
        self.logic.clear_nodes()
        self.ui.frames["devices"].empty_lbx_nodes()
        Thread(target=self.logic.enumerate_nodes).start()

    def on_ui_btn_node_tunnel_https(self):
        self.logic.toggle_https_tunnel()

if __name__ == "__main__":
    app = App()
    app.start()  # infinite loop
    app.on_stop()
