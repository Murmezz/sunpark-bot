"""Real Chromium checks of Mini App workflows; SQLite and Telegram are fixtures."""
import asyncio,json,shutil,threading
from datetime import datetime,timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright
import serve_mini_app as fixture
from test_mini_app import AppHarness
from test_menu_preview import signed

ARTIFACTS=Path(__file__).resolve().parents[1]/'artifacts'

def telegram_stub():
    return 'window.__themes=[];window.__events={};window.Telegram={WebApp:{initData:'+json.dumps(signed())+''',colorScheme:'dark',ready(){},expand(){},onEvent(n,f){window.__events[n]=f;},setHeaderColor(c){window.__themes.push(c);},setBackgroundColor(){},setBottomBarColor(){},BackButton:{show(){window.__backVisible=true;},hide(){window.__backVisible=false;},onClick(f){window.__backHandler=f;}},HapticFeedback:{selectionChanged(){}}}};'''

async def settled(page):
    await page.wait_for_function("()=>!document.body.classList.contains('busy')")
    await page.wait_for_timeout(80)

async def native_ready(page):
    await page.wait_for_function("()=>document.getElementById('native-content').getAttribute('aria-busy')!=='true'")
    await page.wait_for_timeout(100)

async def set_time(page,hour,minute):
    for label,value in [('Часы',hour),('Минуты',minute)]:
        wheel=page.get_by_role('listbox',name=label,exact=True)
        await wheel.focus();await wheel.press('Home')
        for _ in range(value//5):await wheel.press('PageDown')
        for _ in range(value%5):await wheel.press('ArrowDown')
    await page.evaluate('document.activeElement.blur()')
    await page.wait_for_timeout(100)

async def future_date(page,days=4):
    today=await page.locator('.calendar-day[aria-current=date]').get_attribute('data-date')
    return (datetime.fromisoformat(today)+timedelta(days=days)).date().isoformat()

async def choose_day(page,iso):
    for _ in range(3):
        day=page.locator(f'.calendar-day[data-date="{iso}"]:visible')
        if await day.count():await day.click();return
        await page.get_by_role('button',name='Следующий месяц',exact=True).click()
    raise AssertionError('Calendar could not reach date '+iso)

async def open_more(page,title):
    await page.locator('#app-nav [data-view=more]').click()
    await page.locator('#more-actions').get_by_role('button',name=title,exact=True).click()
    await native_ready(page)

async def main():
    ARTIFACTS.mkdir(exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start();origin=f'http://127.0.0.1:{server.server_port}'
    results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for width in [320,390,820]:
            fixture.bot=AppHarness();await fixture.bot.config()
            await fixture.bot.db_run("UPDATE config SET value=? WHERE key='manager_names'",json.dumps({'1':'Менеджер SUNPARK'},ensure_ascii=False))
            await fixture.bot.db_run("INSERT INTO tickets(number,guest_id,status) VALUES(23,99,'closed')")
            await fixture.bot.db_run("INSERT INTO users(user_id,username,first_name,last_name,updated_at) VALUES(2,'alex_sunpark','Алексей','','now')")
            page=await browser.new_page(viewport={'width':width,'height':844},color_scheme='light',timezone_id='Europe/Moscow',has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_stub()))
            await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible');await page.evaluate('document.fonts.ready')
            for theme in ['light','dark']:
                await page.emulate_media(color_scheme=theme);await page.wait_for_timeout(180)
                assert await page.evaluate('document.documentElement.dataset.theme')==theme
                await page.evaluate('window.__events.themeChanged()')
                assert await page.evaluate('document.documentElement.dataset.theme')==theme
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                await page.screenshot(path=str(ARTIFACTS/f'adapt-home-{theme}-{width}.png'))
            await page.emulate_media(color_scheme='light')
            await page.locator('#home-services [data-service=restaurant]').click();await page.locator('#restaurant-booking').click();await native_ready(page)
            iso=await future_date(page)
            assert await page.locator('.calendar-day:disabled').count()>0
            await choose_day(page,iso);await set_time(page,19,30)
            assert await page.get_by_role('listbox',name='Минуты',exact=True).get_by_role('option',selected=True).inner_text()=='30'
            assert await page.locator('.native-footer').evaluate('(e)=>e.getBoundingClientRect().bottom<=document.getElementById("app-nav").getBoundingClientRect().top+1')
            for theme in ['light','dark']:
                await page.emulate_media(color_scheme=theme);await page.wait_for_timeout(180);await page.screenshot(path=str(ARTIFACTS/f'adapt-calendar-{theme}-{width}.png'))
            await page.emulate_media(color_scheme='light')
            await page.get_by_role('button',name='Продолжить',exact=True).click()
            await page.get_by_role('button',name='Увеличить количество гостей',exact=True).click();await page.get_by_role('button',name='Увеличить количество гостей',exact=True).click()
            await page.locator('#native-name').fill('Иван');await page.locator('#native-phone').fill('+79001234567');await page.locator('#native-comment').fill('Столик у окна')
            await page.get_by_role('button',name='Продолжить',exact=True).click();await page.locator('#native-back').click()
            assert await page.locator('#native-name').input_value()=='Иван'
            assert await page.locator('[name=guests]').input_value()=='4'
            await page.get_by_role('button',name='Продолжить',exact=True).click();await page.screenshot(path=str(ARTIFACTS/f'adapt-review-light-{width}.png'))
            await page.get_by_role('button',name='Отправить заявку',exact=True).click();await page.get_by_role('button',name='Открыть переписку',exact=True).wait_for()
            await page.get_by_role('button',name='Открыть переписку',exact=True).click();await page.locator('#chat-input').wait_for(state='visible')
            await page.locator('#chat-input').fill('Добрый вечер! Можно столик у окна?');await page.locator('#chat-send').click()
            await page.get_by_text('Добрый вечер! Можно столик у окна?',exact=True).wait_for()
            await page.set_viewport_size({'width':width,'height':500});await page.wait_for_timeout(100)
            assert await page.locator('#chat-send').evaluate('(e)=>e.getBoundingClientRect().bottom<=document.getElementById("app-nav").getBoundingClientRect().top+1')
            await page.set_viewport_size({'width':width,'height':844})
            # Menu/cart regressions and deep-scrolled dish modal.
            await page.locator('#app-nav [data-view=menu]').click();await page.get_by_role('button',name='Бар',exact=True).click()
            assert await page.locator('.category-title').all_text_contents()==['Пиво и сидр','Коктейльная карта','Вино','Крепкий алкоголь']
            await page.locator('.category-card').filter(has_text='Пиво и сидр').click();await page.locator('.item-row').filter(has_text='Эль Капулько').click()
            assert await page.locator('#dish-add').is_disabled();await page.locator('.option-choice').filter(has_text='350 ₽').click();await page.locator('#dish-add').click()
            await page.locator('#cart-launcher').click();assert await page.locator('#cart-total').inner_text()=='350 ₽'
            await page.locator('.cart-row').click();await page.locator('#quantity-plus').click();await page.locator('#dish-add').click();assert await page.locator('#cart-total').inner_text()=='700 ₽'
            await page.reload();await page.locator('#app-shell').wait_for(state='visible');await page.locator('#cart-launcher').click();assert await page.locator('#cart-total').inner_text()=='700 ₽'
            await page.locator('.cart-row').click();await page.locator('#dish-remove').click()
            await page.locator('#app-nav [data-view=menu]').click();await page.get_by_role('button',name='Еда',exact=True).click();await page.locator('.category-card').filter(has_text='Закуски').click()
            await page.locator('.item-row').last.scroll_into_view_if_needed();old_y=await page.evaluate('scrollY');await page.locator('.item-row').last.click()
            assert await page.evaluate("getComputedStyle(document.querySelector('#dish-dialog')).position")=='fixed'
            await page.evaluate('window.__backHandler()');assert abs(await page.evaluate('scrollY')-old_y)<2
            if width==390:
                await open_more(page,'Админ-панель');await page.screenshot(path=str(ARTIFACTS/'adapt-dashboard-light-390.png'))
                await page.get_by_role('button',name='Найти заявку',exact=True).click();await native_ready(page)
                await page.get_by_role('searchbox',name='Поиск заявок').fill('ИВАН');await page.get_by_role('button',name='Найти',exact=True).click();await native_ready(page)
                await page.locator('.request-row').first.click();await page.get_by_role('button',name='Взять в работу',exact=True).click();await page.get_by_role('button',name='Заметка',exact=True).wait_for()
                await page.locator('#chat-input').fill('Добрый вечер! Уточню наличие свободного столика и вернусь с ответом.');await page.locator('#chat-send').click()
                await page.get_by_text('Добрый вечер! Уточню наличие свободного столика и вернусь с ответом.',exact=True).wait_for()
                await page.get_by_role('button',name='Заметка',exact=True).click();await native_ready(page);await page.locator('#native-note').fill('Нужен детский стул');await page.get_by_role('button',name='Сохранить',exact=True).click();await page.locator('#chat-input').wait_for(state='visible')
                await page.get_by_role('button',name='Быстрый ответ',exact=True).click();await page.locator('#picker-dialog').wait_for(state='visible');assert await page.locator('.template-choice').count()>0
                await page.evaluate('window.__backHandler()');assert not await page.locator('#picker-dialog').is_visible()
                # Match the visual target's fixture names, attachment and timestamps.
                await fixture.bot.db_run("UPDATE ticket_messages SET created_at=CASE WHEN sender_role='guest' THEN '2026-11-10 11:20:00' ELSE '2026-11-10 11:22:00' END WHERE ticket_number=24")
                await fixture.bot.save_ticket_message(24,1,'guest',fixture.bot.stored_message_body('',{'type':'document','file_id':'fixture-pdf-id','file_name':'Пожелания.pdf'}))
                await fixture.bot.db_run("UPDATE ticket_messages SET created_at='2026-11-10 11:23:00' WHERE id=(SELECT MAX(id) FROM ticket_messages WHERE ticket_number=24)")
                # Guest chat visual evidence with real typed data, no admin controls.
                await page.locator('#app-nav [data-view=inbox]').click();await native_ready(page)
                await page.locator('#app-nav [data-view=home]').click();await page.locator('#home-inbox').click();await native_ready(page);await page.locator('.request-row').first.click();await page.locator('#chat-input').wait_for(state='visible')
                await page.locator('#cart-toast').wait_for(state='hidden')
                for theme in ['light','dark']:
                    await page.emulate_media(color_scheme=theme);await page.wait_for_timeout(180);await page.screenshot(path=str(ARTIFACTS/f'adapt-chat-{theme}-390.png'))
                await page.emulate_media(color_scheme='light')
                # Polling preserves the reading position and exposes a jump to new messages.
                for i in range(18):await fixture.bot.save_ticket_message(24,1,'guest','Сообщение из истории '+str(i)+' — проверяем сохранение позиции в длинной переписке.')
                await page.wait_for_timeout(6200)
                await page.locator('#chat-log').evaluate('(e)=>e.scrollTop=80')
                old_scroll=await page.locator('#chat-log').evaluate('(e)=>e.scrollTop')
                await fixture.bot.save_ticket_message(24,1,'manager','Новое сообщение во время чтения истории')
                await page.wait_for_timeout(6200)
                assert abs(await page.locator('#chat-log').evaluate('(e)=>e.scrollTop')-old_scroll)<2
                assert await page.locator('#chat-new').is_visible()
                await page.locator('#chat-new').click();assert await page.locator('#chat-new').is_hidden()
                # Event creation via actual calendar and time-picker sheets.
                await open_more(page,'Мероприятия и регистрации');await page.get_by_role('button',name='Создать мероприятие',exact=True).click();await native_ready(page)
                await page.locator('#native-title').fill('Вечер в SUNPARK');await page.locator('#native-location').fill('SUNPARK');await page.locator('#native-price').fill('Бесплатно')
                await page.get_by_role('button',name='Дата мероприятия',exact=True).click();await choose_day(page,iso);await page.get_by_role('button',name='Выбрать дату',exact=True).click()
                await page.get_by_role('button',name='Время мероприятия',exact=True).click();await set_time(page,19,30);await page.get_by_role('button',name='Выбрать время',exact=True).click()
                await page.locator('[name=capacity]').fill('4');await page.get_by_role('button',name='Сохранить',exact=True).click();await page.get_by_role('button',name='Открыть регистрацию',exact=True).wait_for()
                await page.get_by_role('button',name='Открыть регистрацию',exact=True).click();await page.get_by_role('button',name='Закрыть регистрацию',exact=True).wait_for();await page.locator('#cart-toast').wait_for(state='hidden');await page.screenshot(path=str(ARTIFACTS/'adapt-event-light-390.png'))
                await page.get_by_role('button',name='Добавить гостей вручную',exact=True).click();await native_ready(page)
                for key,value in [('first_name','Анна'),('last_name','Иванова'),('phone','+79001234568')]:await page.locator('#native-'+key).fill(value)
                await page.locator('[name=party_size]').fill('6');await page.get_by_role('button',name='Добавить в список',exact=True).click();await page.get_by_role('button',name='Список гостей',exact=True).wait_for();await page.get_by_role('button',name='Список гостей',exact=True).click();await native_ready(page)
                assert 'Анна Иванова' in await page.locator('#native-content').inner_text()
                await page.get_by_role('button',name='Удалить запись: Анна Иванова',exact=True).click();await page.get_by_role('button',name='Удалить запись',exact=True).click();await native_ready(page);await page.get_by_text('В списке пока нет гостей.',exact=True).wait_for()
                # Manager forms, stateful roster, rename and deletion.
                await open_more(page,'Менеджеры');await page.get_by_role('button',name='Добавить менеджера',exact=True).click();await page.locator('#native-username').fill('@alex_sunpark');await page.locator('#native-name').fill('Алексей');await page.get_by_role('button',name='Сохранить',exact=True).click();await page.get_by_role('button',name='Изменить имя: Алексей',exact=True).wait_for()
                await page.get_by_role('button',name='Изменить имя: Алексей',exact=True).click();await page.locator('#native-name').fill('Александр');await page.get_by_role('button',name='Сохранить',exact=True).click();await page.get_by_role('button',name='Удалить менеджера: Александр',exact=True).wait_for();await page.get_by_role('button',name='Удалить менеджера: Александр',exact=True).click();await page.get_by_role('button',name='Удалить менеджера',exact=True).click();await native_ready(page)
                assert await page.get_by_role('button',name='Удалить менеджера: Александр',exact=True).count()==0
                await open_more(page,'Правила и контакты');assert await page.get_by_role('link',name='Показать на карте',exact=True).is_visible()
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert errors==[],errors
            results.append({'width':width,'themes':['light','dark'],'booking_and_cart':'passed','keyboard_viewport':'passed','full_admin':width==390,'console_errors':errors})
            print('passed',width,flush=True);await page.close()
        fixture.bot=AppHarness();await fixture.bot.config()
        await fixture.bot.db_run("INSERT INTO events(title,description,starts_at,location,price,capacity,is_open,created_by,creation_key) VALUES('Проверка лимита','','2099-01-01 16:00:00','SUNPARK','Бесплатно',1,1,1,'capacity-fixture')")
        page=await browser.new_page(viewport={'width':390,'height':844})
        await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_stub()))
        await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible');await open_more(page,'Мероприятия');await page.locator('.event-row').first.click();await page.get_by_role('button',name='Записаться',exact=True).click();await native_ready(page)
        for key,value in [('first_name','Иван'),('last_name','Иванов'),('phone','+79001234567')]:await page.locator('#native-'+key).fill(value)
        await page.locator('[name=party_size]').fill('2');await page.get_by_role('button',name='Зарегистрироваться',exact=True).click();await page.locator('#native-form-error').wait_for(state='visible')
        assert await page.locator('#native-form-error').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.top>=0 && r.bottom<=document.getElementById("app-nav").getBoundingClientRect().top;}')
        await page.close();results.append({'capacity_error_visibility':'passed','expected_api_status':409})
        page=await browser.new_page();await page.add_init_script('window.matchMedia=undefined;');await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_stub()));await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible');assert await page.evaluate('document.documentElement.dataset.theme')=='dark';await page.evaluate("Telegram.WebApp.colorScheme='light';window.__events.themeChanged();");assert await page.evaluate('document.documentElement.dataset.theme')=='light';await page.close()
        await browser.close()
    server.shutdown();results.append({'telegram_fallback':'passed'});(ARTIFACTS/'browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
