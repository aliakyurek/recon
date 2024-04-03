from customtkinter import (
    CTk, CTkFrame, CTkLabel,
    CTkEntry, CTkButton, CTkComboBox,
    set_appearance_mode, set_default_color_theme,
    ThemeManager
)
from CTkListbox import CTkListbox
import util

def center_window(Screen: CTk, width: int, height: int, scale_factor: float = 1.0):
    """Centers the window to the main display/monitor"""
    screen_width = Screen.winfo_screenwidth()
    screen_height = Screen.winfo_screenheight()
    x = int(((screen_width/2) - (width/2)) * scale_factor)
    y = int(((screen_height/2) - (height/1.5)) * scale_factor)
    return f"{width}x{height}+{x}+{y}"

class LoginFrame(CTkFrame):
    row_weight = 2
    column_weight = 2
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)

        CTkLabel(self, text="SSH host:").grid(row=0, column=0, pady=(10,0), sticky="e")
        self.cmbx_sshosts = CTkComboBox(self, values=[])
        self.cmbx_sshosts.set("")
        self.cmbx_sshosts.grid(row=0, column=1, padx=10, pady=(10,0), sticky="we")

        CTkLabel(self, text="Username:").grid(row=1, column=0, pady=(10,0), sticky="e")
        self.txt_username = CTkEntry(self)
        self.txt_username.grid(row=1, column=1, padx=10, pady=(10,0), sticky="we")

        CTkLabel(self, text="Password:").grid(row=2, column=0, pady=(10,0), sticky="e")
        self.txt_password = CTkEntry(self, show="*")
        self.txt_password.grid(row=2, column=1, padx=10, pady=(10,0), sticky="we")

        self.btn_connect = CTkButton(self, text="Connect")
        self.btn_connect.grid(row=3, column=1, padx=10, pady=(10,0), sticky="e")

    def set_accessibility(self, val):
        for k,v in self.children.items():
            if k != "!ctkcanvas":
                v.configure(state=val)


class DeviceFrame(CTkFrame):
    row_weight=5
    column_weight=5
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=5)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=1)

        self.btn_spawn_shell = CTkButton(self, text="Spawn Shell", state="normal")
        self.btn_spawn_shell.grid(row=0, column=1, padx=0, pady=(10, 0), sticky="w")

        CTkLabel(self, text="Consoles:").grid(row=1, column=0, pady=(10, 0), sticky="e")
        self.cmbx_consoles = CTkComboBox(self, values=[])
        self.cmbx_consoles.set("")
        self.cmbx_consoles.grid(row=1, column=1, padx=(3,1), pady=(10,0), sticky="we")
        self.btn_consoles_refresh = CTkButton(self, text="↺", state="disabled", width=26)
        self.btn_consoles_refresh.grid(row=1, column=2, padx=0, pady=(10, 0))

        self.btn_spawn_console = CTkButton(self, text="Spawn", state="disabled")
        self.btn_spawn_console.grid(row=1, column=3, padx=(3,1), pady=(10,0), sticky="w")

        CTkLabel(self, text="Local Networks:").grid(row=2, column=0, pady=(10,0), sticky="e")
        self.cmbx_nics = CTkComboBox(self, values=[])
        self.cmbx_nics.set("")
        self.cmbx_nics.grid(row=2, column=1, padx=(3,1), pady=(10,0), sticky="we")
        self.btn_nics_refresh = CTkButton(self, text="↺", state="disabled", width=26)
        self.btn_nics_refresh.grid(row=2, column=2, padx=0, pady=(10, 0))

        CTkLabel(self, text="Found nodes:").grid(row=3, column=0, pady=(10, 0), sticky="ne")
        self.lbx_nodes = CTkListbox(self,  button_color="#1F6AA5", hover_color="#3D81FF",
                                    highlight_color="#3D81FF", height=200)
        self.lbx_nodes.grid(row=3, column=1, padx=(3,1), pady=(10, 0), sticky="nswe")
        self.btn_nodes_refresh = CTkButton(self, text="↺", state="disabled", width=26)
        self.btn_nodes_refresh.grid(row=3, column=2, padx=0, pady=(10, 0), sticky="s")


        self.btn_tunnel_https = CTkButton(self, text="Tunnel HTTPS", state="disabled")
        self.btn_tunnel_https.grid(row=3, column=3, padx=(3,1), pady=(10,0), sticky="sw")


    def add_lbx_node(self, node):
        self.lbx_nodes.insert(node, node, height=20)
        self.lbx_nodes.buttons[node].pack_configure(pady=(0,1))

    def extend_lbx_nodes(self, node_port_map, handler):
        for n,p in node_port_map.items():
            self.lbx_nodes.buttons[n].port = p
            self.lbx_nodes.buttons[n].bind('<Double-Button-1>',handler)

    def get_selected_lbx_node_port(self):
        node = self.lbx_nodes.get()
        return self.lbx_nodes.buttons[node].port

    def empty_lbx_nodes(self):
        self.lbx_nodes.delete("all")


class RcUI(CTk):
    ICO_PATH = util.get_path("static/app.ico")
    def __init__(self, title):
        super().__init__()
        self.frames = {}

        set_appearance_mode("dark")  # Modes: system (default), light, dark
        set_default_color_theme("blue")  # Themes: blue (default), dark-blue, green

        self.frames["login"] = LoginFrame(master=self)
        self.frames["devices"] = DeviceFrame(master=self)

        self.status = CTkLabel(self, height=16)
        self.status.grid(row=2, column=0, sticky="se", padx=(0,5), columnspan=3)

        self.raw_title = title
        self.title(self.raw_title)
        self.grid_columnconfigure((0,2), weight=1)
        self.grid_rowconfigure((0,2), weight=1)
        self.geometry(center_window(self, 600, 400, self._get_window_scaling()))
        self.configure(fg_color=ThemeManager.theme["CTkFrame"]["fg_color"])
        self.iconbitmap(self.ICO_PATH)

    def start(self):
        self.mainloop()

    def set_status(self, status, highlight=False):
        if highlight:
            self.status.configure(text_color="#E16944")
        else:
            self.status.configure(text_color=ThemeManager.theme["CTkLabel"]["text_color"])
        self.status.configure(text=status)

    def set_connection_info_at_title(self, username, host):
        self.title(f"{self.raw_title} [{username}@{host}]")

    def show(self, frame):
        for f in self.frames:
            if f != frame:
                self.frames[f].grid_remove()
        self.grid_rowconfigure(1, weight=self.frames[frame].row_weight)
        self.grid_columnconfigure(1, weight=self.frames[frame].column_weight)
        self.frames[frame].grid(row=1, column=1, sticky="nsew", pady=(0, 0))


