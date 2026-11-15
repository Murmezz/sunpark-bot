"""Long-open Telegram session and restaurant action regression in Chromium."""
import asyncio
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from playwright.async_api import async_playwright
import serve_mini_app as fixture
from browser_services_check import ARTIFACTS, telegram_mock
from test_menu_preview import signed
from test_mini_app import AppHarness
from mini_app_auth import SESSION_TTL, authenticate_app


async def main():
    clock = [int(time.time())]
    started = clock[0]
    raw = signed(when=started)
    mock = telegram_mock() + '\nwindow.Telegram.WebApp.initData=' + json.dumps(raw) + ';'
    mock += "document.documentElement.style.setProperty('--tg-safe-area-inset-top','32px');document.documentElement.style.setProperty('--tg-content-safe-area-inset-top','56px');"
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    results = []
    async with async_playwright() as p:
        proxy = {'server': os.environ['HTTPS_PROXY'], 'bypass': '127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None
        browser = await p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, proxy=proxy)
        with patch('mini_app.authenticate_app', side_effect=lambda raw, token, session=None: authenticate_app(raw, token, session, now=clock[0])):
            for width in [320, 390, 820]:
                clock[0] = started
                fixture.bot = AppHarness()
                await fixture.bot.config()
                page = await browser.new_page(viewport={'width': width, 'height': 844}, color_scheme='light', has_touch=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.route('https://telegram.org/js/telegram-web-app.js', lambda route: route.fulfill(content_type='text/javascript', body=mock))
                await page.goto(origin + '/app')
                await page.locator('#home-services [data-service=restaurant]').click()
                await page.evaluate('document.fonts.ready')
                await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
                await page.wait_for_function("()=>{const i=document.querySelector('.service-photo img');return i.complete&&i.naturalWidth>0}")
                assert (await page.locator('.restaurant-actions').bounding_box())['y'] < (await page.locator('.service-gallery').bounding_box())['y']
                for selector in ['#restaurant-menu', '#restaurant-booking', '#restaurant-banquet']:
                    assert await page.locator(selector).evaluate("e=>e.getBoundingClientRect().bottom<=document.getElementById('app-nav').getBoundingClientRect().top")
                assert await page.locator('.service-call[href^="tel:"]').count() == 1
                for theme in ['light', 'dark']:
                    await page.emulate_media(color_scheme=theme)
                    await page.wait_for_function('(theme)=>document.documentElement.dataset.theme===theme', arg=theme)
                    await page.wait_for_timeout(180)
                    await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
                    await page.screenshot(path=str(ARTIFACTS / f'session-restaurant-refined-{theme}-{width}.png'))
                await page.locator('#restaurant-menu').click()
                assert await page.locator('#menu-hub').is_visible()
                await page.locator('#back-to-sections').click()
                for selector in ['#restaurant-booking', '#restaurant-banquet']:
                    await page.locator(selector).click()
                    await page.wait_for_function("()=>document.getElementById('native-content').getAttribute('aria-busy')!=='true'")
                    assert await page.locator('.date-control').count()
                    await page.locator('#native-back').click()
                    assert await page.locator('#service-view').is_visible()
                # Old initData is now expired, but the launch-bound app session is valid.
                clock[0] = started + 7200
                await page.locator('#app-nav [data-view=inbox]').click()
                await page.get_by_role('heading', name='Пока нет обращений', exact=True).wait_for()
                await page.reload()
                await page.locator('#app-shell').wait_for(state='visible')
                await page.locator('#app-nav [data-view=inbox]').click()
                await page.get_by_role('heading', name='Пока нет обращений', exact=True).wait_for()
                # A genuine server failure remains an error, never a fake empty inbox.
                async def unavailable(route):
                    payload = route.request.post_data_json
                    if payload.get('screen') == 'tickets':
                        await route.fulfill(status=500, content_type='application/json', body=json.dumps({'error': 'Временный сбой сервера'}))
                    else:
                        await route.continue_()
                await page.route(origin + '/api/app', unavailable)
                await page.locator('#app-nav [data-view=inbox]').click()
                await page.get_by_role('heading', name='Не удалось загрузить', exact=True).wait_for()
                assert await page.get_by_role('heading', name='Пока нет обращений', exact=True).count() == 0
                await page.unroute(origin + '/api/app', unavailable)
                await page.get_by_role('button', name='Попробовать ещё раз', exact=True).click()
                await page.get_by_role('heading', name='Пока нет обращений', exact=True).wait_for()
                clock[0] = started + SESSION_TTL + 1
                await page.locator('#app-nav [data-view=inbox]').click()
                await page.get_by_role('heading', name='Сеанс завершён', exact=True).wait_for()
                assert await page.get_by_role('button', name='Попробовать ещё раз', exact=True).count() == 0
                if width == 390:
                    await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
                    await page.screenshot(path=str(ARTIFACTS / 'session-refined-expired-dark-390.png'))
                await page.get_by_role('button', name='Закрыть приложение', exact=True).click()
                assert await page.evaluate('window.__closed') == 1
                # Reload with an expired session also has a specific recovery screen.
                await page.reload()
                await page.get_by_role('heading', name='Сеанс завершён', exact=True).wait_for()
                assert await page.get_by_role('button', name='Закрыть приложение', exact=True).count() == 1
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors, errors
                results.append({'width': width, 'restaurant_actions': 'passed', 'two_hour_messages_and_reload': 'passed', 'server_error_retry': 'passed', 'session_expiry_recovery': 'passed', 'errors': errors})
                await page.close()
        await browser.close()
    server.shutdown()
    (ARTIFACTS / 'session-restaurant-browser-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
