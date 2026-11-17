import ast
import hashlib
import hmac
import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from menu_preview import MenuPreviewMixin, preview_catalog, preview_price_options, validate_init_data, read_preview_body

MENU = {
    'snacks': {'title':'Закуски', 'emoji':'🥟', 'items':[
        ['Брускетты с ростбифом','со сливочным сыром и вялеными томатами','740 ₽'],
        ['Брускетты с томлёной свининой','с песто, паприкой и томатами','710 ₽'],
        ['Брускетты с томатами','и песто','690 ₽'],
        ['Брускетты с форелью слабой соли','и крем-чизом','780 ₽'],
        ['Овощные оладьи','из кабачка и моркови','550 ₽'],
        ['Хрустящие ржаные гренки','с чесноком, сыром и зеленью','450 ₽'],
        ['Батат фри','с соусом тартар','510 ₽'],
        ['Тар-тар из тунца','с ломтиками чёрного хлеба','890 ₽'],
        ['Креветки темпура','со сладким васаби','980 ₽'],
        ['Паштет из куриной печени','с чиабаттой и брусничным соусом','710 ₽'],
        ['Сельдь','с маринованным луком, картофелем и хлебом','680 ₽'],
        ['Винная тарелка','','1390 ₽'],
        ['Тарелка свежих овощей и зелени','','850 ₽'],
        ['Пирог с говяжьими щёчками','200 г / 2000 г. Наличие уточните у официанта','510 ₽ / 4600 ₽']]},
    'soups': {'title':'Супы','emoji':'🍲','items':[['Грибной крем-суп капучино','','610 ₽'],['Тыквенный крем-суп','Креветки +260 ₽ / краб +350 ₽','610 ₽'],['Борщ','с чёрным хлебом и домашним смальцем','790 ₽']]},
    'hot_drinks': {'title':'Горячие напитки','emoji':'☕','items':[['Капучино','200 мл','290 ₽']]},
    'beer': {'title':'Пиво и сидр','emoji':'🍺','sections':[['Разливное',[['Амбер Вайс','330 мл / 500 мл','390 ₽ / 490 ₽']]],['Бутылочное',[['Эль Капулько','Алкогольный / безалкогольный','410 ₽ / 350 ₽']]]]},
    'cocktails': {'title':'Коктейльная карта','emoji':'🍸','items':[['Апероль Спритц','Апероль, игристое вино, содовая','790 ₽']]},
    'wine': {'title':'Вино','emoji':'🍷','sections':[['Белое',[['Совиньон Блан','сухое, Чили','450 ₽ / 2800 ₽']]],['Красное',[['Мальбек','сухое, Аргентина','690 ₽ / 4140 ₽']]]], 'footer':'Цена за бокал / бутылку'},
    'strong': {'title':'Крепкий алкоголь','emoji':'🥃','items':[['Водка Царская','40 мл','250 ₽']]},
    'banquet': {'title':'Скрытый раздел','items':[['Не показывать','','0 ₽']]},
}
SECTIONS = [['🍽 ЕДА',['snacks','soups']],['☕ НАПИТКИ',['hot_drinks']],['🍷 АЛКОГОЛЬ',['beer','cocktails','wine','strong','banquet']]]
TOKEN = '12345:test-secret-for-local-tests-only'


def signed(uid=1, when=None, token=TOKEN, extra=None):
    fields = {'auth_date':str(int(time.time()) if when is None else when),'query_id':'test-query','user':json.dumps({'id':uid},separators=(',',':'))}
    fields.update(extra or {})
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(fields)


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.body,self.status,self.headers=body,status,headers or {}


class Body:
    def __init__(self, chunks):
        self.chunks=list(chunks)
        self.cancelled=False
    def getReader(self):
        return self
    async def read(self):
        if not self.chunks:
            return NS(done=True)
        chunk=self.chunks.pop(0)
        return NS(done=False,value=NS(byteLength=len(chunk),to_py=lambda:memoryview(chunk)))
    async def cancel(self):
        self.cancelled=True
    def releaseLock(self):
        pass


def request(path='/api/menu-preview', method='POST', data=None):
    raw=json.dumps(data or {}).encode()
    return NS(url='https://example.test'+path,method=method,headers={'content-length':str(len(raw))},body=Body([raw]))


class PreviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot=MenuPreviewMixin()
        self.bot.env=NS(BOT_TOKEN=TOKEN)
        self.bot.is_manager=AsyncMock(side_effect=lambda uid,cfg:uid==1)
        self.bot.answer=AsyncMock()
        self.bot.edit=AsyncMock()
        self.bot.tg=AsyncMock()
        self.bot.event_clear_session=AsyncMock()
        self.bot.clear_action=AsyncMock()
        self.bot.config=AsyncMock(return_value=(MENU,SECTIONS,'',{'not_for_api':'secret'}))

    def test_telegram_signature_and_id_validation(self):
        self.assertEqual(validate_init_data(signed(),TOKEN),1)
        for raw in ['',signed(token='other'),signed().replace('test-query','changed'),signed(when=int(time.time())-3601),signed(when=int(time.time())+100),signed(uid='1'),signed()+'&user=forged']:
            with self.assertRaises((ValueError,TypeError)):
                validate_init_data(raw,TOKEN)
        # The optional signature participates in Telegram's HMAC data-check-string.
        self.assertEqual(validate_init_data(signed(extra={'signature':'example'}),TOKEN),1)

    def test_catalog_preserves_prices_sections_and_excludes_hidden(self):
        before=json.dumps(MENU)
        catalog=preview_catalog(MENU,SECTIONS)
        wine=next(c for c in catalog['categories'] if c['key']=='wine')
        self.assertEqual(wine['items'][0]['price'],'450 ₽ / 2800 ₽')
        self.assertEqual(wine['items'][1]['section'],'Красное')
        self.assertNotIn('banquet',[c['key'] for c in catalog['categories']])
        self.assertEqual(before,json.dumps(MENU))

    def test_development_has_only_current_mini_app(self):
        text,kb=self.bot.menu_preview_chooser()
        self.assertEqual(kb['inline_keyboard'],[
            [{'text':'Sunpark','web_app':{'url':'https://sunparkbot.lovison1979.workers.dev/app'}}],
            [{'text':'Клод тест','web_app':{'url':'https://sunparkbot.lovison1979.workers.dev/app-claude'}}],
            [{'text':'◀️ В админ-панель','callback_data':'admin:panel'}],
        ])
        self.assertIn('Разработка',text)
        self.assertIn('Доступ только администраторам',text)

    def test_bar_includes_all_four_categories_and_every_position(self):
        catalog=preview_catalog(MENU,SECTIONS)
        bar=next(group for group in catalog['groups'] if 'АЛКОГОЛЬ' in group['title'])
        self.assertEqual(bar['keys'],['beer','cocktails','wine','strong'])
        categories={cat['key']:cat for cat in catalog['categories']}
        for key in bar['keys']:
            source=MENU[key]
            rows=[row for _,items in source['sections'] for row in items] if source.get('sections') else source['items']
            self.assertEqual([(item['name'],item['price']) for item in categories[key]['items']],[(row[0],row[2]) for row in rows])

    def test_cart_prices_and_variant_labels(self):
        cases=[
            ('Пиво','330 мл / 500 мл','390 ₽ / 490 ₽','',['330 мл','500 мл'],[39000,49000]),
            ('Пиво','0,33 / 0,5 л','390 / 490','',['0,33 л','0,5 л'],[39000,49000]),
            ('Эль Капулько / безалкогольный','440 мл','410 ₽ / 350 ₽','',['Алкогольное','Безалкогольное'],[41000,35000]),
            ('Яйцо Бенедикт','с форелью / ростбифом','850 ₽ / 810 ₽','',['С форелью','С ростбифом'],[85000,81000]),
            ('Пирог','200 г / 2000 гр','510 ₽ / 4600 ₽','',['200 г','2000 г'],[51000,460000]),
            ('Совиньон','','450 ₽ / 2800 ₽','Цена за бокал / бутылку',['Бокал','Бутылка'],[45000,280000]),
            ('Другое','','100 ₽ / 200 ₽','',['Вариант 1','Вариант 2'],[10000,20000]),
            ('Дробная цена','','1\u202f234,56 ₽','',[''],[123456]),
        ]
        for name,description,price,footer,labels,amounts in cases:
            with self.subTest(name=name,price=price):
                options=preview_price_options(name,description,price,footer)
                self.assertEqual([o['label'] for o in options],labels)
                self.assertEqual([o['amount'] for o in options],amounts)
        for price in ['от 300 ₽','Уточните у официанта','100 ₽ за 100 г','-100 ₽','100–200 ₽','300 ₽ / уточняется']:
            self.assertIsNone(preview_price_options('Тест','',price)[0]['amount'])

    def test_cart_identity_survives_price_changes_without_stale_prices(self):
        menu=json.loads(json.dumps(MENU))
        before=preview_catalog(menu,SECTIONS)['categories'][0]['items'][0]
        menu['snacks']['items'][0][2]='800 ₽'
        after=preview_catalog(menu,SECTIONS)['categories'][0]['items'][0]
        self.assertEqual(before['id'],after['id'])
        self.assertEqual(after['options'][0]['amount'],80000)
        self.assertEqual(before['options'][0]['amount'],74000)

    async def test_all_native_screens_paginate_without_guest_menu_callbacks(self):
        catalog=preview_catalog(MENU,SECTIONS)
        for variant in (1,2,3):
            root,kb=self.bot.menu_preview_root(variant,catalog)
            self.assertIn('SUNPARK',root)
            for cat in catalog['categories']:
                for page in (0,1,999,-1):
                    plain,rich,kb=self.bot.menu_preview_category(variant,cat,page)
                    self.assertLess(len(plain),4096)
                    if rich:
                        self.assertLess(len(rich),32768)
                    for row in kb['inline_keyboard']:
                        for b in row:
                            self.assertTrue(b['callback_data'].startswith('mp:'))
                            self.assertLessEqual(len(b['callback_data'].encode()),64)
            plain,rich,kb=self.bot.menu_preview_category(variant,catalog['categories'][0],0,1)
            self.assertIn('паприкой',plain)
            if variant==2:
                self.assertIn('<table compact>',rich)
                self.assertIn('<tg-button',rich)
            elif variant==3:
                self.assertIn('<details>',rich)

    async def test_non_admin_and_group_callbacks_blocked(self):
        for uid,kind in [(2,'private'),(1,'group')]:
            cb={'id':'x','from':{'id':uid},'data':'mp:home','message':{'message_id':7,'chat':{'id':uid,'type':kind}}}
            self.assertTrue(await self.bot.menu_preview_callback(cb,MENU,SECTIONS,{}))
        self.bot.edit.assert_not_called()
        self.bot.tg.assert_not_called()
        self.bot.event_clear_session.assert_not_called()

    async def test_admin_current_and_old_buttons_open_development(self):
        for data in ('mp:home','mp:root:1','mp:cat:2:snacks:0','mp:item:3:snacks:0:0'):
            cb={'id':'x','from':{'id':1},'data':data,'message':{'message_id':7,'chat':{'id':1,'type':'private'}}}
            await self.bot.menu_preview_callback(cb,MENU,SECTIONS,{})
            self.assertEqual(self.bot.edit.call_args.args[1:],self.bot.menu_preview_chooser())
        self.bot.tg.assert_not_called()
        cat={'key':'test','title':'<script>','emoji':'','footer':'','items':[{'name':'<b>Тест</b>','price':'10 & 20','description':'<img src=x onerror=1>','section':''}]}
        plain,rich,_=self.bot.menu_preview_category(3,cat,0,0)
        self.assertNotIn('<script>',rich)
        self.assertIn('&lt;img',rich)
        self.assertNotIn('<img src=x',plain)

    async def test_rich_fallback_and_rate_limit(self):
        msg={'message_id':7,'chat':{'id':1}}
        cat=preview_catalog(MENU,SECTIONS)['categories'][0]
        plain,rich,kb=self.bot.menu_preview_category(2,cat)
        self.bot.tg.side_effect=Exception('editMessageText: Bad Request: unsupported rich_message')
        await self.bot.menu_preview_render(msg,plain,kb,rich)
        self.assertIn('совместимый вид',self.bot.edit.call_args.args[1])
        self.bot.edit.reset_mock()
        self.bot.tg.side_effect=Exception('Too Many Requests: retry after 30')
        with self.assertRaises(Exception):
            await self.bot.menu_preview_render(msg,plain,kb,rich)
        self.bot.edit.assert_not_called()
        self.bot.tg.side_effect=Exception('Bad Request: message is not modified')
        await self.bot.menu_preview_render(msg,plain,kb,rich)
        self.bot.edit.assert_not_called()

    async def test_auth_required_for_api_not_static_shell(self):
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            for path in ['/menu-preview','/menu-preview.css','/menu-preview.js','/menu-preview-logo.svg']:
                r=await self.bot.menu_preview_http(request(path,'GET'))
                self.assertEqual(r.status,200)
                self.assertNotIn(TOKEN,r.body)
                self.assertIn('no-store',r.headers['cache-control'])
            r=await self.bot.menu_preview_http(request(data={'user_id':1}))
            self.assertEqual(r.status,401)
            self.bot.config.assert_not_called()
            r=await self.bot.menu_preview_http(request(data={'init_data':signed(2)}))
            self.assertEqual(r.status,403)
            self.assertNotIn('Брускетты',r.body)
            r=await self.bot.menu_preview_http(request(data={'init_data':signed()}))
            self.assertEqual(r.status,200)
            body=json.loads(r.body)
            self.assertEqual(set(body),{'groups','categories'})
            self.assertNotIn('not_for_api',r.body)
            self.assertEqual((await self.bot.menu_preview_http(request(method='GET'))).status,405)
            self.assertIsNone(await self.bot.menu_preview_http(request('/webhook','POST')))

    async def test_bounded_body_reader(self):
        r=request()
        r.headers={}
        r.body=Body([b'a'*10000,b'b'*10001])
        with self.assertRaises(ValueError):
            await read_preview_body(r)
        self.assertTrue(r.body.cancelled)

    def test_entry_integration_admin_only_button(self):
        source=(ROOT/'src'/'entry.py').read_text()
        tree=ast.parse(source)
        tree.body=[n for n in tree.body if not(isinstance(n,ast.ImportFrom) and n.module in ('workers','validation'))]
        ns={'WorkerEntrypoint':type('WorkerEntrypoint',(),{})}
        exec(compile(tree,'entry.py','exec'),ns)
        bot=ns['Bot']()
        self.assertIn({'text':'🛠 Разработка','callback_data':'mp:home'},[b for row in bot.admin_keyboard()['inline_keyboard'] for b in row])
        self.assertFalse(any(b.get('callback_data','').startswith('mp:') for row in bot.home_keyboard(False)['inline_keyboard'] for b in row))
        self.assertFalse(any(b.get('callback_data','').startswith('cart:') for row in bot.main_keyboard(MENU,SECTIONS)['inline_keyboard'] for b in row))
        self.assertLess(source.index('await self.menu_preview_http(request)'),source.index('if method != "POST"'))


if __name__=='__main__':
    unittest.main()


