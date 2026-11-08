"""Exercise the Mini App cart through the UI against a local signed test API."""
import asyncio
import json
import re
import shutil
import threading
from copy import deepcopy
from http.server import ThreadingHTTPServer
from unittest.mock import AsyncMock

from playwright.async_api import async_playwright
import browser_preview_check as check
from menu_preview import preview_catalog
from test_menu_preview import MENU, SECTIONS, signed


def clean(value):
    return re.sub(r'\s+', ' ', value).strip()


async def total(page, value):
    assert clean(await page.locator('#cart-launcher-total').text_content()) == value


async def find_dish(page, name):
    if await page.locator('#cart-view').is_visible():
        await page.locator('#cart-back').click()
    await page.locator('#search').fill(name)
    await page.locator('.item-row').first.click()


async def main():
    menu=deepcopy(MENU)
    menu['snacks']['items'].append(['Блюдо без цены','Стоимость уточните у официанта','Цена уточняется'])
    check.bot.config=AsyncMock(return_value=(menu,SECTIONS,'',{}))
    server=ThreadingHTTPServer(('127.0.0.1',0),check.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
        for variant in (4,5):
            for width in (320,390,820):
                page=await browser.new_page(viewport={'width':width,'height':844})
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=check.telegram_stub(signed())))
                await page.goto(origin+f'/menu-preview?variant={variant}')
                await page.locator('#cart-launcher').wait_for(state='visible')
                await total(page,'0 ₽')
                for _ in range(2):
                    await find_dish(page,'Брускетты с ростбифом')
                    assert not await page.locator('#dish-add').is_disabled()
                    await page.locator('#dish-add').click()
                await total(page,'1 480 ₽')
                await page.locator('#cart-launcher').click()
                assert await page.locator('.cart-row').count()==1
                await page.locator('.cart-row').first.click()
                await page.locator('#quantity-plus').click()
                assert await page.locator('#quantity-value').text_content()=='3'
                await page.locator('#quantity-minus').click()
                await page.evaluate('window.__backHandler()')
                assert await page.locator('#cart-view').is_visible()
                await page.locator('#cart-back').click()
                assert await page.locator('#search').input_value()=='Брускетты с ростбифом'
                for label in ('Бутылка','Бокал'):
                    await find_dish(page,'Мальбек')
                    assert await page.locator('#dish-add').is_disabled()
                    await page.get_by_role('radio',name=re.compile(label)).check()
                    await page.locator('#dish-add').click()
                await find_dish(page,'Амбер')
                assert await page.locator('#dish-add').is_disabled()
                await page.get_by_role('radio',name=re.compile('500 мл')).check()
                await page.locator('#dish-add').click()
                await find_dish(page,'Эль Капулько')
                await page.get_by_role('radio',name=re.compile('^Безалкогольное')).check()
                await page.locator('#dish-add').click()
                await total(page,'7 150 ₽')
                await page.reload()
                await page.locator('#cart-launcher').wait_for(state='visible')
                await total(page,'7 150 ₽')
                assert await page.locator('#cart-badge').text_content()=='6'
                await page.locator('#cart-launcher').click()
                assert await page.locator('.cart-row').count()==5
                assert clean(await page.locator('#cart-total').text_content())=='7 150 ₽'
                assert await page.locator('.cart-row').evaluate_all('(rows)=>rows.every(b=>{const r=b.getBoundingClientRect();return r.height>=44 && r.right<=innerWidth && getComputedStyle(b.querySelector(".cart-row-name")).whiteSpace==="nowrap";})')
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                await page.screenshot(path=str(check.ROOT/'artifacts'/f'cart-{variant}-{width}.png'),full_page=True)
                await page.locator('.cart-row').first.click()
                assert 'Брускетты с ростбифом' in await page.locator('#dish-name').text_content()
                await page.locator('#dish-remove').click()
                assert await page.locator('.cart-row').count()==4
                assert clean(await page.locator('#cart-total').text_content())=='5 670 ₽'
                await page.locator('#cart-clear').click()
                await page.locator('#cart-clear-no').click()
                assert await page.locator('.cart-row').count()==4
                await page.locator('#cart-clear').click()
                await page.locator('#cart-clear-yes').click()
                assert await page.locator('#cart-empty').is_visible()
                await page.evaluate('window.__backHandler()')
                assert await page.locator('#menu-hub').is_visible()
                await find_dish(page,'Блюдо без цены')
                await page.locator('#dish-add').click()
                await total(page,'Сумма уточняется')
                await find_dish(page,'Брускетты с ростбифом')
                await page.locator('#dish-add').click()
                await page.locator('#cart-launcher').click()
                assert clean(await page.locator('#cart-total').text_content())=='740 ₽ + уточняется'
                assert await page.locator('#cart-price-note').is_visible()
                assert not errors,errors
                await page.close()

        # Restore 20 rows, including variants. Every row remains directly editable.
        page=await browser.new_page(viewport={'width':320,'height':844})
        await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=check.telegram_stub(signed())))
        await page.goto(origin+'/menu-preview?variant=4')
        await page.locator('#cart-launcher').wait_for(state='visible')
        catalog=preview_catalog(menu,SECTIONS)
        lines=[{'itemId':item['id'],'optionId':option['id'],'optionLabel':option['label'],'quantity':1,'amount':1} for cat in catalog['categories'] for item in cat['items'] for option in item['options'] if option['amount'] is not None][:20]
        await page.evaluate('(lines)=>localStorage.setItem("sunpark:menu-cart:v1:1",JSON.stringify({version:1,lines}))',lines)
        await page.reload()
        await page.locator('#cart-launcher').click()
        assert await page.locator('.cart-row').count()==20
        await page.locator('.cart-row').nth(17).click()
        await page.locator('#dish-remove').click()
        assert await page.locator('.cart-row').count()==19
        # Saved prices are never trusted: totals use current catalogue prices.
        single=[{'itemId':catalog['categories'][0]['items'][0]['id'],'optionId':'0','optionLabel':'','quantity':2,'amount':1}]
        menu['snacks']['items'][0][2]='800 ₽'
        await page.evaluate('(lines)=>localStorage.setItem("sunpark:menu-cart:v1:1",JSON.stringify({version:1,lines}))',single)
        await page.reload()
        await page.locator('#cart-launcher').wait_for(state='visible')
        await total(page,'1 600 ₽')
        # A removed dish and corrupt local data cannot leave an incorrect total.
        menu['snacks']['items'].pop(0)
        await page.reload()
        await page.locator('#cart-launcher').wait_for(state='visible')
        await total(page,'0 ₽')
        await page.evaluate('localStorage.setItem("sunpark:menu-cart:v1:1","broken json")')
        await page.reload()
        await page.locator('#cart-launcher').wait_for(state='visible')
        await total(page,'0 ₽')
        # Different Telegram accounts on the same device have separate drafts.
        await find_dish(page,'Батат')
        await page.locator('#dish-add').click()
        await total(page,'510 ₽')
        check.bot.is_manager=AsyncMock(side_effect=lambda uid,cfg:uid in (1,2))
        await page.unroute('https://telegram.org/js/telegram-web-app.js')
        await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=check.telegram_stub(signed(2))))
        await page.reload()
        await page.locator('#cart-launcher').wait_for(state='visible')
        await total(page,'0 ₽')
        await page.close()
        await browser.close()
    server.shutdown()
    print('PASS: cart in both themes at 320/390/820px; required variants, exact totals, merge/quantity/remove/clear, native Back, persistence, unknown prices, 20 rows, current menu prices, corrupt drafts and account isolation')


if __name__=='__main__':
    asyncio.run(main())
