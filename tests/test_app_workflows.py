import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src')]
from test_mini_app import AppHarness,app_request
from test_menu_preview import signed,FakeResponse


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot=AppHarness();await self.bot.config();self.key=0

    async def call(self,operation,uid=1,**values):
        self.key+=1
        payload={'operation':operation,'init_data':signed(uid),'request_key':f'workflow-{self.key:016d}',**values}
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            r=await self.bot.mini_app_http(app_request(payload))
        return r.status,json.loads(r.body)

    def booking(self,**changes):
        return {'date':'2099-01-01','time':'19:30','guests':'4','name':'Иван','phone':'+79001234567','comment':'У окна',**changes}

    def event(self,**changes):
        return {'title':'Вечер в SUNPARK','description':'','starts_at':'2099-01-01T19:00','location':'SUNPARK','price':'Бесплатно','capacity':'2',**changes}

    async def test_inbox_works_with_actual_legacy_tickets_schema(self):
        columns=await self.bot.db_all('PRAGMA table_info(tickets)')
        self.assertNotIn('created_at',[row.name for row in columns.results])
        status,data=await self.call('screen',screen='tickets',scope='guest')
        self.assertEqual(status,200,data)
        self.assertEqual(data['tickets'],[])
        await self.bot.db_run("INSERT INTO tickets(guest_id,status,claimed_at) VALUES(1,'closed','2026-11-12 12:00:00')")
        status,data=await self.call('screen',screen='tickets',scope='guest')
        self.assertEqual(status,200,data)
        self.assertEqual(data['tickets'][0]['created_at'],'2026-11-12 12:00:00')
        self.assertEqual(data['tickets'][0]['details'],{})
        await self.bot.db_run("INSERT INTO ticket_messages(ticket_number,sender_id,sender_role,body,created_at) VALUES(1,1,'guest','Вопрос','2026-11-11 12:00:00')")
        status,data=await self.call('screen',screen='tickets',scope='staff',filter='all')
        self.assertEqual(status,200,data)
        self.assertEqual(data['tickets'][0]['created_at'],'2026-11-11 12:00:00')

    async def test_app_name_sync_is_idempotent_and_sends_no_messages(self):
        await self.bot.db_run("INSERT INTO config(key,value) VALUES('telegram_app_name_v1','Sunpark')")
        calls=[]
        async def metadata(method,params):
            calls.append((method,params))
            return {'first_name':'SunPark'} if method=='getMe' else True
        self.bot.tg=metadata
        self.assertTrue(await self.bot.sync_app_name())
        self.assertTrue(await self.bot.sync_app_name())
        self.assertEqual([method for method,_ in calls],['setMyName','setMyName','getMe'])
        self.assertTrue(all(params['name']=='SunPark' for method,params in calls if method=='setMyName'))
        self.assertEqual((await self.bot.db_first("SELECT value FROM config WHERE key='telegram_app_name_v1'")).value,'SunPark')
        self.assertEqual(self.bot.notifications,[])

    async def test_whole_booking_and_duplicate_retry(self):
        for _ in range(2):
            status,data=await self.call('submit_form',kind='booking',values=self.booking(),request_key='same-full-booking-12345')
            self.assertEqual(status,200,data)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM tickets')).n,1)
        self.assertEqual((await self.bot.db_first('SELECT status FROM tickets')).status,'waiting')
        self.assertEqual(len(self.bot.notifications),1)
        self.assertIsNone(await self.bot.db_first('SELECT * FROM guest_flows'))
        status,data=await self.call('screen',screen='booking')
        self.assertEqual(data['existing_ticket'],1)
        status,_=await self.call('submit_form',kind='booking',values=self.booking())
        self.assertEqual(status,409)

    async def test_invalid_fields_write_nothing(self):
        status,data=await self.call('submit_form',kind='booking',values=self.booking(date='2000-01-01',phone='+12025550123',time='25:99'))
        self.assertEqual(status,400)
        self.assertEqual(set(data['fields']),{'date','phone','time'})
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM tickets')).n,0)

    async def test_inquiry_and_cancellation_do_not_duplicate_or_close_claimed_ticket(self):
        for _ in range(2):
            status,data=await self.call('submit_form',kind='inquiry',values={'message':'Вопрос <b>о банкете</b>'},request_key='same-inquiry-123456789')
            self.assertEqual(status,200,data)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM tickets')).n,1)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM ticket_messages')).n,1)
        self.assertIn('&lt;b&gt;',self.bot.notifications[0][1])
        status,_=await self.call('command',command='cancel_ticket',ticket=1)
        self.assertEqual(status,200)
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(1,1,'active')")
        status,_=await self.call('command',command='cancel_ticket',ticket=2)
        self.assertEqual(status,409)
        self.assertEqual((await self.bot.db_first('SELECT status FROM tickets WHERE number=2')).status,'active')

    async def test_event_edit_conflict_and_manual_beyond_limit(self):
        status,data=await self.call('submit_form',kind='event_create',scope='staff',values=self.event())
        self.assertEqual(status,200,data);eid=data['event']
        status,_=await self.call('command',command='toggle_event',event=eid,version=0,scope='staff')
        self.assertEqual(status,200)
        person={'first_name':'Иван','last_name':'Иванов','phone':'+79001234567','party_size':'2'}
        status,_=await self.call('submit_form',kind='register',event=eid,scope='guest',values=person)
        self.assertEqual(status,200)
        person.update(phone='+79001234568',party_size='10')
        status,_=await self.call('submit_form',kind='manual',event=eid,scope='staff',values=person)
        self.assertEqual(status,200)
        e=await self.bot.event_get(eid);self.assertEqual(e.self_guests,2);self.assertEqual(e.total_guests,12)
        status,data=await self.call('screen',screen='event_guests',event=eid,scope='staff')
        self.assertEqual(len(data['registrations']),2)
        status,_=await self.call('submit_form',kind='event_edit',event=eid,version=0,scope='staff',values=self.event(title='Изменено'))
        self.assertEqual(status,409)
        status,_=await self.call('submit_form',kind='event_edit',event=eid,version=1,scope='staff',values=self.event(title='Изменено'))
        self.assertEqual(status,200)
        status,_=await self.call('submit_form',kind='manual',event=eid,scope='staff',values=person)
        self.assertEqual(status,409)

    async def test_past_event_can_keep_its_date_when_other_settings_change(self):
        await self.bot.db_run("INSERT INTO events(title,description,starts_at,location,price,capacity,created_by,creation_key) VALUES('Прошедшее','','2000-01-01 16:00:00','SUNPARK','Бесплатно',50,1,'past-fixture')")
        status,data=await self.call('submit_form',kind='event_edit',event=1,version=0,scope='staff',values=self.event(title='Новое название',starts_at='2000-01-01T19:00'))
        self.assertEqual(status,200,data)
        event=await self.bot.event_get(1)
        self.assertEqual(event.starts_at,'2000-01-01 16:00:00')
        self.assertEqual(event.title,'Новое название')

    async def test_cyrillic_search_and_pagination(self):
        for i in range(24):
            await self.bot.db_run("INSERT INTO tickets(guest_id,status) VALUES(?,'waiting')",i+2)
            await self.bot.db_run("INSERT INTO ticket_details(ticket_number,request_type,payload,created_at) VALUES(?,'booking',?,datetime('now'))",i+1,json.dumps({'name':'Ёлкин ИВАН','phone':'+79001234567'},ensure_ascii=False))
        status,data=await self.call('screen',screen='tickets',scope='staff',filter='search',query='ёлкин иван')
        self.assertEqual(status,200,data);self.assertEqual(len(data['tickets']),20);self.assertTrue(data['more'])
        status,next_page=await self.call('screen',screen='tickets',scope='staff',filter='search',query='ЁЛКИН',page=1)
        self.assertEqual(status,200,next_page);self.assertEqual(len(next_page['tickets']),4);self.assertFalse(next_page['more'])

    async def test_note_and_chat_history_pagination(self):
        await self.bot.db_run("INSERT INTO tickets(guest_id,manager_id,status) VALUES(2,1,'active')")
        status,_=await self.call('submit_form',kind='note',ticket=1,scope='staff',values={'note':'Стол у окна'})
        self.assertEqual(status,200)
        for i in range(105):await self.bot.save_ticket_message(1,2,'guest',str(i))
        status,data=await self.call('chat',ticket=1,scope='staff')
        self.assertEqual(status,200);self.assertEqual(len(data['messages']),100);self.assertTrue(data['has_more'])
        status,older=await self.call('chat',ticket=1,scope='staff',before=data['messages'][0]['id'])
        self.assertEqual(status,200);self.assertEqual(len(older['messages']),5);self.assertFalse(older['has_more'])

    async def test_new_routes_enforce_privileges(self):
        with patch('mini_app.MINIAPP_ADMIN_ONLY',False):
            for screen in ['dashboard','managers','event_create']:
                status,_=await self.call('screen',uid=2,screen=screen,scope='guest')
                self.assertEqual(status,403)
            status,_=await self.call('submit_form',uid=2,kind='event_create',values=self.event())
            self.assertEqual(status,403)
            status,_=await self.call('command',uid=2,command='remove_manager',manager=1)
            self.assertEqual(status,403)

    async def test_manager_forms_and_fixed_admin(self):
        await self.bot.db_run("INSERT INTO users(user_id,username,first_name,last_name,updated_at) VALUES(2,'manager_two','Имя','','now')")
        status,_=await self.call('submit_form',kind='manager_add',scope='staff',values={'username':'@manager_two','name':'Алексей'})
        self.assertEqual(status,200)
        status,data=await self.call('screen',screen='managers',scope='staff')
        self.assertEqual(len(data['managers']),2)
        status,_=await self.call('submit_form',kind='manager_edit',scope='staff',manager=2,values={'name':'Александр'})
        self.assertEqual(status,200)
        status,_=await self.call('command',command='remove_manager',manager=1,scope='staff')
        self.assertEqual(status,409)
        status,_=await self.call('command',command='remove_manager',manager=2,scope='staff')
        self.assertEqual(status,200)


if __name__=='__main__':unittest.main()
