#!/bin/sh
set -eu
python3 -m unittest discover -v
python3 -m frugalbar_linux --version
python3 -m frugalbar_linux --demo --json >/dev/null
dbus-run-session -- xvfb-run -a -s '-screen 0 1440x1000x24' python3 scripts/gtk-smoke.py
