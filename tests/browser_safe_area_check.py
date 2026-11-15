"""Regression for fullscreen Telegram controls covering the Mini App content."""
import asyncio
import json
import os
import threading
from http.server import ThreadingHTTPServer

from playwright.async_api import async_playwright
import serve_mini_app as fixture
from browser_services_check import ARTIFACTS, telegram_mock
from test_mini_app import AppHarness


async def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    mock = telegram_mock() + '''
window.__setInsets=(device,content)=>{
  for(const [prefix,value] of [['safe',device],['content-safe',content]])
    document.documentElement.style.setProperty(`--tg-${prefix}-area-inset-top`,value+'px');
  window.__chromeEmit('safeAreaChanged');window.__chromeEmit('contentSafeAreaChanged');
};
window.__setInsets(32,56);
'''
    results = []
    async with async_playwright() as p:
        proxy = {'server': os.environ['HTTPS_PROXY'], 'bypass': '127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None
        browser = await p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, proxy=proxy)
        for width in [320, 393, 820]:
            fixture.bot = AppHarness()
            await fixture.bot.config()
            page = await browser.new_page(viewport={'width': width, 'height': 1024 if width == 820 else 853}, color_scheme='dark', has_touch=True)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.route('https://telegram.org/js/telegram-web-app.js', lambda route: route.fulfill(content_type='text/javascript', body=mock))
            await page.goto(origin + '/app')
            await page.locator('#app-shell').wait_for(state='visible')
            await page.evaluate('document.fonts.ready')
            await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
            for device, content in [(32, 56), (44, 64), (0, 0)]:
                await page.evaluate('([device,content])=>window.__setInsets(device,content)', [device, content])
                safe = device + content
                for selector in ['.complex-intro h1', '.complex-leaf']:
                    box = await page.locator(selector).bounding_box()
                    assert box['y'] >= safe, f'{selector} overlaps Telegram controls: {box["y"]} < {safe}'
                bounds = await page.evaluate("()=>({bottom:document.getElementById('home-services').getBoundingClientRect().bottom, nav:document.getElementById('app-nav').getBoundingClientRect().top})")
                assert bounds['bottom'] < bounds['nav'], (width, device, content, bounds)
            await page.evaluate('window.__setInsets(32,56)')
            await page.wait_for_function("()=>[...document.querySelectorAll('#home-services img')].every(i=>i.complete&&i.naturalWidth>0)")
            # Representative overlay only in screenshots; no test chrome ships with the app.
            await page.evaluate('''()=>{
              const chrome=document.createElement('div');chrome.id='test-telegram-chrome';
              chrome.style='position:fixed;inset:0 0 auto;height:88px;z-index:100;pointer-events:none;background:var(--paper)';
              for(const [text,style] of [
                ['23:42','position:absolute;top:12px;left:20px;font-size:14px'],
                ['× Закрыть','position:absolute;left:12px;top:48px;border-radius:20px;background:#203329;padding:5px 12px;color:#fff'],
                ['⌄ ⋮','position:absolute;right:12px;top:48px;border-radius:20px;background:#203329;padding:5px 12px;color:#fff']
              ]){const span=document.createElement('span');span.textContent=text;span.style.cssText=style;chrome.append(span);}
              document.body.append(chrome);
            }''')
            for theme in ['dark', 'light']:
                await page.emulate_media(color_scheme=theme)
                await page.screenshot(path=str(ARTIFACTS / f'safe-area-home-{theme}-{width}.png'))
            await page.locator('#test-telegram-chrome').evaluate('e=>e.remove()')
            await page.locator('#home-services [data-service=restaurant]').click()
            assert (await page.locator('.service-topline .back-link').bounding_box())['y'] >= 88
            await page.locator('#restaurant-menu').click()
            await page.evaluate('window.scrollTo(0,160)')
            assert (await page.locator('#back-to-sections').bounding_box())['y'] >= 88
            await page.locator('#app-nav [data-view=inbox]').click()
            await page.get_by_role('heading', name='Пока нет обращений', exact=True).wait_for()
            await page.evaluate('window.scrollTo(0,160)')
            assert (await page.locator('#native-back').bounding_box())['y'] >= 88
            await page.locator('#native-back').click()
            assert await page.locator('#home-view').is_visible()
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors, errors
            results.append({'width': width, 'safe_top_pairs': [[32, 56], [44, 64], [0, 0]], 'home_and_leaf_clear': True, 'sticky_back_clear': True, 'directions_visible': 4, 'errors': errors})
            await page.close()
        await browser.close()
    server.shutdown()
    (ARTIFACTS / 'safe-area-browser-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
