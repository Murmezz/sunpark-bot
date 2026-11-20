"""Headless loopback QA of the development Mini App; fixture data only."""
import asyncio
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright
import serve_mini_app as fixture
from browser_services_check import telegram_mock
from test_app_bookings import BookingHarness

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'artifacts'
PHOTOS=Path('/workspace/sites/sunpark-design-review/public/assets')


async def screenshot(page,name):
    await page.locator('[id^=tg-mock]').evaluate_all("xs=>xs.forEach(e=>e.style.opacity='0')")
    await page.screenshot(path=str(ARTIFACTS/(name+'.png')))
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),name+' overflows'


async def main():
    ARTIFACTS.mkdir(exist_ok=True)
    fixture.bot=BookingHarness();await fixture.bot.seed()
    bot=fixture.bot
    for i in range(1,5):
        bot.db.execute("INSERT INTO miniapp_v2_slots SELECT ?,service,rate_id,resource_id,resources,starts_at+?,ends_at+?,capacity,active FROM miniapp_v2_slots WHERE id='slot'",('later-'+str(i),i*1800,i*1800))
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        async def photo(route):
            # The photos are verified source assets, never sent to production by this test.
            from urllib.parse import unquote
            url=unquote(route.request.url)
            name='hotel.png' if 'IMG_' in url or 'hotel' in url else 'wake.jpg' if 'wake' in url else 'wave.jpg' if 'Wave' in url else 'restaurant.jpg'
            await route.fulfill(content_type='image/png' if name.endswith('png') else 'image/jpeg',body=(PHOTOS/name).read_bytes())
        for width,height in [(320,640),(390,844),(820,1024)]:
            page=await browser.new_page(viewport={'width':width,'height':height},has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            mock=telegram_mock()+"\nsdk.openInvoice=(url,callback)=>{window.__invoice=url;callback('paid');};"
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=mock))
            await page.route('https://sunparkspb.ru/**',photo)
            await page.goto(origin+os.environ.get('SUNPARK_ENTRY','/app'));await page.locator('#app-shell').wait_for(state='visible')
            assert await page.locator('#app-nav button').all_text_contents()==['Главная','Мои планы','Сообщения']
            assert await page.locator('#home-services .service-card').count()==4
            for theme in ['light','dark']:
                await page.emulate_media(color_scheme=theme)
                await page.wait_for_timeout(180)
                await screenshot(page,f'concept-home-{theme}-{width}')
            cards=await page.locator('#home-services').bounding_box();nav=await page.locator('#app-nav').bounding_box()
            assert cards['y']+cards['height']<=nav['y'],(cards,nav)
            await page.locator('[data-service=wave]').click()
            await page.get_by_role('heading',name='Волна',exact=True).wait_for()
            await page.locator('.concept-photo>img').wait_for()
            await page.get_by_role('button',name='Следующее фото',exact=True).click()
            assert await page.locator('.concept-photo figcaption').inner_text()=='2 / 3'
            await page.get_by_role('button',name='Выбрать дату',exact=True).click()
            await page.get_by_role('heading',name='Дата и время',exact=True).wait_for()
            await page.locator('.concept-wheel .selected').first.wait_for()
            await page.wait_for_timeout(160)
            assert await page.locator('.concept-wheel').count()==2
            hour=page.get_by_role('listbox',name='Часы',exact=True)
            await hour.focus();await hour.press('ArrowDown');await page.wait_for_timeout(400)
            await screenshot(page,f'concept-time-dark-{width}')
            selected=await page.locator('.concept-wheel .selected').first.evaluate("e=>({font:getComputedStyle(e).fontSize,transform:getComputedStyle(e).transform,stretch:getComputedStyle(e).fontStretch})")
            assert selected['font']=='40px' and selected['transform']=='none',selected
            if os.environ.get('SUNPARK_ENTRY')=='/app-claude':
                # The visible booking price must change with the guest count,
                # using the seeded tariff (2,200 RUB per person).
                price=page.locator('.refined-dock-total strong')
                await page.get_by_role('button',name='Увеличить: Участники',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.refined-dock-total strong')?.textContent.replace(/\\D/g,'')==='4400'")
                assert await price.is_visible()
                await page.get_by_role('button',name='Уменьшить: Участники',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.refined-dock-total strong')?.textContent.replace(/\\D/g,'')==='2200'")
            await page.get_by_role('button',name='Далее · контакты',exact=True).click()
            await page.get_by_role('heading',name='Ваши контакты',exact=True).wait_for()
            await page.get_by_label('Имя',exact=True).fill('Иван')
            await page.get_by_label('Телефон',exact=True).fill('+79001234567')
            await page.get_by_role('button',name='Проверить бронь',exact=True).click()
            await page.get_by_role('heading',name='Проверка брони',exact=True).wait_for()
            assert await page.locator('#concept-content textarea').count()==0
            assert 'Пожелания' not in await page.locator('#concept-content').inner_text()
            await screenshot(page,f'concept-review-{width}')
            await page.locator('#app-nav [data-view=home]').click()
            await page.locator('[data-service=hotel]').click()
            await page.get_by_role('heading',name='Отель',exact=True).wait_for()
            await page.get_by_role('button',name='Выбрать даты',exact=True).click()
            await page.get_by_role('heading',name='Даты и гости',exact=True).wait_for()
            await page.get_by_role('button',name='Дата заезда',exact=True).click()
            await page.locator(f'[data-date="{bot.day}"]').click()
            await page.get_by_role('button',name='Выбрать дату',exact=True).click()
            await page.get_by_role('button',name='Дата выезда',exact=True).click()
            from datetime import timedelta
            await page.locator(f'[data-date="{bot.day+timedelta(days=2)}"]').click()
            await page.get_by_role('button',name='Выбрать дату',exact=True).click()
            await page.get_by_role('button',name='Показать свободные номера',exact=True).click()
            await page.get_by_role('heading',name='Свободные номера',exact=True).wait_for()
            assert '10 000' in await page.locator('#concept-content').inner_text()
            await screenshot(page,f'concept-rooms-{width}')
            await page.locator('#app-nav [data-view=home]').click()
            await page.locator('[data-service=restaurant]').click()
            await page.locator('#restaurant-menu').click()
            await page.locator('.item-add').first.click()
            if await page.locator('#dish-dialog').is_visible():
                if await page.locator('#dish-add').is_disabled(): await page.locator('#dish-option-list input').first.check()
                await page.locator('#dish-add').click()
            await page.locator('#cart-launcher').click();await page.locator('#preorder-checkout').click()
            await page.get_by_role('heading',name='Когда вас ждать?',exact=True).wait_for()
            await page.get_by_label('Приход по московскому времени',exact=True).fill(str(bot.day)+'T18:00')
            await page.get_by_label('Имя',exact=True).fill('Иван')
            await page.get_by_label('Телефон',exact=True).fill('+79001234567')
            await page.get_by_role('button',name='Проверить предзаказ',exact=True).click()
            await page.get_by_role('heading',name='Проверка предзаказа',exact=True).wait_for()
            await page.get_by_role('button',name='Оплатить ·',exact=False).click()
            await page.get_by_role('heading',name='Проверяем оплату',exact=True).wait_for()
            assert await page.locator('.concept-qr').count()==0
            assert await page.locator('#concept-content').get_by_text('Оплачено',exact=True).count()==0
            row=bot.db.execute("SELECT id FROM miniapp_v2_orders ORDER BY rowid DESC LIMIT 1").fetchone();order=row[0]
            from test_app_bookings import BookingTests
            case=BookingTests();case.bot=bot
            await case.pay(order)
            from datetime import datetime
            from events import MSK
            start=int(datetime.now(MSK).replace(hour=18,minute=0,second=0).timestamp())
            bot.db.execute('UPDATE miniapp_v2_orders SET starts_at=?,ends_at=? WHERE id=?',(start,start+60,order))
            # Force a refresh through the actual plans route; the invoice callback alone was insufficient.
            await page.locator('#app-nav [data-view=plans]').click()
            await page.get_by_role('heading',name='Мои планы',exact=True).wait_for()
            await page.locator('.concept-order').first.click()
            await page.get_by_role('button',name='Показать QR официанту',exact=True).click()
            await page.get_by_role('heading',name='Покажите QR официанту',exact=True).wait_for()
            assert (await page.locator('.concept-qr img').get_attribute('src')).startswith('data:image/gif;base64,')
            await screenshot(page,f'concept-qr-{width}')
            await page.locator('#app-nav [data-view=inbox]').click()
            await page.get_by_role('button',name='Управление',exact=True).click()
            await page.get_by_role('button',name='Мои столы и QR',exact=True).click()
            await page.get_by_role('button',name='Сканировать QR',exact=True).click()
            await page.get_by_label('Код из карточки гостя',exact=True).fill(order[:8].upper())
            await page.get_by_role('button',name='Найти по коду',exact=True).click()
            await page.get_by_role('heading',name='Выберите стол',exact=True).wait_for()
            await page.locator('.concept-table').first.click()
            await page.get_by_role('button',name='Посадить за стол',exact=False).click()
            await page.get_by_role('button',name='Завершить обслуживание',exact=True).wait_for()
            await screenshot(page,f'concept-seated-{width}')
            await page.get_by_role('button',name='Завершить обслуживание',exact=True).click()
            await page.locator('#picker-dialog').get_by_role('button',name='Завершить',exact=True).click()
            await page.get_by_role('heading',name='Мои столы',exact=True).wait_for()
            assert bot.db.execute('SELECT active FROM miniapp_v2_assignments WHERE order_id=?',(order,)).fetchone()[0]==0
            await page.locator('#app-nav [data-view=inbox]').click()
            await page.get_by_role('button',name='Управление',exact=True).click()
            await page.get_by_role('button',name='Услуги и ресурсы',exact=True).click()
            await page.get_by_role('heading',name='Услуги и ресурсы',exact=True).wait_for()
            await page.get_by_role('button',name='Ресурсы и номера',exact=True).click()
            await page.get_by_role('button',name='Тестовый номер',exact=True).click()
            await page.get_by_role('heading',name='Ресурс или номер',exact=True).wait_for()
            assert await page.get_by_label('Тип',exact=True).is_disabled()
            await screenshot(page,f'concept-inventory-edit-{width}')
            assert not errors,errors
            results.append({'viewport':[width,height],'themes':['light','dark'],'wave_hotel_preorder_qr_inventory':'passed','client_paid_callback_ignored':True,'errors':errors})
            await page.close()
        # Preserved old app must still boot and render its two-tab navigation.
        page=await browser.new_page(viewport={'width':390,'height':844})
        await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_mock()))
        await page.route('https://sunparkspb.ru/**',photo)
        await page.goto(origin+'/app/legacy');await page.locator('#app-shell').wait_for(state='visible')
        assert await page.locator('#app-nav button').all_text_contents()==['Главная','Сообщения']
        await page.locator('[data-service=wave]').click();await page.get_by_role('heading',name='Волна',exact=True).wait_for()
        results.append({'legacy_shell':'passed'})
        await browser.close()
    server.shutdown()
    (ARTIFACTS/'concept-browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
