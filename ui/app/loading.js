// Shared, real-request loading states. Background refreshes keep their content.
const loadingJobs=new WeakMap(),entranceAnimations=new WeakMap();
const reducedMotion=window.matchMedia?.('(prefers-reduced-motion: reduce)');
const bootTemplate=$('status').firstElementChild.cloneNode(true);
function loadingPanel(label='Загружаем раздел',compact=false){
  const panel=node('div','app-loading'+(compact?' loading-compact':' loading-section'));
  panel.setAttribute('role','status');panel.setAttribute('aria-label',label);
  const head=node('div','loading-heading'),wave=icon('waves');wave.classList.add('loading-wave');
  head.append(wave,node('p','loading-label',label));panel.append(head);
  const skeleton=node('div','loading-skeleton');skeleton.setAttribute('aria-hidden','true');
  for(let i=0;i<(compact?2:4);i++)skeleton.append(node('span','loading-line'));
  panel.append(skeleton);return panel;
}
function clearLoading(root){
  loadingJobs.delete(root);root.removeAttribute('aria-busy');
  if(root.id==='status')root.removeAttribute('data-loading');
}
function beginLoading(root,label,compact=false){
  const job={};loadingJobs.set(root,job);root.setAttribute('aria-busy','true');
  root.replaceChildren(loadingPanel(label,compact));
  return ()=>{if(loadingJobs.get(root)!==job)return false;clearLoading(root);return true;};
}
function revealContent(root){
  entranceAnimations.get(root)?.cancel();
  if(reducedMotion?.matches||typeof root.animate!=='function')return;
  const animation=root.animate([{opacity:.3},{opacity:1}],{duration:180,easing:'ease-out'});
  entranceAnimations.set(root,animation);
}
function buttonLoading(buttonNode,label='Выполняем…'){
  if(!buttonNode)return ()=>{};
  const children=[...buttonNode.childNodes],disabled=buttonNode.disabled;
  buttonNode.disabled=true;buttonNode.setAttribute('aria-busy','true');
  if(buttonNode.tagName!=='BUTTON')return ()=>{buttonNode.disabled=disabled;buttonNode.removeAttribute('aria-busy');};
  buttonNode.classList.add('button-loading');
  const wave=icon('waves');wave.classList.add('loading-wave');
  buttonNode.replaceChildren(wave,node('span','',label));
  return ()=>{buttonNode.replaceChildren(...children);buttonNode.disabled=disabled;buttonNode.removeAttribute('aria-busy');buttonNode.classList.remove('button-loading');};
}
function finishBoot(){
  const status=$('status');status.setAttribute('aria-busy','false');
  status.classList.add('boot-complete');status.setAttribute('aria-hidden','true');
  const remove=()=>{status.hidden=true;status.replaceChildren();status.removeAttribute('data-loading');status.classList.remove('boot-complete');status.removeAttribute('aria-hidden');};
  if(reducedMotion?.matches)remove();else setTimeout(remove,200);
}
function showBoot(){
  const status=$('status');status.hidden=false;status.classList.remove('boot-complete');status.removeAttribute('aria-hidden');
  status.setAttribute('data-loading','boot');status.setAttribute('aria-busy','true');status.replaceChildren(bootTemplate.cloneNode(true));
}
const conceptLoadingLabels={landing:'Открываем направление',addons:'Подбираем снаряжение',time:'Ищем свободное время',hotel_dates:'Открываем даты проживания',rooms:'Ищем свободные номера',review:'Проверяем стоимость',plans:'Загружаем ваши планы',order:'Открываем посещение',qr:'Готовим QR предзаказа',payment:'Проверяем оплату',transfer:'Подбираем перенос',staff_tables:'Загружаем столы',scan_result:'Проверяем предзаказ',calendar:'Открываем календарь',preorders:'Загружаем предзаказы',inventory:'Открываем управление',edit:'Открываем настройки'};
const nativeLoadingLabels={tickets:'Загружаем сообщения',info:'Открываем контакты',dashboard:'Открываем управление',events:'Загружаем мероприятия',event:'Открываем мероприятие',event_guests:'Загружаем участников',managers:'Загружаем команду'};
function conceptLoadingLabel(screen,service){return screen==='landing'?({wave:'Открываем волну',wake:'Открываем вейк',hotel:'Открываем отель',restaurant:'Открываем ресторан'})[service]||conceptLoadingLabels.landing:conceptLoadingLabels[screen]||'Открываем раздел';}
