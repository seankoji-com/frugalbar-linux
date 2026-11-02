"""Verify first application activation with no SVG pixbuf loader."""
from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gdk
from frugalbar_linux.ui import Ledger

original_loader = GdkPixbuf.Pixbuf.new_from_file_at_scale


def no_svg(path, *args):
    if str(path).endswith(".svg"):
        raise GLib.Error("Fixture: missing SVG loader")
    return original_loader(path, *args)


with tempfile.TemporaryDirectory() as home:
    os.environ["HOME"] = home
    os.environ["XDG_CONFIG_HOME"] = home
    with patch.object(GdkPixbuf.Pixbuf, "new_from_file_at_scale", side_effect=no_svg):
        app = Ledger(demo=True)
        assert app.register(None)
        app.activate()
        loop = GLib.MainLoop()
        GLib.timeout_add(150, lambda: (loop.quit(), False)[1])
        loop.run()
        assert app.window.get_visible(), "Missing loader prevented first activation"
        width, height = app.window.get_size()
        destination = Path(".artifacts/screenshots/missing-loader-first-activation.png")
        destination.parent.mkdir(parents=True, exist_ok=True)
        Gdk.pixbuf_get_from_window(app.window.get_window(), 0, 0, width, height).savev(str(destination), "png", [], [])
        app.tray.menu.get_children()[4].activate()
        assert app.stopping
        print("First GTK activation and Quit passed without an SVG loader")
