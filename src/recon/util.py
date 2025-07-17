from functools import partial
import os

# Get the directory where this util.py file is located
PACKAGE_DIR = os.path.dirname(__file__)

def get_static_path(filename):
    """Get path to static files within the package"""
    return os.path.join(PACKAGE_DIR, "static", filename)

# For dynamic files (logs, etc.) use current working directory  
get_dyn_path = partial(os.path.join, os.getcwd())
