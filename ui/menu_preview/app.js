'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const dialog = $('dish-dialog');
  let catalog = null, groupIndex = 0, categoryKey = '', query = '';
  let variant = new URL(location.href).searchParams.get('variant') === '5' ? 5 : 4;
  function theme() {
    const dark = variant === 5;
    document.body.classList.toggle('night', dark);
    document.body.classList.toggle('pdf-menu', !dark);
    if (!dark && !$('pdf-logo').getAttribute('src')) $('pdf-logo').src = '/menu-preview-logo.svg';
    $('edition').textContent = dark ? '05 / ВЕЧЕРНИЙ' : '04 / ДНЕВНОЙ';
    $('intro').textContent = dark ? 'Вкус вашего вечера.' : 'Найдите своё любимое.';
    try { tg?.setHeaderColor(dark ? '#141b19' : '#ffffff'); tg?.setBackgroundColor(dark ? '#141b19' : '#ffffff'); } catch (_) {}
  }
  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function countWord(n) {
    const m = n % 100;
    return `${n} ${m >= 11 && m <= 14 ? 'позиций' : n%10 === 1 ? 'позиция' : n%10 >=2 && n%10 <=4 ? 'позиции' : 'позиций'}`;
  }
  function closeDish() { if (dialog.open) dialog.close(); }
  function showDish(item, category) {
    $('dish-section').textContent = [category.title, item.section].filter(Boolean).join(' / ');
    $('dish-name').textContent = item.name;
    $('dish-price').textContent = item.price;
    $('dish-description').textContent = item.description || 'Состав не указан в меню. Уточните у официанта.';
    $('dish-footer').textContent = category.footer || '';
    dialog.showModal();
    try { tg?.BackButton.show(); tg?.HapticFeedback.selectionChanged(); } catch (_) {}
  }
  function renderNavigation() {
    $('groups').replaceChildren();
    catalog.groups.forEach((group, i) => {
      const b = node('button', '', group.title === 'АЛКОГОЛЬ' ? 'Бар' : group.title);
      b.type = 'button'; b.setAttribute('aria-pressed', String(groupIndex === i));
      b.addEventListener('click', () => {
        groupIndex = i; categoryKey = group.keys[0]; query = ''; $('search').value = '';
        renderNavigation(); renderItems();
      });
      $('groups').append(b);
    });
    $('categories').replaceChildren();
    const keys = catalog.groups[groupIndex]?.keys || [];
    catalog.categories.filter(c => keys.includes(c.key)).forEach(cat => {
      const b = node('button', '', cat.title); b.type = 'button';
      b.setAttribute('aria-pressed', String(categoryKey === cat.key && !query));
      b.addEventListener('click', () => { categoryKey = cat.key; query = ''; $('search').value = ''; renderNavigation(); renderItems(); });
      $('categories').append(b);
    });
  }
  function renderItems() {
    const category = catalog.categories.find(c => c.key === categoryKey);
    const list = [];
    if (query) {
      catalog.categories.forEach(cat => cat.items.forEach(item => {
        if ([item.name, item.description, cat.title].join(' ').toLocaleLowerCase('ru').includes(query)) list.push({item, cat});
      }));
    } else if (category) category.items.forEach(item => list.push({item, cat:category}));
    $('section-title').textContent = query ? 'Результаты поиска' : category?.title || 'Меню';
    $('section-kicker').textContent = query ? 'ПО ВСЕМУ МЕНЮ' : catalog.groups[groupIndex]?.title || 'SUNPARK';
    $('item-count').textContent = countWord(list.length);
    $('category-footer').textContent = query ? '' : category?.footer || '';
    $('items').replaceChildren();
    $('status').textContent = list.length ? '' : query ? 'Ничего не найдено. Попробуйте другое название.' : 'В этом разделе пока нет блюд.';
    let section = '';
    list.forEach(({item, cat}) => {
      const newSection = query ? cat.title : item.section;
      if (newSection && newSection !== section) $('items').append(node('h3', 'subsection', newSection));
      section = newSection;
      const b = node('button', 'item-row'); b.type = 'button';
      b.setAttribute('aria-label', `${item.name}, ${item.price}. Посмотреть состав`);
      b.append(node('span', 'name', item.name), node('span', 'price', item.price), node('span', 'arrow', ''));
      b.addEventListener('click', () => showDish(item, cat));
      $('items').append(b);
    });
  }
  $('search').addEventListener('input', e => { query = e.target.value.trim().toLocaleLowerCase('ru'); if(catalog) { renderNavigation(); renderItems(); } });
  $('theme-switch').addEventListener('click', () => { variant = variant === 4 ? 5 : 4; const u = new URL(location.href); u.searchParams.set('variant', variant); history.replaceState(null, '', u); theme(); });
  $('close-dialog').addEventListener('click', closeDish);
  $('back-to-menu').addEventListener('click', closeDish);
  dialog.addEventListener('click', e => { if(e.target === dialog) { const r = dialog.getBoundingClientRect(); if(e.clientY < r.top || e.clientY > r.bottom || e.clientX < r.left || e.clientX > r.right) closeDish(); } });
  dialog.addEventListener('close', () => { try { tg?.BackButton.hide(); } catch (_) {} });
  try { tg?.ready(); tg?.expand(); tg?.BackButton.onClick(closeDish); } catch (_) {}
  theme();
  async function load() {
    if (!tg?.initData) throw new Error('Откройте этот экран из бота: /admin → «Просмотр меню». Доступ только администраторам.');
    const response = await fetch('/api/menu-preview', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({init_data:tg.initData}), cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Не удалось открыть меню. Попробуйте ещё раз.');
    catalog = data;
    if (!catalog.groups.length || !catalog.categories.length) throw new Error('Меню пока пусто.');
    categoryKey = catalog.groups[0].keys[0];
    renderNavigation(); renderItems();
  }
  load().catch(error => { $('section-title').textContent = 'Меню SUNPARK'; $('status').textContent = error.message; });
})();

