"""B2 Mint Ledger: native GTK widgets, original FrugalBar vendor artwork."""
import collections
from decimal import Decimal
from pathlib import Path
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, Gdk, GdkPixbuf, Pango

from . import __version__, config, secretstore
from .engine import Engine
from .models import countdown, tray_reading, urgency
from .tray import Tray

ASSETS = Path(__file__).with_name("assets")
COLOURS = {"normal": "#4ecb71", "warning": "#efb84b", "critical": "#ef6868", "unknown": "#999999"}
GROUPS = {"claude": "Claude", "openai": "ChatGPT", "gemini": "Antigravity",
          "antigravityArgon": "Antigravity", "antigravityClaude": "Antigravity",
          "githubRest": "Developer limits", "githubGraphql": "Developer limits"}


def label(text, *, dim=False, bold=False):
    item = Gtk.Label(label=text, xalign=0)
    item.set_line_wrap(True)
    item.set_max_width_chars(90)
    if dim:
        item.get_style_context().add_class("dim-label")
    if bold:
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_weight_new(Pango.Weight.SEMIBOLD))
        item.set_attributes(attrs)
    return item


def box(vertical=False, spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                   spacing=spacing)


def artwork(provider, size=26):
    image = None
    for suffix in ("svg", "png"):
        try:
            image = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / f"{provider}.{suffix}"), size, size, True))
            break
        except GLib.Error:
            continue
    if image is None:
        image = Gtk.Image.new_from_icon_name("image-missing-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        image.get_accessible().set_name(provider + " logo unavailable")
        image.set_tooltip_text("Logo unavailable. Install the librsvg image loader.")
    else:
        image.get_accessible().set_name(provider + " logo, from FrugalBar")
    return image


class WindowCell(Gtk.Box):
    def __init__(self, window, snapshot, now, wide=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.set_hexpand(True)
        self.set_size_request(96, -1)
        self.window = window
        self.now = now
        self.tone = COLOURS["unknown" if snapshot.stale else urgency(window, now)]
        if window.used is not None:
            area = Gtk.DrawingArea()
            area.set_size_request(90, 10)
            area.connect("draw", self.draw)
            self.pack_start(area, False, False, 0)
            percent = f"{window.used * 100:.0f}" if window.reported_percent is None else f"{window.reported_percent:.4g}"
            text = percent + "% used" + (" · blocked" if window.blocked else "")
        else:
            text = "Blocked" if window.blocked else "Not published"
        self.pack_start(label(text), False, False, 0)
        reset = countdown(window.resets_at, now)
        if wide and window.resets_at is not None and window.resets_at > now:
            reset = "Resets in " + reset
        self.pack_start(label(reset, dim=True), False, False, 0)
        self.set_tooltip_text(snapshot.name + ": " + window.label + " · " + text + " · " + reset
                              + (" · Last known reading" if snapshot.stale else "")
                              + (" · " + window.detail if window.detail else ""))
        self.get_accessible().set_name(self.get_tooltip_text())

    def draw(self, area, cr):
        width = area.get_allocated_width()
        cr.set_source_rgba(.5, .5, .5, .25)
        cr.rectangle(0, 2, width, 6)
        cr.fill()
        colour = Gdk.RGBA()
        colour.parse(self.tone)
        cr.set_source_rgb(colour.red, colour.green, colour.blue)
        cr.rectangle(0, 2, width * self.window.used, 6)
        cr.fill()
        pace = self.window.pace(self.now)
        if pace is not None:
            cr.set_source_rgba(.9, .9, .9, .9)
            cr.rectangle(max(0, min(width - 2, pace * width)), 0, 2, 10)
            cr.fill()


class Ledger(Gtk.Application):
    def __init__(self, *, demo=False, hidden=False):
        super().__init__(application_id="com.seankoji.FrugalBarLinux" + (".Demo" if demo else ""),
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.demo = demo
        self.hidden = hidden
        self.preferences = config.load()
        self.window = None
        self.tray = None
        self.busy = False
        self.last_attempt = None
        self.history = collections.defaultdict(lambda: collections.deque(maxlen=60))
        self.timer = None
        self.stopping = False
        self.wide = True
        if not demo:
            from . import providers
            self.engine = Engine(providers.fetch, providers.definitions())
        else:
            from .demo import snapshots
            self.demo_data = snapshots(time.time())

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.hold()
        self.window = Gtk.ApplicationWindow(application=self, title="FrugalBar")
        self.window.set_default_size(960, 750)
        self.window.set_size_request(720, 400)
        self.window.connect("delete-event", self.on_close)
        self.window.set_icon_name("utilities-system-monitor")
        outer = box(True, 0)
        self.window.add(outer)
        toolbar = box(False, 10)
        toolbar.set_border_width(10)
        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.refresh_button.set_label("Refresh")
        self.refresh_button.set_always_show_image(True)
        self.refresh_button.connect("clicked", lambda *_: self.refresh(True))
        toolbar.pack_start(self.refresh_button, False, False, 0)
        self.checked = label("Waiting for first reading", dim=True)
        toolbar.pack_start(self.checked, True, True, 0)
        settings = Gtk.Button(label="Settings")
        settings.connect("clicked", lambda *_: self.settings())
        toolbar.pack_end(settings, False, False, 0)
        outer.pack_start(toolbar, False, False, 0)
        self.health = label("")
        self.health.set_margin_start(14)
        self.health.set_margin_end(14)
        self.health.set_margin_bottom(8)
        outer.pack_start(self.health, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.content = box(True, 14)
        self.content.set_border_width(12)
        scroll.add(self.content)
        outer.pack_start(scroll, True, True, 0)
        footer = label("FrugalBar Linux " + __version__ + " · Ctrl+R refresh · Ctrl+, settings", dim=True)
        footer.set_margin_start(12)
        footer.set_margin_bottom(8)
        outer.pack_start(footer, False, False, 0)
        self.window.connect("key-press-event", self.key_pressed)
        self.tray = Tray(self.toggle, lambda: self.refresh(True), self.settings, self.stop)
        self.window.connect("configure-event", self.resized)
        self.render()
        self.window.show_all()
        if self.hidden:
            self.window.hide()
            GLib.timeout_add_seconds(2, self.ensure_visible)
        self.refresh()
        self.timer = GLib.timeout_add_seconds(15, self.tick)

    def ensure_visible(self):
        if not self.tray.available():
            self.window.show_all()
            self.window.present()
        return False

    def resized(self, _, event):
        wide = event.width >= 960
        if wide != self.wide:
            self.wide = wide
            self.render()
        return False

    def on_close(self, *_):
        if self.tray and self.tray.available():
            self.window.hide()
        else:
            self.stop()
        return True

    def toggle(self):
        if self.window.get_visible() and self.window.is_active():
            self.window.hide()
        else:
            self.window.show_all()
            self.window.present()

    def stop(self):
        self.stopping = True
        if not self.demo:
            self.engine.stopped.set()
        if self.timer:
            GLib.source_remove(self.timer)
        if self.tray:
            self.tray.close()
        self.quit()

    def key_pressed(self, _, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_r:
                self.refresh(True)
            elif event.keyval == Gdk.KEY_comma:
                self.settings()
            elif event.keyval == Gdk.KEY_q:
                self.stop()

    def tick(self):
        self.refresh()
        self.render()
        return not self.stopping

    def refresh(self, manual=False):
        if self.busy or self.stopping:
            return
        if self.demo:
            self.last_attempt = time.time()
            self.render()
            return
        now = time.time()
        deadlines = self.engine.next_manual if manual else self.engine.next_poll
        if not any(now >= deadlines.get(key, 0) for key, _ in self.engine.definitions):
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.checked.set_text("Refreshing…")
        discover = bool(self.preferences.get("discover"))
        def work():
            try:
                self.engine.refresh(manual=manual, discover=discover)
            finally:
                GLib.idle_add(self.refreshed)
        threading.Thread(target=work, daemon=True).start()

    def refreshed(self):
        self.busy = False
        if self.stopping:
            return False
        self.last_attempt = time.time()
        self.refresh_button.set_sensitive(True)
        self.render()
        return False

    def render(self):
        if self.stopping or not self.window:
            return
        now = time.time()
        snapshots = self.demo_data if self.demo else list(self.engine.snapshots.values())
        for child in self.content.get_children():
            self.content.remove(child)
        visible = [s for s in snapshots if self.preferences.get("show_unconfigured")
                   or s.state != "not_configured"]
        if self.demo:
            self.content.pack_start(label("ILLUSTRATIVE DATA · Demo only · No credentials or network reads"), False, False, 0)
        critical = sum(s.critical or any(urgency(w, now) == "critical" for w in s.windows) for s in visible)
        stale = sum(s.stale for s in visible)
        failed = sum(s.state not in {"measured", "not_configured"} and not s.stale for s in visible)
        self.health.set_text(f"{critical} critical · {failed} not readable · {stale} stale")
        if not visible:
            self.content.pack_start(label("No providers configured", bold=True), False, False, 0)
            self.content.pack_start(label("Open Settings to save a credential in the desktop keyring, or enable read-only CLI discovery. Missing credentials never show as unused quota."), False, False, 0)
        quotas = [s for s in visible if s.windows or not s.balances]
        if quotas:
            self.content.pack_start(label("AI subscriptions and developer limits · Percentages used", bold=True), False, False, 0)
            grid = Gtk.Grid(column_spacing=16, row_spacing=12)
            for col, text in enumerate(("Provider", "5H", "WK", "MO", "Status")):
                grid.attach(label(text, dim=True, bold=True), col, 0, 1, 1)
            row = 1
            current_group = None
            for snapshot in quotas:
                group = GROUPS.get(snapshot.provider, snapshot.name)
                if group != current_group:
                    grid.attach(label(group + (" · " + snapshot.plan if snapshot.plan else ""), bold=True), 0, row, 5, 1)
                    row += 1
                    current_group = group
                identity = box(False)
                identity.set_valign(Gtk.Align.CENTER)
                identity.pack_start(artwork(snapshot.provider), False, False, 0)
                identity_text = box(True, 2)
                identity_text.pack_start(label(snapshot.name), False, False, 0)
                if self.wide and snapshot.source:
                    identity_text.pack_start(label(snapshot.source, dim=True), False, False, 0)
                identity.pack_start(identity_text, True, True, 0)
                identity.set_size_request(170, -1)
                identity.set_tooltip_text(snapshot.source + (" · Read " + time.strftime("%H:%M:%S", time.localtime(snapshot.measured_at)) if snapshot.measured_at else ""))
                grid.attach(identity, 0, row, 1, 1)
                for col, token in enumerate(("5H", "WK", "MO"), 1):
                    matching = [w for w in snapshot.windows if w.label == token]
                    column = box(True)
                    if not matching:
                        missing = label("—", dim=True)
                        missing.set_tooltip_text(token + " window not published")
                        column.pack_start(missing, False, False, 0)
                    for window in matching:
                        if len(matching) > 1 and window.detail:
                            column.pack_start(label(window.detail, dim=True), False, False, 0)
                        column.pack_start(WindowCell(window, snapshot, now, self.wide), False, False, 0)
                    column.set_hexpand(True)
                    grid.attach(column, col, row, 1, 1)
                status = box(True, 3)
                text = self.status(snapshot, now)
                status.pack_start(label(text), False, False, 0)
                status.set_size_request(140, -1)
                grid.attach(status, 4, row, 1, 1)
                row += 1
                extra = [w for w in snapshot.windows if w.label not in {"5H", "WK", "MO"}]
                for window in extra:
                    grid.attach(label(window.label, dim=True), 0, row, 1, 1)
                    grid.attach(WindowCell(window, snapshot, now, self.wide), 1, row, 3, 1)
                    row += 1
                if snapshot.message or snapshot.stale:
                    message = snapshot.message
                    if snapshot.stale:
                        stamp = time.strftime("%H:%M:%S", time.localtime(snapshot.measured_at))
                        message = "⚠ Last read " + stamp + ". " + message
                    grid.attach(label(message, dim=True), 0, row, 5, 1)
                    row += 1
            self.content.pack_start(grid, False, False, 0)
        balances = [s for s in visible if s.balances]
        if balances:
            self.content.pack_start(Gtk.Separator(), False, False, 0)
            self.content.pack_start(label("API spend & credits · Balances, never counted as quota", bold=True), False, False, 0)
            grid = Gtk.Grid(column_spacing=20, row_spacing=14)
            for col, text in enumerate(("Provider", "Balance", "Kind", "Trend", "Status")):
                grid.attach(label(text, dim=True), col, 0, 1, 1)
            row = 1
            for snapshot in balances:
                for balance in snapshot.balances:
                    identity = box()
                    identity.pack_start(artwork(snapshot.provider), False, False, 0)
                    identity.pack_start(label(snapshot.name), False, False, 0)
                    grid.attach(identity, 0, row, 1, 1)
                    grid.attach(label(balance.value + " " + balance.unit, bold=True), 1, row, 1, 1)
                    grid.attach(label(balance.kind, dim=True), 2, row, 1, 1)
                    key = (snapshot.provider, balance.unit, snapshot.credential_id)
                    history = self.history[key]
                    if not snapshot.stale and snapshot.state == "measured" and (not history or history[-1][0] != snapshot.measured_at):
                        history.append((snapshot.measured_at, Decimal(balance.value)))
                    grid.attach(label("Collecting readings" if len(history) < 2 else self.trend(history), dim=True), 3, row, 1, 1)
                    grid.attach(label(self.status(snapshot, now)), 4, row, 1, 1)
                    row += 1
                    if snapshot.message:
                        grid.attach(label(snapshot.message, dim=True), 0, row, 5, 1)
                        row += 1
            self.content.pack_start(grid, False, False, 0)
        title, tooltip, level = tray_reading(snapshots, now)
        attention = sum(s.state not in {"measured", "not_configured"} for s in snapshots)
        self.tray.update(title, tooltip + (f" · {attention} readings need attention" if attention else ""), level)
        if self.last_attempt and not self.busy:
            self.checked.set_text("Checked " + time.strftime("%H:%M:%S", time.localtime(self.last_attempt)))
        self.content.show_all()

    @staticmethod
    def trend(history):
        change = history[-1][1] - history[0][1]
        return f"{'↑' if change > 0 else '↓' if change < 0 else '→'} {change:+f} this session"

    @staticmethod
    def status(snapshot, now):
        if snapshot.stale:
            return "⚠ Stale · last known"
        if snapshot.state == "not_configured":
            return "— Not configured"
        if snapshot.state != "measured":
            return "⊖ Not readable"
        if snapshot.critical:
            return "! Insufficient balance"
        if any(urgency(w, now) == "critical" for w in snapshot.windows):
            return "! Exhausted / near limit"
        if any(urgency(w, now) == "warning" for w in snapshot.windows):
            return "! Running low"
        return "✓ Measured"

    def settings(self):
        dialog = Gtk.Dialog(title="FrugalBar Settings", transient_for=self.window, modal=True)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.set_default_size(620, 480)
        content = dialog.get_content_area()
        content.set_border_width(16)
        content.set_spacing(12)
        discover = Gtk.CheckButton(label="Read credentials from local CLIs, read-only")
        discover.set_active(bool(self.preferences.get("discover")))
        content.pack_start(discover, False, False, 0)
        content.pack_start(label("Opt-in reads local CLI login files. FrugalBar never refreshes or overwrites their tokens. Environment variables override saved keys.", dim=True), False, False, 0)
        show = Gtk.CheckButton(label="Show providers without credentials")
        show.set_active(bool(self.preferences.get("show_unconfigured")))
        content.pack_start(show, False, False, 0)
        startup = Gtk.CheckButton(label="Start in the tray when I log in")
        startup.set_active(config.autostart_enabled())
        startup.set_sensitive(not self.demo)
        content.pack_start(startup, False, False, 0)
        content.pack_start(Gtk.Separator(), False, False, 0)
        content.pack_start(label("Credentials · desktop Secret Service", bold=True), False, False, 0)
        from . import providers
        selector = Gtk.ComboBoxText()
        for key, name in providers.definitions():
            selector.append(key, name)
        selector.set_active(0)
        content.pack_start(selector, False, False, 0)
        entry = Gtk.Entry()
        entry.set_visibility(False)
        entry.set_placeholder_text("Paste a key or OAuth access token")
        content.pack_start(entry, False, False, 0)
        help_text = label("", dim=True)
        def selected(*_):
            from .credentials import ENV_KEYS
            keys = ENV_KEYS.get(selector.get_active_id(), ())
            if isinstance(keys, str):
                keys = (keys,)
            help_text.set_text("Environment alternative: " + ", ".join(keys))
            entry.set_text("")
        selector.connect("changed", selected)
        selected()
        content.pack_start(help_text, False, False, 0)
        actions = box()
        save = Gtk.Button(label="Save key")
        clear = Gtk.Button(label="Remove saved key")
        actions.pack_start(save, False, False, 0)
        actions.pack_start(clear, False, False, 0)
        content.pack_start(actions, False, False, 0)
        result = label("Keys are stored in your login keyring. No key is written to settings.json.", dim=True)
        content.pack_start(result, False, False, 0)
        if not secretstore.available():
            result.set_text("Secret Service helper missing. Install libsecret-tools with apt, or libsecret with Homebrew. CLI discovery and environment keys still work.")
        save.set_sensitive(secretstore.available() and not self.demo)
        clear.set_sensitive(secretstore.available() and not self.demo)
        def store(remove=False):
            provider = selector.get_active_id()
            value = "" if remove else entry.get_text().strip()
            if not remove and not value:
                return
            entry.set_text("")
            save.set_sensitive(False)
            clear.set_sensitive(False)
            result.set_text("Waiting for the desktop keyring…")
            def work():
                okay = secretstore.save_secret(provider, value)
                def done():
                    result.set_text("Saved key removed." if okay and remove else "Key saved." if okay else "Keyring operation failed or timed out. Unlock your login keyring and try again.")
                    save.set_sensitive(True)
                    clear.set_sensitive(True)
                    if not self.demo:
                        self.history.clear()
                        self.engine.credentials_changed()
                        self.refresh(True)
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()
        save.connect("clicked", lambda *_: store())
        clear.connect("clicked", lambda *_: store(True))
        dialog.show_all()
        dialog.run()
        if not self.demo:
            self.preferences = {"discover": discover.get_active(), "show_unconfigured": show.get_active()}
            try:
                config.save(self.preferences)
                config.set_autostart(startup.get_active())
                self.history.clear()
                self.engine.credentials_changed()
            except OSError:
                error = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.ERROR,
                                          buttons=Gtk.ButtonsType.CLOSE, text="Could not save desktop preferences.")
                error.run()
                error.destroy()
        dialog.destroy()
        self.refresh(True)
