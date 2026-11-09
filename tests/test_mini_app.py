import ast
import asyncio
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from unittest.mock import AsyncMock
import base64

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from validation import valid_date,valid_time,valid_guests,normalize_phone
from test_menu_preview import MENU,SECTIONS,TOKEN,signed,Body,FakeResponse

tree=ast.parse((ROOT/'src'/'entry.py').read_text())
tree.body=[n for n in tree.body if not(isinstance(n,ast.ImportFrom) and n.module in ('workers','validation'))]
namespace={'WorkerEntrypoint':type('WorkerEntrypoint',(),{}),'valid_date':valid_date,'valid_time':valid_time,'valid_guests':valid_guests,'normalize_phone':normalize_phone}
exec(compile(tree,'entry.py','exec'),namespace)


class AppHarness(namespace['Bot']):
    def __init__(self):
        self.db=sqlite3.connect(':memory:',check_same_thread=False,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.env=NS(BOT_TOKEN=TOKEN,MANAGER_IDS='1')
        self.ctx=NS(waitUntil=lambda task:None)
        self.notifications=[]
        self.db.executescript("CREATE TABLE config(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE tickets(number INTEGER PRIMARY KEY AUTOINCREMENT,guest_id INTEGER NOT NULL,manager_id INTEGER,status TEXT NOT NULL DEFAULT 'waiting',created_at TEXT DEFAULT (datetime('now')),claimed_at TEXT,closed_at TEXT);")
        self.db.executemany('INSERT INTO config VALUES(?,?)',[
            ('menu',json.dumps({'MENU':MENU,'MENU_SECTIONS':SECTIONS,'INFO_TEXT':'Правила SUNPARK'},ensure_ascii=False)),('manager_ids','1'),('manager_names','{"1":"Менеджер"}')])

    async def db_run(self,sql,*args):
        if any(value is None for value in args):
            raise AssertionError('Python None must not be bound through D1')
        cur=self.db.execute(sql,args)
        return NS(meta=NS(changes=max(0,cur.rowcount)))
    async def db_first(self,sql,*args):
        row=self.db.execute(sql,args).fetchone()
        return NS(**dict(row)) if row else None
    async def db_all(self,sql,*args):
        return NS(results=[NS(**dict(row)) for row in self.db.execute(sql,args)])
    async def send(self,chat_id,text,markup=None):
        self.notifications.append((chat_id,text,markup))
        return {'message_id':1000+len(self.notifications)}
    async def tg(self,method,params):
        self.notifications.append((method,params))
        return {'message_id':1000+len(self.notifications)}


def app_request(payload=None,path='/api/app',method='POST'):
    raw=json.dumps(payload or {}).encode()
    return NS(url='https://example.test'+path,method=method,headers={'content-length':str(len(raw))},body=Body([raw]))


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot=AppHarness()
        await self.bot.config()
        self.sequence=0

    async def call(self,operation,uid=1,**data):
        self.sequence+=1
        payload={'operation':operation,'init_data':signed(uid),'request_key':f'test-request-{self.sequence:010d}',**data}
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            result=await self.bot.mini_app_http(app_request(payload))
        return result.status,json.loads(result.body)

    async def test_bootstrap_and_authorization(self):
        status,data=await self.call('bootstrap')
        self.assertEqual(status,200)
        self.assertTrue(data['admin'])
        self.assertTrue(any(cat['key']=='beer' for cat in data['categories']))
        self.assertNotIn('manager_ids',data)
        status,_=await self.call('bootstrap',uid=2)
        self.assertEqual(status,403)
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            r=await self.bot.mini_app_http(app_request({'operation':'bootstrap','user_id':1}))
            self.assertEqual(r.status,401)
            r=await self.bot.mini_app_http(app_request(path='/app',method='GET'))
            self.assertEqual(r.status,200)
            self.assertNotIn(TOKEN,r.body)
            r=await self.bot.mini_app_http(app_request(path='/api/app',method='GET'))
            self.assertEqual(r.status,405)

    async def test_booking_uses_existing_workflow_and_sends_once(self):
        status,data=await self.call('action',callback='booking:start',scope='guest')
        self.assertEqual(status,200)
        self.assertEqual(data['input']['field'],'date')
        for value in ['01.01.2099','19:30','4','Иван','+79001234567','У окна']:
            status,data=await self.call('message',text=value,scope='guest')
            self.assertEqual(status,200,data)
        row=await self.bot.db_first('SELECT * FROM tickets')
        self.assertEqual(row.status,'waiting')
        detail=await self.bot.db_first('SELECT payload FROM ticket_details WHERE ticket_number=?',row.number)
        self.assertEqual(json.loads(detail.payload)['guests'],'4')
        self.assertIsNone(await self.bot.db_first('SELECT * FROM guest_flows'))
        self.assertEqual(len(self.bot.notifications),1)
        self.assertTrue(self.bot.notifications[0][2]['inline_keyboard'][0][0]['callback_data'].startswith('claim:'))

    async def test_chat_permissions_and_idempotency(self):
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(2,1,'active')")
        status,_=await self.call('chat',ticket=1,scope='guest')
        self.assertEqual(status,404)
        status,data=await self.call('chat',ticket=1,scope='staff')
        self.assertEqual(status,200)
        self.assertTrue(data['ticket']['can_reply'])
        status,data=await self.call('chat_send',ticket=1,scope='staff',text='Ответ <b>гостю</b>',request_key='same-message-123456')
        self.assertEqual(status,200,data)
        status,data=await self.call('chat_send',ticket=1,scope='staff',text='Ответ <b>гостю</b>',request_key='same-message-123456')
        self.assertEqual(status,200,data)
        count=await self.bot.db_first('SELECT COUNT(*) n FROM ticket_messages')
        self.assertEqual(count.n,1)
        self.assertEqual(len(self.bot.notifications),1)
        self.assertIn('&lt;b&gt;',self.bot.notifications[0][1])
        status,_=await self.call('chat_send',ticket=1,scope='staff',text='Другой ответ',request_key='same-message-123456')
        self.assertEqual(status,409)

    async def test_owned_guest_chat_and_readonly_foreign_staff_ticket(self):
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(1,99,'active')")
        status,data=await self.call('chat_send',ticket=1,scope='guest',text='Сообщение менеджеру')
        self.assertEqual(status,200,data)
        self.assertEqual(data['messages'][0]['sender_role'],'guest')
        status,_=await self.call('chat_send',ticket=1,scope='staff',text='Чужая заявка')
        self.assertEqual(status,409)
        status,data=await self.call('tickets',scope='guest')
        self.assertEqual(len(data['tickets']),1)

    async def test_event_flow_available_in_mini_app(self):
        status,data=await self.call('action',callback='ev:create',scope='staff')
        self.assertEqual(status,200,data)
        self.assertEqual(data['input']['field'],'title')
        for value in ['Вечер в SUNPARK','Дегустация','01.01.2099 19:00','SUNPARK','Бесплатно','50']:
            status,data=await self.call('message',text=value,scope='staff')
            self.assertEqual(status,200,data)
        # Creation still requires the existing explicit review/save action.
        session=await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=1')
        self.assertIsNotNone(session)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM events')).n,0)
        text=json.dumps(data,ensure_ascii=False)
        self.assertIn('ev:save:',text)

    async def test_signed_profile_and_event_navigation(self):
        status,_=await self.call('bootstrap')
        self.assertEqual(status,200)
        self.assertIsNotNone(await self.bot.db_first('SELECT user_id FROM users WHERE user_id=1'))
        await self.call('action',callback='ev:create',scope='staff')
        status,data=await self.call('action',callback='admin:search',scope='staff')
        self.assertEqual(status,200)
        self.assertEqual(data['input']['kind'],'staff')
        self.assertIsNone(await self.bot.db_first('SELECT * FROM event_sessions'))
        status,data=await self.call('message',text='unknown',scope='staff')
        self.assertEqual(status,200)
        self.assertIn('Ничего не найдено',json.dumps(data,ensure_ascii=False))

    async def test_attachment_validation_and_ownership(self):
        for encoded in ['invalid###',base64.b64encode(b'<html>fake.pdf').decode()]:
            status,_=await self.call('upload',name='fake.pdf',data=encoded)
            self.assertEqual(status,400)
        await self.bot.app_init()
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(1,1,'active')")
        await self.bot.db_run("INSERT INTO miniapp_uploads(token,user_id,file_id,kind,file_name) VALUES('foreign',2,'private-telegram-id','document','file.pdf')")
        status,_=await self.call('chat_send',ticket=1,scope='guest',upload='foreign')
        self.assertEqual(status,400)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM ticket_messages')).n,0)

    async def test_media_authorization_and_failed_upstream(self):
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(2,1,'active')")
        await self.bot.save_ticket_message(1,2,'guest','ATTACH:'+json.dumps({'file_id':'private','type':'photo'}))
        request={'init_data':signed(),'message_id':1,'scope':'guest'}
        mocked_fetch=AsyncMock(return_value=NS(ok=False))
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse,fetch=mocked_fetch)}):
            r=await self.bot.mini_app_http(app_request(request,path='/api/app/media'))
            self.assertEqual(r.status,404)
            mocked_fetch.assert_not_awaited()
            self.bot.tg=AsyncMock(return_value={'file_path':'photos/test.jpg','file_size':100})
            request['scope']='staff'
            r=await self.bot.mini_app_http(app_request(request,path='/api/app/media'))
            self.assertEqual(r.status,502)
            self.assertNotIn(TOKEN,r.body)

    async def test_notification_failure_keeps_saved_message_idempotent(self):
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(2,1,'active')")
        self.bot.send_ticket_content=AsyncMock(side_effect=RuntimeError('offline'))
        for _ in range(2):
            status,data=await self.call('chat_send',ticket=1,scope='staff',text='Сохранённый ответ',request_key='notification-error-123456')
            self.assertEqual(status,200)
            self.assertIn('warning',data)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM ticket_messages')).n,1)
        self.bot.send_ticket_content.assert_awaited_once()


if __name__=='__main__':
    unittest.main()
