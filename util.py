from functools import partial
import os

# get_path = partial(os.path.join, sys._MEIPASS if hasattr(sys,'_MEIPASS') else "")
get_static_path = partial(os.path.join, os.path.dirname(__file__))
get_dyn_path = partial(os.path.join, os.getcwd())
