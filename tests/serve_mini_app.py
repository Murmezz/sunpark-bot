"""Local authenticated fixture server; never deployed with the Worker."""
import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace as NS
from unittest.mock import patch
from test_mini_app import AppHarness
from test_menu_preview import Body,FakeResponse

bot=AppHarness()
lock=threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def dispatch(self):
        size=int(self.headers.get('Content-Length',0))
        data=self.rfile.read(min(size,8*1024*1024+1))
        request=NS(url='http://terminal.local:4173'+self.path,method=self.command,headers=self.headers,body=Body([data]))
        with lock,patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            result=asyncio.run(bot.mini_app_http(request))
        self.send_response(result.status if result else 404)
        for key,value in (result.headers if result else {}).items():self.send_header(key,value)
        self.end_headers()
        if result:self.wfile.write(result.body.encode() if isinstance(result.body,str) else result.body)
    do_GET=dispatch
    do_POST=dispatch


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',4173),Handler).serve_forever()
