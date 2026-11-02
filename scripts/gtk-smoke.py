"""Exercise the actual GTK app with isolated fixtures, never live credentials."""
from pathlib import Path
import sys
import tempfile
import os
from unittest.mock import patch
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from frugalbar_linux.ui import Ledger
from frugalbar_linux.models import Window, Balance

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
    app.tray.menu.get_children()[1].activate()
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
    app.tray.menu.get_children()[3].activate()
    now = app.demo_data[0].measured_at
    app.demo_data = [replace(app.demo_data[1], balances=(Balance("62500.000001", "credits"),)),
        replace(app.demo_data[6], windows=(Window("MO", .8, now + 360000, detail="Premium"),
                                          Window("MO", .5, now + 360000, detail="Chat"))),
        replace(app.demo_data[9], critical=True, message="DeepSeek reports that this balance cannot fund calls.")]
    app.window.resize(960, 750)
    app.render()
    capture(app.window, "codex-copilot-960.png")
    def texts(widget):
        if isinstance(widget, Gtk.Label):
            yield widget.get_text()
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                yield from texts(child)
    rendered = set(texts(app.content))
    assert {"Premium", "Chat", "62500.000001 credits", "! Insufficient balance"} <= rendered
    assert "1 critical" in app.health.get_text()
    original_loader = GdkPixbuf.Pixbuf.new_from_file_at_scale
    def no_svg(path, *args):
        if str(path).endswith(".svg"):
            raise GLib.Error("Fixture: missing SVG loader")
        return original_loader(path, *args)
    with patch.object(GdkPixbuf.Pixbuf, "new_from_file_at_scale", side_effect=no_svg):
        app.render()
        capture(app.window, "missing-svg-loader.png")
        assert app.window.get_visible()
    with patch.object(app.tray, "available", return_value=True):
        app.on_close()
        assert not app.window.get_visible() and not app.stopping
    app.hidden = True
    with patch.object(app.tray, "available", return_value=False):
        app.ensure_visible()
        assert app.window.get_visible()
        app.on_close()
        assert app.stopping
    print("GTK ledger, dual allowances, credits, missing-loader fallback, tray menu, Settings and close outcomes passed")
