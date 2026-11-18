"""Cart quantities stay in sync across menu, option sheet, cart and reloads."""
import asyncio
import json
import os
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from playwright.async_api import async_playwright, expect
import serve_mini_app as fixture
from browser_services_check import telegram_mock
from test_mini_app import AppHarness

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'cart-brand'
PHOTOS = Path('/workspace/sites/sunpark-design-review/public/assets')


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fixture.bot = AppHarness()
    await fixture.bot.config()
    server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    engine = os.environ.get('SUNPARK_BROWSER', 'chromium')
    results = []
    async with async_playwright() as p:
        browser = await (p.webkit.launch(headless=True) if engine == 'webkit' else p.chromium.launch(executable_path='/usr/bin/chromium', headless=True))
        for width in [280, 393]:
            for route in ['/app', '/app-claude']:
                for theme in ['light', 'dark']:
                    context = await browser.new_context(viewport={'width': width, 'height': 853}, color_scheme=theme, is_mobile=True, has_touch=True)
                    page = await context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    await page.route('https://telegram.org/js/telegram-web-app.js', lambda r: r.fulfill(content_type='text/javascript', body=telegram_mock()))
                    async def photos(r):
                        url = unquote(r.request.url)
                        name = 'hotel.png' if 'IMG_' in url or 'hotel' in url else 'wake.jpg' if 'wake' in url else 'wave.jpg' if 'Wave' in url else 'restaurant.jpg'
                        await r.fulfill(body=(PHOTOS / name).read_bytes(), content_type='image/png' if name.endswith('png') else 'image/jpeg')
                    await page.route('https://sunparkspb.ru/**', photos)

                    async def menu(reload=False):
                        await (page.reload() if reload else page.goto(origin + route))
                        await page.locator('#app-shell').wait_for(state='visible')
                        await page.locator('[id^=tg-mock]').evaluate_all("xs=>xs.forEach(e=>e.style.display='none')")
                        assert await page.title() == 'SunPark' + (' · Клод тест' if route.endswith('claude') else '')
                        await page.locator('[data-service=restaurant]').click()
                        await page.locator('#restaurant-menu').click()

                    async def check_layout():
                        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (width, route, theme)
                        assert not errors, errors

                    await menu()
                    row = page.locator('.item-row').first
                    quantity = row.locator('.item-quantity')
                    await row.locator('.item-add').click()
                    await expect(quantity).to_have_text('1')
                    await expect(row.locator('.item-add')).to_be_enabled()
                    await row.locator('.item-add').click()
                    await row.locator('.item-add').click()
                    await expect(quantity).to_have_text('3')
                    await expect(page.locator('#cart-badge')).to_have_text('3')
                    await check_layout()
                    if width == 393:
                        await page.wait_for_timeout(220)
                        await page.screenshot(path=str(OUT / f'{engine}-{route[1:]}-{theme}-quantity.png'))
                    unit = float(re.sub(r'[^\d,.]', '', await row.locator('.price').inner_text()).replace(',', '.'))
                    await row.locator('.item-open').click()
                    await expect(page.locator('#quantity-value')).to_have_text('3')
                    await page.locator('#quantity-minus').click()
                    await page.locator('#dish-add').click()
                    await expect(quantity).to_have_text('2')
                    await menu(reload=True)
                    await expect(quantity).to_have_text('2')
                    await page.locator('#cart-launcher').click()
                    total = float(re.sub(r'[^\d,.]', '', await page.locator('#cart-total').inner_text()).replace(',', '.'))
                    assert total == unit * 2
                    await page.locator('.cart-stepper [data-change="1"]').click()
                    await page.locator('.cart-product').click()
                    await expect(page.locator('#quantity-value')).to_have_text('3')
                    for _ in range(3):
                        await page.locator('#quantity-minus').click()
                    await expect(page.locator('#quantity-value')).to_have_text('0')
                    await page.locator('#dish-add').click()
                    await expect(page.locator('.cart-stepper output')).to_have_text('1')
                    await page.locator('.cart-stepper [data-change="-1"]').click()
                    await expect(page.locator('#cart-empty')).to_be_visible()
                    await page.locator('#cart-back').click()
                    await expect(quantity).to_be_hidden()

                    # Two independently priced options share an aggregate menu count.
                    await page.locator('#groups').get_by_role('button', name='Бар', exact=True).click()
                    await page.locator('[data-category=beer]').click()
                    beer = page.locator('.item-row').first
                    for option in [0, 1]:
                        await beer.locator('.item-add').click()
                        await page.locator('#dish-option-list input').nth(option).check()
                        await page.locator('#dish-add').click()
                    await expect(beer.locator('.item-quantity')).to_have_text('2')
                    await beer.locator('.item-minus').click()
                    await expect(page.locator('#dish-option-list .option-cart-count').first).to_have_text('В корзине: 1')
                    await page.locator('#dish-option-list input').first.check()
                    await page.locator('#quantity-minus').click()
                    await page.locator('#close-dialog').click()
                    await expect(beer.locator('.item-quantity')).to_have_text('1')
                    await beer.locator('.item-minus').click()
                    await expect(beer.locator('.item-quantity')).to_be_hidden()
                    await expect(page.locator('#cart-launcher')).to_be_hidden()
                    await check_layout()

                    # Stored quantities keep the existing 99-per-option bound.
                    await page.locator('#groups').get_by_role('button', name='Еда', exact=True).click()
                    await row.locator('.item-add').click()
                    await page.evaluate("()=>{const k='sunpark:menu-cart:v1:1',v=JSON.parse(localStorage.getItem(k));v.lines[0].quantity=99;localStorage.setItem(k,JSON.stringify(v));}")
                    await menu(reload=True)
                    await expect(quantity).to_have_text('99')
                    await expect(row.locator('.item-add')).to_be_disabled()
                    await row.locator('.item-minus').click()
                    await expect(quantity).to_have_text('98')
                    await expect(row.locator('.item-add')).to_be_enabled()
                    await page.locator('#cart-launcher').click()
                    await page.locator('#cart-clear').click()
                    await page.locator('#cart-clear-yes').click()
                    await page.locator('#cart-back').click()
                    await expect(quantity).to_be_hidden()
                    await check_layout()
                    results.append({'width': width, 'route': route, 'theme': theme, 'single_and_multiple_options': True, 'reload_and_limits': True, 'errors': errors})
                    print(json.dumps(results[-1], ensure_ascii=False), flush=True)
                    await context.close()
        await browser.close()
    server.shutdown()
    (OUT / f'{engine}-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
