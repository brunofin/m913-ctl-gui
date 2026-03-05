"""Main application window."""

import configparser
import io
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import backend  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────

LED_MODES = ["off", "steady", "respiration", "rainbow"]
POLLING_RATES = [125, 250, 500, 1000]

BUTTON_NAMES = [
    ("left", "Left Click"),
    ("right", "Right Click"),
    ("middle", "Middle Click"),
    ("fire", "Fire Button"),
    ("side1", "Side 1"),
    ("side2", "Side 2"),
    ("side3", "Side 3"),
    ("side4", "Side 4"),
    ("side5", "Side 5"),
    ("side6", "Side 6"),
    ("side7", "Side 7"),
    ("side8", "Side 8"),
    ("side9", "Side 9"),
    ("side10", "Side 10"),
    ("side11", "Side 11"),
    ("side12", "Side 12"),
]

BUTTON_DEFAULTS = {
    "left": "left",
    "right": "right",
    "middle": "middle",
    "fire": "fire",
    "side1": "backward",
    "side2": "forward",
    "side3": "dpi+",
    "side4": "dpi-",
    "side5": "",
    "side6": "",
    "side7": "",
    "side8": "",
    "side9": "",
    "side10": "",
    "side11": "",
    "side12": "",
}


# ── Window ───────────────────────────────────────────────────────────────


class M913Window(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, title="M913 Control", default_width=520, default_height=780)

        # ── Header bar ───────────────────────────────────────────────
        header = Adw.HeaderBar()

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        header.pack_end(apply_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Load Profile…", "win.load-profile")
        menu.append("Save Profile…", "win.save-profile")
        menu.append("Probe Mouse", "win.probe")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        # ── Actions ──────────────────────────────────────────────────
        for name, cb in [
            ("load-profile", self._on_load_profile),
            ("save-profile", self._on_save_profile),
            ("probe", self._on_probe),
        ]:
            action = Gio.SimpleAction(name=name)
            action.connect("activate", cb)
            self.add_action(action)

        # ── Toast overlay (for status messages) ──────────────────────
        self._toast_overlay = Adw.ToastOverlay()

        # ── Scrollable preferences page ──────────────────────────────
        page = Adw.PreferencesPage()

        # ── DPI Group ────────────────────────────────────────────────
        dpi_group = Adw.PreferencesGroup(title="DPI Profiles")
        self._dpi_rows: list[Adw.SpinRow] = []
        for i in range(1, 6):
            defaults = [400, 800, 1600, 3200, 6400]
            row = Adw.SpinRow.new_with_range(100, 16000, 100)
            row.set_title(f"DPI {i}")
            row.set_value(defaults[i - 1])
            self._dpi_rows.append(row)
            dpi_group.add(row)
        page.add(dpi_group)

        # ── LED Group ────────────────────────────────────────────────
        led_group = Adw.PreferencesGroup(title="LED Lighting")

        # Mode
        self._led_mode = Adw.ComboRow(title="Mode")
        mode_model = Gtk.StringList()
        for m in LED_MODES:
            mode_model.append(m.capitalize())
        self._led_mode.set_model(mode_model)
        self._led_mode.set_selected(3)  # rainbow default
        self._led_mode.connect("notify::selected", self._on_led_mode_changed)
        led_group.add(self._led_mode)

        # Color
        self._color_row = Adw.ActionRow(title="Color")
        self._color_btn = Gtk.ColorButton()
        self._color_btn.set_rgba(Gdk.RGBA(red=0, green=1.0, blue=0, alpha=1.0))
        self._color_btn.set_valign(Gtk.Align.CENTER)
        self._color_row.add_suffix(self._color_btn)
        self._color_row.set_activatable_widget(self._color_btn)
        led_group.add(self._color_row)

        # Brightness
        self._brightness_row = Adw.ActionRow(title="Brightness")
        self._brightness_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 255, 1
        )
        self._brightness_scale.set_value(255)
        self._brightness_scale.set_hexpand(True)
        self._brightness_scale.set_size_request(200, -1)
        self._brightness_row.add_suffix(self._brightness_scale)
        led_group.add(self._brightness_row)

        # Speed
        self._speed_row = Adw.ActionRow(title="Speed")
        self._speed_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 1, 5, 1
        )
        self._speed_scale.set_value(3)
        self._speed_scale.set_hexpand(True)
        self._speed_scale.set_size_request(200, -1)
        self._speed_row.add_suffix(self._speed_scale)
        led_group.add(self._speed_row)

        page.add(led_group)
        self._on_led_mode_changed()  # set initial sensitivity

        # ── Polling Rate Group ───────────────────────────────────────
        poll_group = Adw.PreferencesGroup(title="Polling Rate")
        self._polling_row = Adw.ComboRow(title="Rate (Hz)")
        poll_model = Gtk.StringList()
        for r in POLLING_RATES:
            poll_model.append(f"{r} Hz")
        self._polling_row.set_model(poll_model)
        self._polling_row.set_selected(3)  # 1000 Hz default
        poll_group.add(self._polling_row)
        page.add(poll_group)

        # ── Buttons Group ────────────────────────────────────────────
        btn_group = Adw.PreferencesGroup(
            title="Button Mapping",
            description="Action names: left, right, middle, forward, backward, "
            "dpi+, dpi-, media_play, ctrl+c, f1, etc. "
            "Run m913-ctl --list-actions for full list.",
        )
        self._btn_rows: dict[str, Adw.EntryRow] = {}
        for key, label in BUTTON_NAMES:
            row = Adw.EntryRow(title=label)
            row.set_text(BUTTON_DEFAULTS.get(key, ""))
            self._btn_rows[key] = row
            btn_group.add(row)
        page.add(btn_group)

        # ── Status bar at bottom ─────────────────────────────────────
        self._status_label = Gtk.Label(
            label="Ready", xalign=0, margin_start=12, margin_end=12,
            margin_top=4, margin_bottom=8,
        )
        self._status_label.add_css_class("dim-label")
        self._status_label.add_css_class("caption")

        # ── Layout ───────────────────────────────────────────────────
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.append(header)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_child(page)
        vbox.append(scrolled)
        vbox.append(self._status_label)

        self._toast_overlay.set_child(vbox)
        self.set_content(self._toast_overlay)

        # ── Load last-applied settings on startup ────────────────────
        last = backend.load_last()
        if last:
            self._load_ini_into_ui(last)
            self._set_status("Loaded last-applied settings")

    # ── Helpers ──────────────────────────────────────────────────────

    def _toast(self, msg: str) -> None:
        toast = Adw.Toast(title=msg, timeout=3)
        self._toast_overlay.add_toast(toast)

    def _set_status(self, msg: str) -> None:
        self._status_label.set_label(msg)

    def _get_led_mode_name(self) -> str:
        return LED_MODES[self._led_mode.get_selected()]

    def _get_color_hex(self) -> str:
        rgba = self._color_btn.get_rgba()
        r = int(rgba.red * 255)
        g = int(rgba.green * 255)
        b = int(rgba.blue * 255)
        return f"{r:02x}{g:02x}{b:02x}"

    # ── Collect current UI state into kwargs for backend ─────────────

    def _collect_settings(self) -> dict:
        dpi = {}
        for i, row in enumerate(self._dpi_rows, start=1):
            val = int(row.get_value())
            # Round to nearest 100
            val = max(100, min(16000, round(val / 100) * 100))
            dpi[i] = val

        mode = self._get_led_mode_name()
        buttons = {}
        for key, row in self._btn_rows.items():
            text = row.get_text().strip()
            if text:
                buttons[key] = text

        return dict(
            dpi=dpi,
            led_mode=mode,
            led_color=self._get_color_hex(),
            led_brightness=int(self._brightness_scale.get_value()),
            led_speed=int(self._speed_scale.get_value()),
            polling_rate=POLLING_RATES[self._polling_row.get_selected()],
            buttons=buttons if buttons else None,
        )

    # ── Build INI from current state (for save) ─────────────────────

    def _build_current_ini(self) -> str:
        return backend.build_ini(**self._collect_settings())

    # ── Load INI into UI ─────────────────────────────────────────────

    def _load_ini_into_ui(self, ini_text: str) -> None:
        cfg = configparser.ConfigParser()
        cfg.read_string(ini_text)

        if cfg.has_section("dpi"):
            for i in range(5):
                key = f"dpi{i + 1}"
                if cfg.has_option("dpi", key):
                    self._dpi_rows[i].set_value(cfg.getint("dpi", key))

        if cfg.has_section("led"):
            mode = cfg.get("led", "mode", fallback="rainbow").lower()
            if mode in LED_MODES:
                self._led_mode.set_selected(LED_MODES.index(mode))
            color = cfg.get("led", "color", fallback=None)
            if color and len(color) == 6:
                r = int(color[0:2], 16) / 255
                g = int(color[2:4], 16) / 255
                b = int(color[4:6], 16) / 255
                rgba = Gdk.RGBA(red=r, green=g, blue=b, alpha=1.0)
                self._color_btn.set_rgba(rgba)
            brightness = cfg.get("led", "brightness", fallback=None)
            if brightness is not None:
                self._brightness_scale.set_value(int(brightness))
            speed = cfg.get("led", "speed", fallback=None)
            if speed is not None:
                self._speed_scale.set_value(int(speed))

        if cfg.has_section("mouse"):
            rate = cfg.getint("mouse", "polling_rate", fallback=1000)
            if rate in POLLING_RATES:
                self._polling_row.set_selected(POLLING_RATES.index(rate))

        if cfg.has_section("buttons"):
            for key, row in self._btn_rows.items():
                full_key = f"button_{key}"
                if cfg.has_option("buttons", full_key):
                    row.set_text(cfg.get("buttons", full_key))

    # ── Signal handlers ──────────────────────────────────────────────

    def _on_led_mode_changed(self, *_args) -> None:
        mode = self._get_led_mode_name()
        # Color relevant for steady + respiration
        has_color = mode in ("steady", "respiration")
        self._color_row.set_sensitive(has_color)
        # Brightness only for steady
        self._brightness_row.set_sensitive(mode == "steady")
        # Speed only for respiration
        self._speed_row.set_sensitive(mode == "respiration")

    def _on_apply(self, _btn) -> None:
        self._set_status("Applying…")
        settings = self._collect_settings()
        ini = backend.build_ini(**settings)

        def _do_apply():
            ok, output = backend.apply_ini(ini)
            GLib.idle_add(self._apply_done, ok, output)

        threading.Thread(target=_do_apply, daemon=True).start()

    def _apply_done(self, ok: bool, output: str) -> None:
        if ok:
            self._set_status("Applied successfully")
            self._toast("Settings applied ✓")
            # Persist last-applied settings
            ini = self._build_current_ini()
            backend.save_last(ini)
        else:
            self._set_status(f"Error: {output[:100]}")
            self._toast("Failed to apply — check m913-ctl output")

    def _on_probe(self, *_args) -> None:
        self._set_status("Probing…")

        def _do():
            result = backend.probe()
            GLib.idle_add(self._probe_done, result)

        threading.Thread(target=_do, daemon=True).start()

    def _probe_done(self, result: str) -> None:
        if "Connected" in result:
            self._set_status("Mouse connected")
            self._toast("Mouse detected ✓")
        else:
            self._set_status("Mouse not found")
            self._toast("Could not connect to mouse")

    def _on_save_profile(self, *_args) -> None:
        dialog = Gtk.FileDialog(title="Save Profile")
        dialog.set_initial_name("m913_profile.ini")

        ini_filter = Gtk.FileFilter()
        ini_filter.set_name("INI files")
        ini_filter.add_pattern("*.ini")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ini_filter)
        dialog.set_filters(filters)

        dialog.save(self, None, self._on_save_response)

    def _on_save_response(self, dialog, result) -> None:
        try:
            file = dialog.save_finish(result)
            path = file.get_path()
            ini = self._build_current_ini()
            backend.save_profile(path, ini)
            self._toast(f"Saved to {path}")
        except GLib.Error:
            pass  # user cancelled

    def _on_load_profile(self, *_args) -> None:
        dialog = Gtk.FileDialog(title="Load Profile")

        ini_filter = Gtk.FileFilter()
        ini_filter.set_name("INI files")
        ini_filter.add_pattern("*.ini")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ini_filter)
        dialog.set_filters(filters)

        dialog.open(self, None, self._on_load_response)

    def _on_load_response(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
            path = file.get_path()
            ini = backend.load_profile(path)
            self._load_ini_into_ui(ini)
            self._toast(f"Loaded {path}")
        except GLib.Error:
            pass  # user cancelled
