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


def save_last(ini_content: str) -> None:
    """Persist the last-applied config to ~/.config/m913-gui/last.ini."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LAST_INI.write_text(ini_content)


def load_last() -> str | None:
    """Load the last-applied config, or None if it doesn't exist."""
    if LAST_INI.is_file():
        return LAST_INI.read_text()
    return None
