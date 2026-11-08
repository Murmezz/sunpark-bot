"""Regression: scrolling a dish must never move the menu or detach the sheet."""
import asyncio
import shutil
import threading
from copy import deepcopy
from http.server import ThreadingHTTPServer
from unittest.mock import AsyncMock

from playwright.async_api import async_playwright
import browser_preview_check as check
from test_menu_preview import MENU, SECTIONS, signed


async def snapshot(page):
    return await page.evaluate('''() => {
      const d=document.getElementById('dish-dialog'), r=d.getBoundingClientRect();
      return {y:scrollY,background:document.querySelector('.menu-paper').getBoundingClientRect().top,
        top:r.top,bottom:r.bottom,height:innerHeight,position:getComputedStyle(d).position,scroll:d.scrollTop};
    }''')


async def swipe(page,client,x,start,end):
    await client.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':start}]})
    for step in range(1,9):
        await client.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':start+(end-start)*step/8}]})
        await page.wait_for_timeout(20)
    await client.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    await page.wait_for_timeout(150)


async def anchored(page,expected_background,mobile):
    state=await snapshot(page)
    assert state['position']=='fixed',state
    assert state['top']>=-1 and state['bottom']<=state['height']+1,state
    if mobile:
        assert abs(state['bottom']-state['height'])<=1,state
    assert abs(state['background']-expected_background)<=1,state
    return state


async def main():
    menu=deepcopy(MENU)
    menu['snacks']['items'] += [
        ['Ведьмино болото · безалкогольный + десерт','Безалкогольный коктейль и десерт из Halloween-меню','750 ₽'],
        ['Позиция с длинным составом','Подробный состав и подача блюда. '*80,'800 ₽'],
    ]
    check.bot.config=AsyncMock(return_value=(menu,SECTIONS,'',{}))
    server=ThreadingHTTPServer(('127.0.0.1',0),check.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
        for variant in (4,5):
            for width in (320,390,820):
                page=await browser.new_page(viewport={'width':width,'height':730},is_mobile=width<600,has_touch=True)
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=check.telegram_stub(signed())))
                await page.goto(f'http://127.0.0.1:{server.server_port}/menu-preview?variant={variant}')
                await page.locator('.category-card').filter(has_text='Закуски').click()
                short=page.locator('.item-row').filter(has_text='Ведьмино болото')
                await short.scroll_into_view_if_needed()
                before=await snapshot(page)
                assert before['y']>300,before
                await short.click()
                await page.wait_for_timeout(180)
                initial=await anchored(page,before['background'],width<600)
                await page.mouse.move(width/2,initial['top']+80)
                await page.mouse.wheel(0,500)
                await page.wait_for_timeout(150)
                await anchored(page,before['background'],width<600)
                client=await page.context.new_cdp_session(page)
                await swipe(page,client,width/2,min(650,initial['bottom']-50),max(initial['top']+30,250))
                await anchored(page,before['background'],width<600)
                await page.screenshot(path=str(check.ROOT/'artifacts'/f'scroll-fixed-{variant}-{width}.png'))
                await page.locator('#back-to-menu').click()
                assert abs(await page.evaluate('scrollY')-before['y'])<=1
                assert not await page.locator('body').evaluate('(body)=>body.classList.contains("modal-open")')

                long=page.locator('.item-row').filter(has_text='Позиция с длинным составом')
                await long.scroll_into_view_if_needed()
                before=await snapshot(page)
                await long.click()
                await page.wait_for_timeout(180)
                initial=await anchored(page,before['background'],width<600)
                assert initial['scroll']==0,initial
                await page.mouse.move(width/2,initial['top']+100)
                await page.mouse.wheel(0,600)
                await page.wait_for_timeout(150)
                state=await anchored(page,before['background'],width<600)
                assert state['scroll']>0,state
                # Reaching either end must not chain the scroll to the page.
                for amount in (10000,10000,-10000,-10000):
                    await page.mouse.wheel(0,amount)
                    await page.wait_for_timeout(80)
                    await anchored(page,before['background'],width<600)
                await page.set_viewport_size({'width':width,'height':600})
                await page.wait_for_timeout(100)
                await anchored(page,before['background'],width<600)
                await page.set_viewport_size({'width':width,'height':730})
                await page.evaluate('window.__backHandler()')
                assert abs(await page.evaluate('scrollY')-before['y'])<=1
                # All close paths release the lock, including Escape and backdrop.
                for method in ('escape','backdrop','close','add'):
                    await long.click()
                    await page.wait_for_timeout(180)
                    assert (await snapshot(page))['scroll']==0
                    if method=='escape':
                        await page.keyboard.press('Escape')
                    elif method=='backdrop':
                        await page.mouse.click(1,1)
                    elif method=='close':
                        await page.locator('#close-dialog').click()
                    else:
                        await page.locator('#dish-add').click()
                    assert not await page.locator('#dish-dialog').evaluate('(d)=>d.open')
                    assert not await page.locator('html').evaluate('(el)=>el.classList.contains("modal-open")')
                    assert abs(await page.evaluate('scrollY')-before['y'])<=1
                assert not errors,errors
                await page.close()
        await browser.close()
    server.shutdown()
    print('PASS: fixed dialog at 320/390/820px in both themes; wheel/touch stay inside, background preserved, long content scrolls, viewport resize, all close paths restore the menu position')


if __name__=='__main__':
    asyncio.run(main())
