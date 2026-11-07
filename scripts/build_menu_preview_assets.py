"""Package the Mini App resources as Python constants for Python Workers."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
assets = root / 'ui' / 'menu_preview'
out = '# Generated from ui/menu_preview assets. No menu data or credentials.\n'
for name, path in [('PREVIEW_HTML', 'index.html'), ('PREVIEW_CSS', 'style.css'), ('PREVIEW_JS', 'app.js')]:
    out += name + ' = ' + repr((assets / path).read_text()) + '\n'
(root / 'src' / 'menu_preview_assets.py').write_text(out)
