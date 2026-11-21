// Dedicated Mini App screens. Bundled inside app.js's existing private scope.
let nativeState=null,nativeStack=[],nativeSequence=0,pickerDone=null,nativeOrigin='home';
let chatRenderKey='',chatTicketKey='',nativeChatKey='',chatRequest=null,chatMessages=new Map(),chatOlder=false;
const chatDrafts=new Map();
const formLabels={date:'Дата',time:'Время по Москве',guests:'Количество гостей',name:'Ваше имя',phone:'Телефон',comment:'Пожелания',event:'Повод или формат',wishes:'Пожелания',title:'Название',description:'Описание',starts_at:'Дата и время по Москве',location:'Место',price:'Стоимость и условия',capacity:'Лимит самостоятельной записи',first_name:'Имя',last_name:'Фамилия',party_size:'Гостей, включая контактное лицо',telegram_username:'Telegram-ник',username:'Telegram-ник',note:'Заметка менеджера',message:'Ваш вопрос'};
const clone=value=>JSON.parse(JSON.stringify(value));
const dayISO=(year,month,day)=>`${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
function displayDate(value,options={day:'numeric',month:'long'}){if(!/^\d{4}-\d{2}-\d{2}/.test(value||''))return value||'Выберите дату';return new Date(value.slice(0,10)+'T12:00:00Z').toLocaleDateString('ru-RU',{...options,timeZone:'UTC'});}
function guestCount(n){const v=Number(n),m=v%100;return v+' '+(m>=11&&m<=14?'гостей':v%10===1?'гость':v%10>=2&&v%10<=4?'гостя':'гостей');}
function requestDate(value){const m=/^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value||'');return m?displayDate(`${m[3]}-${m[2]}-${m[1]}`):displayDate(value);}
function parseStamp(value){const text=String(value||'').replace(' ','T');return new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(text)?text:text+'Z');}
function button(label,className,action){const b=node('button',className,label);b.type='button';if(action)b.addEventListener('click',action);return b;}
function heading(root,title,subtitle=''){root.append(node('h1','native-title',title));if(subtitle)root.append(node('p','native-subtitle',subtitle));}
function message(root,text,kind='hint'){const p=node('p','native-'+kind,text);if(kind==='error')p.setAttribute('role','alert');root.append(p);return p;}
function draftKey(kind){return `sunpark:request-draft:v2:${catalog?.user?.id}:${kind}`;}
function saveNativeDraft(){if(!nativeState||!['booking','banquet'].includes(nativeState.screen))return;try{localStorage.setItem(draftKey(nativeState.screen),JSON.stringify(nativeState.values));}catch(_){}}
function getNativeDraft(kind){try{const value=JSON.parse(localStorage.getItem(draftKey(kind))||'null');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch(_){return {};}}
function nativeBack(){nativeSequence++;saveNativeDraft();if(nativeState&&['booking','banquet'].includes(nativeState.screen)&&nativeState.step>0){nativeState.step--;renderNative();return;}if(nativeStack.length){nativeState=nativeStack.pop();nativeOrigin=nativeState.origin||'home';setView('native');renderNative();}else{const current=nativeState?.screen;if(['event','event_edit','manual','register','event_guests'].includes(current)){openNative(current==='event'?'events':'event',{...nativeState.args},true);return;}if(nativeOrigin==='restaurant'){openService('restaurant','home');return;}if(nativeOrigin==='messages'){openInbox('guest');return;}setView(nativeOrigin==='management'?'more':'home');scrollPage();}}
$('native-back').addEventListener('click',()=>appView==='more'?openInbox('guest'):nativeBack());
function rememberNative(){if(nativeState){const saved=clone(nativeState);saved.origin=nativeState.origin||nativeOrigin;nativeStack.push(saved);}}
async function openNative(screen,args={},root=false){
  let origin=nativeState?.origin||nativeOrigin;
  if(screen==='tickets'&&args.scope!=='staff')origin='home';
  else if(appView==='service'&&currentServiceId==='restaurant')origin='restaurant';
  else if(appView==='native'&&nativeState?.screen==='tickets'&&nativeState.args.scope!=='staff')origin='messages';
  else if(appView==='more'||args.scope==='staff')origin='management';
  else if(appView!=='native')origin='home';
  saveNativeDraft();if(root===true)nativeStack=[];else if(root!=='replace'&&appView==='native'&&nativeState?.data)rememberNative();nativeOrigin=origin;
  const sequence=++nativeSequence;nativeState={screen,args,data:null,values:{},step:0,origin:nativeOrigin};setView('native');scrollPage();
  $('native-content').replaceChildren(node('p','empty-state','Загружаем…'));$('native-content').setAttribute('aria-busy','true');
  try{
    const data=await api('screen',{screen,...args});
    if(sequence!==nativeSequence||appView!=='native')return;
    if(data.existing_ticket){toast('У вас уже есть открытая заявка');await openChat(data.existing_ticket,'guest');return;}
    nativeState.data=data;
    nativeState.values={...(data.data||{})};
    if(['booking','banquet'].includes(screen))nativeState.values={guests:'2',name:data.profile_name||'',...nativeState.values,...getNativeDraft(screen)};
    renderNative();
  }catch(error){if(sequence===nativeSequence&&appView==='native'){if(error.status===401)renderSessionRecovery($('native-content'),error);else{$('native-content').replaceChildren();heading($('native-content'),'Не удалось загрузить');message($('native-content'),error.message,'error');$('native-content').append(button('Попробовать ещё раз','primary-button',()=>openNative(screen,args,'replace')));}}}
  finally{if(sequence===nativeSequence)$('native-content').removeAttribute('aria-busy');}
}
function openLocalForm(kind,data={},args={}){if(appView==='native'&&nativeState)rememberNative();nativeOrigin='management';nativeState={origin:nativeOrigin,screen:'local_form',args:{scope:'staff',...args},kind,values:{...data},data:{today:new Date().toISOString().slice(0,10)}};setView('native');renderNative();}
function renderNative(){
  const root=$('native-content');root.replaceChildren();root.classList.remove('request-screen');$('native-content').removeAttribute('aria-busy');setView('native');scrollPage();
  const s=nativeState;if(!s)return;
  if(['booking','banquet'].includes(s.screen))return renderRequest(root,s);
  if(s.screen==='dashboard')return renderDashboard(root,s);
  if(s.screen==='tickets')return renderTicketList(root,s);
  if(s.screen==='events')return renderEventList(root,s);
  if(s.screen==='event')return renderEventDetail(root,s);
  if(s.screen==='event_guests')return renderRegistrations(root,s);
  if(s.screen==='managers')return renderManagers(root,s);
  if(s.screen==='info')return renderInfo(root,s);
  if(['event_create','event_edit','manual','register','note','local_form','inquiry'].includes(s.screen))return renderTypedForm(root,s);
  if(s.screen==='success'){
    const mark=node('div','success-mark');mark.append(icon('check'));root.append(mark);heading(root,s.title||'Готово');if(s.request){const v=s.request.values;root.append(node('p','success-context',[displayDate(v.date),v.time,guestCount(v.guests)].filter(Boolean).join(' · ')));message(root,(s.notice||'Менеджер подтвердит возможность бронирования.').replace(/^Заявка отправлена[.!]?\s*/,''));message(root,'Следите за ответом в переписке.');}else message(root,s.notice||'Изменения сохранены.');
    if(s.ticket)root.append(button('Открыть переписку','primary-button',()=>openChat(s.ticket,'guest')));
    root.append(button('На главную','secondary-button',()=>setView('home')));
  }
}
function calendar(root,selected,today,onChange){
  const initial=(selected&&selected>=today?selected:today).split('-').map(Number);let year=initial[0],month=initial[1]-1;
  const wrap=node('div','calendar');root.append(wrap);
  function draw(focusDate){
    wrap.replaceChildren();const head=node('div','calendar-heading');
    const prev=button('','icon-button',()=>{if(month===0){month=11;year--;}else month--;draw();});prev.append(icon('arrow-left'));prev.setAttribute('aria-label','Предыдущий месяц');prev.disabled=dayISO(year,month,1)<=today.slice(0,7)+'-01';
    const next=button('','icon-button',()=>{if(month===11){month=0;year++;}else month++;draw();});next.append(icon('arrow-right'));next.setAttribute('aria-label','Следующий месяц');
    const label=node('h2','calendar-month',displayDate(dayISO(year,month,1),{month:'long',year:'numeric'}).replace(/\s*г\.$/,''));label.id='calendar-month-label';head.append(prev,label,next);wrap.append(head);
    const days=node('div','calendar-weekdays');for(const name of ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'])days.append(node('span','',name));days.setAttribute('aria-hidden','true');wrap.append(days);
    const grid=node('div','calendar-days');grid.setAttribute('role','group');grid.setAttribute('aria-label',label.textContent);
    const offset=(new Date(Date.UTC(year,month,1)).getUTCDay()+6)%7,count=new Date(Date.UTC(year,month+1,0)).getUTCDate();const tabDate=focusDate||([selected,today].find(d=>d&&d.slice(0,7)===dayISO(year,month,1).slice(0,7)))||dayISO(year,month,1);
    for(let i=0;i<offset;i++){const blank=node('span','calendar-blank');blank.setAttribute('aria-hidden','true');grid.append(blank);}
    for(let day=1;day<=count;day++){
      const iso=dayISO(year,month,day),b=button(String(day),'calendar-day',()=>{selected=iso;onChange(iso);draw(iso);});
      b.dataset.date=iso;b.disabled=iso<today;b.setAttribute('aria-label',displayDate(iso,{weekday:'long',day:'numeric',month:'long',year:'numeric'}));b.setAttribute('aria-pressed',String(iso===selected));if(iso===today)b.setAttribute('aria-current','date');
      b.tabIndex=iso===tabDate?0:-1;
      b.addEventListener('keydown',event=>{const deltas={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};if(!(event.key in deltas))return;event.preventDefault();const date=new Date(iso+'T12:00Z');date.setUTCDate(date.getUTCDate()+deltas[event.key]);const target=date.toISOString().slice(0,10);if(target<today)return;year=date.getUTCFullYear();month=date.getUTCMonth();draw(target);});grid.append(b);
    }
    wrap.append(grid);if(focusDate)wrap.querySelector(`[data-date="${focusDate}"]`)?.focus({preventScroll:true});
  }
  draw();return wrap;
}
function timeWheel(root,value,onChange){
  let [hour,minute]=/^\d{2}:\d{2}$/.test(value||'')?value.split(':').map(Number):[19,0];
  const wrap=node('div','time-wheel'),wheels=[];wrap.setAttribute('role','group');wrap.setAttribute('aria-label','Время по Москве');
  const change=()=>onChange(`${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`);
  for(const [column,max,label] of [['hour',24,'Часы'],['minute',60,'Минуты']]){
    const scroll=node('div','wheel-column');scroll.tabIndex=0;scroll.setAttribute('role','listbox');scroll.setAttribute('aria-label',label);let timer;
    function select(number,move=false){const n=Math.max(0,Math.min(max-1,number));if(column==='hour')hour=n;else minute=n;for(const option of scroll.children)option.setAttribute('aria-selected',String(Number(option.dataset.value)===n));scroll.setAttribute('aria-activedescendant',`wheel-${column}-${n}`);if(move)scroll.scrollTo({top:n*44,behavior:'auto'});change();}
    for(let n=0;n<max;n++){const option=node('div','wheel-option',String(n).padStart(2,'0'));option.id=`wheel-${column}-${n}`;option.dataset.value=n;option.setAttribute('role','option');option.setAttribute('aria-selected',String(n===(column==='hour'?hour:minute)));option.addEventListener('click',()=>select(n,true));scroll.append(option);}
    scroll.addEventListener('scroll',()=>{cancelAnimationFrame(timer);timer=requestAnimationFrame(()=>{if(scroll.isConnected)select(Math.round(scroll.scrollTop/44));});},{passive:true});
    scroll.addEventListener('keydown',event=>{const current=column==='hour'?hour:minute;const next=({ArrowDown:current+1,ArrowUp:current-1,PageDown:current+5,PageUp:current-5,Home:0,End:max-1})[event.key];if(next===undefined)return;event.preventDefault();select(next,true);});
    wheels.push({scroll,value:column==='hour'?hour:minute});wrap.append(scroll);if(column==='hour')wrap.append(node('span','wheel-colon',':'));
  }
  root.append(wrap);requestAnimationFrame(()=>{for(const {scroll,value} of wheels)scroll.scrollTop=value*44;});change();return wrap;
}
function errorSlot(root,key){const p=node('p','field-error');p.dataset.errorFor=key;p.id='error-'+key;p.setAttribute('role','alert');root.append(p);return p;}
function showFields(errors,notice=''){
  for(const e of document.querySelectorAll('#native-content .field-error'))e.textContent='';
  for(const e of document.querySelectorAll('#native-content [aria-invalid]'))e.removeAttribute('aria-invalid');
  for(const [key,text] of Object.entries(errors||{})){const slot=[...$('native-content').querySelectorAll('[data-error-for]')].find(e=>e.dataset.errorFor===key);if(slot)slot.textContent=text;const input=$('native-content').querySelector(`[name="${key}"]`);if(input)input.setAttribute('aria-invalid','true');}
  let banner=$('native-form-error');if(notice){if(!banner){banner=node('p','native-error');banner.id='native-form-error';banner.setAttribute('role','alert');$('native-content').append(banner);}banner.textContent=notice;}
  const first=$('native-content').querySelector('[aria-invalid=true]')||[...$('native-content').querySelectorAll('.field-error')].find(e=>e.textContent);
  if(first){first.scrollIntoView({block:'center',behavior:'auto'});first.focus?.({preventScroll:true});}else if(banner&&notice){banner.scrollIntoView({block:'center',behavior:'auto'});}
}
function field(root,s,key,label=formLabels[key],type='text',optional=false){
  const group=node('div','form-field'),id=`native-${key}`,l=node('label','field-label',label);l.htmlFor=id;
  if(optional)l.append(node('span','field-optional','необязательно'));group.append(l);
  const input=node(type==='textarea'?'textarea':'input','field-input');input.id=id;input.name=key;if(type!=='textarea')input.type=type;else input.rows=3;
  input.value=s.values[key]??'';input.required=!optional;input.maxLength=({phone:25,name:100,title:100,location:200,price:100,first_name:60,last_name:60,username:33,telegram_username:33,note:1500})[key]||1200;
  input.autocomplete=({name:'name',first_name:'given-name',last_name:'family-name',phone:'tel'})[key]||'off';
  if(type==='tel'){input.placeholder='+7 900 123-45-67';input.inputMode='tel';}
  if(key==='username'||key==='telegram_username')input.placeholder='@username';
  input.addEventListener('input',()=>{s.values[key]=input.value;saveNativeDraft();input.removeAttribute('aria-invalid');group.querySelector('.field-error').textContent='';});
  group.append(input);errorSlot(group,key);input.setAttribute('aria-describedby','error-'+key);root.append(group);return input;
}
function counter(root,s,key,label,max=200){
  const group=node('div','form-field'),row=node('div','counter-row');row.append(node('label','field-label',label));
  const controls=node('div','number-stepper'),input=node('input','');input.type='number';input.name=key;input.min='1';input.max=String(max);input.step='1';input.inputMode='numeric';input.value=s.values[key]||'1';s.values[key]=input.value;input.setAttribute('aria-label',label);input.setAttribute('aria-describedby','error-'+key);
  const down=button('','icon-button',()=>adjust(-1)),up=button('','icon-button',()=>adjust(1));down.append(icon('minus'));up.append(icon('plus'));down.setAttribute('aria-label','Уменьшить количество гостей');up.setAttribute('aria-label','Увеличить количество гостей');
  function adjust(delta){input.value=Math.max(1,Math.min(max,(Number(input.value)||1)+delta));s.values[key]=input.value;saveNativeDraft();update();}
  function update(){down.disabled=Number(input.value)<=1;up.disabled=Number(input.value)>=max;}
  input.addEventListener('input',()=>{s.values[key]=input.value;saveNativeDraft();update();});controls.append(down,input,up);row.append(controls);group.append(row);errorSlot(group,key);root.append(group);update();
}
function requestStepErrors(s){const e={},v=s.values;if(s.step===0){if(!v.date||v.date<s.data.today)e.date='Выберите сегодняшнюю или будущую дату.';if(s.screen==='booking'&&!/^\d{2}:\d{2}$/.test(v.time||''))e.time='Выберите время.';if(s.screen==='booking'&&v.date===s.data.today&&v.time){const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(p=>[p.type,p.value]));if(v.time<=parts.hour+':'+parts.minute)e.time='Выберите время позднее текущего (МСК).';}}else{if(!/^\d+$/.test(String(v.guests))||Number(v.guests)<1||Number(v.guests)>200)e.guests='От 1 до 200 гостей.';if(!String(v.name||'').trim())e.name='Введите ваше имя.';const digits=String(v.phone||'').replace(/\D/g,'');if(!/^(?:[78][3489]\d{9}|[3489]\d{9})$/.test(digits))e.phone='Введите российский номер телефона.';if(s.screen==='banquet'&&!String(v.event||'').trim())e.event='Укажите повод или формат.';}return e;}
function renderRequest(root,s){
  const booking=s.screen==='booking';root.classList.add('request-screen');heading(root,booking?'Забронировать стол':'Провести банкет');
  const steps=booking?['Дата и время','Гости и контакты','Проверьте заявку']:['Дата банкета','Детали и контакты','Проверьте заявку'];
  const progress=node('div','request-progress');progress.append(node('p','step-label',`${steps[s.step]} · ${s.step+1} из 3`));
  if(s.values.date||s.values.phone||s.values.event||s.values.comment||s.values.wishes){
    const reset=button('Сбросить','draft-reset',()=>confirmAction('Очистить черновик?','Введённые данные этой заявки будут удалены.','Очистить черновик',()=>nativeCommand({command:'discard_draft'},()=>{try{localStorage.removeItem(draftKey(s.screen));}catch(_){}s.values={guests:'2',name:catalog.user?.first_name||''};s.step=0;renderNative();})));
    reset.setAttribute('aria-label','Очистить черновик');progress.append(reset);
  }
  root.append(progress);const body=node('div','request-body');root.append(body);
  if(s.step===0){
    const group=node('div','form-field');group.append(node('label','field-label','Дата'));
    const date=button(s.values.date?displayDate(s.values.date,{day:'numeric',month:'long',year:'numeric'}):'Выберите дату','date-control',()=>openPicker(booking?'Дата бронирования':'Дата банкета',content=>{
      let selected=s.values.date||'';calendar(content,selected,s.data.today,value=>selected=value);
      content.append(button('Выбрать дату','primary-button',()=>{if(!selected){toast('Выберите дату');return;}s.values.date=selected;saveNativeDraft();date.textContent=displayDate(selected,{day:'numeric',month:'long',year:'numeric'});date.removeAttribute('aria-invalid');group.querySelector('.field-error').textContent='';closePicker();date.focus({preventScroll:true});}));
    }));date.name='date';date.setAttribute('aria-label',booking?'Дата бронирования':'Дата банкета');date.setAttribute('aria-describedby','error-date');group.append(date);errorSlot(group,'date');body.append(group);
    if(booking){body.append(node('h2','field-label time-label','Время по Москве'));timeWheel(body,s.values.time,time=>{s.values.time=time;saveNativeDraft();});errorSlot(body,'time');}
  }else if(s.step===1){
    counter(body,s,'guests','Сколько будет гостей?');if(!booking)field(body,s,'event');field(body,s,'name');field(body,s,'phone',formLabels.phone,'tel');
    const optional=node('details','request-optional');optional.open=!!s.values[booking?'comment':'wishes'];optional.append(node('summary','','Добавить пожелания'));field(optional,s,booking?'comment':'wishes','Пожелания','textarea',true);body.append(optional);
  }else{
    const groups=[['Дата и время',0,{date:'Дата',...(booking?{time:'Время'}:{})}],['Гости и контакты',1,{guests:'Гостей',...(!booking?{event:'Формат'}:{}),name:'Имя',phone:'Телефон',...(booking?{comment:'Пожелания'}:{wishes:'Пожелания'})}]];
    for(const [title,step,fields] of groups){
      const block=node('section','review-block'),head=node('div','review-heading');head.append(node('h2','',title));head.append(button('Изменить','review-edit',()=>{s.step=step;renderNative();}));head.lastChild.setAttribute('aria-label','Изменить: '+title);block.append(head);
      const list=node('dl','review-list');for(const [key,label] of Object.entries(fields)){if(!s.values[key]&&['comment','wishes'].includes(key))continue;const row=node('div','review-row');row.append(node('dt','',label),node('dd','',key==='date'?displayDate(s.values[key],{day:'numeric',month:'long',year:'numeric'}):String(s.values[key]||'Не указаны')));list.append(row);}block.append(list);body.append(block);
    }
  }
  const footer=node('div','native-footer');message(footer,s.step===2?'Заявку получит менеджер. Дождитесь подтверждения.':booking?'Наличие стола подтвердит менеджер':'Дату и формат банкета подтвердит менеджер');
  const next=button(s.step===2?'Отправить заявку':'Продолжить','primary-button',async()=>{
    if(s.step===0&&booking){const columns=body.querySelectorAll('.wheel-column');if(columns.length===2)s.values.time=[...columns].map(e=>String(Math.round(e.scrollTop/44)).padStart(2,'0')).join(':');}
    if(s.step<2){const errors=requestStepErrors(s);if(Object.keys(errors).length){showFields(errors);return;}s.step++;saveNativeDraft();renderNative();}
    else await submitNative(s.screen,s.values,{},next,result=>{try{localStorage.removeItem(draftKey(s.screen));}catch(_){}nativeStack=[];nativeState={screen:'success',origin:nativeOrigin,title:'Заявка отправлена',notice:result.notice,ticket:result.ticket,request:{kind:s.screen,values:clone(s.values)}};renderNative();});
  });footer.append(next);root.append(footer);if(!booking&&s.step===0)root.append(button('Обсудить с менеджером','text-button',()=>openNative('inquiry',{})));
}
function closePicker(){const picker=$('picker-dialog');if(picker.open)picker.close();unlockMenuScroll();updateBackButton();}
function openPicker(title,render){
  const picker=$('picker-dialog');if(picker.open)closePicker();const root=$('picker-content');root.replaceChildren();const head=node('div','picker-heading');const titleNode=node('h2','',title);titleNode.id='picker-title';head.append(titleNode);const close=button('','icon-button',closePicker);close.append(icon('x'));close.setAttribute('aria-label','Закрыть окно');head.append(close);root.append(head);lockMenuScroll();picker.showModal();render(root);updateBackButton();
}
$('picker-dialog').addEventListener('cancel',event=>{event.preventDefault();closePicker();});
$('picker-dialog').addEventListener('click',event=>{if(event.target!==$('picker-dialog'))return;const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closePicker();});
function confirmAction(title,text,label,action){openPicker(title,root=>{message(root,text);root.append(button(label,'primary-button',async()=>{closePicker();await action();}),button('Отмена','text-button',closePicker));});}
function datetimeField(root,s){
  const group=node('div','form-field');group.append(node('div','field-label',formLabels.starts_at));const row=node('div','datetime-controls');
  let [date='',time='19:00']=String(s.values.starts_at||'').split('T');
  const dateButton=button(date?displayDate(date):'Выберите дату','date-control',()=>openPicker('Дата мероприятия',content=>{let next=date;calendar(content,date,s.data.today,value=>next=value);content.append(button('Выбрать дату','primary-button',()=>{if(!next){toast('Выберите дату');return;}date=next;set();dateButton.textContent=displayDate(date);closePicker();}));}));dateButton.setAttribute('aria-label','Дата мероприятия');
  const timeButton=button(time,'date-control',()=>openPicker('Время по Москве',content=>{let next=time;timeWheel(content,time,value=>next=value);content.append(button('Выбрать время','primary-button',()=>{time=next;set();timeButton.textContent=time;closePicker();}));}));timeButton.setAttribute('aria-label','Время мероприятия');
  const set=()=>{s.values.starts_at=date?date+'T'+time:'';};row.append(dateButton,timeButton);group.append(row);errorSlot(group,'starts_at');root.append(group);
}
function renderTypedForm(root,s){
  const kind=s.kind||s.screen,event=s.data.event;
  const titles={event_create:'Новое мероприятие',event_edit:'Настройки мероприятия',manual:'Добавить гостей',register:'Запись на мероприятие',manager_add:'Новый менеджер',manager_edit:'Имя менеджера',note:'Заметка по заявке',inquiry:'Написать менеджеру'};
  heading(root,titles[kind]||'Данные',event?.title||'');const form=node('form','typed-form');form.noValidate=true;
  if(kind.startsWith('event_')){field(form,s,'title');field(form,s,'description',formLabels.description,'textarea',true);datetimeField(form,s);field(form,s,'location');field(form,s,'price');counter(form,s,'capacity','Лимит самостоятельной записи',100000);message(form,'Гости, добавленные вручную, в этот лимит не входят.');}
  if(['manual','register'].includes(kind)){
    if(kind==='manual'&&event.available===0)message(form,'Лимит самостоятельных регистраций достигнут, но вы добавляете вручную.','warning');
    if(kind==='register')message(form,`Сохраним данные контактного лица. Свободно мест: ${event.available}.`);
    field(form,s,'first_name');field(form,s,'last_name');field(form,s,'phone',formLabels.phone,'tel');counter(form,s,'party_size',formLabels.party_size,100000);if(kind==='manual')field(form,s,'telegram_username',formLabels.telegram_username,'text',true);
  }
  if(kind==='manager_add'){field(form,s,'username');field(form,s,'name','Имя для гостей');message(form,'Новый менеджер должен сначала открыть бота и нажать /start.');}
  if(kind==='manager_edit')field(form,s,'name','Имя для гостей');
  if(kind==='inquiry'){const input=field(form,s,'message','Ваш вопрос','textarea');input.maxLength=3500;input.rows=5;message(form,'Ответ менеджера появится в этой переписке.');}
  if(kind==='note'){field(form,s,'note','Заметка','textarea',true);message(form,'Заметку видят только менеджеры.');}
  const submit=button(kind==='register'?'Зарегистрироваться':kind==='manual'?'Добавить в список':kind==='inquiry'?'Отправить сообщение':'Сохранить','primary-button');submit.type='submit';form.append(submit);root.append(form);
  form.addEventListener('submit',async event=>{event.preventDefault();await submitNative(kind,s.values,{...s.args,...(s.data.event?{event:s.data.event.id,version:s.data.event.version}:{})},submit,result=>{if(result.ticket){openChat(result.ticket,kind==='inquiry'?'guest':'staff');return;}if(result.event){openNative(kind==='register'?'event':'event',{event:result.event,scope:kind==='register'?'guest':'staff'},true);return;}openNative('managers',{scope:'staff'},true);});});
}
async function submitNative(kind,values,args,submit,onSuccess){
  if(busy)return;busy=true;submit.disabled=true;const label=submit.textContent;submit.textContent='Сохраняем…';
  try{const result=await api('submit_form',{kind,values,...args});if(result.notice&&!['booking','banquet'].includes(kind))toast(result.notice);onSuccess(result);}
  catch(error){if(['booking','banquet'].includes(nativeState?.screen)&&error.fields&&Object.keys(error.fields).length){nativeState.step=Object.keys(error.fields).some(k=>['date','time'].includes(k))?0:1;renderNative();}showFields(error.fields,error.message);}
  finally{busy=false;submit.disabled=false;submit.textContent=label;}
}
function renderDashboard(root,s){
  heading(root,'Рабочий стол','Заявки, мероприятия и команда');const stats=node('div','dashboard-stats');
  for(const [key,label,filter] of [['waiting','Новые','waiting'],['mine','Мои в работе','mine'],['active','Всего в работе','others'],['closed','Завершённые','closed']]){
    const b=button('','stat-tile',()=>openNative('tickets',{scope:'staff',filter}));b.append(node('strong','',String(s.data.stats[key])),node('span','',label));stats.append(b);
  }root.append(stats);
  for(const [label,name,screen,args] of [['Все заявки','chat-circle','tickets',{scope:'staff',filter:'all'}],['Найти заявку','magnifying-glass','tickets',{scope:'staff',filter:'search'}],['Мероприятия','ticket','events',{scope:'staff'}],['Менеджеры · '+s.data.managers,'users-three','managers',{scope:'staff'}]])root.append(actionRow(label,name,()=>openNative(screen,args)));
}
function pagers(root,page,more,action){if(page===0&&!more)return;const row=node('div','pagination');const back=button('Назад','secondary-button',()=>action(page-1));back.disabled=page===0;const next=button('Далее','secondary-button',()=>action(page+1));next.disabled=!more;row.append(back,node('span','',String(page+1)),next);root.append(row);}
function renderTicketList(root,s){
  const staff=s.args.scope==='staff';heading(root,staff?'Заявки гостей':'Сообщения',staff?'История и переписка с гостями':'');
  if(staff){const tabs=node('div','list-tabs');for(const [label,filter] of [['Новые','waiting'],['Мои','mine'],['Коллеги','others'],['Архив','closed']]){const b=button(label,'',()=>openNative('tickets',{...s.args,filter,page:0,query:''},'replace'));b.setAttribute('aria-pressed',String(s.args.filter===filter));tabs.append(b);}root.append(tabs);
    const form=node('form','native-search'),input=node('input');input.type='search';input.placeholder='Имя, телефон или номер заявки';input.value=s.args.query||'';input.setAttribute('aria-label','Поиск заявок');const find=button('','icon-button');find.append(icon('magnifying-glass'));find.type='submit';find.setAttribute('aria-label','Найти');form.append(input,find);form.addEventListener('submit',event=>{event.preventDefault();openNative('tickets',{scope:'staff',filter:'search',query:input.value,page:0},'replace');});root.append(form);
  }
  if(!s.data.tickets.length){
    if(staff)message(root,s.args.query?'Ничего не найдено. Попробуйте другой запрос.':'В этом разделе пока нет заявок.');
    else{
      const empty=node('section','inbox-empty');empty.append(node('h2','','Пока нет обращений'),node('p','','Начните с бронирования или вопроса менеджеру.'));root.append(empty);
      for(const [label,name,screen] of [['Забронировать стол','calendar-blank','booking'],['Провести банкет','users-three','banquet'],['Написать менеджеру','chat-circle','inquiry']])root.append(actionRow(label,name,()=>openNative(screen,{},true)));
    }
  }
  for(const t of s.data.tickets){
    const b=button('','request-row',()=>openChat(t.number,staff?'staff':'guest'));const label=t.request_type==='booking'?'Бронирование':t.request_type==='banquet'?'Банкет':'Обращение';
    const top=node('span','request-row-top');top.append(node('strong','',staff?(t.details.name||[t.first_name,t.last_name].filter(Boolean).join(' ')||t.username||'Гость'):`${label} №${t.number}`),node('span','status-chip',staff?statusLabel(t.status):guestTicketStatus(t)));b.append(top);
    const details=[staff?`${label} №${t.number}`:'',t.details.date,t.details.time,t.details.guests?`${t.details.guests} гост.`:''].filter(Boolean).join(' · ');if(details)b.append(node('span','request-meta',details));
    const last=node('span','request-last',t.preview);if(t.unread){last.append(node('strong','unread-count',String(t.unread)));}b.append(last);root.append(b);
  }
  pagers(root,s.data.page,s.data.more,page=>openNative('tickets',{...s.args,page},'replace'));
  if(!staff&&catalog.admin){const links=node('div','message-tools');links.append(button('Управление','text-button',()=>{setView('more');scrollPage();}));root.append(links);}
}
function renderEventList(root,s){
  const staff=s.args.scope==='staff';heading(root,staff?'Мероприятия':'Встречи в SUNPARK');if(staff)root.append(button('Создать мероприятие','primary-button',()=>openNative('event_create',{scope:'staff'})));
  if(!s.data.events.length)message(root,'Мероприятий пока нет.');
  for(const event of s.data.events){const row=button('','event-row',()=>openNative('event',{event:event.id,scope:staff?'staff':'guest'}));row.append(node('span','event-row-date',displayDate(event.starts_at,{day:'numeric',month:'long'})+' · '+event.starts_at.slice(11,16)),node('strong','event-row-title',event.title),node('span','request-meta',event.location),node('span','status-chip',event.is_open?'Регистрация открыта':'Регистрация закрыта'));root.append(row);}
  pagers(root,s.data.page,s.data.more,page=>openNative('events',{...s.args,page},'replace'));
}
function renderEventDetail(root,s){
  const e=s.data.event,staff=s.args.scope==='staff';heading(root,e.title);message(root,displayDate(e.starts_at,{day:'numeric',month:'long',year:'numeric'})+' · '+e.starts_at.slice(11,16)+' МСК');
  const details=node('dl','detail-list');for(const [name,value] of [['Место',e.location],['Стоимость',e.price],['Свободно для записи',String(e.available)+' мест']]){const row=node('div');row.append(node('dt','',name),node('dd','',value));details.append(row);}root.append(details);if(e.description)message(root,e.description);root.append(node('p','event-state',e.is_open?'Регистрация открыта':'Регистрация закрыта'));
  if(staff){
    const stats=node('div','event-counts');for(const [number,label] of [[e.total_guests,'Гостей всего'],[e.self_guests+' / '+e.capacity,'Самостоятельно'],[e.total_guests-e.self_guests,'Вручную']]){const box=node('div');box.append(node('strong','',String(number)),node('span','',label));stats.append(box);}root.append(stats);
    root.append(button(e.is_open?'Закрыть регистрацию':'Открыть регистрацию','primary-button',()=>nativeCommand({command:'toggle_event',event:e.id,version:e.version,scope:'staff'},()=>openNative('event',{event:e.id,scope:'staff'},true))));
    root.append(actionRow('Настройки','gear-six',()=>openNative('event_edit',{event:e.id,scope:'staff'})),actionRow('Добавить гостей вручную','users-three',()=>openNative('manual',{event:e.id,scope:'staff'})),actionRow('Список гостей','ticket',()=>openNative('event_guests',{event:e.id,scope:'staff'})));
  }else if(e.mine){message(root,`Вы записаны: ${e.mine.party_size} чел.`);root.append(button('Отменить запись','secondary-button',()=>confirmAction('Отменить запись?',`Мероприятие «${e.title}», ${e.mine.party_size} чел.`, 'Отменить запись',()=>nativeCommand({command:'cancel_registration',event:e.id,registration:e.mine.id,scope:'guest'},()=>openNative('event',{event:e.id,scope:'guest'},true)))));
  }else if(e.is_open&&e.available>0)root.append(button('Записаться','primary-button',()=>openNative('register',{event:e.id,scope:'guest'})));
}
function renderRegistrations(root,s){
  const e=s.data.event;heading(root,'Список гостей',e.title+' · '+e.total_guests+' чел.');if(!s.data.registrations.length)message(root,'В списке пока нет гостей.');
  for(const r of s.data.registrations){const row=node('article','registration-row'),body=node('div');body.append(node('strong','',r.first_name+' '+r.last_name),node('p','',r.phone+' · '+r.party_size+' чел.'),node('p','request-meta',[(r.telegram_username?'@'+r.telegram_username:''),r.added_by_admin?'Добавил администратор':'Самостоятельная запись'].filter(Boolean).join(' · ')));const remove=button('','icon-button',()=>confirmAction('Удалить запись?',`${r.first_name} ${r.last_name} · ${r.phone} · ${r.party_size} чел.`, 'Удалить запись',()=>nativeCommand({command:'delete_registration',event:e.id,registration:r.id,scope:'staff'},()=>openNative('event_guests',{...s.args},true))));remove.append(icon('trash'));remove.setAttribute('aria-label','Удалить запись: '+r.first_name+' '+r.last_name);row.append(body,remove);root.append(row);}
  root.append(button('Добавить вручную','primary-button',()=>openNative('manual',{event:e.id,scope:'staff'})));pagers(root,s.data.page,s.data.more,page=>openNative('event_guests',{...s.args,page},'replace'));
}
function renderManagers(root,s){
  heading(root,'Команда SUNPARK','Менеджеры получают заявки и отвечают гостям');
  for(const manager of s.data.managers){const row=node('div','manager-row'),copy=node('div');copy.append(node('strong','',manager.name+(manager.self?' · вы':'')),node('p','request-meta',manager.username?'@'+manager.username:'Telegram ID '+manager.id));const controls=node('div','row-controls');const edit=button('','icon-button',()=>openLocalForm('manager_edit',{name:manager.name},{manager:manager.id}));edit.append(icon('gear-six'));edit.setAttribute('aria-label','Изменить имя: '+manager.name);const remove=button('','icon-button',()=>confirmAction('Удалить менеджера?',manager.name+(manager.self?' потеряет доступ к администрированию.':' больше не будет получать новые заявки.'),'Удалить менеджера',()=>nativeCommand({command:'remove_manager',manager:manager.id,scope:'staff'},result=>{if(result.access_revoked){$('app-shell').hidden=true;$('app-nav').hidden=true;$('status').textContent='Доступ администратора удалён.';}else openNative('managers',{scope:'staff'},true);})));remove.append(icon('trash'));remove.setAttribute('aria-label','Удалить менеджера: '+manager.name);if(manager.fixed){remove.disabled=true;remove.title='Права закреплены в настройках бота';}controls.append(edit,remove);row.append(copy,controls);root.append(row);}
  root.append(button('Добавить менеджера','primary-button',()=>openLocalForm('manager_add')));
}
function renderInfo(root,s){
  const d=s.data;heading(root,'Как добраться и контакты');root.append(node('p','info-copy',catalog.services?.address||d.address));
  const map=mapLink();map.classList.add('secondary-button');map.target='_blank';map.rel='noopener noreferrer';root.append(map);
  for(const service of catalog.services?.items||[]){const block=node('section','contact-block');block.append(node('h2','subsection',service.title),serviceLink(service.phone_label,'tel:'+service.phone,'contact-phone'),node('p','catalog-hint',service.hours));if(service.additional_phone)block.append(serviceLink('Городской · '+service.additional_phone_label,'tel:'+service.additional_phone,'service-phone'));root.append(block);}
  const rules=node('details','rules-details'),summary=node('summary','field-label','Правила ресторана'),copy=node('div','system-copy');copy.append(safeMarkup(d.rules));rules.append(summary,copy);root.append(rules);
  if(catalog.events_visible)root.append(button('Мероприятия','text-button',()=>openNative('events',{})));
  root.append(button('Написать менеджеру ресторана','primary-button',()=>openNative('inquiry',{})),button('Закрыть приложение','text-button',closeApp));
}
function guestTicketStatus(t){return ({waiting:t.request_type==='inquiry'?'Ожидаем ответа':'Ждём подтверждения',active:'Менеджер на связи',waiting_guest:'Менеджер ответил',closed:'Завершено'})[t.status]||statusLabel(t.status);}
async function nativeCommand(args,onSuccess){if(busy)return;busy=true;try{const result=await api('command',args);toast(result.notice||'Готово');onSuccess(result);}catch(error){toast(error.message);}finally{busy=false;}}
async function nativeAction(callback,scope,keepChat){
  const roots={'manager:start':['inquiry',{}],'manager:write':['inquiry',{}],'booking:start':['booking',{}],'banquet:contact':['banquet',{}],'banquet:request':['banquet',{}],faq:['info',{}],info:['info',{}],'admin:panel':['dashboard',{scope:'staff'}],'admin:stats':['dashboard',{scope:'staff'}],'admin:waiting':['tickets',{scope:'staff',filter:'waiting'}],'admin:active':['tickets',{scope:'staff',filter:'mine'}],'admin:other_active':['tickets',{scope:'staff',filter:'others'}],'admin:closed':['tickets',{scope:'staff',filter:'closed'}],'admin:search':['tickets',{scope:'staff',filter:'search'}],'admin:managers':['managers',{scope:'staff'}]};
  if(roots[callback]){await openNative(...roots[callback],true);return true;}
  let m;if((m=/^ev:(list|manage):(\d+)$/.exec(callback))){await openNative('events',{scope:m[1]==='manage'?'staff':'guest',page:Number(m[2])},true);return true;}
  if(callback==='ev:create'){await openNative('event_create',{scope:'staff'});return true;}
  if((m=/^ev:(admin|view|settings|manual|join|guests):(\d+)/.exec(callback))){const screens={admin:'event',view:'event',settings:'event_edit',manual:'manual',join:'register',guests:'event_guests'};await openNative(screens[m[1]],{event:Number(m[2]),scope:['view','join'].includes(m[1])?'guest':'staff'});return true;}
  if((m=/^admin:note:(\d+)$/.exec(callback))){await openNative('note',{ticket:Number(m[1]),scope:'staff'});return true;}
  if((m=/^admin:(open|archive|other):(\d+)$/.exec(callback))){await openChat(Number(m[2]),'staff');return true;}
  if((m=/^admin:templates:(\d+)$/.exec(callback))){const data=await api('screen',{screen:'templates',ticket:Number(m[1]),scope:'staff'});openPicker('Быстрый ответ',root=>{message(root,'Нажатие сразу отправит ответ гостю.');for(const item of data.choices)root.append(button(item.text,'template-choice',async()=>{closePicker();await runAction(item.callback,'staff',true);}));});return true;}
  if(callback.startsWith('close:')){confirmAction('Завершить заявку?','Переписка сохранится в архиве. Отправлять новые сообщения в эту заявку будет нельзя.','Завершить заявку',async()=>{if(busy)return;busy=true;try{await api('action',{callback,scope:'staff'});await refreshChat();toast('Заявка завершена');}catch(error){toast(error.message);}finally{busy=false;}});return true;}
  return false;
}
function resetNativeChat(number,scope){const key=number+':'+scope;if(nativeChatKey!==key){if(nativeChatKey)chatDrafts.set(nativeChatKey,$('chat-input').value);$('chat-input').value=chatDrafts.get(key)||'';$('chat-input').readOnly=false;nativeChatKey=key;chatMessages=new Map();chatRenderKey='';chatTicketKey='';chatOlder=false;chatData=null;$('chat-log').replaceChildren(node('p','empty-state','Загружаем переписку…'));$('chat-title').textContent='Загружаем…';$('chat-subtitle').textContent='';$('chat-summary').replaceChildren();$('chat-actions').replaceChildren();$('chat-form').hidden=true;if(pendingUpload?.preview)URL.revokeObjectURL(pendingUpload.preview);pendingUpload=null;}}
async function refreshNativeChat(before=null){
  if(!chatNumber)return;const number=chatNumber,scope=chatScope,key=number+':'+scope;if(chatRequest?.key===key)return;const request={key};chatRequest=request;try{
    const data=await api('chat',{ticket:number,scope,...(before?{before}:{})});if(appView!=='chat'||nativeChatKey!==key)return;chatData=data;
    const ticket=data.ticket;const ticketKey=JSON.stringify(ticket);if(ticketKey!==chatTicketKey){chatTicketKey=ticketKey;$('chat-title').textContent=scope==='staff'?ticket.guest_name:(ticket.manager_name||'Менеджер SUNPARK');$('chat-subtitle').textContent=(ticket.request_type==='booking'?'Бронирование':ticket.request_type==='banquet'?'Банкет':'Обращение')+' №'+ticket.number;
    const summary=$('chat-summary');summary.replaceChildren();const date=node('span','summary-date');date.append(icon('calendar-blank'),node('span','',[ticket.details.date?requestDate(ticket.details.date):'',ticket.details.time].filter(Boolean).join(' · ')||'Данные заявки'));
    const people=node('span','summary-guests');people.append(icon('users-three'),node('span','',ticket.details.guests?guestCount(ticket.details.guests):''));const status=node('span','status-chip',scope==='guest'?guestTicketStatus(ticket):statusLabel(ticket.status));summary.append(date);if(ticket.details.guests)summary.append(people);summary.append(status,icon('caret-right'));
    $('chat-details-body').replaceChildren();for(const [field,value] of Object.entries(ticket.details||{}))$('chat-details-body').append(node('p','',`${formLabels[field]||field}: ${value||'—'}`));if(ticket.note)$('chat-details-body').append(node('p','manager-note','Заметка: '+ticket.note));
    const actions=$('chat-actions');actions.replaceChildren();if(scope==='staff'){
      let options=[];if(ticket.status==='waiting')options=[['Взять в работу','claim:'+ticket.guest_id]];else if(['active','waiting_guest'].includes(ticket.status)&&ticket.manager_id!==catalog.user.id)options=[['Забрать себе','take:'+ticket.number]];else if(ticket.can_reply)options=[['Быстрый ответ','admin:templates:'+ticket.number],['Заметка','admin:note:'+ticket.number],['Завершить','close:'+ticket.guest_id]];
      for(const [label,callback] of options)actions.append(button(label,'secondary-button',()=>runAction(callback,'staff',/^(claim|take|close):/.test(callback))));
    }
    if(scope==='guest'&&ticket.status==='waiting'&&!ticket.manager_id)actions.append(button('Отменить заявку','text-button',()=>confirmAction('Отменить заявку?','Заявка будет снята с очереди. Переписка сохранится.','Отменить заявку',()=>nativeCommand({command:'cancel_ticket',ticket:ticket.number},()=>refreshChat()))));
    $('chat-form').hidden=!ticket.can_reply;$('chat-readonly').hidden=ticket.can_reply;$('chat-readonly').textContent=ticket.status==='closed'?'Заявка завершена. Переписка сохранена.':'Чтобы ответить, возьмите заявку в работу.';}
    const previousFirst=chatMessages.size?Math.min(...chatMessages.keys()):null;for(const item of data.messages)chatMessages.set(item.id,item);if(before||previousFirst===null)chatOlder=!!data.has_more;
    const ordered=[...chatMessages.values()].sort((a,b)=>a.id-b.id),renderKey=key+JSON.stringify(ordered);if(renderKey!==chatRenderKey){
      const log=$('chat-log'),atBottom=log.scrollHeight-log.scrollTop-log.clientHeight<60,oldTop=log.scrollTop,oldHeight=log.scrollHeight,initial=!chatRenderKey;chatRenderKey=renderKey;log.replaceChildren();
      if(chatOlder){const earlier=button('Ранние сообщения','older-messages',async()=>{earlier.disabled=true;await refreshNativeChat(Math.min(...chatMessages.keys()));});log.append(earlier);}
      if(!ordered.length)log.append(node('p','empty-state','Здесь начнётся переписка с менеджером.'));
      let day='';for(const item of ordered){const stamp=parseStamp(item.created_at),next=Number.isNaN(stamp.getTime())?'':stamp.toLocaleDateString('ru-RU',{day:'numeric',month:'long',...(stamp.getFullYear()!==new Date().getFullYear()?{year:'numeric'}:{})});if(next&&next!==day){log.append(node('p','chat-date',next));day=next;}
        const mine=scope==='staff'?item.sender_role==='manager':item.sender_role==='guest';const bubble=node('article','chat-bubble'+(mine?' mine':''));bubble.dataset.messageId=item.id;
        if(item.text)bubble.append(node('span','message-text',item.text));
        if(item.attachment){const photo=item.attachment.kind==='photo';if(photo&&mediaCache.has(item.id)){const img=node('img','chat-photo');img.alt='Фото в переписке';img.src=mediaCache.get(item.id);bubble.append(img);}else{const file=button('','attachment-button',async()=>{file.disabled=true;try{const url=await loadMedia(item);if(photo){const img=node('img','chat-photo');img.alt='Фото в переписке';img.src=url;bubble.append(img);file.hidden=true;}else{const link=node('a');link.href=url;link.download=item.attachment.name||'document.pdf';link.click();}}catch(error){toast(error.message);}finally{file.disabled=false;}});file.append(icon(photo?'image':'file-pdf'),node('span','',photo?'Открыть фото':item.attachment.name||'Документ PDF'));bubble.append(file);}}
        if(!Number.isNaN(stamp.getTime())){const time=node('time','message-time',stamp.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}));time.dateTime=stamp.toISOString();bubble.append(time);}log.append(bubble);
      }
      if(before)log.scrollTop=oldTop+(log.scrollHeight-oldHeight);else if(atBottom||initial){log.scrollTop=log.scrollHeight;$('chat-new').hidden=true;}else{log.scrollTop=oldTop;$('chat-new').hidden=false;}
    }
    renderAttachment();
  }catch(error){if(appView==='chat'&&nativeChatKey===key)toast(error.message);}finally{if(chatRequest===request)chatRequest=null;}
}
$('chat-new').addEventListener('click',()=>{$('chat-log').scrollTop=$('chat-log').scrollHeight;$('chat-new').hidden=true;});
$('chat-log').addEventListener('scroll',()=>{const log=$('chat-log');if(log.scrollHeight-log.scrollTop-log.clientHeight<60)$('chat-new').hidden=true;},{passive:true});
$('chat-input').addEventListener('input',event=>{event.target.style.height='auto';event.target.style.height=Math.min(event.target.scrollHeight,132)+'px';});
