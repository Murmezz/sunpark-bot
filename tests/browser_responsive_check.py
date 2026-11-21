"""Phone layout regression against local real APIs and isolated fixture data."""
import asyncio
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from playwright.async_api import async_playwright
import serve_mini_app as fixture
from browser_services_check import telegram_mock
from browser_menu_chrome_check import check_scroll_edges, scroll_content
from test_app_bookings import BookingHarness, BookingTests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'responsive'
PHOTOS=Path('/workspace/sites/sunpark-design-review/public/assets')
PROFILES=[
    (280,653,24,48,0,0), (320,568,20,48,0,0), (360,800,24,56,24,0),
    (375,667,20,48,0,0), (390,844,47,56,34,0), (393,853,32,56,16,0),
    (412,915,32,56,24,0), (430,932,59,56,34,0), (540,720,24,56,24,0),
    (568,320,0,48,0,0), (844,390,0,48,21,47), (768,1024,24,56,20,0),
    (820,1180,24,56,20,0), (1024,768,24,56,20,0),
]


async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bot=fixture.bot=BookingHarness();await bot.seed()
    case=BookingTests();case.bot=bot;case.cfg=(await bot.config())[3]
    preorder=(await case.checkout(case.preorder()))['order'];await case.pay(preorder)
    bot.db.execute("INSERT INTO tickets(number,guest_id,manager_id,status) VALUES(91,1,1,'active')")
    await bot.save_ticket_message(91,1,'guest','Проверка длинного сообщения на маленьком экране. '*12)
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    engine=os.environ.get('SUNPARK_BROWSER','chromium');results=[]
    async with async_playwright() as p:
        browser=await (p.webkit.launch(headless=True) if engine=='webkit' else p.chromium.launch(executable_path='/usr/bin/chromium',headless=True))
        async def photos(route):
            url=unquote(route.request.url)
            name='hotel.png' if 'IMG_' in url or 'hotel' in url else 'wake.jpg' if 'wake' in url else 'wave.jpg' if 'Wave' in url else 'restaurant.jpg'
            await route.fulfill(body=(PHOTOS/name).read_bytes(),content_type='image/png' if name.endswith('.png') else 'image/jpeg')
        for width,height,device,content,bottom,side in PROFILES:
            if os.environ.get('SUNPARK_WIDTHS') and str(width) not in os.environ['SUNPARK_WIDTHS'].split(','):continue
            context=await browser.new_context(viewport={'width':width,'height':height},is_mobile=True,has_touch=True,device_scale_factor=2)
            page=await context.new_page();page.set_default_timeout(12000)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            insets={'device':{'top':device,'bottom':bottom,'left':side,'right':side},'content':{'top':content,'bottom':0,'left':0,'right':0}}
            mock=telegram_mock()+"\nconst insets="+json.dumps(insets)+";sdk.safeAreaInset=insets.device;sdk.contentSafeAreaInset=insets.content;"
            # SDK-property-only mode also checks clients that omit the CSS inset variables.
            if width!=393:
                mock+="\nfor(const [family,values] of [['safe',insets.device],['content-safe',insets.content]])for(const [edge,value] of Object.entries(values))document.documentElement.style.setProperty('--tg-'+family+'-area-inset-'+edge,value+'px');"
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=mock))
            await page.route('https://sunparkspb.ru/**',photos)
            entry=os.environ.get('SUNPARK_ENTRY','/app')
            await page.goto(origin+entry);await page.locator('#app-shell').wait_for(state='visible');await page.evaluate('document.fonts.ready')
            refined=entry=='/app-claude'
            if refined:assert await page.evaluate("document.fonts.check('600 16px \"Golos Text\"','Бронирование')")
            await page.locator('[id^=tg-mock]').evaluate_all("xs=>xs.forEach(e=>e.style.display='none')")
            states=[]

            async def check(name,screenshot=False):
                await page.wait_for_timeout(30)
                metrics=await page.evaluate('''()=>{
                  const modal=document.querySelector('dialog[open]'),root=modal||document.querySelector('#app-shell');
                  const bad=[...root.querySelectorAll('*')].filter(e=>{
                    if(e.matches('.complex-leaf')||e.closest('.category-rail,.service-photos')||e.closest('[hidden]'))return false;
                    const r=e.getBoundingClientRect();return r.width&&r.height&&r.bottom>0&&r.top<innerHeight&&(r.left<-.5||r.right>innerWidth+.5);
                  }).slice(0,8).map(e=>({tag:e.tagName,id:e.id,cls:e.className,rect:e.getBoundingClientRect().toJSON()}));
                  return {width:innerWidth,scroll:document.documentElement.scrollWidth,bad};
                }''')
                assert metrics['scroll']<=metrics['width'] and not metrics['bad'],(engine,width,height,name,metrics)
                if refined and not await page.locator('dialog[open]').count() and not await page.locator('body').evaluate("e=>e.classList.contains('is-keyboard-open')"):
                    docks=page.locator('#concept-view:not([hidden]) .refined-dock,#cart-view:not([hidden]) .cart-actions:not([hidden])')
                    if await docks.count():
                        dock=await docks.first.bounding_box();nav=await page.locator('#app-nav').bounding_box()
                        assert dock['y']>=device+content-1 and dock['y']+dock['height']<=nav['y']+1,(width,height,name,dock,nav)
                        action=docks.first.locator('.primary-button').first
                        assert await action.evaluate("e=>{const r=e.getBoundingClientRect();return r.height>=44&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')===e;}"),(width,height,name,'primary action obscured')
                states.append(name)
                if refined and width==393 and name in ('home-dark','wave','hotel-dates','arrival','qr','chat'):
                    await check_scroll_edges(page.locator('#app-shell > section:not([hidden])'))
                if screenshot:
                    await page.screenshot(path=str(OUT/f'{engine}-{name}-{width}x{height}.png'))

            for theme in ['light','dark']:
                await page.emulate_media(color_scheme=theme);await page.wait_for_timeout(140)
                await check('home-'+theme,width in (320,393,844))
            shell=await page.locator('#app-shell').bounding_box();grid=await page.locator('#home-services').bounding_box()
            gutter=grid['x']-side
            assert 11.5<=gutter<=18.5 if width<=960 else gutter>=18,(width,gutter)
            heading=await page.locator('.complex-intro h1').bounding_box()
            assert heading['y']>=device+content,(width,heading)
            leaf=await page.locator('.complex-leaf').bounding_box()
            subtitle=await page.locator('.complex-intro p').bounding_box()
            assert leaf['x']>=max(heading['x']+heading['width'],subtitle['x']+subtitle['width'])+7,(width,heading,subtitle,leaf)
            # The original asset's straight right edge must be offscreen, with
            # its natural portrait ratio and no contained-image letterboxing.
            assert width+9<=leaf['x']+leaf['width']<=width+11 and leaf['y']>=device+content,(width,leaf)
            assert abs(leaf['width']/leaf['height']-2/3)<.01,(width,leaf)
            decoration=await page.locator('.complex-decoration').bounding_box()
            assert abs(decoration['x'])<1 and abs(decoration['width']-width)<1,(width,decoration)
            assert leaf['y']>=decoration['y']-.5 and leaf['y']+leaf['height']<=decoration['y']+decoration['height']+.5,(width,leaf,decoration)
            assert await page.locator('.complex-decoration').evaluate("e=>getComputedStyle(e).overflowX==='hidden'"),(width,'decoration clipping')
            assert await page.locator('body').evaluate("e=>getComputedStyle(e).overflowX==='hidden'"),(width,'viewport clipping')
            await scroll_content(page, 100000)
            footer=await page.locator('#home-location').bounding_box();nav=await page.locator('#app-nav').bounding_box()
            assert footer['y']+footer['height']<=nav['y']+1,(width,height,footer,nav)
            await scroll_content(page, 0)
            await page.locator('[data-service=wave]').click();await page.get_by_role('heading',name='Волна',exact=True).wait_for();await check('wave')
            await page.get_by_role('button',name='Выбрать дату',exact=True).click();await page.get_by_role('heading',name='Дата и время',exact=True).wait_for();await check('time')
            await page.locator('.date-control').click();await page.locator('#picker-dialog').wait_for(state='visible');await page.wait_for_timeout(160);await check('calendar')
            calendar=await page.locator('#picker-dialog').bounding_box()
            assert calendar['y']>=device+content-1 and calendar['y']+calendar['height']<=height+1,(width,height,calendar)
            await page.keyboard.press('Escape')
            await page.get_by_role('button',name='Далее · контакты',exact=True).click();await page.get_by_role('heading',name='Ваши контакты',exact=True).wait_for();await check('contacts')
            if width in (320,393,430):
                await page.get_by_label('Телефон',exact=True).focus()
                await page.set_viewport_size({'width':width,'height':max(270,height-320)})
                await page.wait_for_function("()=>document.body.classList.contains('is-keyboard-open')")
                assert await page.locator('#app-nav').is_hidden()
                await page.get_by_label('Телефон',exact=True).scroll_into_view_if_needed();await check('keyboard')
                await page.set_viewport_size({'width':width,'height':height});await page.get_by_label('Телефон',exact=True).blur()
                await page.wait_for_function("()=>!document.body.classList.contains('is-keyboard-open')")
            if width==393:
                await page.evaluate("()=>{const sdk=window.Telegram.WebApp;sdk.safeAreaInset={top:0,bottom:21,left:47,right:47};sdk.contentSafeAreaInset={top:48,bottom:0,left:0,right:0};window.__chromeEmit('safeAreaChanged');}")
                await page.set_viewport_size({'width':844,'height':390});await check('rotated-contacts',True)
                await page.evaluate("()=>{const sdk=window.Telegram.WebApp;sdk.safeAreaInset=insets.device;sdk.contentSafeAreaInset=insets.content;window.__chromeEmit('safeAreaChanged');}")
                await page.set_viewport_size({'width':width,'height':height});await check('portrait-again')
            await page.locator('#app-nav [data-view=home]').click();await page.locator('[data-service=hotel]').click();await page.get_by_role('heading',name='Отель',exact=True).wait_for()
            await page.get_by_role('button',name='Выбрать даты',exact=True).click();await page.get_by_role('heading',name='Даты и гости',exact=True).wait_for();await check('hotel-dates')
            await page.locator('#app-nav [data-view=home]').click();await page.locator('[data-service=restaurant]').click();await page.locator('#restaurant-menu').click();await check('menu')
            initial_price=await page.locator('.item-row > .price').first.bounding_box() if refined else None
            initial_row=await page.locator('.item-row').first.bounding_box()
            await page.locator('.item-add').first.click()
            if await page.locator('#dish-dialog').is_visible():
                if await page.locator('#dish-add').is_disabled():await page.locator('#dish-option-list input').first.check()
                await page.locator('#dish-add').click()
            if refined:
                price=await page.locator('.item-row > .price').first.bounding_box();row=await page.locator('.item-row').first.bounding_box()
                assert abs((price['x']-row['x'])-(initial_price['x']-initial_row['x']))<1 and abs((price['y']-row['y'])-(initial_price['y']-initial_row['y']))<1 and abs(row['height']-initial_row['height'])<1,(width,height,'menu moved after add',initial_price,price,initial_row,row)
            launcher=await page.locator('#cart-launcher').bounding_box();nav=await page.locator('#app-nav').bounding_box()
            assert launcher['y']+launcher['height']<=nav['y'],(width,height,launcher,nav)
            await page.locator('#cart-launcher').click();await check('cart')
            await page.locator('#preorder-checkout').click();await page.get_by_role('heading',name='Когда вас ждать?',exact=True).wait_for();await check('arrival')
            await page.locator('#app-nav [data-view=plans]').click();await page.locator('.concept-order').first.click()
            await page.get_by_role('button',name='Показать QR официанту',exact=True).click();await page.locator('.concept-qr img').wait_for();await check('qr')
            await page.locator('#app-nav [data-view=inbox]').click();await page.locator('.request-row').first.click();await page.locator('#chat-input').wait_for();await check('chat')
            chat=await page.locator('.chat-heading').bounding_box()
            assert chat['y']>=device+content,(width,height,chat)
            assert await page.locator('#chat-send').evaluate("e=>e.getBoundingClientRect().bottom<=(document.getElementById('app-nav').getClientRects().length?document.getElementById('app-nav').getBoundingClientRect().top:innerHeight)+1")
            assert not errors,(width,height,errors)
            results.append({'viewport':[width,height],'safe':[device,content,bottom,side],'gutter':round(gutter,2),'leaf_cut_edge':round(leaf['x']+leaf['width'],2),'states':states,'errors':errors})
            print(json.dumps({'engine':engine,'viewport':[width,height],'states':len(states),'passed':True}),flush=True)
            await context.close()
        await browser.close()
    server.shutdown();(OUT/(engine+('-refresh' if os.environ.get('SUNPARK_ENTRY')=='/app-claude' else '')+('-rotation' if os.environ.get('SUNPARK_WIDTHS') else '')+'-results.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':asyncio.run(main())
