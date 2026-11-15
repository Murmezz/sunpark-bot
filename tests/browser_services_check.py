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
    threading.Thread(target=server.serve_forever,daemon=True).start();origin=f'http://127.0.0.1:{server.server_port}';results=[]
    async with async_playwright() as p:
        proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None
        browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,proxy=proxy)
        for width in [320,390,820]:
            fixture.bot=AppHarness();await fixture.bot.config()
            page=await browser.new_page(viewport={'width':width,'height':844},color_scheme='light',has_touch=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_mock()))
            await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible')
            assert await page.title()=='Sunpark'
            assert await page.locator('#home-services .service-card').count()==4
            assert await page.locator('.app-header,#home-inbox,#app-close').count()==0
            assert await page.locator('#app-nav button').all_text_contents()==['Главная','Сообщения']
            assert await page.locator('#cart-launcher').is_hidden()
            for key,title in [('wake','Вейк'),('wave','Волна'),('restaurant','Ресторан'),('hotel','Отель')]:
                await page.locator('#home-services [data-service='+key+']').click()
                await page.get_by_role('heading',name=title,exact=True).wait_for()
                assert await page.locator('.service-tabs').count()==0
                await page.wait_for_function("()=>{const i=document.querySelector('.service-photos img');return i.complete&&i.naturalWidth>0}")
                assert await page.locator('#service-view a').evaluate_all("links=>links.every(a=>a.getAttribute('href').startsWith('tel:')||a.href.startsWith('https://yandex.ru/maps/'))")
                assert await page.locator('.service-photos a').count()==0
                before=await page.locator('.gallery-counter').inner_text();await page.locator('.service-photo img').first.click()
                assert await page.locator('.gallery-counter').inner_text()==before
                assert len(page.context.pages)==1 and await page.evaluate('window.__links.length')==0
                await page.get_by_role('button',name='Следующее фото',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.gallery-counter').textContent==='2 / 3'")
                await page.get_by_role('button',name='Предыдущее фото',exact=True).click()
                await page.wait_for_function("()=>document.querySelector('.gallery-counter').textContent==='1 / 3'")
                assert await page.locator('.service-call[href^="tel:"]').count()==1
                await page.locator('.service-about > summary').click()
                assert await page.locator('.service-description').is_visible()
                text=await page.locator('#service-view').inner_text()
                assert all(word not in text for word in ['Информация с сайта','Цены на сайте','Прайс на сайте','Сайт ресторана'])
                if key=='restaurant':
                    assert await page.locator('#restaurant-menu,#restaurant-booking,#restaurant-banquet').count()==3
                    assert await page.locator('#cart-launcher').is_hidden()
                if key=='hotel':
                    assert 'IMG_9324' in await page.locator('.service-photo img').first.get_attribute('src')
                    assert await page.locator('a[href="tel:+78129262650"]').count()==1
                if key=='wake':
                    await page.locator('summary').filter(has_text='выходные и праздники').click()
                    assert await page.locator('.service-price-group[open]').count()==2
                for theme in ['light','dark']:
                    await page.emulate_media(color_scheme=theme);await page.evaluate('window.scrollTo(0,0)');await page.wait_for_timeout(180)
                    await page.locator('[id^=tg-mock]').evaluate_all("elements=>elements.forEach(e=>e.style.opacity='0')")
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(ARTIFACTS/f'refined-{key}-{theme}-{width}.png'))
                await page.get_by_role('button',name='На главную',exact=True).click()
            await page.locator('#app-nav [data-view=inbox]').click();await page.get_by_role('heading',name='Пока нет обращений',exact=True).wait_for()
            for label in ['Забронировать стол','Провести банкет','Написать менеджеру']:
                await page.get_by_role('button',name=label,exact=True).click()
                await page.wait_for_function("()=>document.getElementById('native-content').getAttribute('aria-busy')!=='true'")
                assert await page.locator('#view-back-label').inner_text()=='К сообщениям'
                await page.locator('#native-back').click();await page.get_by_role('heading',name='Пока нет обращений',exact=True).wait_for()
                assert await page.locator('#view-back-label').inner_text()=='На главную'
            await page.get_by_role('button',name='Управление',exact=True).click();assert await page.locator('#more-view').is_visible()
            await page.locator('#native-back').click();await page.get_by_role('heading',name='Пока нет обращений',exact=True).wait_for()
            await page.locator('#app-nav [data-view=home]').click();await page.locator('#home-services [data-service=restaurant]').click();await page.locator('#restaurant-menu').click()
            assert await page.locator('.item-open').count()>0
            await page.locator('.item-add').first.click();assert await page.locator('#cart-launcher').is_visible()
            await page.locator('#back-to-sections').click();assert await page.locator('#service-view').is_visible();assert await page.locator('#cart-launcher').is_visible()
            await page.locator('#app-nav [data-view=home]').click();assert await page.locator('#cart-launcher').is_hidden()
            await page.locator('#home-location').get_by_role('button',name='Контакты',exact=True).click()
            assert await page.get_by_role('link',name='Сайт ресторана',exact=True).count()==0
            await page.get_by_role('button',name='Закрыть приложение',exact=True).click();assert await page.evaluate('window.__closed')==1
            assert not errors,errors
            results.append({'width':width,'directions':4,'themes':['light','dark'],'photos_inert':True,'phone_and_map_only':True,'empty_cart_hidden':True,'forms_and_return':'passed','errors':errors});await page.close()
        for mode in ['old','unsupported']:
            page=await browser.new_page(viewport={'width':390,'height':844})
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=telegram_mock(mode)))
            await page.goto(origin+'/app');await page.locator('#app-shell').wait_for(state='visible')
            assert await page.evaluate('window.__fullscreenRequests')==(0 if mode=='old' else 1)
            assert await page.evaluate('window.__expandCalls')>0
            await page.locator('#home-location').get_by_role('button',name='Контакты',exact=True).click()
            await page.get_by_role('button',name='Закрыть приложение',exact=True).click();assert await page.evaluate('window.__closed')==1
            results.append({'telegram_client':mode,'fallback_and_close':'passed'});await page.close()
        await browser.close()
    (ARTIFACTS/'audit-service-browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
