"""Real-request loaders, motion preferences, failures and navigation races."""
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
from test_app_bookings import BookingHarness

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'loading'
PHOTOS=Path('/workspace/sites/sunpark-design-review/public/assets')


async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bot=fixture.bot=BookingHarness();await bot.seed()
    bot.db.execute("INSERT INTO tickets(number,guest_id,manager_id,status) VALUES(91,1,1,'active')")
    await bot.save_ticket_message(91,1,'guest','Сообщение остаётся на месте во время фонового обновления.')
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start();origin=f'http://127.0.0.1:{server.server_port}'
    engine=os.environ.get('SUNPARK_BROWSER','chromium');results=[]
    async with async_playwright() as p:
        browser=await (p.webkit.launch(headless=True) if engine=='webkit' else p.chromium.launch(executable_path='/usr/bin/chromium',headless=True))
        async def photos(route):
            gate=state.get('photo_gate')
            if gate:
                state['photo_started'].set();await gate.wait()
            if state.get('photo_fail'):
                await route.fulfill(status=404,body='missing');return
            url=unquote(route.request.url)
            name='hotel.png' if 'IMG_' in url or 'hotel' in url else 'wake.jpg' if 'wake' in url else 'wave.jpg' if 'Wave' in url else 'restaurant.jpg'
            await route.fulfill(body=(PHOTOS/name).read_bytes(),content_type='image/png' if name.endswith('.png') else 'image/jpeg')
        for width,height,theme,motion in [(280,653,'dark','no-preference'),(393,853,'dark','no-preference'),(393,853,'light','reduce'),(844,390,'dark','no-preference')]:
            context=await browser.new_context(viewport={'width':width,'height':height},is_mobile=True,has_touch=True,color_scheme=theme,reduced_motion=motion)
            page=await context.new_page();page.set_default_timeout(10000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            state={}

            def hold(key):
                state[key+'_gate']=asyncio.Event();state[key+'_started']=asyncio.Event()
                return state[key+'_gate']

            async def pending(key):await asyncio.wait_for(state[key+'_started'].wait(),8)

            async def api_route(route):
                body=route.request.post_data_json
                operation=body.get('operation');key=''
                if operation=='bootstrap':key='boot'
                elif operation=='booking_read' and body.get('action')=='availability':key=body.get('service')
                elif operation=='screen' and body.get('screen')=='info':key='native'
                elif operation=='booking_write' and body.get('action')=='checkout':key='checkout'
                elif operation=='chat':key='chat'
                gate=state.get(key+'_gate')
                if gate:
                    state[key+'_started'].set();await gate.wait()
                if state.get(key+'_fail'):
                    await route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':'Временный сбой для проверки загрузки'}));return
                await route.continue_()

            boot=hold('boot')
            mock=telegram_mock()+"\nwindow.Telegram.WebApp.safeAreaInset={top:"+str(0 if width>700 else 32)+",bottom:16,left:0,right:0};window.Telegram.WebApp.contentSafeAreaInset={top:56,bottom:0,left:0,right:0};const realInterval=window.setInterval;window.setInterval=(fn,ms)=>realInterval(fn,ms===6000?450:ms);"
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=mock))
            await page.route('https://sunparkspb.ru/**',photos);await page.route('**/api/app',api_route)
            await page.goto(origin+'/app',wait_until='domcontentloaded');await pending('boot')
            assert await page.locator('#status .boot-loader').is_visible()
            assert await page.locator('#app-shell').is_hidden()
            assert await page.locator('#status').get_attribute('aria-busy')=='true'
            await page.locator('[id^=tg-mock]').evaluate_all("xs=>xs.forEach(e=>e.style.display='none')")
            names=await page.locator('#status').evaluate("e=>e.getAnimations({subtree:true}).filter(a=>a.playState==='running').length")
            assert (names==0) if motion=='reduce' else names>0,(motion,names)
            await page.screenshot(path=str(OUT/f'{engine}-boot-{theme}-{width}.png'),scale='css')
            photo=hold('photo');boot.set();await page.locator('#app-shell').wait_for(state='visible');await page.locator('#status').wait_for(state='hidden');await pending('photo')
            assert await page.locator('#home-services img.is-image-loading').count()>0
            photo_animation=await page.locator('#home-services .service-thumbnail').first.evaluate("e=>getComputedStyle(e,'::after').animationName")
            assert (photo_animation=='none') if motion=='reduce' else photo_animation!='none'
            photo.set();state['photo_gate']=None
            await page.wait_for_function("()=>[...document.querySelectorAll('#home-services img')].every(i=>i.complete&&!i.classList.contains('is-image-loading'))")

            wave=hold('wave')
            await page.locator('[data-service=wave]').click();await pending('wave')
            await page.locator('#concept-content .app-loading').wait_for()
            assert 'Открываем волну' in await page.locator('#concept-content').inner_text()
            names=await page.locator('#concept-content').evaluate("e=>e.getAnimations({subtree:true}).filter(a=>a.playState==='running').length")
            assert (names==0) if motion=='reduce' else names>0,(motion,names)
            await page.locator('[id^=tg-mock]').evaluate_all("xs=>xs.forEach(e=>e.style.display='none')")
            await page.screenshot(path=str(OUT/f'{engine}-section-{theme}-{width}.png'),scale='css')
            wave.set();await page.get_by_role('heading',name='Волна',exact=True).wait_for()
            assert await page.locator('#concept-content .app-loading').count()==0
            if width==393 and motion!='reduce':
                state['photo_fail']=True;await page.get_by_role('button',name='Следующее фото',exact=True).click()
                await page.locator('.concept-photo .photo-fallback').wait_for(state='visible')
                assert await page.locator('.concept-photo img.is-image-loading').count()==0
                state['photo_fail']=False;await page.get_by_role('button',name='Следующее фото',exact=True).click()
                await page.wait_for_function("()=>{const i=document.querySelector('.concept-photo>img');return i?.complete&&i.naturalWidth>0&&!i.classList.contains('is-image-loading')}")

            # An older request must not remove the next screen's loader.
            await page.locator('#app-nav [data-view=home]').click();old=hold('wave');hotel=hold('hotel')
            await page.locator('[data-service=wave]').click();await pending('wave')
            await page.locator('#app-nav [data-view=home]').click();await page.locator('[data-service=hotel]').click();await pending('hotel')
            old.set();await page.wait_for_timeout(160)
            assert await page.locator('#concept-content').get_attribute('aria-busy')=='true'
            assert 'Открываем отель' in await page.locator('#concept-content').inner_text()
            hotel.set();await page.get_by_role('heading',name='Отель',exact=True).wait_for()
            assert await page.locator('.app-loading:visible').count()==0
            state['wave_gate']=state['hotel_gate']=None

            # Failed writes restore the original pay label and allow a new attempt.
            await page.locator('#app-nav [data-view=home]').click();await page.locator('[data-service=wave]').click()
            await page.get_by_role('heading',name='Волна',exact=True).wait_for();await page.get_by_role('button',name='Выбрать дату',exact=True).click()
            await page.get_by_role('button',name='Далее · контакты',exact=True).click()
            await page.get_by_label('Имя',exact=True).fill('Иван');await page.get_by_label('Телефон',exact=True).fill('+79001234567')
            await page.get_by_role('button',name='Проверить бронь',exact=True).click();await page.get_by_role('heading',name='Проверка брони',exact=True).wait_for()
            write=hold('checkout');state['checkout_fail']=True
            pay=page.get_by_role('button',name='Оплатить ·',exact=False);await pay.click();await pending('checkout')
            busy=page.locator('#concept-content button[aria-busy=true]');assert await busy.is_disabled()
            assert 'Открываем оплату' in await busy.inner_text()
            write.set();await pay.wait_for();assert await pay.is_enabled();assert await page.locator('#concept-content button[aria-busy=true]').count()==0

            # Native pages recover from a failed load without a stuck animation.
            await page.locator('#app-nav [data-view=home]').click();native=hold('native');state['native_fail']=True
            await page.locator('#home-location').get_by_role('button',name='Контакты',exact=True).click();await pending('native')
            assert await page.locator('#native-content .app-loading').is_visible()
            native.set();await page.get_by_role('heading',name='Не удалось загрузить',exact=True).wait_for()
            assert await page.locator('#native-content .app-loading').count()==0
            state['native_fail']=False;retry=hold('native')
            await page.get_by_role('button',name='Попробовать ещё раз',exact=True).click();await pending('native')
            assert await page.locator('#native-content .app-loading').is_visible()
            retry.set();await page.wait_for_function("()=>!document.getElementById('native-content').hasAttribute('aria-busy')")
            assert await page.locator('#native-content .app-loading').count()==0

            chat=hold('chat');await page.locator('#app-nav [data-view=inbox]').click();await page.locator('.request-row').first.click();await pending('chat')
            assert await page.locator('#chat-log .app-loading').is_visible()
            chat.set();await page.locator('.chat-bubble').first.wait_for();assert await page.locator('#chat-log .app-loading').count()==0
            poll=hold('chat');await pending('chat')
            assert await page.locator('.chat-bubble').first.is_visible()
            assert await page.locator('#chat-log .app-loading').count()==0
            poll.set();state['chat_gate']=None
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            results.append({'viewport':[width,height],'theme':theme,'motion':motion,'boot_and_sections':'passed','navigation_race':'passed','failed_write_restores_button':True,'native_retry':True,'background_chat_keeps_content':True,'errors':errors})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            await context.close()

        # Initial network failure supports retry, with no endlessly running splash.
        context=await browser.new_context(viewport={'width':393,'height':853},color_scheme='dark')
        page=await context.new_page();boot_attempts=0
        async def fail_boot_once(route):
            nonlocal boot_attempts
            if route.request.post_data_json.get('operation')=='bootstrap':
                boot_attempts+=1
                if boot_attempts==1:
                    await route.fulfill(status=503,content_type='application/json',body='{"error":"Нет соединения"}');return
            await route.continue_()
        await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_mock()))
        await page.route('https://sunparkspb.ru/**',photos);await page.route('**/api/app',fail_boot_once)
        await page.goto(origin+'/app');await page.get_by_role('heading',name='Не удалось открыть Sunpark',exact=True).wait_for()
        assert await page.locator('.boot-loader').count()==0
        await page.get_by_role('button',name='Попробовать снова',exact=True).click();await page.locator('#app-shell').wait_for(state='visible')
        assert boot_attempts==2;await context.close();await browser.close()
    server.shutdown();(OUT/f'{engine}-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':asyncio.run(main())
