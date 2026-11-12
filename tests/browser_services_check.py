"""Exercise service journeys in Chromium; Telegram/API identity is a fixture."""
import asyncio
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright
import serve_mini_app as fixture
from test_mini_app import AppHarness
from test_menu_preview import signed

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'


async def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    # The skill's complete SDK mock is test-only; no mock or test identity is
    # served by the production Worker, and its existing signature check stays on.
    mock = (ROOT / '.agents/skills/telegram-webapps/assets/miniapp-mock.js').read_text()
    mock += '\nwindow.Telegram.WebApp.initData=' + json.dumps(signed()) + ';'
    mock += "window.__links=[];window.Telegram.WebApp.openLink=url=>window.__links.push(url);"
    results = []
    async with async_playwright() as p:
        proxy = {'server': os.environ['HTTPS_PROXY'], 'bypass': '127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None
        browser = await p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, proxy=proxy)
        for width in [320, 390, 820]:
            fixture.bot = AppHarness()
            await fixture.bot.config()
            page = await browser.new_page(viewport={'width':width, 'height':844}, color_scheme='light', timezone_id='Europe/Moscow', has_touch=True)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.route('https://telegram.org/js/telegram-web-app.js', lambda r:r.fulfill(content_type='text/javascript',body=mock))
            await page.goto(origin+'/app')
            await page.locator('#app-shell').wait_for(state='visible')
            await page.evaluate('document.fonts.ready')
            # The mock's simulated native header is outside app-owned content.
            await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
            if width==390:
                await page.screenshot(path=str(ARTIFACTS/'services-home-light-390.png'))
                await page.locator('#home-services').scroll_into_view_if_needed()
                await page.wait_for_function("()=>[...document.querySelectorAll('#home-services img')].every(i=>i.complete&&i.naturalWidth>0)")
                await page.screenshot(path=str(ARTIFACTS/'services-home-list-light-390.png'))
            for key,title in [('wake','Вейк'),('wave','Волна'),('hotel','Отель')]:
                if key=='wake':
                    await page.locator('#home-services .service-card').filter(has_text=title).click()
                else:
                    await page.locator('.service-tabs').get_by_role('button',name=title,exact=True).click()
                await page.get_by_role('heading',name=title,exact=True).wait_for()
                await page.locator('.service-photos img').first.wait_for()
                await page.wait_for_function("()=>{const i=document.querySelector('.service-photos img');return i.complete&&i.naturalWidth>0}")
                assert await page.locator('.service-photos img').count()==3
                await page.get_by_role('button',name='Следующее фото',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.gallery-counter').textContent==='2 / 3'")
                await page.get_by_role('button',name='Предыдущее фото',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.gallery-counter').textContent==='1 / 3'")
                assert (await page.locator('.service-actions a').nth(1).get_attribute('href')).startswith('tel:+7')
                await page.locator('.service-actions .primary-button').click()
                assert await page.evaluate('window.__links.length')>0
                await page.evaluate('window.scrollTo(0,0)')
                for theme in ['light','dark']:
                    await page.emulate_media(color_scheme=theme)
                    await page.wait_for_timeout(120)
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(ARTIFACTS/f'services-{key}-{theme}-{width}.png'))
                await page.emulate_media(color_scheme='light')
                if key=='wake':
                    assert 'лето 2026' in await page.locator('.service-prices').inner_text()
                    await page.locator('summary').filter(has_text='выходные и праздники').click()
                    assert await page.locator('.service-price-group[open]').count()==2
                if key=='wave':
                    assert '/ человек' in await page.locator('.service-price-list').first.inner_text()
                if key=='hotel':
                    assert '5\u00a0000' in await page.locator('.service-price-list').inner_text()
                    assert await page.locator('a[href="tel:+78129262650"]').count()==1
                    await page.locator('.service-prices').scroll_into_view_if_needed()
                    if width==390:await page.screenshot(path=str(ARTIFACTS/'services-hotel-prices-light-390.png'))
            # The Telegram mock emits its registered BackButton callback.
            await page.keyboard.press('Escape')
            assert await page.locator('#home-view').is_visible()
            await page.locator('#app-nav [data-view=more]').click()
            await page.locator('#more-actions').get_by_role('button',name='Волна',exact=True).click()
            await page.locator('#service-view .back-link').click()
            assert await page.locator('#more-view').is_visible()
            assert not errors,errors
            results.append({'width':width,'themes':['light','dark'],'services':3,'gallery':'passed','links':'passed','navigation':'passed','errors':errors})
            await page.close()
        await browser.close()
    (ARTIFACTS/'services-browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
