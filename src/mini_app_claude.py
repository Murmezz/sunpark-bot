"""'Клод тест': the same Mini App logic with a refreshed visual layer.

Served at /app-claude. HTML structure, JavaScript and API are shared with /app;
only an extra stylesheet is appended, so nothing here can change behaviour.
"""
from mini_app_assets import APP_CSS, APP_HTML

CLAUDE_EXTRA_CSS = r"""
/* ===== Клод тест: tokens ===== */
:root{--card:#fffdf7;--r:18px;--r-sm:14px;--ring:rgba(23,62,43,.22);
--shadow:0 1px 2px rgba(23,56,41,.06),0 10px 26px -14px rgba(23,56,41,.28);
--shadow-sm:0 1px 2px rgba(23,56,41,.08);--hairline:rgba(191,179,155,.55);--nav-bg:rgba(248,245,235,.88)}
@media(prefers-color-scheme:dark){:root:not([data-theme]){--card:#16261f;--ring:rgba(155,181,132,.32);
--shadow:0 1px 0 rgba(255,255,255,.04) inset,0 12px 28px -16px rgba(0,0,0,.7);--shadow-sm:0 1px 0 rgba(255,255,255,.04) inset;
--hairline:rgba(78,88,73,.8);--nav-bg:rgba(16,28,24,.88)}}
:root[data-theme=dark]{--card:#16261f;--ring:rgba(155,181,132,.32);
--shadow:0 1px 0 rgba(255,255,255,.04) inset,0 12px 28px -16px rgba(0,0,0,.7);--shadow-sm:0 1px 0 rgba(255,255,255,.04) inset;
--hairline:rgba(78,88,73,.8);--nav-bg:rgba(16,28,24,.88)}

/* ===== Typography: one consistent heading voice ===== */
.page-title,.ruled-title,.service-view h2,#home-services-title,.home-services h2{
font-family:'Cormorant Garamond',Georgia,serif;font-weight:400;letter-spacing:-.2px}
.page-title,.service-view>.page-title,#menu-hub>.page-title{font-size:34px;line-height:1.1;margin:14px 0 18px}
.home-services h2,#home-services-title{font-size:27px;line-height:1.15;margin:0 0 16px}
.complex-intro p{color:var(--muted);line-height:1.55}
body{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}

/* ===== Back link and header ===== */
.back-link{border-radius:12px;padding-right:10px;transition:background .15s}
.back-link:active{background:var(--soft)}

/* ===== Home: direction cards ===== */
.direction-grid{gap:14px}
.direction-grid .service-card{border:0;border-radius:var(--r);background:var(--card);box-shadow:var(--shadow);
transition:transform .15s ease,box-shadow .15s ease}
.service-card:active{transform:scale(.975)}
.service-card .service-thumbnail,.service-card img{border-radius:0}
.direction-grid .service-card-copy{padding:13px 14px 16px;gap:5px}
.direction-grid .service-card-copy strong,.direction-grid .service-card-copy h3{font-family:'Cormorant Garamond',Georgia,serif;
font-size:26px;line-height:1.05;font-weight:400;letter-spacing:-.2px;color:var(--ink)}
.service-card-copy span,.service-card-copy small{color:var(--muted);line-height:1.4}
.home-location{margin-top:22px;padding-top:18px;border-top:1px solid var(--hairline)}
.home-location button,.home-location a{display:inline-flex;align-items:center;min-height:40px;padding:0 16px;margin:6px 8px 0 0;
border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--green);
text-decoration:none;font-size:14px;font-weight:600;box-shadow:var(--shadow-sm)}

/* ===== Menu ===== */
.search{border-radius:16px;background:var(--card);box-shadow:var(--shadow-sm);border-color:var(--hairline)}
.search:focus-within{outline:2px solid var(--green);outline-offset:0}
#groups.group-tabs button{border-radius:14px;border:1px solid var(--hairline);background:var(--card);font-weight:600;
min-height:44px;padding:10px 16px;transition:background .15s,color .15s}
#groups.group-tabs button[aria-pressed=true]{background:var(--green);color:var(--button-ink);border-color:var(--green)}
#groups.group-tabs{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;gap:8px;border-bottom:0}
#groups.group-tabs::-webkit-scrollbar{display:none}
.category-rail{box-shadow:0 1px 0 var(--hairline);gap:8px}
.category-rail button,.category-rail a{border-radius:999px;border:1px solid var(--hairline);background:var(--card);
min-height:42px;padding:0 18px;font-weight:600;white-space:nowrap;box-shadow:var(--shadow-sm)}
.category-rail [aria-pressed=true],.category-rail [aria-current=true],.category-rail .active{background:var(--green);color:var(--button-ink);border-color:var(--green)}
.items{display:grid;gap:10px}
.item-row{background:var(--card);border:0;border-radius:var(--r);box-shadow:var(--shadow-sm);padding:12px 12px 12px 16px;min-height:84px}
.item-row .name{font-weight:600;font-size:16.5px;line-height:1.3;color:var(--ink)}
.item-row .desc,.item-row small,.item-row .description{color:var(--muted);font-size:13.5px;line-height:1.45;margin-top:3px}
.item-row .price{font-weight:700;font-size:15px;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.item-open{grid-template-columns:minmax(0,1fr) auto}
.item-open>.icon,.item-open>svg{display:none}
.item-add{width:44px;height:44px;border:0;border-radius:50%;background:var(--green);color:var(--button-ink);
box-shadow:0 4px 12px -4px rgba(23,62,43,.55);transition:transform .12s}
.item-add:active{transform:scale(.9)}
.item-add .icon{width:22px;height:22px}
.subsection,.items h3{font-family:'Cormorant Garamond',Georgia,serif;font-size:24px;font-weight:400;margin:18px 2px 4px}

/* ===== Cart ===== */
.cart-launcher{border-radius:18px;box-shadow:0 14px 30px -12px rgba(0,0,0,.45);border:0}
.cart-row{background:var(--card);border-radius:var(--r-sm);box-shadow:var(--shadow-sm);margin-bottom:8px;padding:12px 14px}
.cart-summary{border-radius:var(--r);background:var(--card);box-shadow:var(--shadow-sm);padding:14px 16px}
.cart-toast{border-radius:14px;box-shadow:0 12px 28px -10px rgba(0,0,0,.5)}

/* ===== Buttons and fields ===== */
.primary-button{border-radius:var(--r-sm);min-height:54px;font-size:17px;letter-spacing:.1px;
box-shadow:0 8px 18px -10px rgba(23,62,43,.7);transition:transform .12s,box-shadow .12s}
.primary-button:active{transform:scale(.985);box-shadow:none}
.secondary-button{border-radius:var(--r-sm);min-height:50px;border:1px solid var(--hairline);background:var(--card);box-shadow:var(--shadow-sm)}
input,textarea,select{border-radius:var(--r-sm);border-color:var(--hairline);background:var(--card);transition:border-color .15s,box-shadow .15s}
input:focus,textarea:focus,select:focus{outline:0;border-color:var(--green);box-shadow:0 0 0 4px var(--ring)}

/* ===== Service pages ===== */
.service-view .service-facts{padding:16px;border-radius:var(--r);background:var(--card);box-shadow:var(--shadow-sm);margin:18px 0}
.service-notice{border-radius:var(--r-sm);border-left:3px solid var(--accent);background:var(--soft)}
.service-gallery{border-radius:var(--r);overflow:hidden;box-shadow:var(--shadow)}
.service-gallery img{display:block;width:100%}
.photo-fallback{text-decoration:none!important;color:var(--muted);background:linear-gradient(135deg,var(--soft),var(--card))}
.gallery-controls .icon-button{background:color-mix(in srgb,var(--paper) 82%,transparent);backdrop-filter:blur(8px);border-color:transparent;box-shadow:var(--shadow-sm)}
.gallery-counter{background:color-mix(in srgb,var(--paper) 78%,transparent);backdrop-filter:blur(8px);border-radius:999px;padding:4px 12px}
.service-price-group{border:0;border-radius:var(--r);background:var(--card);box-shadow:var(--shadow-sm);padding:0 14px 6px;margin:0 0 12px}
.service-price-row:last-child{border-bottom:0}
.service-link,.service-call{text-decoration:none;font-weight:600}
.service-call{min-height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--line);background:var(--card)}

/* Disclosure rows: replace the browser triangles with a single chevron */
summary{list-style:none;display:flex;align-items:center;gap:10px;cursor:pointer}
summary::-webkit-details-marker{display:none}
summary::marker{content:''}
summary::after{content:'';flex:none;width:9px;height:9px;margin-left:auto;border-right:2px solid currentColor;
border-bottom:2px solid currentColor;transform:rotate(45deg) translateY(-2px);transition:transform .2s;opacity:.7}
details[open]>summary::after{transform:rotate(-135deg) translateY(-2px)}

/* ===== Bottom navigation ===== */
.app-nav{background:var(--paper);background:var(--nav-bg);-webkit-backdrop-filter:saturate(1.4) blur(16px);backdrop-filter:saturate(1.4) blur(16px);
border-top:1px solid var(--hairline)}
.app-nav button{position:relative;border-radius:16px;font-weight:600;color:var(--muted);transition:color .15s,background .15s}
.app-nav button[aria-current=page]{color:var(--ink);background:var(--soft)}
.app-nav .icon{width:26px;height:26px}

/* ===== Dialogs (dish sheet, pickers) ===== */
dialog{border:0;box-shadow:0 -12px 40px -12px rgba(0,0,0,.5)}
dialog::backdrop{background:rgba(7,19,14,.55);backdrop-filter:blur(4px)}
dialog[open]{border-radius:26px 26px 0 0}
dialog::before{content:'';display:block;width:40px;height:4px;margin:-14px auto 16px;border-radius:2px;background:var(--line);opacity:.8}
dialog h2{font-family:'Cormorant Garamond',Georgia,serif;font-size:32px;line-height:1.1;font-weight:400}
.close-dialog{border-radius:50%;background:var(--soft)}
.option-choice{border-radius:var(--r-sm);border-color:var(--hairline);background:var(--card)}
.quantity-controls button{border-radius:50%}

/* ===== Messages and chat ===== */
.chat-bubble{border-radius:20px 20px 20px 6px;box-shadow:var(--shadow-sm)}
.chat-bubble.mine{border-radius:20px 20px 6px 20px}
.chat-form,.chat-compose{border-radius:var(--r)}
.chat-compose textarea{border-radius:20px}
#chat-send{background:var(--green);color:var(--button-ink);border-radius:50%}
.inbox-row,.ticket-row,.dialog-card,.ticket-card{border-radius:var(--r);background:var(--card);box-shadow:var(--shadow-sm);border:0}
.action-row{border-bottom-color:var(--hairline)}

/* ===== Small screens and motion ===== */
@media(max-width:360px){.page-title,.service-view>.page-title,#menu-hub>.page-title{font-size:30px}.direction-grid .service-card-copy strong,.direction-grid .service-card-copy h3{font-size:23px}.item-row{padding-left:14px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

CLAUDE_STYLE = APP_CSS + "\n" + CLAUDE_EXTRA_CSS
CLAUDE_HTML = APP_HTML.replace("/app/style.css", "/app-claude/style.css").replace(
    "<title>Sunpark</title>", "<title>Sunpark · Клод тест</title>"
)
