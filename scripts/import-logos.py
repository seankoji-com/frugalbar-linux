#!/usr/bin/env python3
"""Extract original FrugalBar artwork without redrawing or remote downloads."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import textwrap

parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
destination = root / "frugalbar_linux/assets"
source = args.source / "Sources/QuotaBarUI/Components"
svg_source = source / "VendorAvatarView.swift"
png_source = source / "VendorAssetData.swift"
text = svg_source.read_text().split("public static func svgString", 1)[1]
assets = {}
for names, body in re.findall(r'case ([^:]+):(.*?)(?=\n        case |\n        default:|\n        \})', text, re.S):
    match = re.search(r'return """\n(.*?)\n            """', body, re.S)
    if not match:
        continue
    data = (textwrap.dedent(match[1]) + "\n").encode()
    for name in re.findall(r'\.(\w+)', names):
        filename = name + ".svg"
        (destination / filename).write_bytes(data)
        assets[filename] = hashlib.sha256(data).hexdigest()
for name, encoded in re.findall(r'case \.(\w+):\s*return "([A-Za-z0-9+/=]+)"', png_source.read_text()):
    data = base64.b64decode(encoded, validate=True)
    filename = name + ".png"
    (destination / filename).write_bytes(data)
    assets[filename] = hashlib.sha256(data).hexdigest()
revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.source, text=True).strip()
manifest = {"repository": "https://github.com/seankoji-com/frugalbar", "revision": revision,
            "sources": [str(p.relative_to(args.source)) for p in (svg_source, png_source)],
            "licence": "MIT; copyright 2026 Sean Carey; vendor trademarks belong to their owners",
            "sha256": dict(sorted(assets.items()))}
(destination / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
(root / "LICENSE").write_bytes((args.source / "LICENSE").read_bytes())
print(f"Imported {len(assets)} original assets from {revision}")
