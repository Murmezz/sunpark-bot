'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const dialog = $('dish-dialog');
  const dark = new URL(location.href).searchParams.get('variant') === '5';
  let catalog = null, groupIndex = 0, categoryKey = '', query = '';
  let cartOpen = false, cartScroll = 0, currentDish = null, storageKey = null, toastTimer;
  const cart = new Map(), products = new Map();
  const money = amount => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(amount/100) + ' ₽';
  document.body.classList.toggle('night', dark);
  document.body.classList.toggle('pdf-menu', !dark);
  if (!dark) $('pdf-logo').src = '/menu-preview-logo.svg';
  try { tg?.setHeaderColor(dark ? '#141b19' : '#ffffff'); tg?.setBackgroundColor(dark ? '#141b19' : '#ffffff'); } catch (_) {}

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function arrow() {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden','true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d','m9 6 6 6-6 6'); svg.append(path);
    return svg;
  }
  function countWord(n) {
    const m = n % 100;
    return `${n} ${m >= 11 && m <= 14 ? 'позиций' : n%10 === 1 ? 'позиция' : n%10 >=2 && n%10 <=4 ? 'позиции' : 'позиций'}`;
  }
  function groupName(title) {
    const normalized = String(title).toLocaleUpperCase('ru').replace(/[^А-ЯЁA-Z0-9 ]/g,' ').replace(/\s+/g,' ').trim();
    return ({'ЕДА':'Еда','НАПИТКИ':'Напитки','АЛКОГОЛЬ':'Бар','БАР':'Бар','СЕЗОННОЕ МЕНЮ':'Сезонное'})[normalized] || title;
  }
  function updateBackButton() {
    try { if(dialog.open || cartOpen || categoryKey || query) tg?.BackButton.show(); else tg?.BackButton.hide(); } catch (_) {}
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
    $('cart-launcher').hidden=cartOpen||!catalog;
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
    closeDish(); cartScroll=window.scrollY; cartOpen=true;
    $('menu-search').hidden=true; $('menu-hub').hidden=true; $('catalog-view').hidden=true; $('cart-view').hidden=false;
    renderCart(); updateBackButton(); window.scrollTo(0,0);
  }
  function closeCart() {
    cartOpen=false; $('cart-view').hidden=true; $('menu-search').hidden=false;
    if(query||categoryKey) renderItems(); else renderHub();
    renderCart(); updateBackButton(); window.scrollTo(0,cartScroll);
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
  function closeDish() { if (dialog.open) dialog.close(); }
  function showHub() {
    closeDish(); categoryKey = ''; query = ''; $('search').value = '';
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
    dialog.showModal(); updateBackButton();
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
  dialog.addEventListener('close',updateBackButton);
  try { tg?.ready();tg?.expand();tg?.BackButton.onClick(()=>{if(dialog.open)closeDish();else if(cartOpen)closeCart();else if(catalog)showHub();}); } catch (_) {}

  async function load() {
    if(!tg?.initData) throw new Error('Откройте меню из бота: /admin → «Разработка» → «Меню SUNPARK». Доступ только администраторам.');
    const response=await fetch('/api/menu-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData}),cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Не удалось открыть меню. Попробуйте ещё раз.');
    catalog=data;
    if(!catalog.groups.length||!catalog.categories.length)throw new Error('Меню пока пусто.');
    const food=catalog.groups.findIndex(g=>groupName(g.title)==='Еда');
    if(food>=0)groupIndex=food;
    catalog.categories.forEach(category=>category.items.forEach(item=>products.set(item.id,{item,category})));
    restoreCart(); renderHub(); renderCart();
  }
  load().catch(error=>{$('menu-hub').hidden=true;$('catalog-view').hidden=true;$('status').textContent=error.message;});
})();
