// Opt-in UI refinement. Shared booking, payment and storage contracts stay intact.
let refinedDockObserver=null;
let refinedDockContentObserver=null;
function refinedPlaces(n){const m=n%100;return n+' '+(m>=11&&m<=14?'мест':n%10===1?'место':n%10>=2&&n%10<=4?'места':'мест');}
function refinedHotelRange(root,arrival,departure,values){
  if(!refinedDesign)return;
  const range=node('div','hotel-date-range');root.insertBefore(range,arrival);
  for(const [button,label,value] of [[arrival,'Заезд',values.arrival],[departure,'Выезд',values.departure]]){
    button.setAttribute('aria-label','Дата '+(label==='Заезд'?'заезда':'выезда'));
    const date=node('strong','',value?displayDate(value):'Выбрать дату');date.id=label==='Заезд'?'refined-arrival-value':'refined-departure-value';button.setAttribute('aria-describedby',date.id);
    button.replaceChildren(node('span','date-caption',label),date);
    range.append(button);
  }
}
function refinedProgress(root){
  if(!refinedDesign||root.id!=='concept-content'||typeof conceptState==='undefined')return;
  const s=conceptState,service=s.values?.service;
  let labels,active;
  if(service==='restaurant'){labels=['Заказ','Приход','Оплата'];active={arrival:1,review:2}[s.screen];}
  else if(service==='hotel'){labels=['Даты','Номер','Контакты','Оплата'];active={hotel_dates:0,rooms:1,contacts:2,review:3}[s.screen];}
  else{labels=['Формат','Время','Контакты','Оплата'];active={addons:0,time:1,contacts:2,review:3}[s.screen];}
  if(active===undefined)return;
  const progress=node('div','journey-progress');progress.setAttribute('aria-label',`Шаг ${active+1} из ${labels.length}: ${labels[active]}`);
  progress.setAttribute('role','progressbar');progress.setAttribute('aria-valuemin','1');progress.setAttribute('aria-valuemax',String(labels.length));progress.setAttribute('aria-valuenow',String(active+1));
  const top=node('div','journey-progress-label');top.append(node('span','',labels[active]),node('span','',`${active+1} / ${labels.length}`));
  const track=node('div','journey-progress-track');track.setAttribute('aria-hidden','true');
  labels.forEach((_,i)=>track.append(node('span',i<=active?'complete':'')));
  progress.append(top,track);root.append(progress);
}
function refinedDock(root,box){
  if(!refinedDesign)return;
  refinedDockObserver?.disconnect();
  refinedDockContentObserver?.disconnect();
  root.querySelectorAll('.refined-dock').forEach(e=>e.classList.remove('refined-dock'));
  root.classList.add('has-refined-dock');box.classList.add('refined-dock');
  const updatePrice=()=>{
    if(!['time','landing'].includes(conceptState?.screen))return;
    const total=root.querySelector('.concept-total'),choice=root.querySelector('.concept-choice.selected');
    const amount=(total?.querySelector('strong')||choice?.querySelector('b'))?.textContent;if(!amount)return;
    const label=total?.querySelector('span')?.textContent||'Выбранный формат';
    let caption=box.querySelector('.refined-dock-total');if(caption?.dataset.value===label+amount)return;
    if(!caption){caption=node('div','refined-dock-total');box.prepend(caption);}
    caption.dataset.value=label+amount;caption.replaceChildren(node('span','',label),node('strong','',amount));
  };
  updatePrice();
  if(typeof MutationObserver==='function'){refinedDockContentObserver=new MutationObserver(updatePrice);refinedDockContentObserver.observe(root,{childList:true,subtree:true,characterData:true});}
  const measure=()=>{if(box.isConnected)root.style.setProperty('--dock-height',Math.ceil(box.getBoundingClientRect().height)+'px');};
  requestAnimationFrame(()=>{if(!box.isConnected)return;measure();if(typeof ResizeObserver==='function'){refinedDockObserver=new ResizeObserver(measure);refinedDockObserver.observe(box);}});
}
function refinedTag(element,status){if(refinedDesign)element.dataset.status=status;}
if(refinedDesign){
  // Keep page scrolling inside the Mini App instead of dragging its host sheet.
  try{if(tg?.isVersionAtLeast?.('7.7')&&typeof tg.disableVerticalSwipes==='function')tg.disableVerticalSwipes();}catch(_){}
  const menuBack=$('back-to-sections');
  if(typeof ResizeObserver==='function')new ResizeObserver(()=>{
    const height=Math.ceil(menuBack.getBoundingClientRect().height);
    if(height)document.documentElement.style.setProperty('--menu-back-height',height+'px');
  }).observe(menuBack);
  const sheetActions=node('div','dish-actions');sheetActions.append($('dish-quantity'),$('dish-add'),$('dish-remove'));dialog.append(sheetActions);
  const cartActions=node('div','cart-actions');cartActions.id='refined-cart-actions';cartActions.hidden=true;
  cartActions.append(...['preorder-checkout','cart-clear','cart-clear-confirm'].map($).filter(Boolean));$('cart-view').append(cartActions);
  if(typeof ResizeObserver==='function')new ResizeObserver(()=>$('cart-view').style.setProperty('--dock-height',Math.ceil(cartActions.getBoundingClientRect().height)+'px')).observe(cartActions);
  $('cart-title').firstElementChild.textContent='Корзина';
  $('cart-clear').textContent='Очистить корзину';
}
