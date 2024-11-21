from threading import Thread
from ui import RcUI
from model import ReCon
from CTkMessagebox import CTkMessagebox
import webbrowser
import os
import logging
import util

# Set the default log level to INFO. Log file will be created in the same directory with the name recon.log
logging.basicConfig(level=logging.INFO,  
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[ logging.FileHandler(util.get_dyn_path("recon.log"),mode='w')])
logger = logging.getLogger("recon")

class App:
    def __init__(self):
        self.logic = None
        self.ui = None
        self.init_logic()
        self.init_ui()

    def init_logic(self):
        # init model, restoring host data if available
        self.logic = ReCon()

        # bind events of model to app event handlers
        # any activity in model like connecting, enumerating etc will be reflected in ui
        self.logic.bind("activity", self.on_model_activity)

        # remaining events
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

        # bind events of ui to app event handlers
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
        self.ui.start()  # starts ui mainloop and doesn't return till exit click


    # Event handlers
    # app
    def on_stop(self):
        self.logic.stop()

    def on_model_initialize(self):
        """Triggered when the model initialized in the start() method"""
        if len(self.logic.host_pool):
            # fill the combobox with host_pool values
            values = tuple(h.address for h in self.logic.host_pool.values())
            self.ui.frames["login"].cmbx_sshosts.configure(values=values)
            
            # get the first host from host_pool dictionary and set username and address
            first_host = next(iter(self.logic.host_pool.values()))            
            self.ui.frames["login"].txt_username.insert(0, first_host.username)
            self.ui.frames["login"].cmbx_sshosts.set(first_host.address)
        else:
            # if there's no host in host_pool, set the current user as username
            self.ui.frames["login"].txt_username.insert(0, os.getlogin())
        
        # update status and show login frame
        self.ui.set_status("Ready!")
        self.ui.show("login")

    def on_model_activity(self, msg):
        """Triggered when the model is doing some activity"""
        self.ui.set_status(msg)

    def on_model_host_establishment(self, is_ok, error=None):
        """Triggered when the model is trying to establish a connection with the host"""
        if is_ok:
            # if the connection is established, update the title with the current host info and show the devices frame
            self.ui.set_connection_info_at_title(self.logic.current_host.username, self.logic.current_host.address)
            self.ui.set_status("Connection established!")
            self.ui.show("devices")
        else:
            # if not, show the error message and enable the login frame controls again.
            self.ui.set_status(f"Can't connect! ({error})", True)
            self.ui.frames["login"].set_accessibility("normal")

    def on_model_consoles_loaded(self, consoles):
        """Triggered when the model has loaded the consoles"""
        self.ui.set_status("Consoles loaded.")
        self.ui.frames["devices"].cmbx_consoles.configure(values=consoles)
        self.ui.frames["devices"].cmbx_consoles.set(consoles[0])
        self.ui.frames["devices"].btn_spawn_console.configure(state="normal")
        self.ui.frames["devices"].btn_consoles_refresh.configure(state="normal")

    def on_model_local_networks_loaded(self, networks):
        """Triggered when the model has loaded the local networks"""
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
        """Triggered when a node is found"""
        self.ui.frames["devices"].add_lbx_node(node)

    def on_model_nodes_loaded(self):
        """Triggered when node loading completed (either from cache or by scanning)"""
        self.ui.set_status(f"Nodes loaded.")

        # reactivate the refresh button and tunnel buttons
        self.ui.frames["devices"].btn_nodes_refresh.configure(state="normal")
        self.ui.frames["devices"].btn_tunnel_https.configure(state="normal")

    def on_model_tunnel_established(self, port_mapping):
        """Triggered when the model has established ssh tunnel for HTTP connections"""
        # if the tunnel is established, extend the listbox with the port mapping and double click handler
        # double click handler will open the browser with the url
        self.ui.frames["devices"].extend_lbx_nodes(port_mapping, handler=self.on_ui_lbx_node_double_click)
        self.ui.frames["devices"].btn_tunnel_https.configure(text="Close tunnel")
        self.ui.set_status(f"Tunnel established!")

    def on_model_tunnel_closed(self):
        """Triggered when the model has closed the ssh tunnel"""
        self.ui.frames["devices"].btn_tunnel_https.configure(text="Tunnel HTTPS")
        self.ui.set_status(f"Tunnel closed!")

    # ui
    def on_ui_cmbx_sshosts_change(self, arg):
        """Triggered when the host combobox selection changes"""
        # update the username field with the selected host's username if available
        prev_username = self.ui.frames["login"].txt_username.get()
        if prev_username:
            self.ui.frames["login"].txt_username.delete(0,len(prev_username))
        self.ui.frames["login"].txt_username.insert(0, self.logic.host_pool[arg].username)

    def on_ui_txt_password_keyrelease(self, arg):
        if arg.keycode == 13 and arg.widget.winfo_ismapped():
            # if enter clicked on password field and if password field is visible, trigger connect click
            # because even if we press enter while device frame is visible, password field is not visible, keyrelease event is triggered.
            self.on_ui_btn_connect_click()

    def on_ui_btn_connect_click(self):
        """Triggered when the connect button is clicked"""
        # get the host, username and password from the login frame
        host = self.ui.frames["login"].cmbx_sshosts.get()
        username = self.ui.frames["login"].txt_username.get()
        password = self.ui.frames["login"].txt_password.get()

        # if any of the fields are empty, show a message and return
        if not(host and username and password):
            self.ui.set_status("Missing fields!", True)
            return
        # otherwise, disable the login frame controls and start the setup process
        self.ui.frames["login"].set_accessibility("disabled")
        Thread(target=self.logic.setup, args=(host, username, password)).start()

    def on_ui_btn_spawn_shell(self):
        """Triggered when the spawn shell button is clicked"""
        self.logic.spawn_shell()

    def on_ui_btn_consoles_refresh(self):
        """Triggered when the refresh consoles button is clicked"""
        self.logic.clear_consoles()
        self.logic.enumerate_consoles()

    def on_ui_btn_spawn_console(self):
        """Triggered when the spawn console button is clicked"""
        console = self.ui.frames["devices"].cmbx_consoles.get()
        self.logic.spawn_console(console)

    def on_ui_btn_nics_refresh(self):
        """Triggered when the refresh nics button is clicked"""
        self.logic.clear_local_networks()
        self.logic.enumerate_local_networks()

    def on_ui_lbx_node_double_click(self, arg):
        port = self.ui.frames["devices"].get_selected_lbx_node_port()
        url = f"https://127.0.0.1:{port}"
        webbrowser.open_new_tab(url)

    def on_ui_btn_nodes_refresh(self):
        """Triggered when the refresh nodes button is clicked"""
        self.logic.clear_nodes()
        self.ui.frames["devices"].empty_lbx_nodes()
        Thread(target=self.logic.enumerate_nodes).start()

    def on_ui_btn_node_tunnel_https(self):
        self.logic.toggle_https_tunnel()

if __name__ == "__main__":
    logger.info("Application started.")
    app = App()
    app.start()  # infinite loop till exit click
    app.on_stop()
