#!/usr/bin/env python3
"""Launch the M913 GUI."""

import sys
from m913_gui.app import M913App

if __name__ == "__main__":
    app = M913App()
    sys.exit(app.run(sys.argv))
