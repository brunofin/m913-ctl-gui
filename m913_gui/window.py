"""Main application window."""

import configparser
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

# ── GDK → m913-ctl key name mapping ─────────────────────────────────────

_GDK_KEY_MAP: dict[int, str] = {}
for _i in range(26):
    _GDK_KEY_MAP[Gdk.KEY_a + _i] = chr(ord("a") + _i)
for _i in range(10):
    _GDK_KEY_MAP[Gdk.KEY_0 + _i] = str(_i)
for _i in range(1, 25):
    _k = getattr(Gdk, f"KEY_F{_i}", None)
    if _k:
        _GDK_KEY_MAP[_k] = f"f{_i}"
_GDK_KEY_MAP.update({
    Gdk.KEY_Return: "enter", Gdk.KEY_KP_Enter: "numenter",
    Gdk.KEY_space: "space", Gdk.KEY_Tab: "tab",
    Gdk.KEY_BackSpace: "backspace", Gdk.KEY_Delete: "delete",
    Gdk.KEY_Insert: "insert", Gdk.KEY_Home: "home", Gdk.KEY_End: "end",
    Gdk.KEY_Page_Up: "pageup", Gdk.KEY_Page_Down: "pagedown",
    Gdk.KEY_Up: "up", Gdk.KEY_Down: "down",
    Gdk.KEY_Left: "left", Gdk.KEY_Right: "right",
    Gdk.KEY_Caps_Lock: "capslock", Gdk.KEY_Scroll_Lock: "scrolllock",
    Gdk.KEY_Pause: "pause", Gdk.KEY_Print: "printscreen",
    Gdk.KEY_Num_Lock: "numlock",
    Gdk.KEY_minus: "minus", Gdk.KEY_equal: "equal",
    Gdk.KEY_bracketleft: "[", Gdk.KEY_bracketright: "]",
    Gdk.KEY_backslash: "backslash",
    Gdk.KEY_semicolon: ";", Gdk.KEY_apostrophe: "'",
    Gdk.KEY_grave: "`", Gdk.KEY_comma: ",",
    Gdk.KEY_period: ".", Gdk.KEY_slash: "/",
    Gdk.KEY_KP_0: "num0", Gdk.KEY_KP_1: "num1", Gdk.KEY_KP_2: "num2",
    Gdk.KEY_KP_3: "num3", Gdk.KEY_KP_4: "num4", Gdk.KEY_KP_5: "num5",
    Gdk.KEY_KP_6: "num6", Gdk.KEY_KP_7: "num7", Gdk.KEY_KP_8: "num8",
    Gdk.KEY_KP_9: "num9",
    Gdk.KEY_KP_Add: "numplus", Gdk.KEY_KP_Subtract: "numminus",
    Gdk.KEY_KP_Multiply: "nummul", Gdk.KEY_KP_Divide: "numdiv",
    Gdk.KEY_KP_Decimal: "numdot",
})

_MODIFIER_KEYVALS = {
    Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
    Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R,
    Gdk.KEY_ISO_Level3_Shift,
}

# Map shifted symbol keyvals back to their base keyvals (US layout)
_SHIFTED_SYMBOL_MAP: dict[int, int] = {
    Gdk.KEY_exclam: Gdk.KEY_1, Gdk.KEY_at: Gdk.KEY_2,
    Gdk.KEY_numbersign: Gdk.KEY_3, Gdk.KEY_dollar: Gdk.KEY_4,
    Gdk.KEY_percent: Gdk.KEY_5, Gdk.KEY_asciicircum: Gdk.KEY_6,
    Gdk.KEY_ampersand: Gdk.KEY_7, Gdk.KEY_asterisk: Gdk.KEY_8,
    Gdk.KEY_parenleft: Gdk.KEY_9, Gdk.KEY_parenright: Gdk.KEY_0,
    Gdk.KEY_underscore: Gdk.KEY_minus, Gdk.KEY_plus: Gdk.KEY_equal,
    Gdk.KEY_braceleft: Gdk.KEY_bracketleft,
    Gdk.KEY_braceright: Gdk.KEY_bracketright,
    Gdk.KEY_bar: Gdk.KEY_backslash, Gdk.KEY_colon: Gdk.KEY_semicolon,
    Gdk.KEY_quotedbl: Gdk.KEY_apostrophe,
    Gdk.KEY_asciitilde: Gdk.KEY_grave,
    Gdk.KEY_less: Gdk.KEY_comma, Gdk.KEY_greater: Gdk.KEY_period,
    Gdk.KEY_question: Gdk.KEY_slash,
}

# Unmodified key names that shadow mouse actions in the CLI parser
_SPECIAL_CONFLICTS = {"left", "right"}


# ── Keybind capture dialog ───────────────────────────────────────────────


class KeybindDialog(Adw.Window):
    """Modal dialog that captures a keyboard shortcut."""

    def __init__(self, parent, btn_label: str, current: str = ""):
        super().__init__(
            transient_for=parent, modal=True,
            default_width=400, default_height=220, resizable=False,
            title=f"Keybind \u2014 {btn_label}",
        )
        self.captured: str = current
        self.accepted: bool = False

        # Header
        header = Adw.HeaderBar()
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        header.pack_start(cancel_btn)
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        header.pack_end(apply_btn)

        # Content
        body = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16,
            margin_top=24, margin_bottom=24, margin_start=32, margin_end=32,
            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
        )
        self._hint = Gtk.Label(label="Press a key combination\u2026")
        self._hint.add_css_class("dim-label")
        body.append(self._hint)

        self._display = Gtk.Label(label=current or "\u2014")
        self._display.add_css_class("title-1")
        body.append(self._display)

        clear_btn = Gtk.Button(label="Clear", halign=Gtk.Align.CENTER)
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", self._on_clear)
        body.append(clear_btn)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(header)
        outer.append(body)
        self.set_content(outer)

        # Key capture controller
        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_key)
        self.add_controller(ctrl)

    def _on_key(self, _ctrl, keyval, _keycode, state):
        if keyval in _MODIFIER_KEYVALS:
            return False
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        # Resolve shifted keyvals: try direct → lowercase → shifted-symbol base
        name = _GDK_KEY_MAP.get(keyval) or _GDK_KEY_MAP.get(Gdk.keyval_to_lower(keyval))
        if not name:
            base = _SHIFTED_SYMBOL_MAP.get(keyval)
            if base:
                name = _GDK_KEY_MAP.get(base)
        if not name:
            return True

        mods: list[str] = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            mods.append("ctrl")
        if state & Gdk.ModifierType.SHIFT_MASK:
            mods.append("shift")
        if state & Gdk.ModifierType.ALT_MASK:
            mods.append("alt")
        if state & Gdk.ModifierType.SUPER_MASK:
            mods.append("super")

        # Unmodified arrow "left"/"right" would be parsed as mouse actions
        if not mods and name in _SPECIAL_CONFLICTS:
            self._hint.set_label(
                f"\u2018{name}\u2019 maps to a mouse action \u2014 use the dropdown or add a modifier."
            )
            return True

        combo = "+".join(mods + [name])
        self.captured = combo
        self._display.set_label(combo)
        self._hint.set_label("Press another key to change, or Apply.")
        return True

    def _on_apply(self, _btn):
        self.accepted = True
        self.close()

    def _on_clear(self, _btn):
        self.captured = ""
        self._display.set_label("\u2014")
        self._hint.set_label("Press a key combination\u2026")


# ── Main window ──────────────────────────────────────────────────────────


class M913Window(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, title="M913 Control", default_width=520, default_height=780)

        # ── Special actions for dropdown (built once from CLI) ────────
        self._special_actions = backend.list_special_actions()
        self._special_items = ["(none)"] + self._special_actions
        self._special_index = {n: i for i, n in enumerate(self._special_items)}
        self._btn_keybinds: dict[str, str] = {}
        self._loading = False

        # ── Header bar ───────────────────────────────────────────────
        header = Adw.HeaderBar()

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        header.pack_end(apply_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Load Profile\u2026", "win.load-profile")
        menu.append("Save Profile\u2026", "win.save-profile")
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

        # ── Toast overlay ────────────────────────────────────────────
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

        self._led_mode = Adw.ComboRow(title="Mode")
        mode_model = Gtk.StringList()
        for m in LED_MODES:
            mode_model.append(m.capitalize())
        self._led_mode.set_model(mode_model)
        self._led_mode.set_selected(3)
        self._led_mode.connect("notify::selected", self._on_led_mode_changed)
        led_group.add(self._led_mode)

        self._color_row = Adw.ActionRow(title="Color")
        self._color_btn = Gtk.ColorButton()
        self._color_btn.set_rgba(Gdk.RGBA(red=0, green=1.0, blue=0, alpha=1.0))
        self._color_btn.set_valign(Gtk.Align.CENTER)
        self._color_row.add_suffix(self._color_btn)
        self._color_row.set_activatable_widget(self._color_btn)
        led_group.add(self._color_row)

        self._brightness_row = Adw.ActionRow(title="Brightness")
        self._brightness_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
        self._brightness_scale.set_value(255)
        self._brightness_scale.set_hexpand(True)
        self._brightness_scale.set_size_request(200, -1)
        self._brightness_row.add_suffix(self._brightness_scale)
        led_group.add(self._brightness_row)

        self._speed_row = Adw.ActionRow(title="Speed")
        self._speed_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 5, 1)
        self._speed_scale.set_value(3)
        self._speed_scale.set_hexpand(True)
        self._speed_scale.set_size_request(200, -1)
        self._speed_row.add_suffix(self._speed_scale)
        led_group.add(self._speed_row)

        page.add(led_group)
        self._on_led_mode_changed()

        # ── Polling Rate Group ───────────────────────────────────────
        poll_group = Adw.PreferencesGroup(title="Polling Rate")
        self._polling_row = Adw.ComboRow(title="Rate (Hz)")
        poll_model = Gtk.StringList()
        for r in POLLING_RATES:
            poll_model.append(f"{r} Hz")
        self._polling_row.set_model(poll_model)
        self._polling_row.set_selected(3)
        poll_group.add(self._polling_row)
        page.add(poll_group)

        # ── Buttons Group ────────────────────────────────────────────
        btn_group = Adw.PreferencesGroup(
            title="Button Mapping",
            description="Pick a special action from the dropdown, "
            "or press \u2328 to record a key binding.",
        )
        self._btn_rows: dict[str, Adw.ActionRow] = {}
        self._btn_dropdowns: dict[str, Gtk.DropDown] = {}

        for key, label in BUTTON_NAMES:
            row = Adw.ActionRow(title=label)

            suffix = Gtk.Box(spacing=8)
            suffix.set_valign(Gtk.Align.CENTER)

            # Dropdown: special actions only
            model = Gtk.StringList()
            for item in self._special_items:
                model.append(item)
            dropdown = Gtk.DropDown(model=model)
            dropdown.set_size_request(180, -1)
            try:
                dropdown.set_enable_search(True)
            except (AttributeError, TypeError):
                pass

            default = BUTTON_DEFAULTS.get(key, "")
            if default and default in self._special_index:
                dropdown.set_selected(self._special_index[default])
            else:
                dropdown.set_selected(0)
            dropdown.connect("notify::selected", self._on_dropdown_changed, key)
            suffix.append(dropdown)

            # Keybind capture button
            kb_btn = Gtk.Button(icon_name="input-keyboard-symbolic")
            kb_btn.set_tooltip_text("Record a key binding")
            kb_btn.add_css_class("flat")
            kb_btn.connect("clicked", self._on_keybind_btn, key)
            suffix.append(kb_btn)

            row.add_suffix(suffix)
            self._btn_rows[key] = row
            self._btn_dropdowns[key] = dropdown
            btn_group.add(row)
        page.add(btn_group)

        # ── Status bar ───────────────────────────────────────────────
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
        self._toast_overlay.add_toast(Adw.Toast(title=msg, timeout=3))

    def _set_status(self, msg: str) -> None:
        self._status_label.set_label(msg)

    def _get_led_mode_name(self) -> str:
        return LED_MODES[self._led_mode.get_selected()]

    def _get_color_hex(self) -> str:
        rgba = self._color_btn.get_rgba()
        return f"{int(rgba.red*255):02x}{int(rgba.green*255):02x}{int(rgba.blue*255):02x}"

    # ── Collect current UI state ─────────────────────────────────────

    def _collect_settings(self) -> dict:
        dpi = {}
        for i, row in enumerate(self._dpi_rows, start=1):
            val = int(row.get_value())
            dpi[i] = max(100, min(16000, round(val / 100) * 100))

        buttons = {}
        for key in self._btn_rows:
            kb = self._btn_keybinds.get(key)
            if kb:
                buttons[key] = kb
            else:
                idx = self._btn_dropdowns[key].get_selected()
                if idx > 0:
                    buttons[key] = self._special_items[idx]

        return dict(
            dpi=dpi,
            led_mode=self._get_led_mode_name(),
            led_color=self._get_color_hex(),
            led_brightness=int(self._brightness_scale.get_value()),
            led_speed=int(self._speed_scale.get_value()),
            polling_rate=POLLING_RATES[self._polling_row.get_selected()],
            buttons=buttons if buttons else None,
        )

    def _build_current_ini(self) -> str:
        return backend.build_ini(**self._collect_settings())

    # ── Load INI into UI ─────────────────────────────────────────────

    def _load_ini_into_ui(self, ini_text: str) -> None:
        self._loading = True
        cfg = configparser.ConfigParser()
        cfg.read_string(ini_text)

        if cfg.has_section("dpi"):
            for i in range(5):
                k = f"dpi{i + 1}"
                if cfg.has_option("dpi", k):
                    self._dpi_rows[i].set_value(cfg.getint("dpi", k))

        if cfg.has_section("led"):
            mode = cfg.get("led", "mode", fallback="rainbow").lower()
            if mode in LED_MODES:
                self._led_mode.set_selected(LED_MODES.index(mode))
            color = cfg.get("led", "color", fallback=None)
            if color and len(color) == 6:
                r = int(color[0:2], 16) / 255
                g = int(color[2:4], 16) / 255
                b = int(color[4:6], 16) / 255
                self._color_btn.set_rgba(Gdk.RGBA(red=r, green=g, blue=b, alpha=1.0))
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
                    action = cfg.get("buttons", full_key)
                    if action in self._special_index:
                        self._btn_dropdowns[key].set_selected(self._special_index[action])
                        self._btn_keybinds.pop(key, None)
                        row.set_subtitle("")
                    else:
                        self._btn_dropdowns[key].set_selected(0)
                        self._btn_keybinds[key] = action
                        row.set_subtitle(f"\u2328 {action}")
                else:
                    self._btn_dropdowns[key].set_selected(0)
                    self._btn_keybinds.pop(key, None)
                    row.set_subtitle("")
        self._loading = False

    # ── Button mapping handlers ──────────────────────────────────────

    def _on_dropdown_changed(self, dropdown, _pspec, key: str) -> None:
        if self._loading:
            return
        idx = dropdown.get_selected()
        if idx > 0:
            # Special action selected — clear keybind
            self._btn_keybinds.pop(key, None)
            self._btn_rows[key].set_subtitle("")
        else:
            # (none) — show keybind subtitle if one exists
            kb = self._btn_keybinds.get(key)
            self._btn_rows[key].set_subtitle(f"\u2328 {kb}" if kb else "")

    def _on_keybind_btn(self, _btn, key: str) -> None:
        label = dict(BUTTON_NAMES)[key]
        current = self._btn_keybinds.get(key, "")
        dialog = KeybindDialog(self, label, current)
        dialog.connect("close-request", self._on_keybind_close, key)
        dialog.present()

    def _on_keybind_close(self, dialog, key: str) -> bool:
        if dialog.accepted:
            self._loading = True
            if dialog.captured:
                self._btn_keybinds[key] = dialog.captured
                self._btn_dropdowns[key].set_selected(0)
                self._btn_rows[key].set_subtitle(f"\u2328 {dialog.captured}")
            else:
                self._btn_keybinds.pop(key, None)
                self._btn_rows[key].set_subtitle("")
            self._loading = False
        return False  # allow close

    # ── Other handlers ───────────────────────────────────────────────

    def _on_led_mode_changed(self, *_args) -> None:
        mode = self._get_led_mode_name()
        has_color = mode in ("steady", "respiration")
        self._color_row.set_sensitive(has_color)
        self._brightness_row.set_sensitive(mode == "steady")
        self._speed_row.set_sensitive(mode == "respiration")

    def _on_apply(self, _btn) -> None:
        self._set_status("Applying\u2026")
        ini = backend.build_ini(**self._collect_settings())

        def _do():
            ok, output = backend.apply_ini(ini)
            GLib.idle_add(self._apply_done, ok, output)

        threading.Thread(target=_do, daemon=True).start()

    def _apply_done(self, ok: bool, output: str) -> None:
        if ok:
            self._set_status("Applied successfully")
            self._toast("Settings applied \u2713")
            backend.save_last(self._build_current_ini())
        else:
            self._set_status(f"Error: {output[:100]}")
            self._toast("Failed to apply \u2014 check m913-ctl output")

    def _on_probe(self, *_args) -> None:
        self._set_status("Probing\u2026")

        def _do():
            result = backend.probe()
            GLib.idle_add(self._probe_done, result)

        threading.Thread(target=_do, daemon=True).start()

    def _probe_done(self, result: str) -> None:
        if "Connected" in result:
            self._set_status("Mouse connected")
            self._toast("Mouse detected \u2713")
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
            f = dialog.save_finish(result)
            path = f.get_path()
            backend.save_profile(path, self._build_current_ini())
            self._toast(f"Saved to {path}")
        except GLib.Error:
            pass

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
            f = dialog.open_finish(result)
            path = f.get_path()
            self._load_ini_into_ui(backend.load_profile(path))
            self._toast(f"Loaded {path}")
        except GLib.Error:
            pass
