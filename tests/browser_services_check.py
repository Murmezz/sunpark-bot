"""SUNPARK hub, in-app service information and Telegram chrome integration."""
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

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'artifacts'


def telegram_mock(mode='modern'):
    mock=(ROOT/'.agents/skills/telegram-webapps/assets/miniapp-mock.js').read_text()
    mock+='\nwindow.Telegram.WebApp.initData='+json.dumps(signed())+';'
    mock+='''
window.__links=[];window.__closed=0;window.__fullscreenRequests=0;window.__expandCalls=0;window.__chromeEvents={};
const sdk=window.Telegram.WebApp, originalOn=sdk.onEvent.bind(sdk);
sdk.onEvent=(name,fn)=>{(window.__chromeEvents[name]??=[]).push(fn);originalOn(name,fn);};
window.__chromeEmit=(name,data)=>{for(const fn of window.__chromeEvents[name]||[])fn(data);};
sdk.openLink=url=>window.__links.push(url);sdk.close=()=>window.__closed++;
sdk.expand=()=>window.__expandCalls++;
sdk.requestFullscreen=()=>{window.__fullscreenRequests++;sdk.isFullscreen=true;window.__chromeEmit('fullscreenChanged');};
'''
    if mode=='old':mock+="sdk.isVersionAtLeast=()=>false;"
    if mode=='unsupported':mock+="sdk.requestFullscreen=()=>{window.__fullscreenRequests++;window.__chromeEmit('fullscreenFailed',{error:'UNSUPPORTED'});};"
    return mock


async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    results=[]
    async with async_playwright() as p:
        proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None
        browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,proxy=proxy)
        for width in [320,390,820]:
            fixture.bot=AppHarness();await fixture.bot.config()
            page=await browser.new_page(viewport={'width':width,'height':844},color_scheme='light',timezone_id='Europe/Moscow',has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_mock()))
            await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible');await page.evaluate('document.fonts.ready')
            await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
            assert await page.locator('#home-services .service-card').count()==4
            await page.wait_for_function("()=>[...document.querySelectorAll('#home-services img')].every(i=>i.complete&&i.naturalWidth>0)")
            assert await page.evaluate('window.__fullscreenRequests')==1
            assert await page.evaluate("document.body.classList.contains('telegram-fullscreen')")
            if width==320:
                await page.set_viewport_size({'width':320,'height':640})
                assert await page.locator('#home-services').evaluate("e=>e.getBoundingClientRect().bottom<=document.getElementById('app-nav').getBoundingClientRect().top"),'Four directions must be immediately visible'
                await page.set_viewport_size({'width':320,'height':844})
            for theme in ['light','dark']:
                await page.emulate_media(color_scheme=theme);await page.wait_for_timeout(100)
                await page.screenshot(path=str(ARTIFACTS/f'complex-home-{theme}-{width}.png'))
            await page.emulate_media(color_scheme='light')
            for key,title in [('wake','Вейк'),('wave','Волна'),('restaurant','Ресторан'),('hotel','Отель')]:
                if key=='wake':await page.locator('#home-services [data-service=wake]').click()
                else:await page.locator('.service-tabs').get_by_role('button',name=title,exact=True).click()
                await page.get_by_role('heading',name=title,exact=True).wait_for()
                await page.wait_for_function("()=>{const i=document.querySelector('.service-photos img');return i.complete&&i.naturalWidth>0}")
                assert await page.locator('#service-view a').evaluate_all("links=>links.every(a=>a.getAttribute('href').startsWith('tel:'))")
                assert await page.locator('.service-photos a').count()==0
                before=await page.locator('.gallery-counter').inner_text()
                await page.locator('.service-photo img').first.click()
                assert await page.locator('.gallery-counter').inner_text()==before
                assert len(page.context.pages)==1 and await page.evaluate('window.__links.length')==0
                await page.get_by_role('button',name='Следующее фото',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.gallery-counter').textContent==='2 / 3'")
                await page.get_by_role('button',name='Предыдущее фото',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.gallery-counter').textContent==='1 / 3'")
                text=await page.locator('#service-view').inner_text()
                assert all(word not in text for word in ['Информация с сайта','Цены на сайте','Прайс на сайте','Контакты на сайте','О направлении'])
                assert await page.locator('.service-actions a[href^="tel:"]').count()==1
                if key=='restaurant':
                    assert await page.locator('#restaurant-menu').count()==1
                    assert await page.locator('#restaurant-booking').count()==1
                else:
                    assert await page.locator('#service-view button').filter(has_text='Запись').count()==0
                if key=='hotel':
                    assert 'IMG_9324' in await page.locator('.service-photo img').first.get_attribute('src')
                    assert await page.locator('a[href="tel:+78129262650"]').count()==1
                for theme in ['light','dark']:
                    await page.emulate_media(color_scheme=theme);await page.evaluate('window.scrollTo(0,0)');await page.wait_for_timeout(100)
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(ARTIFACTS/f'complex-{key}-{theme}-{width}.png'))
                await page.emulate_media(color_scheme='light')
                if key=='wake':
                    await page.locator('summary').filter(has_text='выходные и праздники').click()
                    assert await page.locator('.service-price-group[open]').count()==2
                if key=='hotel' and width==390:
                    await page.locator('.service-prices').scroll_into_view_if_needed();await page.screenshot(path=str(ARTIFACTS/'complex-hotel-prices-light-390.png'))
            await page.keyboard.press('Escape');assert await page.locator('#home-view').is_visible()
            await page.locator('#app-nav [data-view=more]').click()
            await page.locator('#more-actions').get_by_role('button',name='Волна',exact=True).click()
            await page.locator('#service-view .back-link').click();assert await page.locator('#more-view').is_visible()
            await page.locator('#app-close').click();assert await page.evaluate('window.__closed')==1
            assert not errors,errors
            results.append({'width':width,'directions':4,'themes':['light','dark'],'photos_inert':True,'phone_only_services':True,'fullscreen_and_close':'passed','errors':errors})
            await page.close()
        for mode in ['old','unsupported']:
            page=await browser.new_page(viewport={'width':390,'height':844})
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_mock(mode)))
            await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible')
            assert await page.evaluate('window.__fullscreenRequests')==(0 if mode=='old' else 1)
            assert await page.evaluate('window.__expandCalls')>0
            await page.locator('#app-close').click();assert await page.evaluate('window.__closed')==1
            results.append({'telegram_client':mode,'fallback_and_close':'passed'});await page.close()
        await browser.close()
    (ARTIFACTS/'complex-browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
