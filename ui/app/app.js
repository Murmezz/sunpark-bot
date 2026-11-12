'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const dialog = $('dish-dialog');
  let catalog = null, groupIndex = 0, categoryKey = '', query = '';
  let cartOpen = false, cartScroll = 0, currentDish = null, storageKey = null, toastTimer, menuScroll = null;
  let appView='home', cartOrigin='menu', flowScope='guest', flowInput=null, inboxScope='guest', chatNumber=0, chatScope='guest', pendingUpload=null, busy=false, chatData=null;
  const cart = new Map(), products = new Map(), mediaCache = new Map();
  // __WORKFLOWS__
  // __SERVICES__
  const money = amount => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(amount/100) + ' ₽';
  const systemDark=window.matchMedia?.('(prefers-color-scheme: dark)'), systemLight=window.matchMedia?.('(prefers-color-scheme: light)');
  function applyTheme() {
    const dark=systemDark?.matches?true:systemLight?.matches?false:tg?.colorScheme==='dark';
    document.documentElement.dataset.theme=dark?'dark':'light';
    const background=dark?'#101c18':'#f8f5eb';
    try {tg?.setHeaderColor(background);tg?.setBackgroundColor(background);tg?.setBottomBarColor?.(background);} catch (_) {}
  }
  applyTheme();
  for(const mq of [systemDark,systemLight]) {if(mq?.addEventListener)mq.addEventListener('change',applyTheme);else mq?.addListener?.(applyTheme);}
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)applyTheme();});
  window.addEventListener('pageshow',applyTheme);
  try {tg?.onEvent?.('themeChanged',applyTheme);} catch (_) {}

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function icon(name) {
    const element=node('span','icon');element.setAttribute('aria-hidden','true');
    element.style.maskImage=`url(/app/icons/${name}.svg)`;element.style.webkitMaskImage=`url(/app/icons/${name}.svg)`;return element;
  }
  function arrow() {return icon('caret-right');}
  document.querySelectorAll('[data-icon]').forEach(element=>{const name=element.dataset.icon;element.style.maskImage=`url(/app/icons/${name}.svg)`;element.style.webkitMaskImage=`url(/app/icons/${name}.svg)`;});
  function countWord(n) {
    const m = n % 100;
    return `${n} ${m >= 11 && m <= 14 ? 'позиций' : n%10 === 1 ? 'позиция' : n%10 >=2 && n%10 <=4 ? 'позиции' : 'позиций'}`;
  }
  function groupName(title) {
    const normalized = String(title).toLocaleUpperCase('ru').replace(/[^А-ЯЁA-Z0-9 ]/g,' ').replace(/\s+/g,' ').trim();
    return ({'ЕДА':'Еда','НАПИТКИ':'Напитки','АЛКОГОЛЬ':'Бар','БАР':'Бар','СЕЗОННОЕ МЕНЮ':'Сезонное'})[normalized] || title;
  }
  function updateBackButton() {
    try { if(dialog.open || $('picker-dialog').open || cartOpen || appView!=='home') tg?.BackButton.show(); else tg?.BackButton.hide(); } catch (_) {}
  }
  function toast(message) {
    clearTimeout(toastTimer); $('cart-toast').textContent=message; $('cart-toast').hidden=false;
    toastTimer=setTimeout(()=>{$('cart-toast').hidden=true;},3500);
  }
  function cartKey(itemId,optionId) { return `${itemId}:${optionId}`; }
  function lineProduct(line) {
    const product=products.get(line.itemId), option=product?.item.options.find(o=>o.id===line.optionId);
    return option?{...product,option}:null;
  }
  function saveCart() {
    if(!storageKey) return false;
    try {
      localStorage.setItem(storageKey,JSON.stringify({version:1,lines:[...cart.values()].map(line=>({...line,optionLabel:lineProduct(line).option.label}))}));
      return true;
    } catch (_) { toast('Корзина доступна до закрытия меню: сохранить её на устройстве не удалось.'); return false; }
  }
  function restoreCart() {
    try {
      const user=JSON.parse(new URLSearchParams(tg.initData).get('user'));
      if(!Number.isSafeInteger(user?.id)||user.id<=0) return;
      storageKey=`sunpark:menu-cart:v1:${user.id}`;
      const data=JSON.parse(localStorage.getItem(storageKey)||'null');
      if(data?.version!==1||!Array.isArray(data.lines)) return;
      for(const saved of data.lines.slice(0,300)) {
        if(!saved||typeof saved.itemId!=='string'||typeof saved.optionId!=='string'||!Number.isInteger(saved.quantity)||saved.quantity<1||saved.quantity>99) continue;
        const product=lineProduct(saved);
        if(!product||saved.optionLabel!==product.option.label) continue;
        cart.set(cartKey(saved.itemId,saved.optionId),{itemId:saved.itemId,optionId:saved.optionId,quantity:saved.quantity});
      }
    } catch (_) { /* A corrupt or unavailable local draft cannot block the menu. */ }
  }
  function cartTotals() {
    let sum=0,quantity=0,unknown=0;
    for(const line of cart.values()) {
      const product=lineProduct(line); if(!product) continue;
      quantity+=line.quantity;
      if(Number.isSafeInteger(product.option.amount)) sum+=product.option.amount*line.quantity; else unknown++;
    }
    return {sum,quantity,unknown};
  }
  function totalText(total) { return total.unknown?(total.sum?`${money(total.sum)} + уточняется`:'Сумма уточняется'):money(total.sum); }
  function renderCart() {
    const total=cartTotals();
    const showLauncher=!cartOpen&&catalog&&(appView==='menu'||(appView==='home'&&total.quantity>0));
    $('cart-launcher').hidden=!showLauncher;document.body.classList.toggle('has-cart',!!showLauncher);
    $('cart-badge').textContent=total.quantity; $('cart-badge').hidden=!total.quantity;
    $('cart-launcher-total').textContent=totalText(total);
    $('cart-count').textContent=`${countWord(cart.size)} · ${total.quantity} шт.`;
    $('cart-total').textContent=totalText(total);
    $('cart-empty').hidden=cart.size>0; $('cart-hint').hidden=!cart.size;
    $('cart-clear').hidden=!cart.size; $('cart-clear-confirm').hidden=true;
    $('cart-price-note').hidden=!total.unknown;
    $('cart-price-note').textContent=`Стоимость ${total.unknown} поз. уточните у официанта. Она ещё не включена в сумму.`;
    $('cart-items').replaceChildren();
    for(const [key,line] of cart) {
      const product=lineProduct(line); if(!product) continue;
      const {item,category,option}=product;
      const title=[item.cart_name||item.name,option.label].filter(Boolean).join(' · ');
      const sum=Number.isSafeInteger(option.amount)?money(option.amount*line.quantity):'Уточнить';
      const b=node('button','cart-row'); b.type='button';
      b.setAttribute('aria-label',`${title}, ${line.quantity} шт., ${sum}. Изменить или удалить`);
      b.append(node('span','cart-row-name',title),node('span','cart-row-quantity',`${line.quantity} ×`),node('span','cart-row-price',sum),arrow());
      b.addEventListener('click',()=>showDish(item,category,key));
      $('cart-items').append(b);
    }
  }
  function openCart() {
    if(!catalog||cartOpen) return;
    closeDish(); cartScroll=window.scrollY; cartOrigin=appView; cartOpen=true;setView('cart');
    $('menu-search').hidden=true; $('menu-hub').hidden=true; $('catalog-view').hidden=true; $('cart-view').hidden=false;
    renderCart(); updateBackButton(); window.scrollTo(0,0);
  }
  function closeCart() {
    cartOpen=false; $('cart-view').hidden=true; $('menu-search').hidden=false;
    if(query||categoryKey) renderItems(); else renderHub();
    setView(cartOrigin);renderCart(); updateBackButton(); window.scrollTo(0,cartScroll);
  }
  function updateDishAction() {
    if(!currentDish) return;
    const line=cart.get(currentDish.editKey), editing=!!line;
    $('dish-quantity').hidden=!editing; $('dish-remove').hidden=!editing;
    $('quantity-value').textContent=line?.quantity||1;
    $('quantity-minus').disabled=!line||line.quantity<=1; $('quantity-plus').disabled=!!line&&line.quantity>=99;
    const option=currentDish.item.options.find(o=>o.id===currentDish.optionId);
    $('dish-add').disabled=!option;
    $('dish-add').textContent=editing?'Готово':option?`Добавить в корзину${Number.isSafeInteger(option.amount)?' · '+money(option.amount):''}`:'Выберите вариант';
    if(editing) $('dish-price').textContent=[option.label,option.price,`${line.quantity} шт. — ${Number.isSafeInteger(option.amount)?money(option.amount*line.quantity):'стоимость уточняется'}`].filter(Boolean).join(' · ');
  }
  function addDish() {
    if(!currentDish) return;
    if(currentDish.editKey) { closeDish(); return; }
    const option=currentDish.item.options.find(o=>o.id===currentDish.optionId); if(!option) return;
    const key=cartKey(currentDish.item.id,option.id), line=cart.get(key);
    if(line?.quantity>=99) { toast('В корзине уже 99 шт. этой позиции.'); return; }
    if(!line&&cart.size>=300) { toast('Сначала удалите ненужные позиции из корзины.'); return; }
    cart.set(key,{itemId:currentDish.item.id,optionId:option.id,quantity:(line?.quantity||0)+1});
    const saved=saveCart(); renderCart(); closeDish();
    if(saved) toast(`Добавлено в корзину${option.label?' · '+option.label:''}`);
    try { tg?.HapticFeedback.notificationOccurred('success'); } catch (_) {}
  }
  function changeQuantity(delta) {
    const line=cart.get(currentDish?.editKey); if(!line) return;
    line.quantity=Math.max(1,Math.min(99,line.quantity+delta));
    saveCart(); renderCart(); updateDishAction();
  }
  function lockMenuScroll() {
    if(menuScroll) return;
    const body=document.body;
    menuScroll={x:window.scrollX,y:window.scrollY,top:body.style.top,left:body.style.left};
    body.style.top=`-${menuScroll.y}px`; body.style.left=`-${menuScroll.x}px`;
    document.documentElement.classList.add('modal-open'); body.classList.add('modal-open');
  }
  function unlockMenuScroll() {
    if(!menuScroll) return;
    const saved=menuScroll; menuScroll=null;
    document.documentElement.classList.remove('modal-open'); document.body.classList.remove('modal-open');
    document.body.style.top=saved.top; document.body.style.left=saved.left;
    window.scrollTo(saved.x,saved.y);
  }
  function closeDish() {
    if(dialog.open) dialog.close();
    unlockMenuScroll(); updateBackButton();
  }
  function showHub() {
    closeDish(); setView('menu');categoryKey = ''; query = ''; $('search').value = '';
    renderHub(); updateBackButton(); window.scrollTo(0,0);
  }
  function showDish(item, category, editKey=null) {
    const editing=cart.get(editKey);
    currentDish={item,category,editKey,optionId:editing?.optionId??(item.options.length===1?item.options[0].id:null)};
    $('dish-section').textContent = [category.title, item.section].filter(Boolean).join(' / ');
    $('dish-name').textContent = item.name;
    $('dish-price').textContent = item.price;
    $('dish-description').textContent = item.description || 'Состав не указан в меню. Уточните у официанта.';
    $('dish-footer').textContent = category.footer || '';
    $('dish-options').hidden=!!editing||item.options.length<2;
    $('dish-option-list').replaceChildren();
    item.options.forEach(option=>{
      const label=node('label','option-choice'), input=node('input'); input.type='radio'; input.name='dish-option'; input.value=option.id; input.checked=option.id===currentDish.optionId;
      input.addEventListener('change',()=>{currentDish.optionId=option.id;updateDishAction();});
      label.append(input,node('span','',option.label||'Стандартный'),node('strong','',option.price));
      $('dish-option-list').append(label);
    });
    $('back-to-menu').textContent=editing?'К корзине':'Вернуться к меню';
    updateDishAction();
    lockMenuScroll();
    try { dialog.showModal(); dialog.scrollTop=0; } catch(error) { unlockMenuScroll(); throw error; }
    updateBackButton();
    try { tg?.HapticFeedback.selectionChanged(); } catch (_) {}
  }
  function renderHub() {
    $('menu-hub').hidden = false; $('catalog-view').hidden = true;
    $('status').textContent = ''; $('items').replaceChildren();
    $('groups').replaceChildren();
    catalog.groups.forEach((group,i) => {
      const b = node('button','',groupName(group.title)); b.type='button';
      b.setAttribute('aria-pressed',String(groupIndex===i));
      b.addEventListener('click',()=>{groupIndex=i;renderHub();});
      $('groups').append(b);
    });
    $('categories').replaceChildren();
    const keys = catalog.groups[groupIndex]?.keys || [];
    catalog.categories.filter(c=>keys.includes(c.key)).forEach(cat=>{
      const b = node('button','category-card'); b.type='button';
      b.setAttribute('aria-label',`${cat.title}, ${countWord(cat.items.length)}. Открыть раздел`);
      const bottom = node('span','category-count',countWord(cat.items.length)); bottom.append(arrow());
      b.append(node('span','category-title',cat.title),bottom);
      b.addEventListener('click',()=>{categoryKey=cat.key;query='';$('search').value='';renderItems();window.scrollTo(0,0);});
      $('categories').append(b);
    });
    updateBackButton();
  }
  function renderItems() {
    $('menu-hub').hidden=true; $('catalog-view').hidden=false;
    const category=catalog.categories.find(c=>c.key===categoryKey), list=[];
    if(query) catalog.categories.forEach(cat=>cat.items.forEach(item=>{
      if([item.name,item.description,cat.title].join(' ').toLocaleLowerCase('ru').includes(query)) list.push({item,cat});
    }));
    else if(category) category.items.forEach(item=>list.push({item,cat:category}));
    $('section-title').firstElementChild.textContent=query?'Поиск по меню':category?.title||'Меню';
    $('catalog-hint').textContent=list.length?'Нажмите на блюдо, чтобы посмотреть состав':query?'Ничего не найдено. Попробуйте другое название.':'В этом разделе пока нет блюд.';
    $('category-footer').textContent=query?'':category?.footer||'';
    $('status').textContent=''; $('items').replaceChildren();
    let section='';
    list.forEach(({item,cat})=>{
      const next=query?cat.title:item.section;
      if(next && next!==section) $('items').append(node('h3','subsection',next));
      section=next;
      const b=node('button','item-row');b.type='button';
      b.setAttribute('aria-label',`${item.name}, ${item.price}. Посмотреть состав`);
      const icon=arrow();icon.classList.add('arrow');
      b.append(node('span','name',item.name),node('span','price',item.price),icon);
      b.addEventListener('click',()=>showDish(item,cat));
      $('items').append(b);
    });
    updateBackButton();
  }
  $('search').addEventListener('input',e=>{
    query=e.target.value.trim().toLocaleLowerCase('ru');
    if(!catalog) return;
    if(query || categoryKey) renderItems();else renderHub();
  });
  $('back-to-sections').addEventListener('click',showHub);
  $('close-dialog').addEventListener('click',closeDish);
  $('back-to-menu').addEventListener('click',closeDish);
  $('dish-add').addEventListener('click',addDish);
  $('quantity-minus').addEventListener('click',()=>changeQuantity(-1));
  $('quantity-plus').addEventListener('click',()=>changeQuantity(1));
  $('dish-remove').addEventListener('click',()=>{
    if(!currentDish?.editKey) return;
    cart.delete(currentDish.editKey); const saved=saveCart(); renderCart(); closeDish(); if(saved) toast('Позиция удалена из корзины');
  });
  $('cart-launcher').addEventListener('click',openCart);
  $('cart-back').addEventListener('click',closeCart);
  $('cart-clear').addEventListener('click',()=>{$('cart-clear-confirm').hidden=false;$('cart-clear').hidden=true;});
  $('cart-clear-no').addEventListener('click',()=>{$('cart-clear-confirm').hidden=true;$('cart-clear').hidden=false;});
  $('cart-clear-yes').addEventListener('click',()=>{cart.clear();const saved=saveCart();renderCart();if(saved)toast('Корзина очищена');});
  dialog.addEventListener('click',e=>{
    if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientY<r.top||e.clientY>r.bottom||e.clientX<r.left||e.clientX>r.right) closeDish();}
  });
  dialog.addEventListener('cancel',e=>{e.preventDefault();closeDish();});
  dialog.addEventListener('close',()=>{if(!dialog.open)unlockMenuScroll();updateBackButton();});
  try { tg?.ready();tg?.expand();tg?.BackButton.onClick(goBack); } catch (_) {}

  function requestKey() {
    if(crypto.randomUUID)return crypto.randomUUID();
    return [...crypto.getRandomValues(new Uint8Array(16))].map(n=>n.toString(16).padStart(2,'0')).join('');
  }
  async function api(operation,args={}) {
    const payload={...args,operation,init_data:tg?.initData||''};
    if(!['bootstrap','tickets','chat','screen'].includes(operation))payload.request_key=requestKey();
    const body=JSON.stringify(payload);
    let response;
    for(let attempt=0;attempt<2;attempt++) {
      try {response=await fetch('/api/app',{method:'POST',headers:{'Content-Type':'application/json'},body,cache:'no-store'});break;}
      catch(error){if(attempt)throw new Error('Не удалось связаться с сервером. Попробуйте ещё раз.');}
    }
    const data=await response.json();
    if(!response.ok){const error=new Error(data.error||'Не удалось выполнить действие.');error.fields=data.fields||{};error.status=response.status;throw error;}
    return data;
  }
  function setView(view) {
    if(view!=='native')nativeSequence++;
    if(view!==appView){clearTimeout(toastTimer);$('cart-toast').hidden=true;}
    if(dialog.open)closeDish();
    appView=view;
    for(const name of ['home','menu','cart','flow','inbox','chat','more','native','service'])$(name+'-view').hidden=name!==view;
    if(view!=='cart')cartOpen=false;
    $('menu-search').hidden=view!=='menu';
    document.body.classList.toggle('chat-open',view==='chat');
    document.body.classList.toggle('native-open',view==='native');$('native-back').hidden=view!=='native';
    for(const button of document.querySelectorAll('#app-nav [data-view]')) {
      const active=button.dataset.view===view||(view==='service'&&button.dataset.view===serviceOrigin)||(view==='chat'&&button.dataset.view==='inbox')||(['flow','native'].includes(view)&&button.dataset.view===(nativeState?.screen==='tickets'?'inbox':nativeState?.screen==='booking'?'home':'more'));
      if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
    }
    renderCart();updateBackButton();
  }
  function goBack() {
    if($('picker-dialog').open)closePicker();
    else if(dialog.open)closeDish();
    else if(appView==='native')nativeBack();
    else if(appView==='service')closeService();
    else if(cartOpen)closeCart();
    else if(appView==='menu'&&(categoryKey||query))showHub();
    else if(appView==='chat')openInbox(chatScope);
    else {setView('home');window.scrollTo(0,0);}
  }
  function goMenu() {setView('menu');if(query||categoryKey)renderItems();else renderHub();window.scrollTo(0,0);}
  function renderHome() {
    const all=catalog.categories.flatMap(category=>category.items.map(item=>({item,category})));
    const first=all.find(p=>/брускетт.*ростбиф/i.test(p.item.name))||all[0];
    const second=all.find(p=>/тар.?тар.*тунц/i.test(p.item.name))||all.find(p=>p!==first);
    $('home-samples').replaceChildren();
    [first,second].filter(Boolean).forEach(({item,category})=>{
      const b=node('button','sample-row');b.type='button';b.append(node('span','',item.name),node('strong','',item.price));
      b.addEventListener('click',()=>showDish(item,category));$('home-samples').append(b);
    });
    renderServiceLinks();
  }
  function cleanLabel(value) {return String(value||'').replace(/^[\p{Extended_Pictographic}\p{Regional_Indicator}\uFE0F\u200D\s]+/u,'').trim();}
  function actionIcon(callback) {
    if(/booking|date/.test(callback))return 'calendar-blank';
    if(/banquet|managers|other/.test(callback))return 'users-three';
    if(/^ev:/.test(callback))return 'ticket';
    if(/faq|info|phone/.test(callback))return 'info';
    if(/admin:panel|settings/.test(callback))return 'gear-six';
    if(/close|save|claim|take/.test(callback))return 'check';
    if(/search/.test(callback))return 'magnifying-glass';
    return 'chat-circle';
  }
  function actionRow(title,name,onClick) {
    const b=node('button','action-row');b.type='button';b.append(icon(name),node('span','',title),icon('arrow-right'));b.addEventListener('click',onClick);return b;
  }
  function renderMore() {
    $('profile-name').textContent=[catalog.user?.first_name,catalog.user?.last_name].filter(Boolean).join(' ')||'SUNPARK';
    const actions=[['Забронировать стол','booking:start'],['Провести банкет','banquet:contact'],['Мероприятия','ev:list:0'],['Правила и контакты','faq'],['Написать менеджеру','manager:start']];
    if(!catalog.events_visible)actions.splice(2,1);
    const root=$('more-actions');root.replaceChildren();
    for(const [label,callback] of actions)root.append(actionRow(label,actionIcon(callback),()=>runAction(callback,'guest')));
    root.append(node('h3','subsection','Весь SUNPARK'));
    for(const service of catalog.services?.items||[])root.append(actionRow(service.title,'arrow-right',()=>openService(service.id,'more')));
    if(catalog.admin) {
      root.append(node('h3','subsection','Управление'));
      for(const [label,callback] of [['Админ-панель','admin:panel'],['Очередь заявок','admin:waiting'],['Мои активные заявки','admin:active'],['Мероприятия и регистрации','ev:manage:0'],['Менеджеры','admin:managers'],['Поиск заявок','admin:search'],['Статистика','admin:stats']])root.append(actionRow(label,actionIcon(callback),()=>runAction(callback,'staff')));
    }
    $('inbox-scope').hidden=!catalog.admin;
  }
  function safeMarkup(value) {
    const source=new DOMParser().parseFromString(String(value||''),'text/html');
    const result=document.createDocumentFragment();
    const allowed=new Set(['B','STRONG','I','EM','U','S','CODE','PRE','BR','P','BLOCKQUOTE','UL','OL','LI']);
    function copy(parent,target) {
      for(const child of parent.childNodes) {
        if(child.nodeType===Node.TEXT_NODE){target.append(document.createTextNode(child.textContent));continue;}
        if(child.nodeType!==Node.ELEMENT_NODE||['SCRIPT','STYLE','IFRAME','OBJECT','IMG'].includes(child.tagName))continue;
        if(child.tagName==='A') {
          const href=child.getAttribute('href')||'';
          if(/^(https:\/\/|tg:\/\/|tel:\+)/i.test(href)){const a=node('a');a.href=href;a.rel='noopener noreferrer';a.target='_blank';copy(child,a);target.append(a);}else copy(child,target);
        } else if(allowed.has(child.tagName)){const element=node(child.tagName.toLowerCase());copy(child,element);target.append(element);}
        else copy(child,target);
      }
    }
    copy(source.body,result);return result;
  }
  async function runAction(callback,scope='guest',keepChat=false) {
    if(busy)return;
    try{if(await nativeAction(callback,scope,keepChat))return;}catch(error){toast(error.message);return;}
    if(callback==='back'||callback==='admin:guest'){setView('home');return;}
    if(callback==='home:menu'){goMenu();return;}
    busy=true;document.body.classList.add('busy');
    try {
      const data=await api('action',{callback,scope});
      for(const message of data.toasts||[])toast(cleanLabel(message.text));
      if(keepChat){await refreshChat();return;}
      if(data.input?.kind==='chat'){await openChat(data.input.ticket,'staff');return;}
      flowScope=scope;renderFlow(data);
    } catch(error){toast(error.message);}finally{busy=false;document.body.classList.remove('busy');}
  }
  function renderFlow(data) {
    flowInput=data.input||null;
    if(data.cards?.length) {
      const root=$('flow-cards');root.replaceChildren();
      for(const card of data.cards) {
        const section=node('section','workflow-section'),copy=node('div','system-copy');copy.append(safeMarkup(cleanLabel(card.html)));const first=[...copy.childNodes].find(n=>n.nodeType!==Node.TEXT_NODE||n.textContent.trim());if(first?.nodeType===Node.ELEMENT_NODE&&['B','STRONG'].includes(first.tagName))first.classList.add('system-title');section.append(copy);
        const controls=node('div','workflow-buttons');
        for(const row of card.keyboard?.inline_keyboard||[]) {
          const group=node('div','workflow-row');
          for(const action of row) {
            if(action.callback_data?.startsWith('mp:'))continue;
            const label=cleanLabel(action.text)||(/◀/.test(action.text)?'Назад':/▶/.test(action.text)?'Далее':'Продолжить');
            const b=node('button','secondary-button',label);b.type='button';
            if(action.callback_data)b.addEventListener('click',()=>runAction(action.callback_data,flowScope));
            else if(action.url)b.addEventListener('click',()=>{if(/^https:\/\//i.test(action.url))window.open(action.url,'_blank','noopener,noreferrer');});
            else continue;
            group.append(b);
          }
          controls.append(group);
        }
        for(const row of card.keyboard?.keyboard||[])for(const action of row) {
          if(action.request_contact||/Главное меню|Админ-панель|Как гость/.test(action.text))continue;
          const b=node('button','secondary-button',cleanLabel(action.text));b.type='button';b.addEventListener('click',()=>sendFlowText(action.text));controls.append(b);
        }
        section.append(controls);root.append(section);
      }
    }
    $('flow-form').hidden=!flowInput;
    if(flowInput) {
      const field=flowInput.field, multiline=['description','wishes','comment','text'].includes(field);
      $('flow-label').textContent=cleanLabel(flowInput.prompt||'Введите текст');$('flow-label').htmlFor=multiline?'flow-textarea':'flow-input';
      $('flow-progress').textContent=flowInput.total?`Шаг ${flowInput.step} из ${flowInput.total}`:'';
      const input=$('flow-input'),textarea=$('flow-textarea');input.hidden=multiline;textarea.hidden=!multiline;
      input.value='';textarea.value='';input.required=!multiline;textarea.required=multiline;
      input.type=field==='date'?'date':field==='time'?'time':field==='starts_at'?'datetime-local':['guests','party_size','capacity'].includes(field)?'number':field==='phone'?'tel':'text';
      input.inputMode=field==='phone'?'tel':['guests','party_size','capacity'].includes(field)?'numeric':'text';
      input.min='';input.max='';input.maxLength=field==='phone'?25:3500;
      if(input.type==='number'){input.min='1';input.max=field==='guests'?'200':'100000';}
      input.placeholder=field==='phone'?'+7 900 123-45-67':field==='telegram_username'?'@username':'';
    }
    setView('flow');window.scrollTo(0,0);
  }
  async function sendFlowText(text) {
    if(busy)return;
    busy=true;$('flow-submit').disabled=true;
    try {
      const data=await api('message',{text,scope:flowScope});
      for(const message of data.toasts||[])toast(cleanLabel(message.text));
      if(data.input?.kind==='chat')await openChat(data.input.ticket,'staff');else renderFlow(data);
    }catch(error){toast(error.message);}finally{busy=false;$('flow-submit').disabled=false;}
  }
  $('flow-form').addEventListener('submit',e=>{
    e.preventDefault();let value=$('flow-textarea').hidden?$('flow-input').value:$('flow-textarea').value;
    if(flowInput?.field==='date'||flowInput?.field==='starts_at'){
      const [date,time]=value.split('T'),[year,month,day]=date.split('-');value=`${day}.${month}.${year}${time?' '+time:''}`;
    }
    sendFlowText(value);
  });
  async function openInbox(scope=inboxScope) {inboxScope=scope;return openNative('tickets',{scope,filter:scope==='staff'?'waiting':'all'},true);}
  function statusLabel(status) {return ({draft:'Заполняется',waiting:'Новая',active:'В работе',waiting_guest:'Ждём ответа гостя',closed:'Закрыта'})[status]||status;}
  async function openChat(number,scope) {
    if(chatNumber!==number){if(pendingUpload?.preview)URL.revokeObjectURL(pendingUpload.preview);for(const url of mediaCache.values())URL.revokeObjectURL(url);mediaCache.clear();pendingUpload=null;}
    chatNumber=number;chatScope=scope;resetNativeChat(number,scope);setView('chat');window.scrollTo(0,0);await refreshChat();
  }
  async function loadMedia(message) {
    if(mediaCache.has(message.id))return mediaCache.get(message.id);
    const response=await fetch('/api/app/media',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData,message_id:message.id,scope:chatScope}),cache:'no-store'});
    if(!response.ok){const data=await response.json();throw new Error(data.error||'Не удалось загрузить вложение.');}
    const url=URL.createObjectURL(await response.blob());mediaCache.set(message.id,url);
    if(mediaCache.size>20){const first=mediaCache.keys().next().value;URL.revokeObjectURL(mediaCache.get(first));mediaCache.delete(first);}
    return url;
  }
  async function refreshChat() {return refreshNativeChat();}
  function renderAttachment() {
    $('chat-attachment').hidden=!pendingUpload;$('chat-attachment').replaceChildren();
    if(pendingUpload){$('chat-attachment').append(node('span','',pendingUpload.name));const b=node('button','icon-button');b.type='button';b.setAttribute('aria-label','Убрать вложение');b.append(icon('x'));b.addEventListener('click',()=>{if(pendingUpload?.preview)URL.revokeObjectURL(pendingUpload.preview);pendingUpload=null;renderAttachment();});$('chat-attachment').append(b);}
  }
  $('chat-form').addEventListener('submit',async e=>{
    e.preventDefault();if(busy||!chatData?.ticket.can_reply)return;
    const text=$('chat-input').value.trim();if(!text&&!pendingUpload)return;
    const sendingKey=nativeChatKey;busy=true;$('chat-send').disabled=true;$('chat-input').readOnly=true;
    try {const result=await api('chat_send',{ticket:chatNumber,scope:chatScope,text,upload:pendingUpload?.token});if(result.warning)toast(result.warning);chatDrafts.delete(sendingKey);if(nativeChatKey!==sendingKey)return;$('chat-input').value='';$('chat-input').style.height='auto';if(pendingUpload?.preview)URL.revokeObjectURL(pendingUpload.preview);pendingUpload=null;await refreshChat();$('chat-log').scrollTop=$('chat-log').scrollHeight;}
    catch(error){toast(error.message);}finally{busy=false;$('chat-send').disabled=false;$('chat-input').readOnly=false;}
  });
  $('attach-button').addEventListener('click',()=>$('chat-file').click());
  $('chat-file').addEventListener('change',async e=>{
    const file=e.target.files?.[0];if(!file)return;const uploadKey=nativeChatKey;
    if(file.size>5*1024*1024){toast('Максимальный размер вложения — 5 МБ.');e.target.value='';return;}
    busy=true;$('attach-button').disabled=true;toast('Загружаем вложение…');
    try {const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});const uploaded=await api('upload',{name:file.name,data});if(nativeChatKey!==uploadKey)return;pendingUpload={...uploaded,size:file.size,preview:file.type.startsWith('image/')?URL.createObjectURL(file):null};renderAttachment();toast('Вложение готово к отправке');}
    catch(error){toast(error.message);}finally{busy=false;$('attach-button').disabled=false;e.target.value='';}
  });
  $('brand-home').addEventListener('click',()=>{setView('home');window.scrollTo(0,0);});
  $('profile-button').addEventListener('click',()=>{setView('more');window.scrollTo(0,0);});
  $('home-menu-button').addEventListener('click',goMenu);
  $('home-booking').addEventListener('click',()=>runAction('booking:start','guest'));
  $('home-inbox').addEventListener('click',()=>openInbox('guest'));
  $('flow-back').addEventListener('click',()=>{setView('home');window.scrollTo(0,0);});
  $('chat-back').addEventListener('click',()=>openInbox(chatScope));
  $('inbox-reload').addEventListener('click',()=>openInbox());
  document.querySelectorAll('#inbox-scope [data-scope]').forEach(b=>b.addEventListener('click',()=>openInbox(b.dataset.scope)));
  document.querySelectorAll('#app-nav [data-view]').forEach(b=>b.addEventListener('click',()=>{const view=b.dataset.view;if(view==='menu')goMenu();else if(view==='inbox')openInbox();else{setView(view);window.scrollTo(0,0);}}));
  setInterval(()=>{if(!document.hidden&&appView==='chat'&&!busy)refreshChat();},6000);
  const resize=()=>document.documentElement.style.setProperty('--viewport-height',`${tg?.viewportStableHeight||window.visualViewport?.height||innerHeight}px`);
  window.visualViewport?.addEventListener('resize',resize);window.addEventListener('resize',resize);resize();
  try {tg?.onEvent?.('viewportChanged',event=>{if(event.isStateStable)resize();});} catch (_) {}

  async function load() {
    if(!tg?.initData) throw new Error('Откройте приложение из бота: /admin → «Разработка» → «SUNPARK · Mini App». Доступ только администраторам.');
    const data=await api('bootstrap');
    catalog=data;
    if(!catalog.groups.length||!catalog.categories.length)throw new Error('Меню пока пусто.');
    const food=catalog.groups.findIndex(g=>groupName(g.title)==='Еда');
    if(food>=0)groupIndex=food;
    catalog.categories.forEach(category=>category.items.forEach(item=>products.set(item.id,{item,category})));
    restoreCart();renderHub();renderHome();renderMore();$('app-shell').hidden=false;$('app-nav').hidden=false;$('status').textContent='';setView('home');
  }
  load().catch(error=>{$('app-shell').hidden=true;$('app-nav').hidden=true;$('cart-launcher').hidden=true;$('status').textContent=error.message;});
})();
