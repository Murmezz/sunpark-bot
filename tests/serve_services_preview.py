"""Local review server with an isolated SQLite fixture and the skill's SDK mock.

Never deploy this server or its test identity with the production Worker.
"""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from serve_mini_app import Handler as BaseHandler
from test_menu_preview import signed

ROOT=Path(__file__).resolve().parents[1]


class Handler(BaseHandler):
    def do_GET(self):
        if self.path=='/review-telegram.js':
            mock=(ROOT/'.agents/skills/telegram-webapps/assets/miniapp-mock.js').read_text()
            mock+='\nwindow.Telegram.WebApp.initData='+json.dumps(signed())+';'
            self.send_response(200)
            self.send_header('content-type','application/javascript')
            self.end_headers()
            self.wfile.write(mock.encode())
            return
        if self.path.rstrip('/')=='/app':
            from mini_app_assets import APP_HTML
            self.send_response(200)
            self.send_header('content-type','text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(APP_HTML.replace('https://telegram.org/js/telegram-web-app.js','/review-telegram.js').encode())
            return
        super().do_GET()


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',4173),Handler).serve_forever()
