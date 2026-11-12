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
function closeService() {setView(serviceOrigin);window.scrollTo(0,serviceScroll);}
function openService(id,origin=serviceOrigin) {
  const service=catalog.services?.items.find(s=>s.id===id);if(!service)return;
  currentServiceId=id;
  if(appView!=='service'){serviceScroll=window.scrollY;serviceOrigin=origin;}
  const root=$('service-view');root.replaceChildren();
  const back=node('button','back-link','');back.type='button';back.append(icon('arrow-left'),node('span','',serviceOrigin==='more'?'К другим разделам':'На главную'));back.addEventListener('click',closeService);root.append(back);
  const tabs=node('nav','group-tabs service-tabs');tabs.setAttribute('aria-label','Направления SUNPARK');
  for(const item of catalog.services.items){const b=node('button','',item.title);b.type='button';b.setAttribute('aria-pressed',String(item.id===id));b.addEventListener('click',()=>openService(item.id));tabs.append(b);}
  const heading=node('h1','page-title',service.title);heading.tabIndex=-1;
  root.append(tabs,heading,node('p','service-subtitle',service.teaser));
  if(id==='wake')root.append(node('p','service-season',service.price_label));
  const gallery=node('div','service-gallery'),track=node('div','service-photos');track.setAttribute('aria-label',`Фотографии: ${service.title}`);
  service.photos.forEach((url,i)=>{const slide=node('div','service-photo');slide.append(serviceImage(url,`SUNPARK · ${service.title}, фото ${i+1}`),node('span','photo-fallback','Фото временно недоступно'));track.append(slide);});
  const controls=node('div','gallery-controls'),previous=node('button','icon-button'),next=node('button','icon-button'),counter=node('span','gallery-counter',`1 / ${service.photos.length}`);
  previous.type=next.type='button';previous.setAttribute('aria-label','Предыдущее фото');next.setAttribute('aria-label','Следующее фото');previous.append(icon('arrow-left'));next.append(icon('arrow-right'));previous.disabled=true;
  counter.setAttribute('aria-live','polite');let photoIndex=0;
  function move(delta){const width=track.clientWidth;track.scrollTo({left:(photoIndex+delta)*width,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
  previous.addEventListener('click',()=>move(-1));next.addEventListener('click',()=>move(1));
  track.addEventListener('scroll',()=>{photoIndex=Math.max(0,Math.min(service.photos.length-1,Math.round(track.scrollLeft/track.clientWidth)));counter.textContent=`${photoIndex+1} / ${service.photos.length}`;previous.disabled=photoIndex===0;next.disabled=photoIndex===service.photos.length-1;},{passive:true});
  controls.append(previous,counter,next);gallery.append(track,controls);root.append(gallery);
  const actions=node('div','service-actions');
  if(id==='restaurant'){
    const menu=node('button','primary-button','Меню ресторана');menu.id='restaurant-menu';menu.type='button';menu.addEventListener('click',goMenu);actions.append(menu);
    for(const [label,callback,buttonId] of [['Забронировать стол','booking:start','restaurant-booking'],['Провести банкет','banquet:contact','restaurant-banquet']]){
      const b=node('button','secondary-button',label);b.id=buttonId;b.type='button';b.addEventListener('click',()=>runAction(callback,'guest'));actions.append(b);
    }
  }
  actions.append(serviceLink('Позвонить · '+service.phone_label,'tel:'+service.phone,id==='restaurant'?'secondary-button':'primary-button'));
  root.append(actions);
  root.append(node('p','service-description',service.description));
  if(service.additional_phone)root.append(serviceLink('Городской: '+service.additional_phone_label,'tel:'+service.additional_phone,'service-phone'));
  if(service.notice)root.append(node('p','service-notice',service.notice));
  const prices=node('section','service-prices');prices.setAttribute('aria-labelledby','service-prices-title');const title=node('h2','','Цены');title.id='service-prices-title';prices.append(title,node('p','catalog-hint',service.price_label));
  service.groups.forEach((group,i)=>{
    const details=node('details','service-price-group');details.open=i===0;
    const summary=node('summary','',group.title);details.append(summary);
    if(group.note)details.append(node('p','catalog-hint',group.note));
    const list=node('dl','service-price-list');
    for(const row of group.rows){const block=node('div','service-price-row'),label=node('dt','',row.label),value=node('dd');value.append(node('strong','',serviceMoney(row.amount)));if(row.unit)value.append(node('span','',row.unit));block.append(label,value);if(row.note)block.append(node('dd','service-price-note',row.note));list.append(block);}
    details.append(list);prices.append(details);
  });
  if(service.groups.length)root.append(prices);
  const contact=node('section','service-contact');contact.append(node('h2','','Как добраться'),node('p','',catalog.services.address),node('p','catalog-hint',service.hours));root.append(contact);
  setView('service');window.scrollTo(0,0);heading.focus({preventScroll:true});
}
