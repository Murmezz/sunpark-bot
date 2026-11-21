'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const refinedDesign=document.body.dataset.design==='refresh-20261120';
  const sessionLaunch=new URLSearchParams(tg?.initData||'').get('hash')||'';
  let appSession='',authExpired=false;
  try{const saved=JSON.parse(sessionStorage.getItem('sunpark:session:v1')||'null');if(saved?.launch===sessionLaunch&&typeof saved.token==='string')appSession=saved.token;}catch(_){}
  const dialog = $('dish-dialog');
  let catalog = null, groupIndex = 0, categoryKey = '', query = '';
  let cartOpen = false, cartScroll = 0, currentDish = null, storageKey = null, toastTimer, menuScroll = null;
  let appView='home', cartOrigin='menu', flowScope='guest', flowInput=null, inboxScope='guest', chatNumber=0, chatScope='guest', pendingUpload=null, busy=false, chatData=null;
  const cart = new Map(), products = new Map(), mediaCache = new Map();
  // __REDESIGN__
  // __LOADING__
  // __WORKFLOWS__
  // __SERVICES__
  // __CONCEPT__
  const money = amount => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(amount/100) + ' ₽';
  const systemDark=window.matchMedia?.('(prefers-color-scheme: dark)'), systemLight=window.matchMedia?.('(prefers-color-scheme: light)');
  function applyTheme() {
    const dark=systemDark?.matches?true:systemLight?.matches?false:tg?.colorScheme==='dark';
    document.documentElement.dataset.theme=dark?'dark':'light';
    const background=refinedDesign?(dark?'#102119':'#f5f7f0'):(dark?'#101c18':'#f8f5eb');
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
    } catch (_) { toast('Выбор доступен только в этом окне: сохранить список на устройстве не удалось.'); return false; }
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
  function itemCartLines(itemId) { return [...cart.entries()].filter(([,line])=>line.itemId===itemId); }
  function selectedDishKey() { return currentDish?.optionId?cartKey(currentDish.item.id,currentDish.optionId):null; }
  function updateMenuQuantities() {
    if(!catalog)return;
    for(const row of $('items').querySelectorAll('.item-row[data-item-id]')) {
      const product=products.get(row.dataset.itemId);if(!product)continue;
      const {item}=product,lines=itemCartLines(item.id),quantity=lines.reduce((sum,[,line])=>sum+line.quantity,0);
      row.classList.toggle('has-quantity',quantity>0);
      const minus=row.querySelector('.item-minus'),value=row.querySelector('.item-quantity'),plus=row.querySelector('.item-add');
      minus.hidden=value.hidden=quantity===0;value.textContent=quantity;
      minus.setAttribute('aria-label',(quantity===1?'Удалить: ':'Уменьшить: ')+item.name);
      plus.setAttribute('aria-label',(item.options.length===1?(quantity?'Увеличить: ':'Добавить: '):'Выбрать вариант: ')+item.name);
      plus.disabled=item.available===false||(item.options.length===1&&quantity>=99);
    }
  }
  function renderCart() {
    const total=cartTotals();
    const showLauncher=!cartOpen&&catalog&&total.quantity>0&&(appView==='menu'||(appView==='service'&&currentServiceId==='restaurant'));
    $('cart-launcher').hidden=!showLauncher;document.body.classList.toggle('has-cart',!!showLauncher);
    $('cart-badge').textContent=total.quantity; $('cart-badge').hidden=!total.quantity;
    $('cart-launcher-total').textContent=totalText(total);
    $('cart-count').textContent=`${countWord(cart.size)} · ${total.quantity} шт.`;
    $('cart-total').textContent=totalText(total);
    $('cart-empty').hidden=cart.size>0; $('cart-hint').hidden=!cart.size;
    $('cart-clear').hidden=!cart.size; $('cart-clear-confirm').hidden=true;
    if(refinedDesign)$('refined-cart-actions').hidden=!cart.size;
    $('cart-price-note').hidden=!total.unknown;
    $('cart-price-note').textContent=`Стоимость ${total.unknown} поз. уточните у официанта. Она ещё не включена в сумму.`;
    $('preorder-checkout').hidden=!cart.size;$('preorder-checkout').disabled=!!total.unknown;
    $('cart-items').replaceChildren();
    for(const [key,line] of cart) {
      const product=lineProduct(line); if(!product) continue;
      const {item,category,option}=product;
      const title=[item.cart_name||item.name,option.label].filter(Boolean).join(' · ');
      const sum=Number.isSafeInteger(option.amount)?money(option.amount*line.quantity):'Уточнить';
      const row=node('div','cart-row');row.dataset.cartKey=key;row.setAttribute('role','group');row.setAttribute('aria-label',title);
      const productButton=button('','cart-product',()=>showDish(item,category,key));productButton.setAttribute('aria-label','Состав: '+title);productButton.append(node('span','cart-row-name',title),node('span','cart-row-price',sum));
      const controls=node('div','cart-stepper');
      for(const delta of [-1,1]){const b=button('','icon-button',()=>adjustCartLine(key,delta));b.dataset.change=delta;b.setAttribute('aria-label',(delta<0?(line.quantity===1?'Удалить: ':'Уменьшить: '):'Увеличить: ')+title);b.disabled=delta>0&&line.quantity>=99;b.append(icon(delta<0?'minus':'plus'));controls.append(b);if(delta<0){const n=node('output','',line.quantity);n.setAttribute('aria-live','polite');controls.append(n);}}
      const remove=button('','icon-button cart-line-remove',()=>{cart.delete(key);saveCart();renderCart();$('cart-title').focus({preventScroll:true});});remove.setAttribute('aria-label','Удалить: '+title);remove.append(icon('trash'));
      row.append(productButton,controls,remove);$('cart-items').append(row);
    }
    updateMenuQuantities();if(dialog.open)updateDishAction();
  }
  function changeCartLine(key,delta){const line=cart.get(key);if(!line)return;const quantity=Math.max(0,Math.min(99,line.quantity+delta));if(quantity)line.quantity=quantity;else cart.delete(key);saveCart();renderCart();}
  function adjustCartLine(key,delta){changeCartLine(key,delta);const row=[...$('cart-items').children].find(e=>e.dataset.cartKey===key);(row?.querySelector(`[data-change="${delta}"]`)||$('cart-title')).focus({preventScroll:true});}
  function openCart() {
    if(!catalog||cartOpen) return;
    closeDish(); cartScroll=pageScrollTop(); cartOrigin=appView; cartOpen=true;setView('cart');
    $('cart-back').lastChild.textContent=cartOrigin==='service'?'К ресторану':'К меню';
    $('menu-search').hidden=true; $('menu-hub').hidden=true; $('catalog-view').hidden=true; $('cart-view').hidden=false;
    renderCart(); updateBackButton(); scrollPage();
  }
  function closeCart() {
    cartOpen=false; $('cart-view').hidden=true; $('menu-search').hidden=false;
    renderHub();
    setView(cartOrigin);renderCart(); updateBackButton(); scrollPage(cartScroll);
  }
  function updateDishAction() {
    if(!currentDish) return;
    const option=currentDish.item.options.find(o=>o.id===currentDish.optionId);
    const line=cart.get(selectedDishKey());
    $('dish-quantity').hidden=!option;$('dish-remove').hidden=!line;
    $('quantity-value').textContent=line?.quantity||0;
    $('quantity-minus').disabled=!line;
    $('quantity-plus').disabled=!option||currentDish.item.available===false||!!line&&line.quantity>=99;
    $('dish-add').disabled=!option||!line&&currentDish.item.available===false;
    $('dish-add').textContent=line?'Готово':option?`Добавить в корзину${Number.isSafeInteger(option.amount)?' · '+money(option.amount):''}`:'Выберите вариант';
    $('dish-price').textContent=line?[option.label,option.price,`${line.quantity} шт. — ${Number.isSafeInteger(option.amount)?money(option.amount*line.quantity):'стоимость уточняется'}`].filter(Boolean).join(' · '):option?.price||currentDish.item.price;
    for(const label of $('dish-option-list').children){const quantity=cart.get(cartKey(currentDish.item.id,label.dataset.optionId))?.quantity||0;label.querySelector('.option-cart-count').textContent=`В корзине: ${quantity}`;}
  }
  function addDish() {
    if(!currentDish) return;
    if(cart.has(selectedDishKey())) { closeDish(); return; }
    const option=currentDish.item.options.find(o=>o.id===currentDish.optionId); if(!option) return;
    if(addProduct(currentDish.item,option))closeDish();
  }
  function addProduct(item,option){
    if(item.available===false){toast('Блюдо временно недоступно');return false;}
    const key=cartKey(item.id,option.id), line=cart.get(key);
    if(line?.quantity>=99) { toast('В корзине уже 99 шт. этой позиции.'); return; }
    if(!line&&cart.size>=300) { toast('Сначала удалите ненужные позиции из корзины.'); return; }
    cart.set(key,{itemId:item.id,optionId:option.id,quantity:(line?.quantity||0)+1});
    const saved=saveCart(); renderCart();
    if(saved&&!refinedDesign) toast(`Добавлено в корзину${option.label?' · '+option.label:''}`);
    try { tg?.HapticFeedback.notificationOccurred('success'); } catch (_) {}
    return true;
  }
  function changeQuantity(delta) {
    if(!currentDish?.optionId)return;
    if(delta>0){const option=currentDish.item.options.find(o=>o.id===currentDish.optionId);if(option)addProduct(currentDish.item,option);}
    else changeCartLine(selectedDishKey(),delta);
  }
  function lockMenuScroll() {
    if(menuScroll) return;
    const body=document.body;
    menuScroll={x:window.scrollX,y:pageScrollTop(),top:body.style.top,left:body.style.left};
    if (!appScroll) {
      body.style.top=`-${menuScroll.y}px`; body.style.left=`-${menuScroll.x}px`;
    }
    document.documentElement.classList.add('modal-open'); body.classList.add('modal-open');
  }
  function unlockMenuScroll() {
    if(!menuScroll) return;
    const saved=menuScroll; menuScroll=null;
    document.documentElement.classList.remove('modal-open'); document.body.classList.remove('modal-open');
    document.body.style.top=saved.top; document.body.style.left=saved.left;
    if (appScroll) scrollPage(saved.y);
    else window.scrollTo(saved.x,saved.y);
  }
  function closeDish() {
    if(dialog.open) dialog.close();
    unlockMenuScroll(); updateBackButton();
  }
  function showHub() {
    closeDish(); setView('menu');query = ''; $('search').value = '';
    renderHub(); updateBackButton(); scrollPage();
  }
  function showDish(item, category, editKey=null) {
    const editing=cart.get(editKey);
    const selected=itemCartLines(item.id);
    currentDish={item,category,editKey,optionId:editing?.optionId??(item.options.length===1?item.options[0].id:selected.length===1?selected[0][1].optionId:null)};
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
      label.dataset.optionId=option.id;const name=node('span','option-label');name.append(node('span','',option.label||'Стандартный'),node('small','option-cart-count'));
      label.append(input,name,node('strong','',option.price));
      $('dish-option-list').append(label);
    });
    updateDishAction();
    lockMenuScroll();
    try { dialog.showModal(); dialog.scrollTop=0; } catch(error) { unlockMenuScroll(); throw error; }
    updateBackButton();
    try { tg?.HapticFeedback.selectionChanged(); } catch (_) {}
  }
  function renderHub() {
    if(!catalog)return;
    $('menu-back-label').textContent='К ресторану';$('menu-hub').hidden=false;$('catalog-view').hidden=false;
    $('groups').replaceChildren();
    const group=catalog.groups[groupIndex], keys=group?.keys||[];
    if(!keys.includes(categoryKey))categoryKey=keys[0]||'';
    catalog.groups.forEach((group,i)=>{
      const b=button(groupName(group.title),'',()=>{groupIndex=i;categoryKey='';query='';$('search').value='';renderHub();revealContent($('items'));scrollPage();});
      b.setAttribute('aria-pressed',String(groupIndex===i));$('groups').append(b);
    });
    $('categories').replaceChildren();$('categories').hidden=!!query;
    for(const key of keys){const cat=catalog.categories.find(c=>c.key===key);if(!cat)continue;
      const b=button(cat.title,'category-chip',()=>{categoryKey=key;query='';$('search').value='';renderHub();revealContent($('items'));$('catalog-view').scrollIntoView({block:'start'});});
      b.dataset.category=key;b.setAttribute('aria-pressed',String(categoryKey===key));$('categories').append(b);
    }
    renderItems();
    const selected=$('categories').querySelector('[aria-pressed=true]');if(appView==='menu'&&!query&&selected?.getClientRects().length)selected.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  function renderItems() {
    const category=catalog.categories.find(c=>c.key===categoryKey),list=[];
    if(query)catalog.categories.forEach(cat=>cat.items.forEach(item=>{if([item.name,item.description,cat.title].join(' ').toLocaleLowerCase('ru').includes(query))list.push({item,cat});}));
    else if(category)category.items.forEach(item=>list.push({item,cat:category}));
    $('section-title').firstElementChild.textContent=query?'Результаты поиска':category?.title||'Меню';
    $('catalog-hint').textContent=list.length?'':query?'Ничего не найдено. Попробуйте другое название.':'В этом разделе пока нет блюд.';
    $('catalog-hint').hidden=!!list.length;$('category-footer').textContent=query?'':category?.footer||'';
    $('catalog-view').classList.toggle('is-searching',!!query);
    $('status').textContent='';$('items').replaceChildren();let section='';
    for(const {item,cat} of list){
      const next=query?cat.title:item.section;if(next&&next!==section)$('items').append(node('h3','subsection',next));section=next;
      const row=node('div','item-row');row.dataset.itemId=item.id;
      const open=button('','item-open',()=>showDish(item,cat));open.setAttribute('aria-label',`${item.name}, ${item.price}. Посмотреть состав`);
      const copy=node('span','item-copy');copy.append(node('span','name',item.name));
      if(item.description)copy.append(node('span','item-description',item.description));
      const price=node('span','price',item.price);
      if(refinedDesign)open.append(copy);else open.append(copy,price,arrow());
      const add=button('','icon-button item-add',()=>{if(item.options.length===1&&Number.isSafeInteger(item.options[0].amount))addProduct(item,item.options[0]);else showDish(item,cat);});
      const minus=button('','icon-button item-minus',()=>{const lines=itemCartLines(item.id);if(lines.length===1)changeCartLine(lines[0][0],-1);else if(lines.length)showDish(item,cat);});minus.append(icon('minus'));
      const quantity=node('output','item-quantity','0');quantity.setAttribute('aria-live','polite');quantity.setAttribute('aria-label','В корзине: '+item.name);
      const actions=node('div','item-actions');actions.setAttribute('role','group');actions.setAttribute('aria-label','Количество в корзине: '+item.name);actions.append(minus,quantity,add);
      add.disabled=item.available===false;if(item.available===false)copy.append(node('span','item-description','Временно недоступно'));
      add.append(icon('plus'));if(refinedDesign)row.append(open,price,actions);else row.append(open,actions);$('items').append(row);
    }
    updateMenuQuantities();updateBackButton();
  }
  $('search').addEventListener('input',e=>{
    query=e.target.value.trim().toLocaleLowerCase('ru');
    if(!catalog) return;
    renderHub();
  });
  $('back-to-sections').addEventListener('click',()=>openService('restaurant','home'));
  $('close-dialog').addEventListener('click',closeDish);
  $('dish-add').addEventListener('click',addDish);
  $('quantity-minus').addEventListener('click',()=>changeQuantity(-1));
  $('quantity-plus').addEventListener('click',()=>changeQuantity(1));
  $('dish-remove').addEventListener('click',()=>{
    const key=selectedDishKey();if(!cart.has(key))return;
    cart.delete(key); const saved=saveCart(); renderCart(); closeDish(); if(saved) toast('Блюдо удалено из корзины');
  });
  $('cart-launcher').addEventListener('click',openCart);
  $('cart-back').addEventListener('click',closeCart);
  $('cart-clear').addEventListener('click',()=>{$('cart-clear-confirm').hidden=false;$('cart-clear').hidden=true;});
  $('cart-clear-no').addEventListener('click',()=>{$('cart-clear-confirm').hidden=true;$('cart-clear').hidden=false;});
  $('cart-clear-yes').addEventListener('click',()=>{cart.clear();const saved=saveCart();renderCart();if(saved)toast('Список очищен');});
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
  function appHeaders(){return {'Content-Type':'application/json',...(appSession?{'X-Sunpark-Session':appSession}:{})};}
  function saveSession(token){
    if(typeof token!=='string'||!/^v1\.\d+\.[0-9a-f]{64}$/.test(token))return;
    appSession=token;authExpired=false;
    try{sessionStorage.setItem('sunpark:session:v1',JSON.stringify({launch:sessionLaunch,token}));}catch(_){}
  }
  function expiredSession(message){
    appSession='';authExpired=true;try{sessionStorage.removeItem('sunpark:session:v1');}catch(_){}
    const error=new Error(message||'Закройте приложение и откройте SunPark заново в боте.');error.status=401;return error;
  }
  function renderSessionRecovery(root,error){clearLoading(root);root.replaceChildren(node('h1','native-title','Сеанс завершён'),node('p','native-hint',error.message),button('Закрыть приложение','primary-button',closeApp));}
  async function api(operation,args={}) {
    if(authExpired&&operation!=='bootstrap')throw expiredSession();
    const payload={...args,operation,init_data:tg?.initData||''};
    if(!['bootstrap','tickets','chat','screen','booking_read'].includes(operation))payload.request_key=requestKey();
    const body=JSON.stringify(payload);
    let response;
    for(let attempt=0;attempt<2;attempt++) {
      try {response=await fetch('/api/app',{method:'POST',headers:appHeaders(),body,cache:'no-store'});break;}
      catch(error){if(attempt)throw new Error('Не удалось связаться с сервером. Попробуйте ещё раз.');}
    }
    const data=await response.json();
    if(response.status===401)throw expiredSession(data.error);
    if(!response.ok){const error=new Error(data.error||'Не удалось выполнить действие.');error.fields=data.fields||{};error.status=response.status;throw error;}
    if(operation==='bootstrap')saveSession(data.session);
    return data;
  }
  function setView(view) {
    const previous=appView;
    if(previous!==view){
      if(previous==='concept')clearLoading($('concept-content'));
      if(previous==='native')clearLoading($('native-content'));
      if(previous==='chat')clearLoading($('chat-log'));
    }
    if(view!=='native')nativeSequence++;
    if(view!==appView){clearTimeout(toastTimer);$('cart-toast').hidden=true;}
    if(dialog.open)closeDish();
    appView=view;
    for(const name of ['home','menu','cart','flow','inbox','chat','more','native','service','concept'])$(name+'-view').hidden=name!==view;
    if(view!=='cart')cartOpen=false;
    $('menu-search').hidden=view!=='menu';
    document.body.classList.toggle('chat-open',view==='chat');
    document.body.classList.toggle('native-open',view==='native');$('view-back').hidden=!['native','more'].includes(view);
    $('view-back-label').textContent=view==='more'?'К сообщениям':nativeState?.step>0?'Назад':nativeOrigin==='restaurant'?'К ресторану':nativeOrigin==='messages'?'К сообщениям':nativeOrigin==='management'?'К управлению':'На главную';
    for(const button of document.querySelectorAll('#app-nav [data-view]')) {
      const messages=view==='chat'||view==='more'||(view==='native'&&(nativeState?.screen==='tickets'||['messages','management'].includes(nativeOrigin)));
      const plans=view==='concept'&&['plans','order','qr','payment'].includes(conceptState?.screen);
      const active=button.dataset.view===(plans?'plans':messages?'inbox':'home');
      if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
    }
    renderCart();updateBackButton();resize();
    if(view!==previous&&!['native','concept','chat'].includes(view))revealContent($(view+'-view'));
  }
  function goBack() {
    if($('picker-dialog').open)closePicker();
    else if(dialog.open)closeDish();
    else if(appView==='concept')conceptBack();
    else if(appView==='native')nativeBack();
    else if(appView==='service')closeService();
    else if(cartOpen)closeCart();
    else if(appView==='menu'&&query)showHub();
    else if(appView==='menu')openService('restaurant','home');
    else if(appView==='more')openInbox('guest');
    else if(appView==='chat')openInbox(chatScope);
    else {setView('home');scrollPage();}
  }
  function goMenu() {setView('menu');renderHub();scrollPage();}
  function renderHome() {
    renderServiceLinks();renderHomeLocation();
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
    const root=$('more-actions');root.replaceChildren();
    if(catalog.admin||['manager','waiter'].includes(catalog.booking_features?.role))root.append(actionRow('Мои столы и QR','qr-code',()=>openConcept('staff_tables',{},true)));
    if(catalog.admin) {
      root.append(actionRow('Календарь занятости','calendar-blank',()=>openConcept('calendar',{},true)),actionRow('Предзаказы ресторана','fork-knife',()=>openConcept('preorders',{},true)),actionRow('Услуги и ресурсы','gear-six',()=>openConcept('inventory',{},true)));
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
    busy=true;document.body.classList.add('busy');const restore=buttonLoading(document.activeElement?.closest('button'),'Загружаем…');
    try {
      const data=await api('action',{callback,scope});
      for(const message of data.toasts||[])toast(cleanLabel(message.text));
      if(keepChat){await refreshChat();return;}
      if(data.input?.kind==='chat'){await openChat(data.input.ticket,'staff');return;}
      flowScope=scope;renderFlow(data);
    } catch(error){toast(error.message);}finally{busy=false;restore();document.body.classList.remove('busy');}
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
    setView('flow');scrollPage();
  }
  async function sendFlowText(text) {
    if(busy)return;
    busy=true;const restore=buttonLoading($('flow-submit'),'Отправляем…');
    try {
      const data=await api('message',{text,scope:flowScope});
      for(const message of data.toasts||[])toast(cleanLabel(message.text));
      if(data.input?.kind==='chat')await openChat(data.input.ticket,'staff');else renderFlow(data);
    }catch(error){toast(error.message);}finally{busy=false;restore();}
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
    chatNumber=number;chatScope=scope;resetNativeChat(number,scope);setView('chat');scrollPage();await refreshChat();
  }
  async function loadMedia(message) {
    if(mediaCache.has(message.id))return mediaCache.get(message.id);
    const response=await fetch('/api/app/media',{method:'POST',headers:appHeaders(),body:JSON.stringify({init_data:tg.initData,message_id:message.id,scope:chatScope}),cache:'no-store'});
    if(response.status===401){const data=await response.json();throw expiredSession(data.error);}
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
  $('flow-back').addEventListener('click',()=>{setView('home');scrollPage();});
  $('chat-back').addEventListener('click',()=>openInbox(chatScope));
  $('inbox-reload').addEventListener('click',()=>openInbox());
  document.querySelectorAll('#inbox-scope [data-scope]').forEach(b=>b.addEventListener('click',()=>openInbox(b.dataset.scope)));
  document.querySelectorAll('#app-nav [data-view]').forEach(b=>b.addEventListener('click',()=>{const view=b.dataset.view;if(view==='inbox')openInbox('guest');else if(view==='plans')openConcept('plans',{},true);else{setView(view);scrollPage();}}));
  setInterval(()=>{if(!authExpired&&!document.hidden&&appView==='chat'&&!busy)refreshChat();},6000);
  let expandedViewport={width:innerWidth,height:innerHeight};
  function resize(){
    const root=document.documentElement;
    for(const [family,insets] of [['safe',tg?.safeAreaInset],['content',tg?.contentSafeAreaInset]]) {
      for(const edge of ['top','right','bottom','left']) {
        const value=Number(insets?.[edge]);
        root.style.setProperty(`--sdk-${family}-${edge}`,`${Number.isFinite(value)&&value>0?value:0}px`);
      }
    }
    const focused=appView==='chat'&&$('chat-form').contains(document.activeElement);
    const available=Math.min(window.visualViewport?.height||innerHeight,innerHeight);
    const editing=document.activeElement?.matches('input,textarea,select,[contenteditable=true]');
    if(!editing||Math.abs(innerWidth-expandedViewport.width)>48)expandedViewport={width:innerWidth,height:available};
    const keyboard=!!editing&&(window.visualViewport?.scale||1)<1.1&&expandedViewport.height-available>120;
    document.body.classList.toggle('is-keyboard-open',keyboard);
    const compact=appView==='chat'&&(focused||available<600);
    document.body.classList.toggle('chat-typing',compact);
    const stable=Math.min(Number(tg?.viewportStableHeight)||innerHeight,innerHeight);
    root.style.setProperty('--viewport-height',`${compact||keyboard?available:stable}px`);
    const nav=$('app-nav');
    if(!nav.hidden&&!keyboard&&!compact){
      const height=Math.ceil(nav.getBoundingClientRect().height),value=height+'px';
      if(height&&root.style.getPropertyValue('--nav-outer-height')!==value)root.style.setProperty('--nav-outer-height',value);
    }
  }
  window.visualViewport?.addEventListener('resize',resize);window.addEventListener('resize',resize);
  document.addEventListener('focusin',resize);document.addEventListener('focusout',()=>setTimeout(resize,0));resize();
  try{tg?.onEvent?.('viewportChanged',resize);}catch(_){}
  if(window.ResizeObserver)new ResizeObserver(()=>requestAnimationFrame(resize)).observe($('app-nav'));
  function closeApp(){try{if(tg?.close)tg.close();else window.close();}catch(_){}}
  function syncFullscreen(){document.body.classList.toggle('telegram-fullscreen',!!tg?.isFullscreen);resize();}
  try {
    tg?.onEvent?.('fullscreenChanged',syncFullscreen);
    tg?.onEvent?.('safeAreaChanged',resize);tg?.onEvent?.('contentSafeAreaChanged',resize);
    tg?.onEvent?.('fullscreenFailed',event=>{if(event?.error!=='ALREADY_FULLSCREEN')tg?.expand();syncFullscreen();});
    if(tg?.isVersionAtLeast?.('8.0')&&typeof tg.requestFullscreen==='function'&&!tg.isFullscreen)tg.requestFullscreen();
  } catch(_){try{tg?.expand();}catch(_){}}
  syncFullscreen();

  async function load() {
    if(!tg?.initData) throw new Error('Откройте SunPark из бота: /admin → «Разработка» → «SunPark». Доступ только администраторам.');
    const data=await api('bootstrap');
    catalog=data;
    const food=catalog.groups.findIndex(g=>groupName(g.title)==='Еда');
    if(food>=0)groupIndex=food;
    catalog.categories.forEach(category=>category.items.forEach(item=>products.set(item.id,{item,category})));
    restoreCart();renderHub();renderHome();renderMore();$('app-shell').hidden=false;$('app-nav').hidden=false;setView('home');revealContent($('home-view'));finishBoot();
  }
  async function startApp(){
    showBoot();
    try{await load();}
    catch(error){
      $('app-shell').hidden=true;$('app-nav').hidden=true;$('cart-launcher').hidden=true;clearLoading($('status'));
      if(error.status===401)renderSessionRecovery($('status'),error);
      else{$('status').replaceChildren(node('h1','native-title','Не удалось открыть SunPark'),node('p','native-hint',error.message),button('Попробовать снова','primary-button',startApp));}
    }
  }
  startApp();
})();
