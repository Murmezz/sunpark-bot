import asyncio,json,os,sys,threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'src')]
import serve_mini_app as fixture
from browser_services_check import telegram_mock
from test_mini_app import AppHarness
OUT=Path('/workspace/claude-review')/ROOT.name;OUT.mkdir(parents=True,exist_ok=True)
PHOTOS=Path('/workspace/sites/sunpark-design-review/public/assets')
async def main():
 fixture.bot=AppHarness();await fixture.bot.config()
 server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 origin=f'http://127.0.0.1:{server.server_port}';engine=os.environ.get('SUNPARK_BROWSER','chromium');results=[]
 async with async_playwright() as p:
  browser=await (p.webkit.launch(headless=True) if engine=='webkit' else p.chromium.launch(executable_path='/usr/bin/chromium',headless=True))
  for width in [320,390,820]:
   context=await browser.new_context(viewport={'width':width,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)
   page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
   mock=telegram_mock()+"\nsdk.safeAreaInset={top:32,bottom:16,left:0,right:0};sdk.contentSafeAreaInset={top:56,bottom:0,left:0,right:0};"
   await page.route('https://telegram.org/js/telegram-web-app.js',lambda route:route.fulfill(content_type='text/javascript',body=mock))
   async def photos(route):
    url=unquote(route.request.url);name='hotel.png' if 'IMG_' in url or 'hotel' in url else 'wake.jpg' if 'wake' in url else 'wave.jpg' if 'Wave' in url else 'restaurant.jpg'
    await route.fulfill(body=(PHOTOS/name).read_bytes(),content_type='image/png' if name.endswith('png') else 'image/jpeg')
   await page.route('https://sunparkspb.ru/**',photos)
   await page.goto(origin+'/app-claude');await page.locator('#app-shell').wait_for(state='visible');await page.evaluate('document.fonts.ready')
   assert await page.title()=='SunPark · Клод тест'
   await page.locator('[id^=tg-mock]').evaluate_all("xs=>xs.forEach(e=>e.style.display='none')")
   for theme in ['light','dark']:
    await page.emulate_media(color_scheme=theme);await page.wait_for_timeout(160)
    async def check(name):
     await page.wait_for_timeout(220)
     assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme,name,'overflow')
     assert not errors,(width,theme,name,errors)
     if width==390:await page.screenshot(path=str(OUT/f'{engine}-{theme}-{name}.png'))
    await page.locator('#app-nav [data-view=home]').click();await check('home')
    computed=await page.locator('.direction-grid .service-card').first.evaluate("e=>{const s=getComputedStyle(e);return {radius:s.borderRadius,border:s.borderTopWidth,background:s.backgroundColor}}")
    await page.locator('[data-service=restaurant]').click();await check('restaurant')
    await page.locator('#restaurant-menu').click();await check('menu')
    await page.locator('.item-open').first.click();await page.locator('#dish-dialog').wait_for(state='visible');await check('dish')
    await page.keyboard.press('Escape');await page.locator('#app-nav [data-view=home]').click()
    await page.locator('[data-service=hotel]').click();await check('hotel')
    await page.locator('#app-nav [data-view=inbox]').click();await check('inbox')
    assert await page.locator('#app-nav button[aria-current=page]').count()==1
    results.append({'width':width,'theme':theme,'states':6,'card':computed,'errors':errors.copy()})
   await context.close()
  await browser.close()
 server.shutdown();(OUT/f'{engine}-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps({'engine':engine,'results':results},ensure_ascii=False),flush=True)
if __name__=='__main__':asyncio.run(main())
