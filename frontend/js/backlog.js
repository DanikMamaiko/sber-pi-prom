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
  const executors=(row.executors||[]).map(ex=>({
    id:ex.id,team:ex.team,comps:{...(ex.effort_by_competency||{})},attractions:[],
  }));
  if(!executors.length) executors.push({id:null,team:'',comps:{},attractions:[]});
  return {
    _uid:row.id,_backendId:row.id,id:row.issue_key,name:row.title||'',
    description:row.description||'',product:row.product||'',owner:row.owner_team||'',
    type:row.initiative_type||'',quarter:row.target_quarter||'',
    year:row.target_year?String(row.target_year):'',custPrio:row.customer_priority||'',
    teamPrio:row.team_priority||'',status:row.status||'Нет оценки',
    ac:Array.isArray(row.systems)?row.systems:[],tags:Array.isArray(row.tags)?row.tags:[],
    sentTo:Array.isArray(row.sent_to)?row.sent_to:[],totalEffort:+row.total_effort||0,
    executors,
  };
}
// Используется только старым, не развиваемым бюджетным экраном над transient-адаптером.
function ensureBacklogShape(it){ return it; }
function backlogCommandPayload(row){
  return {
    tribe:row.tribe,issue_key:row.issue_key,title:row.title||'',
    description:row.description||'',product:row.product||'',owner_team:row.owner_team||'',
    initiative_type:row.initiative_type||'',target_year:row.target_year,
    target_quarter:row.target_quarter,customer_priority:row.customer_priority||'',
    team_priority:row.team_priority||'',status:row.status||'Нет оценки',
    tags:Array.isArray(row.tags)?row.tags:[],systems:Array.isArray(row.systems)?row.systems:[],
    executors:(row.executors||[]).map(ex=>({
      id:ex.id||null,team:ex.team,effort_by_competency:{...(ex.effort_by_competency||{})},
    })),
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
// и без «Команды-исполнителя и компетенций».
const BK_FILTER_COLS=[
  {k:'custPrio',label:'Приоритет заказчика'},
  {k:'teamPrio',label:'Приоритет трайба/команды'},
  {k:'quarter', label:'Квартал реализации', val:it=>[it.quarter,it.year].filter(Boolean).join(' ')},
  {k:'product', label:'Продукт'},
  {k:'owner',   label:'Команда-владелец'},
  {k:'type',    label:'Тип инициативы'},
  {k:'ac',      label:'АС', val:it=>(Array.isArray(it.ac)?it.ac:[])},
  {k:'status',  label:'Статус'},
  {k:'effort',  label:'Общая оценка (чел/дн)', val:it=>it.totalEffort},
];

// 7.1 — весь бэклог трайба
function viewBacklogBoard(tribe){
  const isBudget=state.ui.mode==='budget';
  const teams=backlogTeamRefs(tribe);
  const filter=state.ui.backlogTeamFilter;
  let list=backlogRows().filter(row=>row.tribe===tribe).map(backlogViewItem);
  if(filter) list=list.filter(it=> it.owner===filter || issueExecTeams(it).includes(filter));
  // фильтры по столбцам применяются поверх фильтра по команде
  colFilterCtx['bk']={rows:list, cols:BK_FILTER_COLS};
  const listAll=list;
  list=applyColFilters(list,BK_FILTER_COLS,'bk');
  list=applyColSort(list,BK_FILTER_COLS,'bk');
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
      BK_FILTER_COLS.map(c=>filterThHTML(c,'bk')).join('')+
      `<th>Команда-исполнитель и компетенции</th>
      <th class="del-col"></th>
    </tr>
  </thead>`;
  html+=tableToolsBarHTML('bk');
  let body='';
  if(!list.length){
    const msg = listAll.length ? 'Ничего не найдено — измените фильтры по столбцам.' : 'Бэклог пуст — добавьте инициативу по № Issue.';
    body=`<tr><td class="stik1 muted">—</td><td class="muted" colspan="12">${msg}</td></tr>`;
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
function backlogExecutorTeamOptions(){
  return backlogTeamRefs();
}
function backlogRowHTML(it,tribe,teams,readonly=false){
  const execTeamOptions=backlogExecutorTeamOptions();
  const exs=it.executors, span=exs.length;
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
    <td rowspan="${span}"><input data-bk="${it._uid}" data-bp="type" value="${esc(it.type)}" ${ro}></td>
    <td rowspan="${span}">${backlogAcCell(it,readonly)}</td>
    <td rowspan="${span}">${backlogStatusCell(it,readonly)}</td>
    <td rowspan="${span}" style="text-align:center;font-weight:700">${round1(it.totalEffort)}</td>`;
  const delCell=readonly?`<td class="row-del-cell" rowspan="${span}"></td>`:`<td class="row-del-cell" rowspan="${span}"><button class="row-del" data-bk-delrow="${esc(it._uid)}" title="Удалить инициативу">✕</button></td>`;
  let rows='';
  exs.forEach((ex,ei)=>{
    const executorCell=readonly
      ? `<td class="exec-cell"><div class="exec-block"><b>${esc(ex.team)||'—'}</b><div class="comp-cells">${Object.entries(ex.comps||{}).map(([c,v])=>`<span class="comp-cell"><span class="cc-lab">${esc(c)}</span>${esc(v)}</span>`).join('')||'<span class="comp-cells-empty">нет оценки</span>'}</div></div></td>`
      : execBlockHTML(it, ex, ei, 'bk', execTeamOptions);
    rows+=`<tr class="exec-row" data-bk-row="${esc(it._uid)}">${ei===0?lead:''}${executorCell}${ei===0?delCell:''}</tr>`;
  });
  return rows;
}
async function sendBacklogToPrePI(tribe){
  const q=state.ui.backlogQuarter, y=state.ui.backlogYear;
  if(!q||!y){ toast('Сначала выберите Квартал и Год',{type:'warn'}); return; }
  const target=cycleId(y,q);
  try{
    const before=new Set(backlogRows().filter(row=>(row.sent_to||[]).includes(target)).map(row=>row.id));
    await executeBacklogCommand('/backlog-board/dispatch','POST',{
      tribe,target_year:+y,target_quarter:q,
    });
    const sent=backlogRows().filter(row=>!before.has(row.id)&&(row.sent_to||[]).includes(target)).length;
    await loadPrePiCycles();
    render();
    toast(`Отправлено на Pre PI (${target}): ${sent} ${sent===1?'инициатива':'инициатив'}`,{type:'success',title:'Отправлено на Pre PI Planning'});
  }catch(error){
    if(error&&error.status===409)return;
  }
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
        customer_priority:'',team_priority:'',status:'Нет оценки',tags:[],systems:[],
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
    const payload=backlogCommandPayload(row);
    const fieldMap={id:'issue_key',name:'title',custPrio:'customer_priority',teamPrio:'team_priority',
      quarter:'target_quarter',year:'target_year',product:'product',owner:'owner_team',type:'initiative_type',status:'status'};
    if(bp==='ac') payload.systems=el.value.split(',').map(s=>s.trim()).filter(Boolean);
    else if(bp==='year') payload.target_year=el.value?+el.value:null;
    else if(bp==='quarter') payload.target_quarter=el.value||null;
    else payload[fieldMap[bp]]=el.value;
    try{ await executeBacklogCommand(`/backlog-board/items/${row.id}`,'PATCH',payload); }
    catch(_){ }
  });
  // выбор команды-исполнителя: единый список, сгруппированный по трайбам
  document.querySelectorAll('[data-bk-exec]').forEach(el=>el.onchange=async()=>{
    const row=findBacklogRow(el.dataset.bkExec); if(!row) return;
    const ei=+el.dataset.ei, payload=backlogCommandPayload(row);
    if(!payload.executors[ei]){
      payload.executors[ei]={id:null,team:el.value,effort_by_competency:{}};
    }
    const old=payload.executors[ei].effort_by_competency||{}, effort={};
    backlogTeamCompetencies(el.value).forEach(code=>{ effort[code]=+old[code]||0; });
    payload.executors[ei]={...payload.executors[ei],team:el.value,effort_by_competency:effort};
    try{ await executeBacklogCommand(`/backlog-board/items/${row.id}`,'PATCH',payload); }
    catch(_){ }
  });
  // ввод чел/дн по компетенции
  document.querySelectorAll('[data-bk-comp]').forEach(el=>el.onchange=async()=>{
    const row=findBacklogRow(el.dataset.bkComp); if(!row) return;
    const ei=+el.dataset.ei, payload=backlogCommandPayload(row);
    if(!payload.executors[ei]) return;
    payload.executors[ei].effort_by_competency={
      ...payload.executors[ei].effort_by_competency,[el.dataset.c]:+el.value||0,
    };
    try{ await executeBacklogCommand(`/backlog-board/items/${row.id}`,'PATCH',payload); }
    catch(_){ }
  });
  // добавить/убрать исполнителя
  document.querySelectorAll('[data-bk-execadd]').forEach(el=>el.onclick=async()=>{
    const row=findBacklogRow(el.dataset.bkExecadd); if(!row) return;
    const payload=backlogCommandPayload(row), used=new Set(payload.executors.map(ex=>ex.team));
    const team=backlogTeamRefs().find(value=>!used.has(value.name));
    if(!team){ toast('Все доступные команды уже добавлены',{type:'info'}); return; }
    payload.executors.push({id:null,team:team.name,effort_by_competency:Object.fromEntries(team.competencies.map(code=>[code,0]))});
    try{ await executeBacklogCommand(`/backlog-board/items/${row.id}`,'PATCH',payload); }
    catch(_){ }
  });
  document.querySelectorAll('[data-bk-execdel]').forEach(el=>el.onclick=async()=>{
    const row=findBacklogRow(el.dataset.bkExecdel); if(!row) return;
    const payload=backlogCommandPayload(row); payload.executors.splice(+el.dataset.ei,1);
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

