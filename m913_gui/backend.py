"""Backend wrapper around the m913-ctl CLI."""

import shutil
import subprocess
import tempfile
from pathlib import Path

M913_CTL = shutil.which("m913-ctl") or "m913-ctl"
CONFIG_DIR = Path.home() / ".config" / "m913-gui"
LAST_INI = CONFIG_DIR / "last.ini"


def probe() -> str:
    """Run m913-ctl --probe and return stdout."""
    r = subprocess.run([M913_CTL, "--probe"], capture_output=True, text=True, timeout=10)
    return r.stdout + r.stderr


def build_ini(
    *,
    dpi: dict[int, int] | None = None,
    led_mode: str | None = None,
    led_color: str | None = None,
    led_brightness: int | None = None,
    led_speed: int | None = None,
    polling_rate: int | None = None,
    buttons: dict[str, str] | None = None,
) -> str:
    """Build an INI config string from the provided settings."""
    lines: list[str] = []

    if polling_rate is not None:
        lines.append("[mouse]")
        lines.append(f"polling_rate={polling_rate}")
        lines.append("")

    if dpi:
        lines.append("[dpi]")
        for slot in sorted(dpi):
            lines.append(f"dpi{slot}={dpi[slot]}")
        lines.append("")

    if led_mode is not None:
        lines.append("[led]")
        lines.append(f"mode={led_mode}")
        if led_color is not None:
            lines.append(f"color={led_color}")
        if led_brightness is not None:
            lines.append(f"brightness={led_brightness}")
        if led_speed is not None:
            lines.append(f"speed={led_speed}")
        lines.append("")

    if buttons:
        lines.append("[buttons]")
        for name, action in buttons.items():
            key = name if name.startswith("button_") else f"button_{name}"
            lines.append(f"{key}={action}")
        lines.append("")

    return "\n".join(lines)


def apply_ini(ini_content: str) -> tuple[bool, str]:
    """Write INI to a temp file and apply via m913-ctl --config.

    Returns (success, output_text).
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ini", prefix="m913_gui_", delete=False
    ) as f:
        f.write(ini_content)
        tmp_path = f.name

    try:
        r = subprocess.run(
            [M913_CTL, "--config", tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = r.stdout + r.stderr
        return r.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timed out waiting for m913-ctl"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def apply_settings(**kwargs) -> tuple[bool, str]:
    """Build INI from kwargs and apply. See build_ini() for params."""
    ini = build_ini(**kwargs)
    if not ini.strip():
        return False, "Nothing to apply"
    return apply_ini(ini)


def save_profile(path: str, ini_content: str) -> None:
    """Save an INI config to a file."""
    Path(path).write_text(ini_content)


def load_profile(path: str) -> str:
    """Load an INI config from a file."""
    return Path(path).read_text()


# ── Categorised action list from CLI ──────────────────────────────────

_parsed: dict | None = None


def _ensure_parsed() -> None:
    global _parsed
    if _parsed is not None:
        return
    try:
        r = subprocess.run(
            [M913_CTL, "--list-actions"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            _parsed = _parse_categorised(r.stdout)
            return
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    _parsed = _fallback_categorised()


def _parse_categorised(output: str) -> dict:
    special: list[str] = []
    keys: set[str] = set()
    section: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("("):
            continue
        if "Mouse/special" in stripped:
            section = "mouse"; continue
        elif "Modifier keys" in stripped:
            section = "modifiers"; continue
        elif "Keyboard keys" in stripped:
            section = "keys"; continue
        elif "Example" in stripped:
            section = None; continue
        if section == "mouse":
            special.append(stripped)
        elif section == "keys":
            for token in stripped.split():
                keys.add(token)
    return {"special": special, "keys": keys}


def _fallback_categorised() -> dict:
    return {
        "special": [
            "left", "right", "middle", "forward", "backward",
            "dpi+", "dpi-", "dpi-cycle", "dpi-loop",
            "fire", "three_click", "led_toggle", "rgb_toggle",
            "polling_switch", "none", "disable",
            "media_play", "media_player", "media_next", "media_prev",
            "media_stop", "media_vol_up", "media_vol_down", "media_mute",
            "media_email", "media_calc", "media_computer", "media_home",
            "media_search", "www_forward", "www_back", "www_stop",
            "www_refresh", "www_favorites", "favorites",
        ],
        "keys": {
            "a","b","c","d","e","f","g","h","i","j","k","l","m",
            "n","o","p","q","r","s","t","u","v","w","x","y","z",
            "0","1","2","3","4","5","6","7","8","9",
            "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10",
            "f11","f12","enter","space","tab","backspace","esc","delete",
            "insert","home","end","pageup","pagedown",
        },
    }


def list_special_actions() -> list[str]:
    """Non-keyboard actions for the button mapping dropdown."""
    _ensure_parsed()
    return _parsed["special"]


def get_valid_keys() -> set[str]:
    """Valid keyboard key names for keybind validation."""
    _ensure_parsed()
    return _parsed["keys"]


def save_last(ini_content: str) -> None:
    """Persist the last-applied config to ~/.config/m913-gui/last.ini."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LAST_INI.write_text(ini_content)


def load_last() -> str | None:
    """Load the last-applied config, or None if it doesn't exist."""
    if LAST_INI.is_file():
        return LAST_INI.read_text()
    return None
