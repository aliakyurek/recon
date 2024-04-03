from functools import partial
import os
import sys

get_path = partial(os.path.join, sys._MEIPASS if hasattr(sys,'_MEIPASS') else "")
