// Public service information shares one server catalogue with the Telegram bot.
let serviceOrigin='home', serviceScroll=0, currentServiceId=null;
const serviceMoney=amount=>new Intl.NumberFormat('ru-RU').format(amount)+' ₽';
function serviceLink(label,href,className='service-link') {
  const a=node('a',className,label);a.href=href;
  return a;
}
function serviceImage(url,alt,thumbnail=false) {
  const image=node('img');image.src=url;image.alt=alt;image.loading='lazy';image.decoding='async';
  const variant=size=>url.replace(/\.(jpe?g|png)$/,`-${size}x${size}.$1`);
  // Full JPEGs are already small and retain the original composition. Use the
  // site's reduced PNGs for rooms, whose originals exceed 2 MB each.
  if(thumbnail||url.endsWith('.png')) {
    image.srcset=`${variant(400)} 400w, ${variant(800)} 800w`;
    image.sizes=thumbnail?'84px':'(max-width: 640px) calc(100vw - 52px), 588px';
  }
  image.addEventListener('error',()=>{image.hidden=true;image.parentElement.classList.add('image-missing');});
  return image;
}
function renderServiceLinks() {
  const root=$('home-services');root.replaceChildren();
  for(const service of catalog.services?.items||[]) {
    const b=node('button','service-card');b.type='button';b.dataset.service=service.id;
    const image=node('span','service-thumbnail');image.append(serviceImage(service.photos[0],'',true));
    const copy=node('span','service-card-copy');copy.append(node('strong','',service.title),node('span','',service.subtitle));
    b.append(image,copy);b.addEventListener('click',()=>openService(service.id,'home'));root.append(b);
  }
}
function mapLink(label='Показать на карте'){
  const url=catalog.services?.map_url||'https://yandex.ru/maps/org/sunpark/1696243668';
  const link=serviceLink(label,/^https:\/\//.test(url)?url:'https://yandex.ru/maps/org/sunpark/1696243668','location-link');link.target='_blank';link.rel='noopener noreferrer';return link;
}
function renderHomeLocation(){
  const root=$('home-location');root.replaceChildren(node('p','',catalog.services?.address||'Санкт-Петербург, ул. Никольская, 9'));
  const links=node('div','location-actions');links.append(mapLink('Маршрут'),button('Контакты','location-link',()=>openNative('info',{},true)));root.append(links);
}
function closeService(){setView(serviceOrigin);window.scrollTo(0,serviceScroll);}
function openService(id,origin=serviceOrigin){
  const service=catalog.services?.items.find(s=>s.id===id);if(!service)return;
  currentServiceId=id;if(appView!=='service'){serviceScroll=window.scrollY;serviceOrigin=origin;}
  const root=$('service-view');root.replaceChildren();
  const top=node('div','service-topline'),back=button('','back-link',closeService);back.append(icon('arrow-left'),node('span','','Главная'));back.setAttribute('aria-label','На главную');
  const call=serviceLink(service.phone_label,'tel:'+service.phone,'service-call');call.setAttribute('aria-label',`Позвонить: ${service.title}, ${service.phone_label}`);top.append(back,call);root.append(top);
  const heading=node('h1','page-title',service.title);heading.tabIndex=-1;root.append(heading,node('p','service-subtitle',service.teaser));
  if(service.facts?.length){const facts=node('dl','service-facts');for(const [label,value] of service.facts){const row=node('div');row.append(node('dt','',label),node('dd','',value));facts.append(row);}root.append(facts);}
  root.append(node('p','service-hours',id==='restaurant'?service.hours.replace(' Кухня работает до 22:30.',''):service.hours));
  if(service.notice&&id!=='restaurant')root.append(node('p','service-note',service.notice));
  if(id==='restaurant'){
    const actions=node('div','restaurant-actions');actions.setAttribute('role','group');actions.setAttribute('aria-label','Действия ресторана');
    const menu=button('','restaurant-menu-link',goMenu),copy=node('span','restaurant-menu-copy');menu.id='restaurant-menu';copy.append(node('strong','','Меню ресторана'),node('span','','Еда, напитки и бар'));menu.append(icon('fork-knife'),copy,icon('arrow-right'));actions.append(menu);
    const requests=node('div','restaurant-requests');
    for(const [label,name,callback,buttonId] of [['Забронировать стол','calendar-blank','booking:start','restaurant-booking'],['Провести банкет','users-three','banquet:contact','restaurant-banquet']]){const b=button('','restaurant-request',()=>runAction(callback,'guest'));b.id=buttonId;b.append(icon(name),node('span','',label));requests.append(b);}
    actions.append(requests);root.append(actions);
  }
  const gallery=node('div','service-gallery'),track=node('div','service-photos');track.setAttribute('aria-label',`Фотографии: ${service.title}`);
  service.photos.forEach((url,i)=>{const slide=node('div','service-photo');slide.append(serviceImage(url,`${id==='hotel'?'Интерьер отеля':'SunPark · '+service.title}, фото ${i+1}`),node('span','photo-fallback','Фото временно недоступно'));track.append(slide);});
  const controls=node('div','gallery-controls'),previous=button('','icon-button'),next=button('','icon-button'),counter=node('span','gallery-counter',`1 / ${service.photos.length}`);
  previous.setAttribute('aria-label','Предыдущее фото');next.setAttribute('aria-label','Следующее фото');previous.append(icon('arrow-left'));next.append(icon('arrow-right'));previous.disabled=true;counter.setAttribute('aria-live','polite');let photoIndex=0;
  function move(delta){track.scrollTo({left:(photoIndex+delta)*track.clientWidth,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
  previous.addEventListener('click',()=>move(-1));next.addEventListener('click',()=>move(1));
  track.addEventListener('scroll',()=>{photoIndex=Math.round(track.scrollLeft/Math.max(1,track.clientWidth));counter.textContent=`${photoIndex+1} / ${service.photos.length}`;previous.disabled=photoIndex===0;next.disabled=photoIndex===service.photos.length-1;},{passive:true});
  controls.append(previous,counter,next);gallery.append(track,controls);root.append(gallery);if(id==='hotel')root.append(node('p','gallery-caption','Интерьеры отеля'));
  if(service.groups.length){
    const prices=node('section','service-prices');prices.setAttribute('aria-labelledby','service-prices-title');const title=node('h2','','Цены');title.id='service-prices-title';prices.append(title);
    if(id!=='wake')prices.append(node('p','catalog-hint',service.price_label));
    service.groups.forEach((group,i)=>{
      const details=node('details','service-price-group');details.open=i===0;details.append(node('summary','',group.title));if(group.note)details.append(node('p','catalog-hint',group.note));const list=node('dl','service-price-list');
      for(const row of group.rows){const block=node('div','service-price-row'),label=node('dt','',row.label),value=node('dd');value.append(node('strong','',serviceMoney(row.amount)));if(row.unit)value.append(node('span','',row.unit));block.append(label,value);if(row.note)block.append(node('dd','service-price-note',row.note));list.append(block);}details.append(list);prices.append(details);
    });root.append(prices);
  }
  const about=node('details','service-about');about.append(node('summary','',id==='restaurant'?'О ресторане':id==='hotel'?'Об отеле':id==='wave'?'О катании на волне':'О вейкпарке'),node('p','service-description',service.description));root.append(about);
  if(service.additional_phone)root.append(serviceLink('Городской · '+service.additional_phone_label,'tel:'+service.additional_phone,'service-phone'));
  const contact=node('section','service-contact');contact.append(node('h2','','Как добраться'),node('p','',catalog.services.address),mapLink());root.append(contact);
  setView('service');window.scrollTo(0,0);heading.focus({preventScroll:true});
}
