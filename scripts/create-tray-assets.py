"""Generate FrugalBar's status glyph; provider logos are imported separately."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "frugalbar_linux/assets"
for name, colour in {"normal": "#4ecb71", "warning": "#efb84b", "critical": "#ef6868", "unknown": "#999999"}.items():
    content = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               f'<g fill="{colour}"><rect x="2" y="14" width="4" height="8" rx="1"/>'
               '<rect x="10" y="8" width="4" height="14" rx="1"/>'
               '<rect x="18" y="2" width="4" height="20" rx="1"/></g></svg>\n')
    (root / f"tray-{name}.svg").write_text(content)
