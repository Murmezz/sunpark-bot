"""Approved audit: direct menu, contextual returns and usable booking controls."""
import asyncio
import json
import os
import threading
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright
import serve_mini_app as fixture
from browser_services_check import telegram_mock
from test_mini_app import AppHarness

OUT=Path(__file__).resolve().parents[1]/'artifacts'/'audit-refinements'


async def ready(page):
    await page.wait_for_function("()=>document.getElementById('native-content').getAttribute('aria-busy')!=='true'")
    await page.wait_for_timeout(80)


async def capture(page,name):
    await page.evaluate('document.fonts.ready')
    await page.wait_for_function("()=>[...document.querySelectorAll('img')].filter(i=>{const r=i.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0&&r.left<innerWidth&&r.right>0}).every(i=>i.complete&&i.naturalWidth>0)")
    await page.wait_for_timeout(180)
    await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
    await page.screenshot(path=str(OUT/(name+'.png')))


async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start();origin=f'http://127.0.0.1:{server.server_port}'
    results=[]
    async with async_playwright() as p:
        proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None
        browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,proxy=proxy)
        for width,height in [(320,640),(390,844),(820,1024)]:
            fixture.bot=AppHarness();await fixture.bot.config()
            if os.environ.get('SUNPARK_PUBLIC_CONFIG_FIXTURE'):
                for row in json.loads(Path(os.environ['SUNPARK_PUBLIC_CONFIG_FIXTURE']).read_text()):
                    await fixture.bot.db_run('INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',row['key'],row['value'])
            page=await browser.new_page(viewport={'width':width,'height':height},color_scheme='light',timezone_id='Europe/Moscow',has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            mock=telegram_mock()+"\ndocument.documentElement.style.setProperty('--tg-safe-area-inset-top','32px');document.documentElement.style.setProperty('--tg-content-safe-area-inset-top','56px');"
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=mock))
            await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible')
            assert await page.locator('#home-services .service-card').count()==4
            assert await page.locator('#home-location').get_by_role('link',name='Маршрут',exact=True).count()==1
            assert await page.locator('#cart-launcher').is_hidden()
            await capture(page,f'final-home-light-{width}')
            # A nested screen must restore its parent's return destination.
            await page.locator('#home-location').get_by_role('button',name='Контакты',exact=True).click();await ready(page)
            assert await page.get_by_role('link',name='Сайт ресторана',exact=True).count()==0
            assert await page.locator('.contact-block').count()==4
            await page.get_by_role('button',name='Мероприятия',exact=True).click();await ready(page)
            await page.locator('#native-back').click();await ready(page)
            assert await page.get_by_role('heading',name='Как добраться и контакты',exact=True).is_visible()
            assert await page.locator('#view-back-label').inner_text()=='На главную'
            await page.locator('#native-back').click();assert await page.locator('#home-view').is_visible()
            await page.locator('#home-services [data-service=restaurant]').click()
            assert await page.locator('.service-tabs').count()==0
            assert await page.locator('#cart-launcher').is_hidden()
            await capture(page,f'final-restaurant-light-{width}')
            await page.locator('#restaurant-menu').click()
            assert await page.locator('.item-open').count()>0,'Menu must start with dishes'
            await page.get_by_role('button',name='Бар',exact=True).click()
            await page.get_by_role('button',name='Пиво и сидр',exact=True).click()
            await page.locator('.item-open').filter(has_text='Эль Капулько').click()
            assert await page.locator('#dish-add').is_disabled(),'Multiple prices require an explicit choice'
            await page.locator('#dish-option-list input').nth(1).check();await page.locator('#dish-add').click()
            assert await page.locator('#cart-launcher').is_visible()
            await page.locator('#cart-launcher').click()
            assert await page.locator('#cart-total').inner_text()=='350 ₽'
            await page.locator('.cart-stepper [data-change="1"]').click()
            assert await page.locator('#cart-total').inner_text()=='700 ₽'
            await page.locator('.cart-stepper [data-change="-1"]').click()
            assert await page.locator('#cart-total').inner_text()=='350 ₽'
            await capture(page,f'final-choice-light-{width}')
            await page.locator('.cart-line-remove').click();await page.locator('#cart-back').click()
            assert await page.locator('#cart-launcher').is_hidden()
            await page.get_by_role('button',name='Еда',exact=True).click()
            await capture(page,f'final-menu-light-{width}')
            await page.locator('#back-to-sections').click();await page.locator('#restaurant-booking').click();await ready(page)
            assert await page.locator('.calendar').count()==0,'Calendar is opened on demand'
            await capture(page,f'final-booking-light-{width}')
            for selector in ['.date-control','.wheel-column','button.primary-button']:
                bounds=await page.locator('#native-content '+selector).first.evaluate("e=>{const r=e.getBoundingClientRect(),n=document.getElementById('app-nav').getBoundingClientRect();return {top:r.top,bottom:r.bottom,nav:n.top}}")
                assert bounds['top']>=88 and bounds['bottom']<=bounds['nav'],(width,height,selector,bounds)
            await page.get_by_role('button',name='Дата бронирования',exact=True).click()
            today=await page.locator('.calendar-day[aria-current=date]').get_attribute('data-date')
            target=(datetime.fromisoformat(today)+timedelta(days=2)).date().isoformat()
            day=page.locator(f'.calendar-day[data-date="{target}"]')
            if not await day.count():await page.get_by_role('button',name='Следующий месяц',exact=True).click()
            await day.click();await page.get_by_role('button',name='Выбрать дату',exact=True).click()
            await page.get_by_role('button',name='Продолжить',exact=True).click()
            await page.locator('#native-name').fill('Алексей');await page.locator('#native-phone').fill('+79001234567')
            await page.get_by_role('button',name='Продолжить',exact=True).click()
            assert await page.locator('.review-edit').count()==2
            await capture(page,f'final-review-light-{width}')
            await page.get_by_role('button',name='Отправить заявку',exact=True).click();await ready(page)
            await page.get_by_role('heading',name='Заявка отправлена',exact=True).wait_for()
            assert target[8:10].lstrip('0') in await page.locator('.success-context').inner_text()
            assert await page.locator('#cart-toast').is_hidden(),'The full success screen needs no duplicate toast'
            await capture(page,f'final-sent-light-{width}')
            await page.get_by_role('button',name='Открыть переписку',exact=True).click()
            await page.locator('#chat-input').fill('Вопрос о заявке')
            await page.set_viewport_size({'width':width,'height':500})
            await page.wait_for_function("()=>parseFloat(document.documentElement.style.getPropertyValue('--viewport-height'))<=innerHeight")
            await capture(page,f'final-chat-keyboard-light-{width}')
            assert await page.locator('#app-nav').is_hidden()
            bounds=await page.locator('#chat-input').evaluate('e=>({bottom:e.getBoundingClientRect().bottom,height:innerHeight})')
            assert bounds['bottom']<=bounds['height'],bounds
            assert await page.locator('#chat-log').evaluate('e=>e.clientHeight>=60')
            await page.locator('#chat-back').click();await ready(page)
            assert await page.locator('#app-nav').is_visible()
            assert await page.locator('#view-back-label').inner_text()=='На главную'
            assert 'Ждём подтверждения' in await page.locator('#native-content').inner_text()
            await page.set_viewport_size({'width':width,'height':height})
            await page.locator('#native-back').click();await page.emulate_media(color_scheme='dark');await page.wait_for_timeout(180)
            await capture(page,f'final-home-dark-{width}')
            assert not errors,errors
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            results.append({'width':width,'height':height,'safe_top':88,'direct_menu_and_variants':'passed','inline_quantity':'passed','return_history':'passed','booking_controls_clear':'passed','success_summary':'passed','keyboard_chat':'passed','errors':errors});await page.close()
        await browser.close()
    server.shutdown();(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
