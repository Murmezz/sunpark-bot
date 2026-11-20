"""Opt-in SunPark interface refresh; the primary app keeps its existing style."""
from mini_app_assets import APP_CSS, APP_HTML, APP_REDESIGN_CSS

CLAUDE_EXTRA_CSS = APP_REDESIGN_CSS
CLAUDE_STYLE = APP_CSS + "\n" + CLAUDE_EXTRA_CSS
CLAUDE_HTML = APP_HTML.replace("/app/style.css", "/app-claude/style.css").replace(
    "<title>SunPark</title>", "<title>SunPark · Клод тест</title>"
).replace("<body>", '<body data-design="refresh-20261120">', 1)
