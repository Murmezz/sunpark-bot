'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const dialog = $('dish-dialog');
  const dark = new URL(location.href).searchParams.get('variant') === '5';
  let catalog = null, groupIndex = 0, categoryKey = '', query = '';
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
    try { if(dialog.open || categoryKey || query) tg?.BackButton.show(); else tg?.BackButton.hide(); } catch (_) {}
  }
  function closeDish() { if (dialog.open) dialog.close(); }
  function showHub() {
    closeDish(); categoryKey = ''; query = ''; $('search').value = '';
    renderHub(); updateBackButton(); window.scrollTo(0,0);
  }
  function showDish(item, category) {
    $('dish-section').textContent = [category.title, item.section].filter(Boolean).join(' / ');
    $('dish-name').textContent = item.name;
    $('dish-price').textContent = item.price;
    $('dish-description').textContent = item.description || 'Состав не указан в меню. Уточните у официанта.';
    $('dish-footer').textContent = category.footer || '';
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
  dialog.addEventListener('click',e=>{
    if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientY<r.top||e.clientY>r.bottom||e.clientX<r.left||e.clientX>r.right) closeDish();}
  });
  dialog.addEventListener('close',updateBackButton);
  try { tg?.ready();tg?.expand();tg?.BackButton.onClick(()=>{if(dialog.open)closeDish();else if(catalog)showHub();}); } catch (_) {}

  async function load() {
    if(!tg?.initData) throw new Error('Откройте меню из бота: /admin → «Просмотр меню». Доступ только администраторам.');
    const response=await fetch('/api/menu-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData}),cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Не удалось открыть меню. Попробуйте ещё раз.');
    catalog=data;
    if(!catalog.groups.length||!catalog.categories.length)throw new Error('Меню пока пусто.');
    const food=catalog.groups.findIndex(g=>groupName(g.title)==='Еда');
    if(food>=0)groupIndex=food;
    renderHub();
  }
  load().catch(error=>{$('menu-hub').hidden=true;$('catalog-view').hidden=true;$('status').textContent=error.message;});
})();
