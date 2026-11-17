"""Booking/payment/seating contracts against SQLite. No live Telegram calls."""
import json
import sys
import time
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch

from test_mini_app import AppHarness, ROOT, app_request
from test_menu_preview import MENU, SECTIONS, signed, FakeResponse
from app_bookings import compact, date_value
from app_workflows import WorkflowError
from events import MSK
from menu_preview import preview_catalog


class BookingHarness(AppHarness):
    def __init__(self):
        super().__init__()
        self.db.execute('PRAGMA foreign_keys=ON')
        for migration in sorted((ROOT/'migrations').glob('*.sql')):
            self.db.executescript(migration.read_text())
        self.env.PAYMENT_PROVIDER_TOKEN = 'fixture-provider'
        self.invoices = []

    async def tg(self, method, params):
        if method == 'createInvoiceLink':
            self.invoices.append(params)
            return 'https://t.me/$fixture-invoice'
        return await super().tg(method, params)

    async def seed(self):
        await self.config()
        self.day = datetime.now(MSK).date() + timedelta(days=2)
        self.start = int(date_value(str(self.day)+'T14:00', True).timestamp())
        self.db.execute("INSERT INTO miniapp_v2_slots VALUES('slot','wave','wave-group-30','wave-main','[\"wave-main\"]',?,?,2,1)", (self.start, self.start+1800))
        self.db.execute("INSERT INTO miniapp_v2_resources VALUES('room','hotel','Тестовый номер','room','hotel-standard',3,1)")
        self.db.execute("INSERT INTO miniapp_v2_tables VALUES('table','Тестовый стол',4,'Тест',1)")
        self.db.executemany("INSERT INTO miniapp_v2_staff VALUES(?,?,'waiter',1)", [(2,'Официант 2'),(3,'Официант 3')])


class BookingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot=BookingHarness()
        await self.bot.seed()
        self.cfg=(await self.bot.config())[3]
        self.seq=0

    def wave(self, **values):
        return dict(service='wave',slot='slot',guests=1,name='Иван',phone='+79001234567',**values)

    def hotel(self, **values):
        return {**dict(service='hotel',room='room',guests=2,children=[],arrival=str(self.bot.day),departure=str(self.bot.day+timedelta(days=2)),name='Иван',phone='+79001234567'),**values}

    def preorder(self):
        product=next(item for c in preview_catalog(MENU,SECTIONS)['categories'] for item in c['items'] if any(type(o.get('amount')) is int and o['amount']>0 for o in item['options']))
        option=next(o for o in product['options'] if type(o.get('amount')) is int and o['amount']>0)
        return dict(service='restaurant',guests=2,name='Иван',phone='+79001234567',arrival=str(self.bot.day)+'T18:00',items=[{'itemId':product['id'],'optionId':option['id'],'quantity':2}])

    async def write(self,action,uid=1,**data):
        return await self.bot.booking_write({'id':uid},{'action':action,**data},MENU,SECTIONS,self.cfg)

    async def read(self,action,uid=1,**data):
        return await self.bot.booking_read({'id':uid},{'action':action,**data},MENU,SECTIONS,self.cfg)

    async def checkout(self,values=None,uid=1):
        return await self.write('checkout',uid,values=values or self.wave())

    async def pay(self,order,uid=1,**changes):
        row=await self.bot.db_first('SELECT * FROM miniapp_v2_orders WHERE id=?',order)
        payment={'invoice_payload':'sunpark-order:'+order,'total_amount':row.amount,'currency':'RUB','telegram_payment_charge_id':'charge-'+order,'provider_payment_charge_id':'provider-'+order,**changes}
        return await self.bot.booking_payment_update({'message':{'from':{'id':uid},'successful_payment':payment}})

    async def paid_preorder(self):
        result=await self.checkout(self.preorder())
        await self.pay(result['order'])
        # Seating is on the guest's arrival day; local fixture only.
        start=int(datetime.now(MSK).replace(hour=18,minute=0,second=0).timestamp())
        self.bot.db.execute('UPDATE miniapp_v2_orders SET starts_at=?,ends_at=? WHERE id=?',(start,start+60,result['order']))
        return result['order'],self.bot.booking_qr(result['order'])

    async def assert_error(self, status, coro):
        with self.assertRaises(WorkflowError) as caught:
            await coro
        self.assertEqual(caught.exception.status,status,str(caught.exception))

    async def test_empty_inventory_is_not_synthesized(self):
        self.bot.db.execute('DELETE FROM miniapp_v2_slots')
        result=await self.read('availability',service='wave',month=str(self.bot.day)[:7])
        self.assertTrue(result['rates'])
        self.assertEqual(result['slots'],[])

    async def test_provider_missing_never_creates_hold(self):
        self.bot.env.PAYMENT_PROVIDER_TOKEN=''
        await self.assert_error(503,self.checkout())
        self.assertEqual(self.bot.db.execute('SELECT COUNT(*) FROM miniapp_v2_orders').fetchone()[0],0)
        self.assertEqual(self.bot.invoices,[])

    async def test_server_price_and_client_tampering(self):
        quote=await self.read('quote',values=self.wave())
        self.assertEqual(quote['amount'],220000)
        await self.assert_error(409,self.checkout(self.wave(expected_amount=1)))
        self.assertEqual(len(self.bot.invoices),0)

    async def test_last_group_seat_and_expiry(self):
        first=await self.checkout()
        await self.checkout(uid=4)
        await self.assert_error(409,self.checkout(uid=5))
        self.bot.db.execute('UPDATE miniapp_v2_orders SET hold_until=? WHERE id=?',(int(time.time())-1,first['order']))
        third=await self.checkout(uid=5)
        self.assertTrue(third['order'])

    async def test_concurrent_insert_guard_after_stale_quote(self):
        # Both prepare calls see the same final seat; the authoritative SQL insert decides.
        self.bot.db.execute('UPDATE miniapp_v2_slots SET capacity=1')
        original=self.bot.booking_prepare
        stale=await original(self.wave(),1,MENU,SECTIONS,int(time.time()))
        await self.checkout(uid=4)
        async def cached(*args): return stale
        self.bot.booking_prepare=cached
        await self.assert_error(409,self.checkout())
        self.assertEqual(len(self.bot.invoices),1)

    async def test_checkout_failure_releases_capacity(self):
        original=self.bot.tg
        async def failed(method,params):
            if method=='createInvoiceLink':raise RuntimeError('offline')
            return await original(method,params)
        self.bot.tg=failed
        await self.assert_error(503,self.checkout())
        self.assertEqual(self.bot.db.execute('SELECT status FROM miniapp_v2_orders').fetchone()[0],'payment_error')
        result=await self.read('availability',service='wave',month=str(self.bot.day)[:7])
        self.assertEqual(result['slots'][0]['remaining'],2)

    async def test_idempotent_api_checkout_and_foreign_order(self):
        payload={'operation':'booking_write','action':'checkout','values':self.wave(),'init_data':signed(),'request_key':'booking-checkout-unique-123'}
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            a=await self.bot.mini_app_http(app_request(payload))
            b=await self.bot.mini_app_http(app_request(payload))
        self.assertEqual(a.status,200,a.body)
        self.assertEqual(json.loads(a.body),json.loads(b.body))
        self.assertEqual(len(self.bot.invoices),1)
        await self.assert_error(404,self.read('order',uid=9,order=json.loads(a.body)['order']))

    async def test_whole_hotel_period_and_adjacent_nights(self):
        await self.checkout(self.hotel())
        await self.assert_error(409,self.checkout(self.hotel(arrival=str(self.bot.day+timedelta(days=1))),uid=4))
        adjacent=self.hotel(arrival=str(self.bot.day+timedelta(days=2)),departure=str(self.bot.day+timedelta(days=3)))
        self.assertTrue((await self.checkout(adjacent,uid=4))['order'])

    async def test_hotel_children_require_published_rule_and_ages(self):
        await self.assert_error(409,self.read('quote',values=self.hotel(children=[7])))
        await self.write('save_rules',values={'children_enabled':True,'child_night_amount':50000})
        quote=await self.read('quote',values=self.hotel(children=[7]))
        self.assertEqual(quote['amount'],1100000)
        await self.assert_error(400,self.read('quote',values=self.hotel(children=[None])))

    async def test_qr_only_after_exact_server_payment_and_repeat(self):
        result=await self.checkout(self.preorder())
        row=(await self.read('order',order=result['order']))['order']
        self.assertNotIn('qr',row)
        await self.pay(result['order'])
        await self.pay(result['order'])
        row=(await self.read('order',order=result['order']))['order']
        self.assertEqual(row['status'],'paid')
        self.assertTrue(row['qr'])
        await self.assert_error(404,self.read('qr',uid=2,token=row['qr'][:-1]+'x'))

    async def test_wrong_payment_amount_is_review_without_qr(self):
        result=await self.checkout(self.preorder())
        await self.pay(result['order'],total_amount=1)
        row=(await self.read('order',order=result['order']))['order']
        self.assertEqual(row['status'],'payment_review')
        self.assertNotIn('qr',row)

    async def test_precheckout_validates_owner_amount_and_deadline(self):
        order=(await self.checkout())['order']
        q={'id':'precheck','from':{'id':1},'invoice_payload':'sunpark-order:'+order,'total_amount':220000,'currency':'RUB'}
        await self.bot.booking_payment_update({'pre_checkout_query':q})
        self.assertTrue(self.bot.notifications[-1][1]['ok'])
        await self.bot.booking_payment_update({'pre_checkout_query':{**q,'from':{'id':8}}})
        self.assertFalse(self.bot.notifications[-1][1]['ok'])
        self.bot.db.execute('UPDATE miniapp_v2_orders SET hold_until=0')
        await self.bot.booking_payment_update({'pre_checkout_query':q})
        self.assertFalse(self.bot.notifications[-1][1]['ok'])

    async def test_late_payment_cannot_overbook_or_reuse_charge(self):
        self.bot.db.execute('UPDATE miniapp_v2_slots SET capacity=1')
        first=(await self.checkout())['order']
        self.bot.db.execute('UPDATE miniapp_v2_orders SET hold_until=0')
        second=(await self.checkout(uid=4))['order']
        await self.pay(second,uid=4)
        await self.pay(first)
        self.assertEqual((await self.read('order',order=first))['order']['status'],'payment_review')
        # A charge attached to one order cannot settle another.
        p=(await self.checkout(self.preorder()))['order']
        await self.pay(p,telegram_payment_charge_id='charge-'+second)
        self.assertEqual((await self.read('order',order=p))['order']['status'],'checkout')

    async def test_scanner_permissions_repeat_and_waiter_transfer(self):
        order,token=await self.paid_preorder()
        await self.assert_error(403,self.read('qr',uid=8,token=token))
        scanned=await self.read('qr',uid=2,token=token)
        self.assertNotIn('phone',scanned['order'])
        first=await self.write('assign_table',uid=2,token=token,table='table')
        repeat=await self.write('assign_table',uid=2,token=token,table='table')
        self.assertTrue(repeat['repeated'])
        await self.assert_error(409,self.write('assign_table',uid=3,token=token,table='table'))
        await self.assert_error(403,self.write('transfer_table',uid=2,values={'order':order,'previous_waiter':2,'waiter_id':3}))
        await self.write('transfer_table',values={'order':order,'previous_waiter':2,'waiter_id':3})
        await self.assert_error(409,self.write('transfer_table',values={'order':order,'previous_waiter':2,'waiter_id':3}))
        self.assertEqual(self.bot.db.execute('SELECT COUNT(*) FROM miniapp_v2_assignment_events').fetchone()[0],2)
        await self.assert_error(404,self.read('order',uid=2,order=order))
        await self.write('complete_table',uid=3,values={'order':order})
        self.assertEqual(self.bot.db.execute('SELECT active FROM miniapp_v2_assignments').fetchone()[0],0)
        self.assertNotIn('qr',(await self.read('order',order=order))['order'])

    async def test_table_exclusive_and_capacity(self):
        order,token=await self.paid_preorder()
        self.bot.db.execute("INSERT INTO miniapp_v2_tables VALUES('small','Маленький',1,'Тест',1)")
        await self.assert_error(409,self.write('assign_table',uid=2,token=token,table='small'))
        await self.write('assign_table',uid=2,token=token,table='table')
        second,token2=await self.paid_preorder()
        await self.assert_error(409,self.write('assign_table',uid=3,token=token2,table='table'))
        await self.assert_error(409,self.write('save_table',values={'id':'table','name':'Тестовый стол','seats':1,'active':True}))
        await self.assert_error(409,self.write('save_staff',values={'user_id':2,'name':'Официант','role':'waiter','active':False}))

    async def test_addon_stock_is_atomic_and_transfer_preserves_original(self):
        self.bot.db.execute("INSERT INTO miniapp_v2_addons VALUES('kit','wave','Тестовое снаряжение',10000,1,1)")
        self.bot.db.execute("INSERT INTO miniapp_v2_slots SELECT 'target',service,rate_id,resource_id,resources,starts_at+3600,ends_at+3600,capacity,active FROM miniapp_v2_slots WHERE id='slot'")
        first=(await self.checkout(self.wave(addons=['kit'])))['order']
        await self.assert_error(409,self.checkout(self.wave(addons=['kit']),uid=4))
        await self.pay(first)
        await self.checkout({**self.wave(addons=['kit']),'slot':'target'},uid=4)
        await self.assert_error(409,self.write('transfer',values={'order':first,'expected_start':self.bot.start,'slot':'target'}))
        self.assertEqual((await self.read('order',order=first))['order']['slot_id'],'slot')
        with self.assertRaisesRegex(Exception,'BOOKED_CAPACITY'):
            self.bot.db.execute("UPDATE miniapp_v2_addons SET capacity=0 WHERE id='kit'")

    async def test_transfer_success_and_stale_request(self):
        self.bot.db.execute("INSERT INTO miniapp_v2_slots SELECT 'target',service,rate_id,resource_id,resources,starts_at+3600,ends_at+3600,capacity,active FROM miniapp_v2_slots WHERE id='slot'")
        order=(await self.checkout())['order']
        await self.pay(order)
        result=await self.write('transfer',values={'order':order,'expected_start':self.bot.start,'slot':'target'})
        self.assertEqual(result['order']['slot_id'],'target')
        await self.assert_error(409,self.write('transfer',values={'order':order,'expected_start':self.bot.start,'slot':'slot'}))
        await self.assert_error(404,self.write('cancel',values={'order':order}))

    async def test_guest_transfer_disabled_by_default(self):
        order=(await self.checkout(uid=4))['order']
        await self.pay(order,uid=4)
        await self.assert_error(409,self.write('transfer',uid=4,values={'order':order,'expected_start':self.bot.start,'slot':'slot'}))

    async def test_occupied_resource_block_and_capacity_guards(self):
        await self.checkout()
        await self.assert_error(409,self.write('block',values={'resource_id':'wave-main','start':str(self.bot.day)+'T13:00','end':str(self.bot.day)+'T15:00'}))
        with self.assertRaisesRegex(Exception,'RESOURCE_OVERLAP'):
            self.bot.db.execute("INSERT INTO miniapp_v2_slots SELECT 'overlap',service,rate_id,resource_id,resources,starts_at,ends_at,capacity,active FROM miniapp_v2_slots WHERE id='slot'")
        await self.checkout(uid=4)
        with self.assertRaisesRegex(Exception,'BOOKED_CAPACITY'):
            self.bot.db.execute('UPDATE miniapp_v2_slots SET capacity=1')

    async def test_real_menu_stoplist_is_enforced(self):
        values=self.preorder()
        await self.write('menu_status',values={'item_id':values['items'][0]['itemId'],'available':False})
        await self.assert_error(409,self.read('quote',values=values))

    async def test_closed_sales_honors_existing_payment_hold(self):
        order=(await self.checkout())['order']
        self.bot.db.execute('UPDATE miniapp_v2_slots SET active=0')
        await self.assert_error(409,self.checkout(uid=4))
        await self.pay(order)
        self.assertEqual((await self.read('order',order=order))['order']['status'],'paid')

    async def test_inactive_catalog_can_be_reopened_and_calendar_edits_keep_ids(self):
        self.bot.db.execute("UPDATE miniapp_v2_rates SET active=0 WHERE id='wave-private-15'")
        inventory=await self.read('inventory')
        self.assertIn('wave-private-15',[r['id'] for r in inventory['rates']])
        self.assertNotIn('wave-private-15',[r['id'] for r in (await self.read('availability',service='wave',month=str(self.bot.day)[:7]))['rates']])
        slot=(await self.read('calendar',service='wave',date=str(self.bot.day)))['slots'][0]
        self.assertEqual(slot['rate_id'],'wave-group-30')
        self.assertEqual(json.loads(slot['resources']),['wave-main'])
        await self.write('block',values={'resource_id':'wave-main','start':str(self.bot.day)+'T17:00','end':str(self.bot.day)+'T18:00'})
        block=(await self.read('inventory'))['blocks'][0]
        await self.write('unblock',values={'id':block['id']})
        self.assertEqual((await self.read('inventory'))['blocks'],[])

    async def test_dependency_deactivated_after_quote_cannot_sell_stale_slot(self):
        self.bot.db.execute("INSERT INTO miniapp_v2_resources VALUES('trainer','wave','Тренер','trainer','',1,1)")
        self.bot.db.execute("UPDATE miniapp_v2_slots SET resources='[\"wave-main\",\"trainer\"]'")
        stale=await self.bot.booking_prepare(self.wave(),1,MENU,SECTIONS,int(time.time()))
        self.bot.db.execute("UPDATE miniapp_v2_resources SET active=0 WHERE id='trainer'")
        async def cached(*args):return stale
        self.bot.booking_prepare=cached
        await self.assert_error(409,self.checkout())

    async def test_development_access_gate_also_covers_new_booking_api(self):
        payload={'operation':'booking_read','action':'availability','service':'wave','init_data':signed(4)}
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            response=await self.bot.mini_app_http(app_request(payload))
        self.assertEqual(response.status,403)

    async def test_legacy_shell_keeps_original_navigation_and_no_token(self):
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            old=await self.bot.mini_app_http(app_request(path='/app/legacy',method='GET'))
            new=await self.bot.mini_app_http(app_request(path='/app',method='GET'))
        self.assertEqual(old.status,200)
        self.assertIn('/app/legacy/app.js',old.body)
        self.assertNotIn('data-view="plans"',old.body)
        self.assertIn('data-view="plans"',new.body)


if __name__=='__main__':unittest.main()
