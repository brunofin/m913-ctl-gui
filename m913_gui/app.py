"""GTK4/Adwaita application."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from .window import M913Window  # noqa: E402


class M913App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="dev.m913.gui")

    def do_activate(self):
        win = M913Window(application=self)
        win.present()
