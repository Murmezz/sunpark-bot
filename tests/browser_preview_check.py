"""Local browser checks; Telegram uses a dummy signed identity in this test only."""
import asyncio
import json
import sys
import threading
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'tests'))
from menu_preview import MenuPreviewMixin
from test_menu_preview import FakeResponse, Body, MENU, SECTIONS, TOKEN, signed
from playwright.async_api import async_playwright

bot=MenuPreviewMixin()
bot.env=NS(BOT_TOKEN=TOKEN)
bot.config=AsyncMock(return_value=(MENU,SECTIONS,'',{}))
bot.is_manager=AsyncMock(side_effect=lambda uid,cfg:uid==1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def handle_request(self):
        raw=self.rfile.read(min(21000,int(self.headers.get('Content-Length',0))))
        req=NS(url='http://127.0.0.1'+self.path,method=self.command,headers=self.headers,body=Body([raw]))
        with patch.dict(sys.modules,{'workers':NS(Response=FakeResponse)}):
            result=asyncio.run(bot.menu_preview_http(req))
        self.send_response(result.status if result else 404)
        for k,v in (result.headers if result else {}).items():
            self.send_header(k,v)
        self.end_headers()
        self.wfile.write((result.body if result else 'Not found').encode())
    do_GET=handle_request
    do_POST=handle_request


def telegram_stub(init):
    return 'window.Telegram={WebApp:{initData:'+json.dumps(init)+',ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){},BackButton:{show(){window.__backVisible=true;},hide(){window.__backVisible=false;},onClick(fn){window.__backHandler=fn;}},HapticFeedback:{selectionChanged(){}}}};'


async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    screenshots=ROOT/'artifacts'
    screenshots.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
        for variant in [4,5]:
            for width in [320,390,820]:
                page=await browser.new_page(viewport={'width':width,'height':844},device_scale_factor=1)
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=telegram_stub(signed())))
                await page.goto(origin+f'/menu-preview?variant={variant}')
                await page.locator('.category-card').first.wait_for()
                assert await page.locator('#theme-switch').count()==0
                assert await page.get_by_text('Сменить вид').count()==0
                assert await page.locator('#menu-hub').is_visible()
                assert not await page.locator('#catalog-view').is_visible()
                assert await page.locator('.category-card').evaluate_all('(cards)=>cards.every(c=>c.getBoundingClientRect().height>=72 && parseFloat(getComputedStyle(c.querySelector(".category-title")).fontSize)>=16)')
                assert await page.locator('#groups button').evaluate_all('(buttons)=>buttons.every(b=>b.getBoundingClientRect().height>=44 && parseFloat(getComputedStyle(b).fontSize)>=16)')
                assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                if variant==4:
                    await page.wait_for_function('document.getElementById("pdf-logo").complete && document.getElementById("pdf-logo").naturalWidth > 0')
                    assert await page.evaluate('getComputedStyle(document.body).backgroundImage.includes("data:image/webp;base64,")')
                    assert await page.evaluate('getComputedStyle(document.querySelector(".menu-paper")).borderTopColor')=='rgb(60, 115, 40)'
                if variant==5:
                    assert await page.evaluate('getComputedStyle(document.body).backgroundColor')=='rgb(20, 27, 25)'
                await page.screenshot(path=str(screenshots/f'hub-{variant}-{width}.png'),full_page=True)
                await page.get_by_role('button',name='Бар',exact=True).click()
                await page.locator('.category-card').first.click()
                assert 'Вино' in await page.locator('#section-title').inner_text()
                await page.locator('#back-to-sections').click()
                assert await page.locator('#menu-hub').is_visible()
                await page.get_by_role('button',name='Еда',exact=True).click()
                await page.locator('.category-card').filter(has_text='Закуски').click()
                assert await page.locator('.item-row').count()==14
                assert not await page.locator('#menu-hub').is_visible()
                assert await page.locator('#back-to-sections').evaluate('(b)=>b.getBoundingClientRect().height>=44')
                assert await page.locator('.item-row').evaluate_all('(rows)=>rows.every(row=>row.getBoundingClientRect().height>=60 && parseFloat(getComputedStyle(row.querySelector(".name")).fontSize)>=16 && parseFloat(getComputedStyle(row.querySelector(".price")).fontSize)>=15 && row.querySelector(".name").getBoundingClientRect().right <= row.querySelector(".price").getBoundingClientRect().left)')
                assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                await page.screenshot(path=str(screenshots/f'menu-{variant}-{width}.png'),full_page=True)
                await page.locator('.item-row').first.click()
                assert await page.locator('#dish-dialog').evaluate('(d)=>d.open')
                assert 'вялеными томатами' in await page.locator('#dish-description').inner_text()
                await page.locator('#back-to-menu').click()
                assert await page.evaluate('window.__backVisible')
                await page.locator('#search').fill('мальбек')
                assert await page.locator('.item-row').count()==1
                assert '4140 ₽' in await page.locator('.item-row .price').inner_text()
                await page.locator('.item-row').first.click()
                assert 'Красное' in await page.locator('#dish-section').inner_text()
                await page.locator('#close-dialog').click()
                await page.evaluate('window.__backHandler()')
                assert await page.locator('#menu-hub').is_visible()
                assert await page.locator('#search').input_value()==''
                assert not await page.evaluate('window.__backVisible')
                await page.locator('#search').fill('Брускетты')
                assert await page.locator('.item-row').count()==4
                await page.locator('#search').fill('неттакогоблюда')
                assert await page.locator('.item-row').count()==0
                assert 'Ничего не найдено' in await page.locator('#catalog-hint').inner_text()
                await page.locator('#search').fill('')
                assert await page.locator('#menu-hub').is_visible()
                assert not errors,errors
                await page.close()
        for init,expected in [('', 'Откройте меню'),(signed(2),'только администраторам')]:
            page=await browser.new_page()
            await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=telegram_stub(init)))
            await page.goto(origin+'/menu-preview')
            await page.wait_for_function('(text)=>document.getElementById("status").textContent.includes(text)',arg=expected)
            assert await page.locator('.item-row').count()==0
            await page.close()
        await browser.close()
    server.shutdown()
    print('PASS: both themes at 320/390/820px; large category buttons, readable text and full prices, group/category navigation, Telegram Back, search, dish details, auth rejection; no theme switch, overflow or JS errors')


if __name__=='__main__':
    asyncio.run(main())


