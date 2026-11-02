"""Cinnamon XApp tray with a classic X11 fallback."""
from pathlib import Path

from gi.repository import Gtk, GdkPixbuf


class Tray:
    def __init__(self, toggle, refresh, settings, quit_app):
        self.icon = None
        self.xapp = False
        self.menu = Gtk.Menu()
        self.reading_item = Gtk.MenuItem(label="FrugalBar")
        self.reading_item.set_sensitive(False)
        self.menu.append(self.reading_item)
        for label, callback in (("Open / hide usage", toggle), ("Refresh", refresh),
                                ("Settings", settings), ("Quit FrugalBar", quit_app)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _, action=callback: action())
            self.menu.append(item)
        self.menu.show_all()
        try:
            import gi
            gi.require_version("XApp", "1.0")
            from gi.repository import XApp
            if XApp.StatusIcon.any_monitors():
                self.icon = XApp.StatusIcon.new_with_name("frugalbar-linux")
                self.icon.set_secondary_menu(self.menu)
                self.icon.connect("activate", lambda *_: toggle())
                self.icon.set_visible(True)
                self.xapp = True
        except (ImportError, ValueError, AttributeError):
            pass
        if self.icon is None:
            self.icon = Gtk.StatusIcon()
            self.icon.set_title("FrugalBar")
            self.icon.connect("activate", lambda *_: toggle())
            self.icon.connect("popup-menu", self._popup)
            self.icon.set_visible(True)
        self.update("FrugalBar", "Waiting for readings", "unknown")

    def _popup(self, icon, button, timestamp):
        self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, timestamp)

    def available(self):
        if self.xapp:
            return True
        return self.icon.is_embedded()

    def update(self, label, tooltip, level):
        path = str(Path(__file__).with_name("assets") / f"tray-{level}.svg")
        self.reading_item.set_label(tooltip)
        self.icon.set_tooltip_text(tooltip)
        if self.xapp:
            self.icon.set_icon_name(path)
            self.icon.set_label(label)
        else:
            self.icon.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 24, 24, True))

    def close(self):
        self.icon.set_visible(False)
