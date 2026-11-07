"""Package the Mini App resources as Python constants for Python Workers."""
from pathlib import Path
import base64

root = Path(__file__).resolve().parents[1]
assets = root / 'ui' / 'menu_preview'
out = '# Generated from ui/menu_preview assets. No menu data or credentials.\n'
for name, path in [('PREVIEW_HTML', 'index.html'), ('PREVIEW_CSS', 'style.css'), ('PREVIEW_JS', 'app.js')]:
    content = (assets / path).read_text()
    if name == 'PREVIEW_CSS':
        pattern = 'data:image/webp;base64,' + base64.b64encode((assets / 'botanical-pattern.webp').read_bytes()).decode('ascii')
        content = content.replace('__SUNPARK_PATTERN_DATA_URL__', pattern)
    out += name + ' = ' + repr(content) + '\n'
out += 'PREVIEW_LOGO = ' + repr((assets / 'sunpark-logo.svg').read_text()) + '\n'
(root / 'src' / 'menu_preview_assets.py').write_text(out)

