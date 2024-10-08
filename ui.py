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

"""
There will be two frames namely login and device frames. The root window will display one of them at a time.
Frames will be created in the root window constructor and will be shown/hidden by the show method.
Root window will have a grid geometry and will have 3 rows and 3 columns. Row(0,2) and Column(0,2) (indices start from zero) will have a weight of 1.
So, Row(1) and Column(1) will be assigned during showing the frame via self.frames[frame].grid(row=1, column=1, sticky="nsew", pady=(0, 0))
The cell weight for row,column 1 will be set using:
    self.grid_rowconfigure(1, weight=self.frames[frame].row_weight)
    self.grid_columnconfigure(1, weight=self.frames[frame].column_weight) respectively.
This way we'll have variable size frames in the center of the root window.
The frames will have their own grid layouts&weights and child widgets.
"""

class LoginFrame(CTkFrame):
    """
    A custom frame for displaying a login form.
    Args:
        root: The parent widget.
        **kwargs: Additional keyword arguments to pass to the parent widget.
    Attributes:
        row_weight (int): The weight of the row in the parent grid layout.
        column_weight (int): The weight of the column in the parent grid layout.
        cmbx_sshosts (CTkComboBox): The combo box widget for selecting SSH hosts.
        txt_username (CTkEntry): The entry widget for entering the username.
        txt_password (CTkEntry): The entry widget for entering the password.
        btn_connect (CTkButton): The button widget for connecting.
    Methods:
        set_accessibility(val): Sets the accessibility state of the child widgets.
    """
    row_weight = 2
    column_weight = 2
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)

        # create a grid layout with 2 columns with 1:3 ratio for labels and controls respectively.
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)

        # create label and control pairs
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
        """
        Set the accessibility state of the child widgets.

        Parameters:
        - val (str): The state to set for the child widgets. Possible values are "normal" and "disabled".

        Returns:
        None
        """
        for k,v in self.children.items():
            # skip internal widgets (they have !ctkkanvas in their name) and only enable/disable our widgets.
            if k != "!ctkcanvas":
                v.configure(state=val)


class DeviceFrame(CTkFrame):
    """
    A custom frame widget for managing devices.
    This class extends the functionality of the CTkFrame widget and provides a user interface for managing devices.
    Attributes:
        row_weight (int): The weight of the rows in the grid layout.
        column_weight (int): The weight of the columns in the grid layout.
    Methods:
        __init__(self, root, **kwargs): Initializes the DeviceFrame widget.
        add_lbx_node(self, node): Adds a node to the listbox.
        extend_lbx_nodes(self, node_port_map, handler): Extends the listbox nodes with port information and event handler.
        get_selected_lbx_node_port(self): Returns the port of the selected node in the listbox.
        empty_lbx_nodes(self): Clears all nodes from the listbox.
    """

    row_weight=5
    column_weight=5
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)

        # create a grid layout with 4 columns with 1:5:1:1 ratio for labels, controls, tiny refresh buttons and buttons respectively
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=5)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=1)

        # create label and controls
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
        """
        Adds a node to the listbox.
        node is a IP address string.
        """
        self.lbx_nodes.insert(node, node, height=20)
        self.lbx_nodes.buttons[node].pack_configure(pady=(0,1))

    def extend_lbx_nodes(self, node_port_map, handler):
        """
        Extends the listbox nodes with port information and event handler.
        node_port_map is a dictionary with node IP address as key and port as value.
        The port number will be stored as a object attribute in the listbox button so that it can be retrieved later
        in the double click event handler.
        """
        for n,p in node_port_map.items():
            self.lbx_nodes.buttons[n].port = p
            self.lbx_nodes.buttons[n].bind('<Double-Button-1>',handler)

    def get_selected_lbx_node_port(self):
        """
        Returns the port of the selected node in the listbox.
        """
        node = self.lbx_nodes.get()
        return self.lbx_nodes.buttons[node].port

    def empty_lbx_nodes(self):
        """
        Clears all nodes from the listbox.
        """
        self.lbx_nodes.delete("all")


class RcUI(CTk):
    """
    Represents a custom UI class for the application.
    Attributes:
        ICO_PATH (str): The path to the application icon file.
    Methods:
        __init__(self, title): Initializes the RcUI object.
        start(self): Starts the main event loop of the UI.
        set_status(self, status, highlight=False): Sets the status text and color of the UI.
        set_connection_info_at_title(self, username, host): Sets the connection information in the UI title.
        show(self, frame): Shows the specified frame in the UI.
    """

    ICO_PATH = util.get_static_path("static/app.ico")
    def __init__(self, title):
        super().__init__()
        self.frames = {}

        set_appearance_mode("dark")  # Modes: system (default), light, dark
        set_default_color_theme("blue")  # Themes: blue (default), dark-blue, green

        # based on the connected host, the title will be updated. So we keep the original title in a variable.
        self.raw_title = title
        self.title(self.raw_title)

        # create a grid layout with 3 rows and 3 columns. Row 1 and Column 1 will be used for frames and they have varying weights.
        self.grid_columnconfigure((0,2), weight=1)
        self.grid_rowconfigure((0,2), weight=1)
        
        self.geometry(center_window(self, 600, 400, self._get_window_scaling()))
        self.configure(fg_color=ThemeManager.theme["CTkFrame"]["fg_color"])
        self.iconbitmap(self.ICO_PATH)

        # create login and device frames and add them to the frames dictionary.
        self.frames["login"] = LoginFrame(root=self)
        self.frames["devices"] = DeviceFrame(root=self)

        # create a status label at the bottom of the window.
        self.status = CTkLabel(self, height=16)
        self.status.grid(row=2, column=0, sticky="se", padx=(0,5), columnspan=3)

    def start(self):
        """
        Starts the main event loop of the UI.
        """
        self.mainloop()

    def set_status(self, status, highlight=False):
        """
        Sets the status text and its color based on highlight parameter.
        """
        if highlight:
            self.status.configure(text_color="#E16944")
        else:
            self.status.configure(text_color=ThemeManager.theme["CTkLabel"]["text_color"])
        self.status.configure(text=status)

    def set_connection_info_at_title(self, username, host):
        """
        Sets the connection information in the UI title.
        """
        self.title(f"{self.raw_title} [{username}@{host}]")

    def show(self, frame):
        """
        Shows the specified frame in the UI.
        """

        # first hide the frames other than the specified frame.
        for f in self.frames:
            if f != frame:
                self.frames[f].grid_remove()

        # resize the center (1,1) of the root window with the weights of designated frame.
        self.grid_rowconfigure(1, weight=self.frames[frame].row_weight)
        self.grid_columnconfigure(1, weight=self.frames[frame].column_weight)

        # show the specified frame in the center(1,1) of the root window.
        self.frames[frame].grid(row=1, column=1, sticky="nsew", pady=(0, 0))
