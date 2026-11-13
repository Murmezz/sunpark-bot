// Optional FFI check: npm install --prefix /tmp/sunpark-runtime-check pyodide
// NODE_PATH=/tmp/sunpark-runtime-check/node_modules node tests/runtime_upload_check.cjs
const {loadPyodide} = require('pyodide');
const fs = require('node:fs');
(async () => {
  const py = await loadPyodide();
  for (const name of ['mini_app','mini_app_auth','app_workflows','events']) py.FS.writeFile('/'+name+'.py', fs.readFileSync('src/'+name+'.py', 'utf8'));
  await py.runPythonAsync(`
import asyncio,sys,types,base64
from types import SimpleNamespace as NS
sys.path.insert(0,'/')
sys.modules['menu_preview']=NS(preview_catalog=None,read_preview_body=None,validate_init_data=None)
sys.modules['mini_app_assets']=NS(APP_HTML='',APP_CSS='',APP_JS='',APP_LOGO='',APP_ICONS={})
requests=[]
async def fetch(url,method,body):
    assert method=='POST'
    assert body.get('chat_id')=='1'
    assert body.get('disable_notification')=='true'
    blob=body.get('document')
    assert blob.type=='application/pdf'
    assert await blob.text()=='%PDF-test-fixture'
    requests.append(url)
    async def json():
        return {'ok':True,'result':{'message_id':25,'document':{'file_id':'fixture-file-id'}}}
    return NS(json=json)
sys.modules['workers']=NS(fetch=fetch)
from mini_app import MiniAppMixin
class Bot(MiniAppMixin):
    env=NS(BOT_TOKEN='fake-token')
    saved=[]
    async def db_run(self,sql,*args): self.saved.append(args)
    async def tg(self,method,params):
        assert method=='deleteMessage' and params=={'chat_id':1,'message_id':25}
bot=Bot()
result=await bot.app_upload(1,{'name':'actual.pdf','data':base64.b64encode(b'%PDF-test-fixture').decode()})
assert len(result['token'])==32
assert result['kind']=='document' and result['name']=='actual.pdf'
assert bot.saved[0][1:]==(1,'fixture-file-id','document','actual.pdf')
assert requests==['https://api.telegram.org/botfake-token/sendDocument']
print('Pyodide / native Blob + FormData / actual upload method: passed (Telegram mocked)')
`);
})().catch(error => { console.error(String(error));process.exitCode=1; });
