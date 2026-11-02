"""Exercise the actual GTK app with isolated fixtures, never live credentials."""
from pathlib import Path
import sys
import tempfile
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from frugalbar_linux.ui import Ledger

destination = Path(".artifacts/screenshots")
destination.mkdir(parents=True, exist_ok=True)


def pump():
    loop = GLib.MainLoop()
    GLib.timeout_add(150, lambda: (loop.quit(), False)[1])
    loop.run()


def capture(window, name):
    pump()
    surface = window.get_window()
    assert surface, "Window did not realise"
    width, height = window.get_size()
    Gdk.pixbuf_get_from_window(surface, 0, 0, width, height).savev(str(destination / name), "png", [], [])


with tempfile.TemporaryDirectory() as home:
    os.environ["HOME"] = home
    os.environ["XDG_CONFIG_HOME"] = home
    app = Ledger(demo=True)
    assert app.register(None)
    app.activate()
    pump()
    assert app.window.get_visible()
    capture(app.window, "ledger-960.png")
    app.window.resize(760, 680)
    pump()
    capture(app.window, "ledger-760.png")
    def find_scroll(widget):
        if isinstance(widget, Gtk.ScrolledWindow):
            return widget
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                found = find_scroll(child)
                if found:
                    return found
        return None
    scroll = find_scroll(app.window)
    adjustment = scroll.get_vadjustment()
    adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
    capture(app.window, "balances-760.png")
    assert app.status(app.demo_data[5], 0).startswith("⚠ Stale")
    assert app.status(app.demo_data[7], 0) == "⊖ Not readable"
    app.window.hide()
    app.toggle()
    pump()
    assert app.window.get_visible(), "Tray action did not restore the window"
    def close_settings():
        for window in Gtk.Window.list_toplevels():
            if isinstance(window, Gtk.Dialog) and window.get_title() == "FrugalBar Settings":
                capture(window, "settings.png")
                window.response(Gtk.ResponseType.CLOSE)
                return False
        raise AssertionError("Settings did not open")
    GLib.timeout_add(250, close_settings)
    app.settings()
    app.stop()
    print("GTK ledger, original logo loading, window restore and Settings passed")
