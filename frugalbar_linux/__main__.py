"""Keep diagnostic/JSON commands usable without a graphical session."""
import argparse
from dataclasses import asdict
import json
import sys
import time
from . import __version__


def main():
    parser = argparse.ArgumentParser(description="FrugalBar usage ledger for Linux Mint Cinnamon")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--hidden", action="store_true", help="Start in the tray; show window if no tray is available")
    parser.add_argument("--demo", action="store_true", help="Isolated illustrative readings; never reads credentials or network")
    parser.add_argument("--json", action="store_true", help="Print a single usage snapshot without starting the GUI")
    parser.add_argument("--discover", action="store_true", help="Opt in to read-only local CLI credentials for --json")
    parser.add_argument("--install-desktop", action="store_true", help="Add FrugalBar to this user's application menu")
    args = parser.parse_args()
    if args.install_desktop:
        from pathlib import Path
        import os
        from .config import desktop_entry
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "applications"
        root.mkdir(parents=True, exist_ok=True)
        (root / "frugalbar-linux.desktop").write_text(desktop_entry())
        print("Added FrugalBar to your application menu.")
        return 0
    if args.json:
        if args.demo:
            from .demo import snapshots
            values = snapshots(time.time())
        else:
            from . import providers, config
            from .engine import Engine
            engine = Engine(providers.fetch, providers.definitions())
            engine.refresh(discover=args.discover or bool(config.load().get("discover")))
            values = list(engine.snapshots.values())
        public = []
        for snapshot in values:
            value = asdict(snapshot)
            value.pop("credential_id", None)
            public.append(value)
        print(json.dumps({"illustrative": args.demo, "providers": public}, allow_nan=False))
        return 0
    try:
        from .ui import Ledger
        return Ledger(demo=args.demo, hidden=args.hidden).run([])
    except (ImportError, ValueError) as exc:
        if "gi" not in str(exc) and "Gtk" not in str(exc):
            raise
        print("GTK 3 Python bindings are missing. See the README for Homebrew or apt dependencies.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
