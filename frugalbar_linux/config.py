"""Non-secret preferences and explicit desktop integration."""
import json
import os
from pathlib import Path
import sys


def config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def load() -> dict:
    try:
        value = json.loads((config_root() / "frugalbar-linux/settings.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save(settings: dict) -> None:
    directory = config_root() / "frugalbar-linux"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / "settings.json"
    temporary = directory / "settings.json.tmp"
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump({"discover": bool(settings.get("discover")),
                   "show_unconfigured": bool(settings.get("show_unconfigured"))}, stream)
    temporary.replace(target)


def desktop_entry(hidden: bool = False) -> str:
    # Desktop Entry quoting is not shell quoting. Quote both executable and path.
    def quote(value):
        return '"' + str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"'
    executable = Path(sys.argv[0]).resolve()
    if executable.name == "launch.py":
        wrapper = executable.parent.parent / "bin/frugalbar-linux"
        if wrapper.is_file():
            executable = wrapper
    if executable.name in {"__main__.py", "ui.py"} or executable.suffix == ".py":
        command = quote(sys.executable) + " -m frugalbar_linux"
        directory = "Path=" + str(Path(__file__).resolve().parents[1]) + "\n"
    else:
        command = quote(executable)
        directory = ""
    return ("[Desktop Entry]\nType=Application\nName=FrugalBar\n"
            "Comment=AI subscription usage and balances\nExec=" + command
            + (" --hidden" if hidden else "") + "\n" + directory
            + "Icon=utilities-system-monitor\nTerminal=false\nCategories=Utility;Monitor;\n")


def set_autostart(enabled: bool) -> None:
    target = config_root() / "autostart/frugalbar-linux.desktop"
    if enabled:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(desktop_entry(hidden=True))
    else:
        target.unlink(missing_ok=True)


def autostart_enabled() -> bool:
    return (config_root() / "autostart/frugalbar-linux.desktop").exists()
