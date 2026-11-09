"""Real Chromium + real Python handlers, isolated SQLite and mocked Telegram."""
import asyncio
import json
import shutil
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
import serve_mini_app as fixture
from test_mini_app import AppHarness
from test_menu_preview import signed

ARTIFACTS = Path(__file__).resolve().parents[1] / 'artifacts'


def telegram_stub():
    return 'window.__themes=[];window.__events={};window.Telegram={WebApp:{initData:' + json.dumps(signed()) + ''',colorScheme:'dark',ready(){},expand(){},onEvent(name,fn){window.__events[name]=fn;},setHeaderColor(c){window.__themes.push(c);},setBackgroundColor(){},setBottomBarColor(){},BackButton:{show(){window.__backVisible=true;},hide(){window.__backVisible=false;},onClick(fn){window.__backHandler=fn;}},HapticFeedback:{selectionChanged(){}}}};'''


async def settled(page):
    await page.wait_for_function("()=>!document.body.classList.contains('busy') && !document.getElementById('flow-submit').disabled && !document.getElementById('chat-send').disabled")


async def main():
    ARTIFACTS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    checks = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=shutil.which('chromium'))
        for width in [320, 390, 820]:
            fixture.bot = AppHarness()
            page = await browser.new_page(viewport={'width': width, 'height': 844}, color_scheme='dark')
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
            await page.route('https://telegram.org/js/telegram-web-app.js', lambda r: r.fulfill(content_type='text/javascript', body=telegram_stub()))
            await page.goto(origin + '/app')
            await page.locator('#app-shell').wait_for(state='visible')
            await page.evaluate('document.fonts.ready')
            for theme in ['dark', 'light']:
                await page.emulate_media(color_scheme=theme)
                await page.wait_for_function(f"()=>document.documentElement.dataset.theme==='{theme}'")
                await page.wait_for_timeout(180)
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert await page.locator('#home-booking').evaluate('(b)=>b.getBoundingClientRect().height>=44')
                # OS preference wins even when Telegram is manually set differently.
                await page.evaluate("window.__events.themeChanged()")
                assert await page.evaluate('document.documentElement.dataset.theme') == theme
                assert await page.evaluate('window.__themes.at(-1)') == ('#101c18' if theme == 'dark' else '#f8f5eb')
                await page.screenshot(path=str(ARTIFACTS / f'home-{theme}-{width}.png'))
            assert await page.get_by_text('Сменить вид').count() == 0
            await page.locator('#home-menu-button').click()
            await page.get_by_role('button', name='Бар', exact=True).click()
            assert await page.locator('.category-title').all_text_contents() == ['Пиво и сидр', 'Коктейльная карта', 'Вино', 'Крепкий алкоголь']
            await page.get_by_role('button', name='Пиво и сидр', exact=False).click()
            await page.locator('.item-row').filter(has_text='Эль Капулько').click()
            assert await page.locator('#dish-add').is_disabled()
            await page.locator('.option-choice').filter(has_text='350 ₽').click()
            await page.locator('#dish-add').click()
            await page.locator('#cart-launcher').click()
            assert await page.locator('#cart-total').inner_text() == '350 ₽'
            await page.locator('.cart-row').click()
            await page.locator('#quantity-plus').click()
            await page.locator('#dish-add').click()
            assert await page.locator('#cart-total').inner_text() == '700 ₽'
            await page.reload()
            await page.locator('#app-shell').wait_for(state='visible')
            assert await page.locator('#cart-launcher').is_visible()
            await page.locator('#cart-launcher').click()
            assert await page.locator('#cart-total').inner_text() == '700 ₽'
            await page.locator('.cart-row').click()
            await page.locator('#dish-remove').click()
            assert await page.locator('#cart-total').inner_text() == '0 ₽'
            await page.locator('#app-nav [data-view=menu]').click()
            await page.get_by_role('button', name='Еда', exact=True).click()
            await page.locator('.category-card').filter(has_text='Закуски').click()
            await page.locator('.item-row').last.scroll_into_view_if_needed()
            scroll = await page.evaluate('scrollY')
            await page.locator('.item-row').last.click()
            assert await page.evaluate("getComputedStyle(document.querySelector('dialog')).position") == 'fixed'
            assert await page.evaluate("document.body.classList.contains('modal-open')")
            await page.screenshot(path=str(ARTIFACTS / f'dish-light-{width}.png'))
            await page.evaluate('window.__backHandler()')
            assert abs(await page.evaluate('scrollY') - scroll) < 2
            await page.locator('#app-nav [data-view=home]').click()
            await page.locator('#home-samples button').first.click()
            await page.locator('#dish-add').click()
            assert await page.locator('#cart-launcher').is_visible()
            if width == 390:
                await page.locator('#home-booking').click()
                for value in ['2099-01-01', '19:30', '4', 'Иван', '+79001234567', 'У окна']:
                    await page.locator('#flow-form').wait_for(state='visible')
                    field = page.locator('#flow-input') if await page.locator('#flow-input').is_visible() else page.locator('#flow-textarea')
                    await field.fill(value)
                    await page.locator('#flow-submit').click()
                    await settled(page)
                assert await page.locator('#flow-form').is_hidden()
                await page.locator('#app-nav [data-view=inbox]').click()
                await page.locator('.ticket-row').first.click()
                await page.locator('#chat-input').fill('Тест <script>без HTML</script>')
                await page.locator('#chat-send').click()
                await settled(page)
                await page.get_by_text('Тест <script>без HTML</script>', exact=True).wait_for()
                await page.locator('#chat-back').click()
                await page.locator('#inbox-scope [data-scope=staff]').click()
                await page.locator('.ticket-row').first.click()
                await page.get_by_role('button', name='Взять в работу', exact=True).click()
                await settled(page)
                await page.locator('#chat-input').fill('Бронь подтверждена')
                await page.locator('#chat-send').click()
                await settled(page)
                await page.get_by_text('Бронь подтверждена', exact=True).wait_for()
                await page.set_viewport_size({'width':390,'height':500})
                await page.wait_for_timeout(100)
                assert await page.locator('#chat-send').evaluate('(b)=>b.getBoundingClientRect().bottom <= document.getElementById("app-nav").getBoundingClientRect().top')
                await page.set_viewport_size({'width':390,'height':844})
                await page.wait_for_timeout(100)
                await page.screenshot(path=str(ARTIFACTS / 'chat-light-390.png'))
                await page.get_by_role('button', name='Заметка', exact=True).click()
                await page.locator('#flow-textarea').fill('Нужен детский стул')
                await page.locator('#flow-submit').click()
                await settled(page)
                await page.locator('#app-nav [data-view=more]').click()
                for title in ['Админ-панель', 'Очередь заявок', 'Мои активные заявки', 'Менеджеры', 'Статистика', 'Правила и контакты']:
                    await page.locator('#more-actions').get_by_role('button', name=title, exact=True).click()
                    await settled(page)
                    assert await page.locator('#flow-cards').inner_text()
                    await page.locator('#app-nav [data-view=more]').click()
                await page.locator('#more-actions').get_by_role('button', name='Мероприятия и регистрации', exact=True).click()
                await page.get_by_role('button', name='Создать мероприятие', exact=True).click()
                for value in ['Вечер в SUNPARK', 'Дегустация', '2099-01-01T19:00', 'SUNPARK', 'Бесплатно', '50']:
                    await page.locator('#flow-form').wait_for(state='visible')
                    field = page.locator('#flow-input') if await page.locator('#flow-input').is_visible() else page.locator('#flow-textarea')
                    await field.fill(value)
                    await page.locator('#flow-submit').click()
                    await settled(page)
                await page.screenshot(path=str(ARTIFACTS / 'event-review-light-390.png'))
                await page.get_by_role('button', name='Подтвердить', exact=True).click()
                await settled(page)
                assert (await fixture.bot.db_first('SELECT COUNT(*) n FROM events')).n == 1
                await page.locator('#app-nav [data-view=more]').click()
                await page.locator('#more-actions').get_by_role('button', name='Поиск заявок', exact=True).click()
                await page.locator('#flow-textarea').fill('9001234567')
                await page.locator('#flow-submit').click()
                await settled(page)
                assert 'Результаты поиска' in await page.locator('#flow-cards').inner_text()
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert errors == [], errors
            checks.append({'width': width, 'themes': ['dark', 'light'], 'console_errors': errors, 'full_workflows': width == 390})
            await page.close()
        # Older WebViews without system media preferences follow Telegram.
        page=await browser.new_page(viewport={'width':390,'height':844})
        await page.add_init_script('window.matchMedia=undefined;')
        await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_stub()))
        await page.goto(origin+'/app')
        await page.locator('#app-shell').wait_for(state='visible')
        assert await page.evaluate('document.documentElement.dataset.theme')=='dark'
        await page.evaluate("Telegram.WebApp.colorScheme='light';window.__events.themeChanged();")
        assert await page.evaluate('document.documentElement.dataset.theme')=='light'
        await page.close()
        checks.append({'telegram_theme_fallback':'passed'})
        await browser.close()
    server.shutdown()
    (ARTIFACTS / 'browser-results.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
