"""Touch menu regressions: released controls, sealed sticky stack, pinned bottom UI."""
import asyncio,json,os,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import unquote
from playwright.async_api import async_playwright,expect
import serve_mini_app as fixture
from browser_services_check import telegram_mock
from test_mini_app import AppHarness

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/menu-chrome'
PHOTOS=Path('/workspace/sites/sunpark-design-review/public/assets')

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    fixture.bot=AppHarness();await fixture.bot.config()
    server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    engine=os.environ.get('SUNPARK_BROWSER','chromium');baseline=bool(os.environ.get('SUNPARK_BASELINE'));results=[]
    async with async_playwright() as p:
        browser=await (p.webkit.launch(headless=True) if engine=='webkit' else p.chromium.launch(executable_path='/usr/bin/chromium',headless=True))
        async def photos(route):
            url=unquote(route.request.url);name='hotel.png' if 'IMG_' in url or 'hotel' in url else 'wake.jpg' if 'wake' in url else 'wave.jpg' if 'Wave' in url else 'restaurant.jpg'
            await route.fulfill(body=(PHOTOS/name).read_bytes(),content_type='image/png' if name.endswith('png') else 'image/jpeg')
        profiles=[(320,640,20,48,0),(393,853,32,56,16),(430,932,59,56,34),(844,390,0,48,21)]
        for width,height,top,chrome,bottom in profiles:
            if os.environ.get('SUNPARK_WIDTHS') and str(width) not in os.environ['SUNPARK_WIDTHS'].split(','):continue
            for theme in ['dark','light']:
                context=await browser.new_context(viewport={'width':width,'height':height},is_mobile=True,has_touch=True,color_scheme=theme)
                page=await context.new_page();page.set_default_timeout(10000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                mock=telegram_mock()+f"\nsdk.safeAreaInset={{top:{top},bottom:{bottom},left:0,right:0}};sdk.contentSafeAreaInset={{top:{chrome},bottom:0,left:0,right:0}};window.__disableSwipesCalls=0;sdk.disableVerticalSwipes=()=>{{window.__disableSwipesCalls++;sdk.isVerticalSwipesEnabled=false;}};"
                await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=mock))
                await page.route('https://sunparkspb.ru/**',photos)
                await page.goto(f'http://127.0.0.1:{server.server_port}/app-claude');await page.locator('#app-shell').wait_for(state='visible');await page.evaluate('document.fonts.ready')
                await page.locator('[id^=tg-mock]').evaluate_all('xs=>xs.forEach(e=>e.remove())')
                await page.locator('[data-service=restaurant]').tap();await page.locator('#restaurant-menu').tap()
                row=page.locator('.item-row').first;plus=row.locator('.item-add');minus=row.locator('.item-minus');quantity=row.locator('.item-quantity')
                touch=[]
                for control,count in [(plus,'1'),(plus,'2'),(minus,'1')]:
                    await control.tap();await expect(quantity).to_have_text(count);await page.wait_for_timeout(180)
                    touch.append(await control.evaluate("e=>({hover:e.matches(':hover'),background:getComputedStyle(e).backgroundColor,transform:getComputedStyle(e).transform,focusVisible:e.matches(':focus-visible')})"))
                findings=[]
                if any(x['background'] not in ['rgba(0, 0, 0, 0)','transparent'] for x in touch):findings.append('touch-hover-retained')
                if any(x['transform']!='none' for x in touch):findings.append('touch-press-retained')
                await page.screenshot(path=str(OUT/(f'{engine}-{theme}-{width}-'+('before' if baseline else 'after')+'-touch.png')))
                await page.evaluate('window.scrollTo(0,600)');await page.wait_for_timeout(220)
                stack=await page.evaluate("""()=>{const b=document.querySelector('#back-to-sections'),c=document.querySelector('#categories'),br=b.getBoundingClientRect(),cr=c.getBoundingClientRect();return {gap:cr.top-br.bottom,back:br.toJSON(),rail:cr.toJSON(),position:getComputedStyle(c).position};}""")
                if stack['position']=='sticky' and abs(stack['gap'])>1:findings.append('gap-between-sticky-bars')
                if stack['position']=='sticky':
                    sealed=await page.evaluate("""()=>{const c=document.querySelector('#categories').getBoundingClientRect(),b=document.querySelector('#back-to-sections').getBoundingClientRect();let bad=[];for(let y=Math.ceil(b.bottom)+1;y<c.top+8;y+=2){const e=document.elementFromPoint(innerWidth/2,y);if(e&&!e.closest('#categories,#back-to-sections'))bad.push({y,tag:e.tagName,cls:e.className});}return bad;}""")
                    if sealed:findings.append('content-visible-in-sticky-gap')
                else:sealed=[]
                nav=[]
                for y in [0,200,600,100000,0]:
                    await page.evaluate('(y)=>window.scrollTo(0,y)',y);await page.wait_for_timeout(60)
                    nav.append(await page.locator('#app-nav').evaluate("e=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom,height:e.getBoundingClientRect().height,position:getComputedStyle(e).position,viewport:innerHeight})"))
                if any(x['position']!='fixed' or abs(x['bottom']-x['viewport'])>1 for x in nav) or max(x['top'] for x in nav)-min(x['top'] for x in nav)>1:findings.append('navigation-moved-on-scroll')
                calls=await page.evaluate('window.__disableSwipesCalls')
                if calls!=1:findings.append('host-vertical-swipes-enabled')
                await page.evaluate('window.scrollTo(0,600)');await page.wait_for_timeout(120)
                launcher=await page.locator('#cart-launcher').bounding_box();bar=await page.locator('#app-nav').bounding_box()
                assert launcher['y']+launcher['height']<=bar['y']+1
                await page.screenshot(path=str(OUT/(f'{engine}-{theme}-{width}-'+('before' if baseline else 'after')+'-scroll.png')))
                # Keyboard hides the nav, blur restores its original bottom anchor.
                await page.evaluate('window.scrollTo(0,0)');await page.locator('#search').focus()
                await page.set_viewport_size({'width':width,'height':max(270,height-250)})
                if height>=640:
                    await page.wait_for_function("()=>document.body.classList.contains('is-keyboard-open')")
                    assert await page.locator('#app-nav').is_hidden()
                await page.set_viewport_size({'width':width,'height':height});await page.locator('#search').blur()
                await page.wait_for_function("()=>!document.body.classList.contains('is-keyboard-open')")
                assert await page.locator('#app-nav').is_visible()
                assert await page.locator('#app-nav').evaluate('e=>Math.abs(e.getBoundingClientRect().bottom-innerHeight)<1')
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                result={'engine':engine,'viewport':[width,height],'theme':theme,'touch':touch,'stack':stack,'exposed_gap':sealed,'nav':nav,'host_swipe_disable_calls':calls,'findings':findings,'errors':errors}
                results.append(result);print(json.dumps({k:result[k] for k in ['engine','viewport','theme','findings']},ensure_ascii=False),flush=True)
                await context.close()
        if not baseline:
            # Mouse hover and keyboard focus must remain useful; old SDKs must load.
            for mode in ['desktop','old-sdk']:
                context=await browser.new_context(viewport={'width':393,'height':853})
                page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                mock=telegram_mock('old' if mode=='old-sdk' else 'modern')+"\nwindow.__disableSwipesCalls=0;sdk.disableVerticalSwipes=()=>window.__disableSwipesCalls++;"
                await page.route('https://telegram.org/js/telegram-web-app.js',lambda r:r.fulfill(content_type='text/javascript',body=mock))
                await page.route('https://sunparkspb.ru/**',photos)
                await page.goto(f'http://127.0.0.1:{server.server_port}/app-claude');await page.locator('#app-shell').wait_for(state='visible')
                await page.locator('[id^=tg-mock]').evaluate_all('xs=>xs.forEach(e=>e.remove())')
                await page.locator('[data-service=restaurant]').click();await page.locator('#restaurant-menu').click()
                plus=page.locator('.item-add').first
                if mode=='desktop':
                    await plus.hover();assert await plus.evaluate("e=>getComputedStyle(e).backgroundColor!=='rgba(0, 0, 0, 0)'")
                    await page.keyboard.press('Tab');await plus.focus()
                    assert await plus.evaluate("e=>e.matches(':focus-visible')&&getComputedStyle(e).outlineStyle!=='none'")
                else:
                    await plus.click();await expect(page.locator('.item-quantity').first).to_have_text('1')
                    assert await page.evaluate('window.__disableSwipesCalls===0')
                assert not errors,errors
                results.append({'engine':engine,'mode':mode,'findings':[],'errors':errors});await context.close()
        await browser.close()
    server.shutdown();(OUT/(f'{engine}-'+('before' if baseline else 'after')+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))
    if not baseline:assert all(not x['findings'] for x in results),results

if __name__=='__main__':asyncio.run(main())
