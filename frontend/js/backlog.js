/* =====================================================================
   ВКЛАДКА «Бэклог команд» (7.0 / 7.1)
   Инициативы могут быть кросс-квартальными, но справочник трайбов, команд и
   компетенций всегда берётся из «Данных PI-цикла» активного цикла.
===================================================================== */
function backlogRows(){ return backlogBoard&&Array.isArray(backlogBoard.items)?backlogBoard.items:[]; }
function backlogRefs(){ return backlogBoard&&backlogBoard.reference_data||{tribes:[],teams:[],statuses:[],competencies:[]}; }
function findBacklogRow(id){ return backlogRows().find(row=>row.id===id)||null; }
function backlogTeamRefs(tribe=null){
  return backlogRefs().teams.filter(team=>!tribe||team.tribe===tribe);
}
function backlogTeamCompetencies(name){
  const team=backlogRefs().teams.find(row=>row.name===name);
  return team&&Array.isArray(team.competencies)?team.competencies:[];
}
// Адаптер только для отображения в точной разметке прототипа. Канонические
// бизнес-данные остаются неизменённым read model backend в backlogBoard.
function backlogViewItem(row){
  const owner=row.owner_team||'';
  const ownerExecutor=(row.executors||[]).find(ex=>ex.team===owner);
  const executors=(ownerExecutor?[ownerExecutor]:[]).map(ex=>({
    id:ex.id,team:ex.team,comps:{...(ex.effort_by_competency||{})},attractions:[],
  }));
  if(!executors.length) executors.push({id:null,team:owner,comps:{},attractions:[]});
  return {
    _uid:row.id,_backendId:row.id,id:row.issue_key,name:row.title||'',
    description:row.description||'',product:row.product||'',owner:row.owner_team||'',
    type:row.initiative_type||'',quarter:row.target_quarter||'',
    year:row.target_year?String(row.target_year):'',custPrio:row.customer_priority||'',
    teamPrio:row.team_priority||'',status:row.status||'Нет оценки',tshirt:row.tshirt_size||'',
    ac:Array.isArray(row.systems)?row.systems:[],tags:Array.isArray(row.tags)?row.tags:[],
    sentTo:Array.isArray(row.sent_to)?row.sent_to:[],totalEffort:+row.total_effort||0,
    executors,
  };
}
// Используется только старым, не развиваемым бюджетным экраном над transient-адаптером.
function ensureBacklogShape(it){ return it; }
function backlogCommandPayload(row){
  const owner=row.owner_team||'';
  const current=(row.executors||[]).find(ex=>ex.team===owner);
  return {
    tribe:row.tribe,issue_key:row.issue_key,title:row.title||'',
    description:row.description||'',product:row.product||'',owner_team:row.owner_team||'',
    initiative_type:row.initiative_type||'',target_year:row.target_year,
    target_quarter:row.target_quarter,customer_priority:row.customer_priority||'',
    team_priority:row.team_priority||'',status:row.status||'Нет оценки',tshirt_size:row.tshirt_size||'',
    tags:Array.isArray(row.tags)?row.tags:[],systems:Array.isArray(row.systems)?row.systems:[],
    executors:owner?[{
      id:current&&current.id||null,
      team:owner,
      effort_by_competency:{...((current&&current.effort_by_competency)||{})},
    }]:[],
  };
}
function backlogCascadeMessage(detail){
  const summary=Object.entries(detail&&detail.affected||{}).filter(([,count])=>count)
    .map(([name,count])=>`${name}: ${count}`).join(', ');
  return `Удаление разорвёт связи с уже отправленными инициативами${summary?` (${summary})`:''}. Продолжить?`;
}
async function executeBacklogCommand(path,method,body={},allowCascade=false){
  try{
    applyBacklogBoard(await backlogMutation(path,method,body));
  }catch(error){
    const cascade=allowCascade&&error&&error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required';
    if(cascade&&window.confirm(backlogCascadeMessage(error.detail))){
      applyBacklogBoard(await backlogMutation(path,method,{...body,confirm_cascade:true}));
    }else{
      reportBacklogSyncError(error);
      throw error;
    }
  }
  render();
  return backlogBoard;
}

function viewBacklog(){
  if(!backlogBoard) return `<div class="card"><h2>Бэклог команд ${activeBadge()}</h2><div class="note">Сервер бэклога недоступен. Локальные или демонстрационные данные не используются.</div></div>`;
  if(!state.ui.backlogTribe) return viewBacklogSelect();
  const tribes=backlogRefs().tribes.map(row=>row.name);
  if(!tribes.includes(state.ui.backlogTribe)){ state.ui.backlogTribe=null; return viewBacklogSelect(); }
  return viewBacklogBoard(state.ui.backlogTribe);
}
// 7.0 — выбор трайба из состава активного PI-цикла.
function viewBacklogSelect(){
  const isBudget=state.ui.mode==='budget';
  const tribes=backlogRefs().tribes.map(row=>row.name);
  let html=`<div class="card${isBudget?' budget-shell':''}"><div class="flex-between"><h2>Бэклог команд ${activeBadge()}</h2>
    <div class="hint">Выберите трайб. Общий бэклог хранится в PostgreSQL и одинаково отображается после перезагрузки и в другом браузере. ${isBudget?'Бюджетные команды в эту доработку не входят.':'Инициативы отправляются на Pre PI по столбцу «Квартал реализации».'}</div></div>`;
  html+=`<div class="tribe-list">`;
  if(!tribes.length) html+=`<div class="muted">Нет трайбов — добавьте команды на «${isBudget?'Данные для бюджетирования':'Данные PI-цикла'}».</div>`;
  tribes.forEach(tribe=>{
    html+=`<div class="tribe-acc"><div class="tribe-acc-head" data-bk-tribe="${esc(tribe)}"><span class="caret">▶</span>${esc(tribe)}</div></div>`;
  });
  html+=`</div></div>`;
  return html;
}
// Столбцы «Бэклога команд», по которым доступен фильтр.
// Порядок совпадает с порядком ячеек в backlogRowHTML(); без №/названия инициативы
// и без «Компетенций команды владельца».
const BK_FILTER_COLS=[
  {k:'custPrio',label:'Приоритет заказчика'},
  {k:'teamPrio',label:'Приоритет трайба/команды'},
  {k:'quarter', label:'Квартал реализации'},
  {k:'product', label:'Продукт'},
  {k:'owner',   label:'Команда-владелец'},
  {k:'type',    label:'Тип инициативы'},
  {k:'ac',      label:'АС', val:it=>(Array.isArray(it.ac)?it.ac:[])},
  {k:'status',  label:'Статус'},
  {k:'tshirt',  label:'Размер майки'},
  {k:'effort',  label:'Общая оценка (чел/дн)', val:it=>it.totalEffort},
];
// «Квартал реализации» — составной столбец из двух измерений, год и квартал.
// Год участвует в фильтрах как виртуальная колонка, но не рисуется
// отдельной ячейкой в шапке/теле: попап у единственной воронки один на оба
// измерения, значение строки подходит, если её год И квартал входят в выбор.
const BK_YEAR_COL={k:'year',label:'Год', val:it=>(it.year?String(it.year):'')};
const BK_FILTER_AND_SORT_COLS=[...BK_FILTER_COLS,BK_YEAR_COL];

// Шапка составного столбца «Квартал реализации»: одна воронка, подсвечивается,
// когда выбран хотя бы один год или квартал.
function bkQuarterThHTML(){
  const scope='bk', cf=colFilters(scope);
  const on = (Array.isArray(cf.quarter)&&cf.quarter.length) || (Array.isArray(cf.year)&&cf.year.length);
  return `<th><div class="th-f"><span>Квартал реализации</span>`+
    `<button class="col-f${on?' on':''}" data-fcol="quarter" data-fscope="bk" data-bk-yq="1" title="Фильтр по столбцу «Квартал реализации»">▼</button></div></th>`;
}
// Попап составного столбца «Квартал реализации»: две независимые группы чекбоксов
// (Год и Квартал) с логикой И. Без сортировки и поиска: только выбор года и квартала.
function openBkYqFilterPop(btn,scope='bk'){
  closeColFilterPop();
  const ctx=colFilterCtx[scope];
  if(!ctx) return;
  const filters=colFilters(scope);
  const selQ=Array.isArray(filters.quarter)?filters.quarter.slice():[];
  const selY=Array.isArray(filters.year)?filters.year.slice():[];
  // Значения, доступные с учётом фильтров по ДРУГИМ столбцам (год/квартал исключены).
  const fNoYq={...filters}; delete fNoYq.quarter; delete fNoYq.year;
  const base=ctx.rows.filter(r=>rowMatchesColFilters(r,ctx.cols,fNoYq));
  const qCol=ctx.cols.find(c=>c.k==='quarter');
  const yCol=ctx.cols.find(c=>c.k==='year');
  if(!qCol||!yCol) return;
  let qVals=colUniqueValues(base,qCol), yVals=colUniqueValues(base,yCol);
  selQ.forEach(v=>{ if(!qVals.includes(v)) qVals.push(v); });
  selY.forEach(v=>{ if(!yVals.includes(v)) yVals.push(v); });

  const itemHTML=(vals,sel)=>vals.map(v=>
    `<label class="colf-item" data-v="${esc(v)}"><input type="checkbox" class="colf-box" ${sel.includes(v)?'checked':''}>
      <span class="${v===''?'muted':''}">${v===''?FILTER_EMPTY_LABEL:esc(v)}</span></label>`
  ).join('')||`<div class="muted" style="padding:6px 4px">Нет значений</div>`;

  const pop=document.createElement('div');
  pop.className='colf-pop colf-pop-yq';
  pop.innerHTML=`<div class="colf-head">Квартал реализации</div>
    <div class="colf-yq-group">
      <div class="colf-yq-title">Год</div>
      <label class="colf-item colf-all"><input type="checkbox" class="colf-allbox" data-grp="year"><span>Выделить всё</span></label>
      <div class="colf-list" data-list="year">${itemHTML(yVals,selY)}</div>
    </div>
    <div class="colf-yq-group">
      <div class="colf-yq-title">Квартал</div>
      <label class="colf-item colf-all"><input type="checkbox" class="colf-allbox" data-grp="quarter"><span>Выделить всё</span></label>
      <div class="colf-list" data-list="quarter">${itemHTML(qVals,selQ)}</div>
    </div>
    <div class="colf-btns">
      <button class="ghost" data-colf-reset>Сбросить</button>
      <button class="primary" data-colf-apply>Применить</button>
    </div>`;
  document.body.appendChild(pop);
  colfPop=pop;

  // позиционирование: под кнопкой, с удержанием в пределах окна
  const r=btn.getBoundingClientRect();
  const w=pop.offsetWidth, h=pop.offsetHeight;
  let left=Math.min(r.left, window.innerWidth-w-8);
  let top=r.bottom+4;
  if(top+h>window.innerHeight-8) top=Math.max(8, r.top-h-4);
  pop.style.left=Math.max(8,left)+'px';
  pop.style.top=top+'px';

  const syncGroup=grp=>{
    const list=pop.querySelector(`[data-list="${grp}"]`);
    const allBox=pop.querySelector(`.colf-allbox[data-grp="${grp}"]`);
    const boxes=[...list.querySelectorAll('.colf-item:not([hidden]) .colf-box')];
    const onC=boxes.filter(x=>x.checked).length;
    allBox.checked=boxes.length>0&&onC===boxes.length;
    allBox.indeterminate=onC>0&&onC<boxes.length;
  };
  ['year','quarter'].forEach(grp=>{
    syncGroup(grp);
    const allBox=pop.querySelector(`.colf-allbox[data-grp="${grp}"]`);
    const list=pop.querySelector(`[data-list="${grp}"]`);
    allBox.onchange=()=>{ list.querySelectorAll('.colf-item:not([hidden]) .colf-box').forEach(x=>{x.checked=allBox.checked;}); syncGroup(grp); };
    list.querySelectorAll('.colf-box').forEach(x=>x.onchange=()=>syncGroup(grp));
  });
  pop.querySelector('[data-colf-reset]').onclick=()=>{
    delete colFilters(scope).quarter; delete colFilters(scope).year;
    closeColFilterPop(); save(); render();
  };
  pop.querySelector('[data-colf-apply]').onclick=()=>{
    const pick=grp=>{const out=[];pop.querySelector(`[data-list="${grp}"]`).querySelectorAll('.colf-item')
      .forEach(it=>{const b=it.querySelector('.colf-box');if(b&&b.checked)out.push(it.dataset.v||'');});return out;};
    const yP=pick('year'), qP=pick('quarter');
    // выбрано всё (или ничего) — измерение снимается
    if(!yP.length||yP.length===yVals.length) delete colFilters(scope).year; else colFilters(scope).year=yP;
    if(!qP.length||qP.length===qVals.length) delete colFilters(scope).quarter; else colFilters(scope).quarter=qP;
    closeColFilterPop(); save(); render();
  };
  setTimeout(()=>{ pop.querySelector('.colf-box')?.focus(); document.addEventListener('mousedown',colfOutside,true); },0);
}
// 7.1 — весь бэклог трайба
function viewBacklogBoard(tribe){
  const isBudget=state.ui.mode==='budget';
  const teams=backlogTeamRefs(tribe);
  const filter=state.ui.backlogTeamFilter;
  let list=backlogRows().filter(row=>row.tribe===tribe).map(backlogViewItem);
  if(filter) list=list.filter(it=> it.owner===filter || issueExecTeams(it).includes(filter));
  // фильтры по столбцам применяются поверх фильтра по команде
  colFilterCtx['bk']={rows:list, cols:BK_FILTER_AND_SORT_COLS};
  const listAll=list;
  list=applyColFilters(list,BK_FILTER_AND_SORT_COLS,'bk');
  list=applyColSort(list,BK_FILTER_AND_SORT_COLS,'bk');
  const q=state.ui.backlogQuarter, y=state.ui.backlogYear || (isBudget ? state.ui.budgetYear : null);
  const canSend=isBudget ? !!y : !!(q&&y);

  let html=`<div class="card${isBudget?' budget-shell':''}">
    <div class="prep-toolbar">
      <span class="team-title">${esc(tribe)}</span>
      <button class="ghost" id="bkBack">← Выбор трайба</button>
    </div>`;
  // фильтр по командам
  html+=`<div class="row" style="margin:8px 0;gap:6px;flex-wrap:wrap">
    <span class="muted">Команда:</span>
    <button class="bk-filter${!filter?' primary':''}" data-bk-filter="">Весь трайб</button>`+
    teams.map(t=>`<button class="bk-filter${filter===t.name?' primary':''}" data-bk-filter="${esc(t.name)}">${esc(t.name)}</button>`).join('')+
  `</div>`;
  // действия: добавить инициативу / по № Issue + отправка
  const qs=['Q1','Q2','Q3','Q4'];
  const years=[2025,2026,2027,2028];
  if(isBudget){
    html+=`<div class="note" style="margin:8px 0">Бюджетирование не входит в текущую доработку. Здесь показана read-only проекция общего бэклога.</div>`;
  }else{
    html+=`<div class="row" style="margin:8px 0;gap:8px;flex-wrap:wrap;align-items:center">
      <input id="bkIssueId" placeholder="Введите № Issue" style="width:200px" title="Например, SBOL-2010. Enter — добавить">
      <button class="primary" id="bkAddIssue" title="Создать инициативу по номеру Issue. Данные подтянутся из Jira после подключения интеграции">Добавить по № Issue</button>
      <span style="flex:1"></span>
      <span class="muted">Отправить на квартал:</span>
      <select id="bkSendQ" style="width:80px"><option value="">Квартал</option>${qs.map(x=>`<option value="${x}" ${q===x?'selected':''}>${x}</option>`).join('')}</select>
      <select id="bkSendY" style="width:90px"><option value="">Год</option>${years.map(x=>`<option value="${x}" ${String(y)===String(x)?'selected':''}>${x}</option>`).join('')}</select>
      <button id="bkSend" class="${canSend?'primary':''}" ${canSend?'':'disabled'} title="${canSend?'Отправить подходящие инициативы на Pre PI':'Сначала выберите квартал и год'}">Отправить на Pre PI Planning</button>
    </div>`;
  }
  // таблица
  const head=`<thead>
    <tr>
      <th class="stik1">№ Инициативы</th>
      <th>Название инициативы</th>`+
      BK_FILTER_COLS.map(c=>c.k==='quarter'?bkQuarterThHTML():filterThHTML(c,'bk')).join('')+
      `<th>Компетенции команды владельца</th>
      <th class="del-col"></th>
    </tr>
  </thead>`;
  html+=tableToolsBarHTML('bk');
  let body='';
  if(!list.length){
    const msg = listAll.length ? 'Ничего не найдено — измените фильтры по столбцам.' : 'Бэклог пуст — добавьте инициативу по № Issue.';
    body=`<tr><td class="stik1 muted">—</td><td class="muted" colspan="13">${msg}</td></tr>`;
  }else{
    list.forEach(it=>{ body+=backlogRowHTML(it,tribe,teams,isBudget); });
  }
  html+=`<div class="prep-wrap" data-scroll-key="bk"><table class="prep bk-table${isBudget?' backlog-readonly':''}"><colgroup></colgroup>${head}<tbody>${body}</tbody></table></div>`;
  html+=`<div class="note" style="margin-top:8px">Порядок инициатив можно менять: перетащите строку за ручку <b>⠿</b> в столбце «№ Инициативы». Кнопка <b>▼</b> в шапке столбца — фильтр и сортировка (по возрастанию / по убыванию, пустые значения всегда внизу). Пока сортировка активна, порядок задаёт она и ручка <b>⠿</b> неактивна — сбросьте сортировку в плашке над таблицей.</div>`;
  html+=isBudget
    ? `<div class="note" style="margin-top:8px">Для бюджета новые инициативы добавляются сразу на вкладке «Оценка инициатив». В карточке инициативы можно вручную указать ID Issue из бэклога.</div>`
    : `<div class="note" style="margin-top:8px">«Отправить на Pre PI Planning»: сначала выберите <b>Квартал</b> и <b>Год</b>. Отправятся только инициативы, у которых «Квартал реализации» точно совпадает с выбранными. Если указан <b>только год</b> — инициатива не отправляется. Отправленные попадают в «Бэклог инициатив — нижний блок» на Pre PI выбранного цикла и получают статус «Отправлена в Pre PI Planning».</div>`;
  html+=`</div>`;
  return html;
}
function backlogQuarterCell(it,readonly=false){
  const qs=['','Q1','Q2','Q3','Q4'];
  const years=['',2025,2026,2027,2028];
  return `<div style="display:flex;gap:3px">
    <select data-bk="${it._uid}" data-bp="quarter" class="q-mini" ${readonly?'disabled':''}>${qs.map(x=>`<option value="${x}" ${String(it.quarter)===String(x)?'selected':''}>${x||'—'}</option>`).join('')}</select>
    <select data-bk="${it._uid}" data-bp="year" class="q-mini" ${readonly?'disabled':''}>${years.map(x=>`<option value="${x}" ${String(it.year)===String(x)?'selected':''}>${x||'—'}</option>`).join('')}</select>
  </div>`;
}
function backlogAcCell(it,readonly=false){
  const val=Array.isArray(it.ac)?it.ac.join(', '):(it.ac||'');
  return `<input data-bk="${it._uid}" data-bp="ac" value="${esc(val)}" placeholder="СБОЛ, CRM…" class="ac-input" ${readonly?'readonly':''}>`;
}
function backlogStatusCell(it,readonly=false){
  const statuses=backlogRefs().statuses.length?backlogRefs().statuses:BACKLOG_STATUSES;
  const disabled=readonly||it.status==='Отправлена в Pre PI Planning';
  return `<select data-bk="${it._uid}" data-bp="status" ${disabled?'disabled':''}>${statuses.map(s=>`<option ${it.status===s?'selected':''}>${esc(s)}</option>`).join('')}</select>`;
}
function backlogTshirtCell(it,readonly=false){
  const disabled=readonly||it.status==='Отправлена в Pre PI Planning';
  return `<select data-bk="${it._uid}" data-bp="tshirt" ${disabled?'disabled':''}>${TSHIRT_SIZES.map(s=>`<option value="${s}" ${it.tshirt===s?'selected':''}>${s||'—'}</option>`).join('')}</select>`;
}
function backlogRowHTML(it,tribe,teams,readonly=false){
  const span=1;
  const ro=readonly?'readonly':'', dis=readonly?'disabled':'';
  const lead=`
    <td class="stik1" rowspan="${span}"><div class="id-cell">
      ${readonly?'':bkDragHandleHTML(it)}
      <input data-bk="${it._uid}" data-bp="id" value="${esc(it.id)}" ${ro}>
    </div></td>
    <td rowspan="${span}"><input data-bk="${it._uid}" data-bp="name" value="${esc(it.name)}" ${ro}></td>
    <td rowspan="${span}"><input data-bk="${it._uid}" data-bp="custPrio" value="${esc(it.custPrio)}" class="w-narrow" ${ro}></td>
    <td rowspan="${span}"><input data-bk="${it._uid}" data-bp="teamPrio" value="${esc(it.teamPrio)}" class="w-narrow" ${ro}></td>
    <td rowspan="${span}">${backlogQuarterCell(it,readonly)}</td>
    <td rowspan="${span}"><input data-bk="${it._uid}" data-bp="product" value="${esc(it.product)}" ${ro}></td>
    <td rowspan="${span}"><select data-bk="${it._uid}" data-bp="owner" ${dis}><option value=""></option>${teams.map(t=>`<option ${t.name===it.owner?'selected':''}>${esc(t.name)}</option>`).join('')}</select></td>
    <td rowspan="${span}">${initiativeTypeFieldHTML(it.type, `data-bk="${it._uid}" data-bp="type"${readonly?' disabled':''}`)}</td>
    <td rowspan="${span}">${backlogAcCell(it,readonly)}</td>
    <td rowspan="${span}">${backlogStatusCell(it,readonly)}</td>
    <td rowspan="${span}">${backlogTshirtCell(it,readonly)}</td>
    <td rowspan="${span}" style="text-align:center;font-weight:700">${round1(it.totalEffort)}</td>`;
  const delCell=readonly?`<td class="row-del-cell" rowspan="${span}"></td>`:`<td class="row-del-cell" rowspan="${span}"><button class="row-del" data-bk-delrow="${esc(it._uid)}" title="Удалить инициативу">✕</button></td>`;
  return `<tr class="exec-row" data-bk-row="${esc(it._uid)}">${lead}${ownerCompsBlockHTML(it,'bk',readonly)}${delCell}</tr>`;
}
async function sendBacklogToPrePI(tribe){
  const q=state.ui.backlogQuarter, y=state.ui.backlogYear;
  if(!q||!y){ toast('Сначала выберите Квартал и Год',{type:'warn'}); return; }
  const target=cycleId(y,q);
  const before=new Set(backlogRows().filter(row=>(row.sent_to||[]).includes(target)).map(row=>row.id));
  try{
    await executeBacklogCommand('/backlog-board/dispatch','POST',{
      tribe,target_year:+y,target_quarter:q,
    });
  }catch(error){
    // Реальные ошибки (нет PI-цикла, нет подходящих инициатив, команда не входит
    // в цикл, конфликт версий бэклога) уже показаны внутри executeBacklogCommand.
    return;
  }
  // Dispatch прошёл — read model бэклога уже обновлён. Считаем, что отправилось.
  const sent=backlogRows().filter(row=>!before.has(row.id)&&(row.sent_to||[]).includes(target)).length;
  if(sent){
    toast(`Отправлено на Pre PI (${target}): ${sent} ${sent===1?'инициатива':'инициатив'}`,{type:'success',title:'Отправлено на Pre PI Planning'});
  }else{
    toast(`Нет новых инициатив для ${target} — все подходящие уже отправлены.`,{type:'info',title:'Отправка на Pre PI Planning'});
  }
  // Обновляем Pre PI. Dispatch инкрементирует version целевого цикла, поэтому
  // сбрасываем локальную версию: иначе последующий read решит, что данные
  // изменились в другом окне (409), и молча погасит уведомление об отправке.
  const prevVersion=cycleVersions[target];
  delete cycleVersions[target];
  try{
    await loadPrePiCycles();
  }catch(_){
    // При сбое перезагрузки вернём прежнюю версию, чтобы будущие мутации целевого
    // цикла не падали с «Версия PI-цикла не загружена». Обратная связь уже показана.
    if(!Number.isInteger(cycleVersions[target])) cycleVersions[target]=prevVersion;
  }
  render();
}
function budgetIssueKey(it){ return it && (it._uid || it.id); }
function backlogInitiativeYear(it){ return String(it && it.year || '').trim(); }
function findBacklogByBudgetKey(key){
  const row=backlogRows().find(value=>value.id===key||value.issue_key===key);
  if(row) return {tribe:row.tribe,it:backlogViewItem(row)};
  return null;
}
function budgetAssessmentFor(it,year){
  const b=ensureBudgetYear(year);
  const key=budgetIssueKey(it);
  if(!key) return null;
  b.assessments[key]=ensureAssessmentShape(b.assessments[key]||{status:'На рассмотрении'});
  return b.assessments[key];
}
function sendBacklogToBudgetAssessment(tribe){
  const y=state.ui.backlogYear || state.ui.budgetYear;
  if(!y){ toast('Сначала выберите год',{type:'warn'}); return; }
  const b=ensureBudgetYear(y);
  const list=backlogRows().filter(row=>row.tribe===tribe).map(backlogViewItem);
  const matched=list.filter(it=>backlogInitiativeYear(it)===String(y));
  if(!matched.length){ toast(`Нет инициатив с годом реализации ${y}`,{type:'info'}); return; }
  let sent=0;
  matched.forEach(it=>{
    ensureBacklogShape(it);
    if(!it.id) it.id='INIT-'+uid().slice(1,6).toUpperCase();
    const key=budgetIssueKey(it);
    b.assessments[key]=ensureAssessmentShape(b.assessments[key]||{status:'На рассмотрении'});
    sent++;
  });
  state.ui.budgetYear=+y;
  state.ui.budgetTab='budgetAssessment';
  save(); render();
  toast(`Отправлено на оценку (${y}): ${sent} ${sent===1?'инициатива':'инициатив'}`,{type:'success',title:'Оценка инициатив'});
}
function bindBacklog(){
  // 7.0 — выбор трайба (фильтры по столбцам сбрасываем: у другого трайба свои значения)
  document.querySelectorAll('[data-bk-tribe]').forEach(el=>el.onclick=()=>{
    state.ui.backlogTribe=el.dataset.bkTribe; state.ui.backlogTeamFilter=null;
    clearColState('bk'); save(); render();
  });
  const tribe=state.ui.backlogTribe;
  if(!tribe) return;
  bindColFilters();
  // составной столбец «Квартал реализации»: своя воронка с двумя группами (Год/Квартал)
  const yqBtn=document.querySelector('[data-bk-yq]');
  if(yqBtn) yqBtn.onclick=(e)=>{ e.stopPropagation(); openBkYqFilterPop(yqBtn); };
  const back=$('#bkBack'); if(back) back.onclick=()=>{ state.ui.backlogTribe=null; clearColState('bk'); save(); render(); };
  document.querySelectorAll('[data-bk-filter]').forEach(el=>el.onclick=()=>{
    state.ui.backlogTeamFilter=el.dataset.bkFilter||null; save(); render();
  });
  if(state.ui.mode==='budget') return;
  const issInput=$('#bkIssueId');
  const addByIssue=async()=>{
    const id=(issInput.value||'').trim();
    if(!id){ toast('Введите № Issue',{type:'warn'}); issInput.focus(); return; }
    const tf=state.ui.backlogTeamFilter;
    const owner=tf||(backlogTeamRefs(tribe)[0]&&backlogTeamRefs(tribe)[0].name)||'';
    const executor=owner?{
      team:owner,
      effort_by_competency:Object.fromEntries(backlogTeamCompetencies(owner).map(code=>[code,0])),
    }:null;
    try{
      clearColFilters('bk');
      await executeBacklogCommand('/backlog-board/items','POST',{
        tribe,issue_key:id,title:'',description:'',product:'',owner_team:owner,
        initiative_type:'',target_year:null,target_quarter:null,
        customer_priority:'',team_priority:'',status:'Нет оценки',tshirt_size:'',tags:[],systems:[],
        executors:executor?[executor]:[],
      });
      issInput.value='';
      toast(`Инициатива ${id} создана. Заполните поля вручную.`,{type:'success'});
      const created=backlogRows().find(row=>row.issue_key.toLowerCase()===id.toLowerCase());
      if(created) flashBacklogRow(created.id);
    }catch(_){ }
  };
  // Показать только что созданную строку: прокрутить к ней, подсветить и поставить курсор в «Название».
  function flashBacklogRow(u){
    const row=[...document.querySelectorAll('tr[data-bk-row]')].find(r=>r.dataset.bkRow===u);
    if(!row) return;
    row.scrollIntoView({block:'center'});
    row.querySelectorAll('td').forEach(td=>td.classList.add('row-new'));
    const inp=row.querySelector('input[data-bp="name"]'); if(inp) inp.focus({preventScroll:true});
  }
  const addIss=$('#bkAddIssue'); if(addIss) addIss.onclick=addByIssue;
  if(issInput) issInput.onkeydown=(e)=>{ if(e.key==='Enter'){ e.preventDefault(); addByIssue(); } };
  const sq=$('#bkSendQ'); if(sq) sq.onchange=()=>{ state.ui.backlogQuarter=sq.value||null; save(); render(); };
  const sy=$('#bkSendY'); if(sy) sy.onchange=()=>{ state.ui.backlogYear=sy.value||null; save(); render(); };
  const send=$('#bkSend'); if(send) send.onclick=()=>sendBacklogToPrePI(tribe);

  // удаление инициативы из бэклога
  document.querySelectorAll('[data-bk-delrow]').forEach(el=>el.onclick=async(e)=>{
    e.stopPropagation();
    try{
      await executeBacklogCommand(`/backlog-board/items/${el.dataset.bkDelrow}`,'DELETE',{},true);
      toast('Инициатива удалена',{type:'success'});
    }catch(_){ }
  });

  // правка полей инициативы
  document.querySelectorAll('[data-bk][data-bp]').forEach(el=>el.onchange=async()=>{
    const row=findBacklogRow(el.dataset.bk); if(!row) return;
    const bp=el.dataset.bp;
    if(bp==='type'&&el.classList.contains('type-pick')){
      if(el.value===INITIATIVE_TYPE_OTHER){ typePickToggle(el); return; }
      typePickToggle(el);
    }
    const payload=backlogCommandPayload(row);
    const fieldMap={id:'issue_key',name:'title',custPrio:'customer_priority',teamPrio:'team_priority',
      quarter:'target_quarter',year:'target_year',product:'product',owner:'owner_team',
      type:'initiative_type',status:'status',tshirt:'tshirt_size'};
    if(bp==='ac') payload.systems=el.value.split(',').map(s=>s.trim()).filter(Boolean);
    else if(bp==='year') payload.target_year=el.value?+el.value:null;
    else if(bp==='quarter') payload.target_quarter=el.value||null;
    else payload[fieldMap[bp]]=el.value;
    if(bp==='owner'){
      const current=(row.executors||[]).find(ex=>ex.team===el.value);
      payload.executors=el.value?[{
        id:current&&current.id||null,
        team:el.value,
        effort_by_competency:Object.fromEntries(backlogTeamCompetencies(el.value).map(code=>[
          code,+((current&&current.effort_by_competency||{})[code])||0,
        ])),
      }]:[];
    }
    try{ await executeBacklogCommand(`/backlog-board/items/${row.id}`,'PATCH',payload); }
    catch(_){ }
  });
  // ввод чел/дн по компетенции
  document.querySelectorAll('[data-bk-comp]').forEach(el=>el.onchange=async()=>{
    const row=findBacklogRow(el.dataset.bkComp); if(!row) return;
    const payload=backlogCommandPayload(row);
    if(!payload.executors[0]) return;
    payload.executors[0].effort_by_competency={
      ...payload.executors[0].effort_by_competency,[el.dataset.c]:+el.value||0,
    };
    try{ await executeBacklogCommand(`/backlog-board/items/${row.id}`,'PATCH',payload); }
    catch(_){ }
  });
  // перетаскивание строк — изменение порядка инициатив
  bindBacklogRowDrag(tribe);
}
// Ручка перетаскивания строки бэклога. При активной сортировке порядок задаёт она,
// поэтому ручка гаснет — иначе перетаскивание молча не давало бы результата.
function bkDragHandleHTML(it){
  if(colSort('bk')) return `<span class="row-drag off" title="${SORT_DRAG_MSG}">⠿</span>`;
  return `<span class="row-drag" draggable="true" data-bk-drag="${esc(it._uid)}" title="Перетащите, чтобы изменить порядок">⠿</span>`;
}
// Перетаскивание строк «Бэклога команд». В отличие от Pre PI, вся строка состоит из
// полей ввода, поэтому тянем только за ручку в ячейке «№ Инициативы».
let bkDragUid=null;
function bindBacklogRowDrag(tribe){
  document.querySelectorAll('[data-bk-drag]').forEach(h=>{
    h.addEventListener('dragstart',e=>{
      bkDragUid=h.dataset.bkDrag;
      e.dataTransfer.effectAllowed='move';
      try{ e.dataTransfer.setData('text/plain',bkDragUid); }catch(_){}
      const tr=h.closest('tr'); if(tr) tr.classList.add('dragging');
    });
    h.addEventListener('dragend',()=>{
      const tr=h.closest('tr'); if(tr) tr.classList.remove('dragging');
      clearPrepRowDropMarkers(); bkDragUid=null;
    });
  });
  document.querySelectorAll('tr[data-bk-row]').forEach(tr=>{
    tr.addEventListener('dragover',e=>{
      if(!bkDragUid || tr.dataset.bkRow===bkDragUid) return;
      e.preventDefault();
      const after=isPrepDropAfter(tr,e);
      tr.classList.toggle('rowdragover-before',!after);
      tr.classList.toggle('rowdragover-after',after);
    });
    tr.addEventListener('dragleave',()=>clearPrepRowDropMarkers(tr));
    tr.addEventListener('drop',e=>{
      e.preventDefault(); e.stopPropagation();
      clearPrepRowDropMarkers(tr);
      moveBacklogRow(tribe,bkDragUid,tr.dataset.bkRow,isPrepDropAfter(tr,e));
    });
  });
}
// Порядок меняем в полном списке бэклога трайба, даже если часть строк скрыта
// фильтрами по команде/столбцам: цель определяем по её позиции в этом списке.
async function moveBacklogRow(tribe,dragUid,targetUid,after){
  if(!dragUid || !targetUid || dragUid===targetUid) return;
  const canonical=backlogRows().map(row=>row.id);
  const list=backlogRows().filter(row=>row.tribe===tribe).map(row=>row.id);
  const from=list.indexOf(dragUid);
  if(from<0) return;
  const [item]=list.splice(from,1);
  const to=list.indexOf(targetUid);
  if(to<0){ list.splice(from,0,item); return; }  // цель исчезла — возвращаем на место
  list.splice(after?to+1:to,0,item);
  let tribeIndex=0;
  const order=canonical.map(id=>{
    const row=findBacklogRow(id);
    return row&&row.tribe===tribe?list[tribeIndex++]:id;
  });
  try{ await executeBacklogCommand('/backlog-board/order','PUT',{item_ids:order}); }
  catch(_){ }
}

