/* =====================================================================
   ВКЛАДКА 2 — Pre PI Planning (5.0 / 5.1)
===================================================================== */
// Столбцы Pre PI — единые для обоих типов команд (Agile и «ИТ-проект»).
// Тип команды на набор столбцов не влияет: разница только в обязательности полей
// Обязательность полей приходит с backend в requiredFields.
//  upperOnly — только в верхнем блоке «Запланировано»;
//  lowerHide — скрыть в нижнем блоке «Бэклог инициатив».
const PREP_COLS=[
  {k:'cel',label:'Цель/Веха',sel:true},
  {k:'custPrio',label:'Приоритет заказчика'},
  {k:'teamPrio',label:'Приоритет трайба/команды'},
  {k:'product',label:'Продукт'},
  {k:'owner',label:'Команда-владелец',ro:true},
  {k:'type',label:'Тип инициативы'},
  {k:'metric',label:'Метрика',lowerHide:true},
  {k:'fact',label:'AS IS (текущее)',lowerHide:true},
  {k:'plan',label:'TO BE (прогноз)',lowerHide:true},
  {k:'hypo',label:'Гипотезы',lowerHide:true},
  {k:'redesign',label:'Редизайн',lowerHide:true},
];
// Набор столбцов блока (верхний/нижний). От типа команды не зависит.
function prepColsFor(isUpper){
  return PREP_COLS.filter(c=>(!c.upperOnly||isUpper) && (isUpper||!c.lowerHide));
}
function allTeamNames(){ return state.pi.teams.map(t=>t.name); }
function prepTeamObj(){
  if(!state.ui.prepSel) return null;
  return state.pi.teams.find(t=>t.name===state.ui.prepSel)||null;
}
// команды трайба и агрегация инициатив трайба (по командам-исполнителям)
function prepTribeTeams(tribe){ return state.pi.teams.filter(t=>t.tribe===tribe); }
function prepTribeBoardData(tribe,filter){
  const teamNames=prepTribeTeams(tribe).map(t=>t.name);
  const inScope=(i)=>{
    const et=issueExecTeams(i);
    return filter ? et.includes(filter) : et.some(n=>teamNames.includes(n));
  };
  const all=state.issues.filter(inScope);
  return {upper:all.filter(i=>i.prePlanned), lower:all.filter(i=>!i.prePlanned)};
}
// Команды трайба, по которым считаются блоки «Емкость / Доступность компетенций / Тех.повестка».
// Тип команды роли не играет: у «ИТ-проекта» тоже есть исполнители с компетенциями.
function prepCapTeams(tribe){ return prepTribeTeams(tribe); }
// Агрегат блоков «Емкость / Доступность компетенций / Тех.повестка» по набору команд.
// Одна команда — показатели этой команды; весь трайб — сумма по всем его командам-исполнителям.
// scope: 'team' — выбрана команда (с кнопкой «Рассчитать/изменить»); 'tribe' — весь трайб (без кнопки).
function prePiServerMetrics(teams,scope){
  const capacity=(prePiViews[currentCycleId()]||{}).capacity||{};
  if(scope==='team')return (capacity.teams||{})[teams[0]._teamId]||{};
  return (capacity.tribes||{})[teams[0]._tribeId]||{};
}
function prePiServerPercent(value){return value===null||value===undefined?'—':round1(value)+'%';}
function prePiCapacityPanelHTML(teams,scope){
  const d=prePiServerMetrics(teams,scope),competencies=d.competencies||{},tech=d.tech_agenda||{},reg=d.reg_agenda||{};
  const isTeam=scope==='team';
  return `<div class="cap-panel">
    <div class="cap-group">
      <div class="cap-group-head">
        <span class="cap-group-title">${isTeam?'Емкость команды':'Емкость трайба'}</span>
        ${isTeam?`<button class="cap-calc" id="prepCalc">Рассчитать/изменить</button>`:''}
      </div>
      <div class="cap-row">
        <div class="cap-box"><div class="cap-lab">Календарная</div><div class="cap-val">${round1(d.calendar_capacity||0)} дн.</div></div>
        <div class="cap-box"><div class="cap-lab">Доступная</div><div class="cap-val">${round1(d.available_capacity||0)} дн.</div></div>
        <div class="cap-box"><div class="cap-lab">Запланированная</div><div class="cap-val"><span class="fact ${d.over_capacity?'over':''}">${round1(d.planned_capacity||0)} дн.</span></div></div>
      </div>
    </div>
    <div class="cap-group cap-group-roles">
      <div class="cap-group-head"><span class="cap-group-title">Доступность компетенций</span></div>
      <div class="cap-row">`+
        Object.entries(competencies).map(([role,row])=>`<div class="cap-box"><div class="cap-lab">${role} · доступно | запланировано</div>
          <div class="cap-val">${round1(row.available||0)} | <span class="fact ${row.over_capacity?'over':''}">${round1(row.planned||0)}</span></div></div>`).join('')+
      `</div>
    </div>
    <div class="cap-group">
      <div class="cap-group-head"><span class="cap-group-title">Тех.повестка</span></div>
      <div class="cap-row">
        <div class="cap-box"><div class="cap-lab">Всего</div><div class="cap-val">${prePiServerPercent(tech.total_percent)}</div></div>
        <div class="cap-box"><div class="cap-lab">Общая</div><div class="cap-val">${prePiServerPercent(tech.common_percent)}</div></div>
        <div class="cap-box"><div class="cap-lab">Командная</div><div class="cap-val">${prePiServerPercent(tech.team_percent)}</div></div>
      </div>
    </div>
    <div class="cap-group">
      <div class="cap-group-head"><span class="cap-group-title">Регуляторка</span></div>
      <div class="cap-row">
        <div class="cap-box"><div class="cap-lab">Всего</div><div class="cap-val">${prePiServerPercent(reg.total_percent)}</div></div>
        <div class="cap-box"><div class="cap-lab">Общая</div><div class="cap-val">${prePiServerPercent(reg.common_percent)}</div></div>
        <div class="cap-box"><div class="cap-lab">Командная</div><div class="cap-val">${prePiServerPercent(reg.team_percent)}</div></div>
      </div>
    </div>
  </div>`;
}

function viewPrep(){
  const id=currentCycleId();
  if(!id||!prePiViews[id])return `<div class="card"><h2>Pre PI Planning ${cycleBadge()}</h2><div class="muted">${prePiApiReady?'Нет данных Pre PI':'Загрузка данных Pre PI…'}</div></div>`;
  if(!state.ui.prepTribe) return viewPrepSelect();
  if(!allTribes().includes(state.ui.prepTribe)){ state.ui.prepTribe=null; return viewPrepSelect(); }
  return viewPrepBoard(state.ui.prepTribe);
}
function viewPrepSelect(){
  const tribes=allTribes();
  let html=`<div class="card"><div class="flex-between"><h2>Pre PI Planning ${cycleBadge()}</h2>
    <div class="hint">Выберите трайб. Отобразится весь Pre PI трайба; сверху можно отфильтровать по команде.</div></div>`;
  html+=`<div class="tribe-list">`;
  if(!tribes.length) html+=`<div class="muted">Нет трайбов — добавьте команды на «Данные PI-цикла».</div>`;
  tribes.forEach(tribe=>{
    html+=`<div class="tribe-acc"><div class="tribe-acc-head" data-prep-tribe="${esc(tribe)}"><span class="caret">▶</span>${esc(tribe)}</div></div>`;
  });
  html+=`</div></div>`;
  return html;
}
function viewPrepBoard(tribe){
  const teams=prepTribeTeams(tribe);
  const filter=state.ui.prepTeamFilter;
  const filterTeam = filter ? teams.find(t=>t.name===filter) : null;
  const {upper,lower}=prepTribeBoardData(tribe,filter);

  let html=`<div class="card">
    <div class="prep-toolbar">
      <span class="team-title">${esc(tribe)}</span>
      <button class="ghost" id="prepBack">← Выбор трайба</button>
      <div class="prep-actions">
        <button class="primary" id="prepSubmit">Отправить на доски</button>
      </div>
    </div>`;
  // фильтр по командам трайба
  html+=`<div class="row" style="margin:8px 0;gap:6px;flex-wrap:wrap">
    <span class="muted">Команда:</span>
    <button class="bk-filter${!filter?' primary':''}" data-prep-filter="">Весь трайб</button>`+
    teams.map(t=>`<button class="bk-filter${filter===t.name?' primary':''}" data-prep-filter="${esc(t.name)}">${esc(t.name)}</button>`).join('')+
  `</div>`;

  // Блоки Емкость/Доступность/Тех.повестка: выбрана команда — по ней;
  // «Весь трайб» — сумма по всем командам трайба (включая «ИТ-проект»).
  if(!filterTeam){
    const capTeams=prepCapTeams(tribe);
    if(capTeams.length){
      html+=prePiCapacityPanelHTML(capTeams,'tribe');
      html+=`<div class="note" style="margin:8px 0">Показатели трайба — сумма по всем его командам-исполнителям (${capTeams.map(t=>esc(t.name)).join(', ')}). Выберите команду сверху, чтобы увидеть её показатели и рассчитать ёмкость.</div>`;
    }
  } else {
    html+=prePiCapacityPanelHTML([filterTeam],'team');
  }

  html+=goalDatalistHTML();
  html+=`<div class="prep-block">
    <div class="prep-block-title">Запланировано — верхний блок</div>
    ${prepTable(upper,true)}
  </div>`;
  html+=`<div class="prep-block">
    <div class="prep-block-title">Бэклог инициатив — нижний блок</div>
    ${prepTable(lower,false)}
  </div>`;
  html+=`<div class="note" style="margin-top:6px">Инициативы попадают в нижний блок с вкладки «Бэклог». Перетащите строку (за ручку <b>⠿</b> в столбце «№ Инициативы») из нижнего блока в верхний, чтобы «взять» инициативу; внутри блока перетаскивание меняет порядок строк. Кнопка <b>▼</b> в шапке столбца — фильтр и сортировка (пустые значения всегда внизу); пока сортировка активна, порядок внутри блока задаёт она, но перетаскивание между блоками работает. Крестик <b>✕</b> в верхнем блоке возвращает инициативу в нижний блок. «Общая оценка (чел/дн)» = сумма по всем командам-исполнителям и компетенциям. У каждого исполнителя — свои компетенции (из «Данных PI-цикла»). «Привлечение»: <b>+</b> добавляет ресурс другой команды с выбором спринта (фиолетовый — не согласовано, красный — согласовано).</div>`;
  html+=`</div>`;
  return html;
}
// «Цель/Веха» — комбобокс: варианты из справочника целей PI (state.pi.goals) плюс свободный ввод.
// Ручной ввод нужен командам «ИТ-проект» — веха у каждого проекта своя и в справочник не входит.
// Введённое вручную значение сохраняется у инициативы, но справочник целей не пополняет.
const GOAL_LIST_ID='piGoalsList';
// Общий на страницу список вариантов; подключается к полям через атрибут list.
function goalDatalistHTML(){
  return `<datalist id="${GOAL_LIST_ID}">`+
    (state.pi.goals||[]).map(g=>`<option value="${esc(g)}"></option>`).join('')+`</datalist>`;
}
function goalInputHTML(i){
  return `<input class="goal-sel" list="${GOAL_LIST_ID}" placeholder="цель или веха"
    title="Выберите цель из справочника PI или впишите свою (для ИТ-проектов — веху)"
    data-pi="${esc(i.id)}" data-pk="cel" value="${esc(i.cel)}">`;
}
// Фильтруемые столбцы Pre PI: все столбцы блока (кроме №/названия инициативы и
// «Команды-исполнителя и компетенций») + расчётная «Общая оценка».
function prepFilterCols(cols,withEffort){
  const fcols=cols.map(c=>({k:c.k,label:c.label}));
  if(withEffort) fcols.push({k:'effort',label:'Общая оценка (чел/дн)',val:i=>round1(i.totalEstimate||0)});
  return fcols;
}
function prepScope(isUpper){ return 'prep:'+(isUpper?'upper':'lower'); }

// Единая таблица инициатив (Agile и «ИТ-проект»): приоритеты, «Цель/Веха», метрика,
// AS IS / TO BE / Гипотезы / Редизайн, матрица компетенций по исполнителям, привлечение.
function prepTable(rows,isUpper){
  const cols=prepColsFor(isUpper);
  const scope=prepScope(isUpper);
  const fcols=prepFilterCols(cols,true);
  colFilterCtx[scope]={rows, cols:fcols};
  const hadRows=rows.length;
  rows=applyColFilters(rows,fcols,scope);
  rows=applyColSort(rows,fcols,scope);
  const sorted=!!colSort(scope); // влияет на подсказку у ручки перетаскивания
  const head=`<thead>
    <tr>
      <th class="stik1">№ Инициативы</th>
      <th class="stik2">Название инициативы</th>`+
      fcols.map(c=>filterThHTML(c,scope)).join('')+
      `<th>Команда-исполнитель и компетенции</th>`+
      (isUpper?`<th>Запросы на привлечение</th>`:``)+
      `<th class="del-col"></th>
    </tr>
  </thead>`;
  let body='';
  if(!rows.length){
    const msg = hadRows ? 'Ничего не найдено — измените фильтры по столбцам'
                        : (isUpper?'Перетащите инициативы сюда':'Инициативы переносятся сюда с вкладки «Бэклог»');
    body=`<tr><td class="stik1 muted">—</td><td class="stik2 muted">${msg}</td>`+
      cols.map(()=>`<td></td>`).join('')+`<td></td><td></td><td></td>`+(isUpper?`<td></td>`:``)+`</tr>`;
  }else{
    const opts=allTeamNames();
    rows.forEach(i=>{
      const exs=Array.isArray(i.executors)&&i.executors.length?i.executors:[{team:'',comps:{},attractions:[]}], span=exs.length;
      const lead=`
        <td class="stik1" rowspan="${span}"><div class="id-cell">
          <span class="row-drag" title="${sorted?'Перетащите, чтобы перенести в другой блок (порядок внутри блока задаёт сортировка)':'Перетащите, чтобы изменить порядок или перенести в другой блок'}">⠿</span>
          <b>${esc(i.id)}</b>
        </div></td>
        <td class="stik2" rowspan="${span}">${esc(i.name)||'<span class=auto>—</span>'}</td>`+
        cols.map(c=> c.ro
          ? `<td rowspan="${span}">${esc(i[c.k])||'<span class=auto>—</span>'}</td>`
          : c.sel
          ? `<td rowspan="${span}">${goalInputHTML(i)}</td>`
          : c.k==='type'
          ? `<td rowspan="${span}">${initiativeTypeFieldHTML(i[c.k], `data-pi="${esc(i.id)}" data-pk="type"`)}</td>`
          : `<td rowspan="${span}"><input data-pi="${esc(i.id)}" data-pk="${c.k}" value="${esc(i[c.k])}" class="${c.k==='custPrio'||c.k==='teamPrio'?'w-narrow':''}"></td>`
        ).join('')+
        `<td rowspan="${span}" style="text-align:center;font-weight:700">${round1(i.totalEstimate||0)}</td>`;
      const delCell=`<td class="row-del-cell" rowspan="${span}">${rowDelBtnHTML(i.id,isUpper)}</td>`;
      exs.forEach((ex,ei)=>{
        const execCell=execBlockHTML(i, ex, ei, 'pi', opts);
        const attrCell=isUpper?`<td class="attr-cell" data-attr-row="${esc(i.id)}">${attractionsHTML(i, ei)}</td>`:'';
        body+=`<tr class="exec-row" ${ei===0?`draggable="true" data-rowdrag="${esc(i.id)}"`:''}>${ei===0?lead:''}${execCell}${attrCell}${ei===0?delCell:''}</tr>`;
      });
    });
  }
  return tableToolsBarHTML(scope)+
    `<div class="prep-wrap prep-dropzone" data-scroll-key="${scope}" data-prep-block="${isUpper?'upper':'lower'}"><table class="prep">${head}<tbody>${body}</tbody></table></div>`;
}
// «Крестик» строки: в верхнем блоке он возвращает инициативу в бэклог (нижний блок),
// в нижнем — удаляет её из PI-цикла.
function rowDelBtnHTML(id,isUpper){
  const title=isUpper?'Вернуть в бэклог инициатив':'Удалить инициативу';
  return `<button class="row-del" data-pi-delrow="${esc(id)}" data-pi-delblock="${isUpper?'upper':'lower'}" title="${title}">✕</button>`;
}
function attractionsHTML(iss, ei){
  const ex=iss.executors && iss.executors[ei];
  const list=(ex && ex.attractions) || [];
  let s=list.map(a=>{
    const aid=a.id;
    const col=a.visualState||({approved:'red',rejected:'gray'}[a.status]||'purple');
    const team=a.team||'—';
    const spr = (a.sprint!==null && a.sprint!==undefined) ? ` · Спринт ${(+a.sprint)+1}` : '';
    return `<span class="chip ${col}"><span class="chip-id">${esc(aid)}</span><span class="chip-team">${esc(team)}${spr}</span><span class="chip-x" data-attr-del="${esc(iss.id)}" data-attr-ei="${ei}" data-attr-aid="${esc(aid)}">✕</span></span>`;
  }).join('');
  s+=`<button class="attr-add" data-attr-add="${esc(iss.id)}" data-attr-ei="${ei}" title="Добавить привлечение">+</button>`;
  return s;
}

let prepDragId=null;
function prePiExecutorPayload(iss,mutate){
  const rows=(iss.executors||[]).map((ex,index)=>({
    id:ex._backendId||null,
    team_id:ex.teamId||null,
    team:ex.team||'',
    tribe:(state.pi.teams.find(t=>t.name===ex.team)||{}).tribe||'',
    effort_by_competency:{...(ex.comps||{})},
    attractions:(ex.attractions||[]).map((a,position)=>({
      id:a._backendId||null,target_initiative_id:a.targetInitiativeId||null,
      issue_key:a.id||'',target_team_id:a.targetTeamId||null,team:a.team||'',
      sprint_index:Number.isInteger(a.sprint)?a.sprint:null,
      approval_status:a.status||'pending',sort_order:position,
    })),
    sort_order:index,
  }));
  mutate(rows);
  return rows;
}
async function runPrePiUiCommand(path,method,body,successMessage){
  try{
    await prePiCommand(path,method,body);
    if(successMessage)toast(successMessage,{type:'success'});
  }catch(error){
    if(reportOptimisticConflict(error))return;
    reportPrePiSyncError(error);render();
  }
}
async function runPrePiCascadeCommand(path,method,body,successMessage){
  try{return await prePiCommand(path,method,body);}
  catch(error){
    if(error.detail&&error.detail.code==='cascade_confirmation_required'){
      if(window.confirm(error.detail.message||'Подтвердить каскадные изменения?')){
        return prePiCommand(path,method,{...body,confirm_cascade:true});
      }
      render();return null;
    }
    if(reportOptimisticConflict(error))return null;
    reportPrePiSyncError(error);render();return null;
  }finally{if(successMessage){} }
}
function bindPrep(){
  // выбор трайба (7.0-подобный экран для Pre PI); фильтры по столбцам сбрасываем
  document.querySelectorAll('[data-prep-tribe]').forEach(el=>el.onclick=()=>{
    state.ui.prepTribe=el.dataset.prepTribe; state.ui.prepTeamFilter=null;
    clearPrepColFilters(); save();render();
  });
  const tribe=state.ui.prepTribe;
  if(!tribe) return;
  bindColFilters();
  const back=$('#prepBack'); if(back)back.onclick=()=>{state.ui.prepTribe=null;clearPrepColFilters();save();render();};

  // фильтр по командам трайба (смена команды может сменить набор столбцов — Agile/ИТ-проект)
  document.querySelectorAll('[data-prep-filter]').forEach(el=>el.onclick=()=>{
    state.ui.prepTeamFilter=el.dataset.prepFilter||null; clearPrepColFilters(); save();render();
  });
  const filter=state.ui.prepTeamFilter;
  const teams=prepTribeTeams(tribe);
  const filterTeam=filter?teams.find(t=>t.name===filter):null;

  // «Рассчитать/изменить» ёмкость → Командные доски → Емкость выбранной команды
  const calc=$('#prepCalc'); if(calc && filterTeam)calc.onclick=()=>{
    state.ui.tab='teams'; state.ui.teamSel=filterTeam.name; state.ui.teamView='capacity';
    save();render();
  };

  // Каждое изменение — одна backend-команда; сохранённый read model до ответа не меняется.
  document.querySelectorAll('[data-pi]').forEach(el=>{
    let committedValue=el.value;
    const commit=()=>{
      if(el.dataset.pk==='type'&&el.classList.contains('type-pick')){
        if(el.value===INITIATIVE_TYPE_OTHER){ typePickToggle(el); return; }
        typePickToggle(el);
      }
      if(el.value===committedValue)return;
      committedValue=el.value;
      const iss=findIssue(el.dataset.pi); if(!iss)return;
      const field={name:'title',description:'description',product:'product',type:'initiative_type',
        cel:'goal_text',metric:'metric',fact:'current_value',plan:'target_value',hypo:'hypothesis',
        redesign:'redesign',custPrio:'customer_priority',teamPrio:'team_priority',comment:'comment'}[el.dataset.pk];
      if(!field||!iss._backendId)return;
      runPrePiUiCommand(`/initiatives/${iss._backendId}`,'PATCH',{[field]:el.value});
    };
    el.onchange=commit;
    // Enter завершает редактирование так же, как уход из поля, и отправляет ровно одну команду.
    el.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();commit();el.blur();}};
  });
  // выбор команды-исполнителя
  document.querySelectorAll('[data-pi-exec]').forEach(el=>el.onchange=()=>{
    const iss=findIssue(el.dataset.piExec); if(!iss)return;
    const ei=+el.dataset.ei,team=state.pi.teams.find(t=>t.name===el.value); if(!iss.executors[ei]||!team)return;
    const executors=prePiExecutorPayload(iss,rows=>{
      rows[ei].team_id=team._teamId;rows[ei].team=team.name;rows[ei].tribe=team.tribe;
      const allowed=new Set(team.comps||[]);
      rows[ei].effort_by_competency=Object.fromEntries(Object.entries(rows[ei].effort_by_competency).filter(([key])=>allowed.has(key)));
    });
    runPrePiUiCommand(`/initiatives/${iss._backendId}`,'PATCH',{executors});
  });
  // ввод чел/дн по компетенции
  document.querySelectorAll('[data-pi-comp]').forEach(el=>el.onchange=()=>{
    const iss=findIssue(el.dataset.piComp); if(!iss)return;
    const ei=+el.dataset.ei;if(!iss.executors[ei])return;
    const executors=prePiExecutorPayload(iss,rows=>{rows[ei].effort_by_competency[el.dataset.c]=+el.value||0;});
    runPrePiUiCommand(`/initiatives/${iss._backendId}`,'PATCH',{executors});
  });
  // добавить/убрать исполнителя
  document.querySelectorAll('[data-pi-execadd]').forEach(el=>el.onclick=()=>{
    const iss=findIssue(el.dataset.piExecadd);if(!iss)return;
    const first=teams.find(t=>!(iss.executors||[]).some(ex=>ex.team===t.name));if(!first)return;
    const executors=prePiExecutorPayload(iss,rows=>rows.push({team_id:first._teamId,team:first.name,tribe:first.tribe,effort_by_competency:{},attractions:[],sort_order:rows.length}));
    runPrePiUiCommand(`/initiatives/${iss._backendId}`,'PATCH',{executors});
  });
  document.querySelectorAll('[data-pi-execdel]').forEach(el=>el.onclick=()=>{
    const iss=findIssue(el.dataset.piExecdel);if(!iss)return;
    const ei=+el.dataset.ei,executors=prePiExecutorPayload(iss,rows=>rows.splice(ei,1));
    runPrePiUiCommand(`/initiatives/${iss._backendId}`,'PATCH',{executors});
  });

  // Крестик строки: из верхнего блока — возврат в бэклог инициатив, из нижнего — удаление.
  document.querySelectorAll('[data-pi-delrow]').forEach(el=>el.onclick=async(e)=>{
    e.stopPropagation();
    const id=el.dataset.piDelrow;
    if(el.dataset.piDelblock==='upper'){
      const iss=findIssue(id);if(iss)await runPrePiCascadeCommand(`/initiatives/${iss._backendId}/move`,'POST',{target_block:'backlog'});
      return;
    }
    const iss=findIssue(id);if(iss)await runPrePiCascadeCommand(`/initiatives/${iss._backendId}`,'DELETE',{});
  });

  // привлечение (по конкретному исполнителю)
  document.querySelectorAll('[data-attr-add]').forEach(b=>b.onclick=()=>openAttractionModal(b.dataset.attrAdd, +b.dataset.attrEi));
  document.querySelectorAll('[data-attr-del]').forEach(b=>b.onclick=()=>{
    const iss=findIssue(b.dataset.attrDel); if(!iss)return;
    const ex=iss.executors[+b.dataset.attrEi]; if(!ex)return;
    const ei=+b.dataset.attrEi;
    const executors=prePiExecutorPayload(iss,rows=>{rows[ei].attractions=rows[ei].attractions.filter(a=>a.issue_key!==b.dataset.attrAid);});
    runPrePiUiCommand(`/initiatives/${iss._backendId}`,'PATCH',{executors});
  });

  // drag строк
  bindPrepRowDrag();

  // отправка на доски: по выбранной команде, иначе по всем командам трайба
  const submit=$('#prepSubmit'); if(submit)submit.onclick=()=>{
    prepSubmitToBoards(filterTeam?[filterTeam]:teams);
  };
}
function bindPrepRowDrag(){
  document.querySelectorAll('tr[data-rowdrag]').forEach(tr=>{
    tr.addEventListener('dragstart',e=>{
      // не начинаем перетаскивание, если тянут за поле/кнопку (чтобы работало редактирование)
      if(e.target.closest('input,select,button,.chip')){ e.preventDefault(); return; }
      prepDragId=tr.dataset.rowdrag;
      e.dataTransfer.effectAllowed='move';
      try{e.dataTransfer.setData('text/plain',prepDragId);}catch(_){}
      tr.classList.add('dragging');
    });
    tr.addEventListener('dragend',()=>{tr.classList.remove('dragging');clearPrepRowDropMarkers();});
    tr.addEventListener('dragover',e=>{
      e.preventDefault();
      const after = isPrepDropAfter(tr,e);
      tr.classList.toggle('rowdragover-before',!after);
      tr.classList.toggle('rowdragover-after',after);
    });
    tr.addEventListener('dragleave',()=>clearPrepRowDropMarkers(tr));
    tr.addEventListener('drop',e=>{
      e.preventDefault();e.stopPropagation();
      clearPrepRowDropMarkers(tr);
      const block=tr.closest('[data-prep-block]').dataset.prepBlock;
      prepMoveRow(prepDragId,block,tr.dataset.rowdrag,isPrepDropAfter(tr,e));
    });
  });
  document.querySelectorAll('[data-prep-block]').forEach(zone=>{
    zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('dragover');});
    zone.addEventListener('dragleave',()=>zone.classList.remove('dragover'));
    zone.addEventListener('drop',e=>{
      e.preventDefault();
      zone.classList.remove('dragover');
      if(e.target.closest('tr[data-rowdrag]')) return; // обработано строкой
      prepMoveRow(prepDragId,zone.dataset.prepBlock,null);
    });
  });
}
function isPrepDropAfter(tr,e){
  const rect=tr.getBoundingClientRect();
  return e.clientY > rect.top + rect.height/2;
}
function clearPrepRowDropMarkers(scope=document){
  if(scope.matches && scope.matches('.rowdragover-before,.rowdragover-after')){
    scope.classList.remove('rowdragover-before','rowdragover-after');
  }
  scope.querySelectorAll('.rowdragover-before,.rowdragover-after').forEach(x=>{
    x.classList.remove('rowdragover-before','rowdragover-after');
  });
}
function prepMoveRow(draggedId,block,targetId,afterTarget=false){
  if(!draggedId || targetId===draggedId) return;
  const dragged=findIssue(draggedId);if(!dragged||!dragged._backendId)return;
  const toUpper=(block==='upper');
  const blockChanged = dragged.prePlanned!==toUpper;
  const sorted=!!colSort(prepScope(toUpper));
  if(sorted && !blockChanged){ toast(SORT_DRAG_MSG,{type:'info'}); return; }
  let beforeId=null;
  if(targetId&&!sorted){
    const target=findIssue(targetId);beforeId=target&&target._backendId;
    if(afterTarget){
      const rows=state.issues.filter(i=>i.prePlanned===toUpper&&i.id!==draggedId);
      const index=rows.findIndex(i=>i.id===targetId);
      beforeId=rows[index+1]&&rows[index+1]._backendId||null;
    }
  }
  runPrePiCascadeCommand(`/initiatives/${dragged._backendId}/move`,'POST',{
    target_block:toUpper?'planned':'backlog',before_id:beforeId,
  });
}

/* ---- Pre PI Planning: действия и модалки ---- */
// Подсветить незаполненные поля прямо в таблице (без ре-рендера — снимется при следующем render()).
function highlightMissingFields(problems){
  document.querySelectorAll('.prep .field-missing').forEach(el=>el.classList.remove('field-missing'));
  problems.forEach(p=>p.missing.forEach(m=>{
    const cell=document.querySelector(`.prep [data-pi="${CSS.escape(p.id)}"][data-pk="${m.k}"]`);
    if(cell) cell.classList.add('field-missing');
  }));
}
// Единая транзакционная отправка: backend повторно валидирует поля, создаёт цели,
// публикует инициативы на командных досках и отправляет привлечения.
async function prepSubmitToBoards(targets){
  targets=Array.isArray(targets)?targets:[targets];
  try{
    const id=currentCycleId(),backendId=cycleBackendIds[id];
    const result=await cycleMutation(id,`/pi-cycles/${backendId}/pre-pi/submit`,{
      method:'POST',body:{teams:targets.map(t=>({tribe:t.tribe,name:t.name}))},
    });
    const c=state.cycles[id];
    applyPrePi(c,result.pre_pi,id);
    applyGoals(c,result.goals,id);
    activateCycle(id);
    save();render();
    const parts=[];
    if(result.goals_added)parts.push(`целей: ${result.goals_added}`);
    if(result.board_added)parts.push(`стикеров на доску: ${result.board_added}`);
    if(result.attractions_added)parts.push(`на согласование: ${result.attractions_added}`);
    if(parts.length)toast(`Отправлено на доски — ${parts.join(', ')}`,{type:'success',title:'Отправлено на доски'});
    else toast('Новых данных для отправки нет — всё уже на досках',{type:'info'});
  }catch(error){
    if(reportOptimisticConflict(error))return;
    const serverProblems=error.detail&&Array.isArray(error.detail.problems)
      ? error.detail.problems.map(p=>({id:p.issue_key,missing:(p.missing||[]).map(m=>({k:m.key,label:m.label}))}))
      : [];
    if(serverProblems.length){
      highlightMissingFields(serverProblems);
      const lines=serverProblems.map(p=>`${p.id}: ${p.missing.map(m=>m.label).join(', ')}`).join('; ');
      toast(`Заполните обязательные поля — ${lines}`,{type:'warn',title:'Не все поля заполнены',duration:7000});
    }else{
      reportGoalsSyncError(error);
      toast(`Не удалось отправить данные на доски: ${error.message||error}`,{type:'warn'});
    }
  }
}
function openAttractionModal(rowId, ei){
  const row=findIssue(rowId); if(!row)return;
  ei=+ei||0;
  const host=row.executors && row.executors[ei]; if(!host) return;
  const sprintCount=+((prePiViews[currentCycleId()]||{}).cycle||{}).sprint_count||0;
  const targets=state.issues.filter(issue=>issue._backendId&&issue._backendId!==row._backendId);
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>Привлечение ресурса · ${esc(row.id)} <span class="muted" style="font-size:12px;font-weight:400">(исполнитель: ${esc(host.team)})</span></h3>
    <label><span>№ Issue (привлекаемая задача)</span><select id="am_id"><option value="">— выберите инициативу —</option>${targets.map(issue=>`<option value="${esc(issue._backendId)}">${esc(issue.id)} · ${esc(issue.name)}</option>`).join('')}</select></label>
    <label><span>Команда-исполнитель (подтягивается из JSW)</span><select id="am_team">${allTeamNames().map(n=>`<option>${esc(n)}</option>`).join('')}</select></label>
    <label><span>Спринт (кол-во из данных PI-цикла)</span><select id="am_sprint">
      <option value="">— не выбран —</option>
      ${Array.from({length:sprintCount},(_,index)=>`<option value="${index}">Спринт ${index+1}</option>`).join('')}
    </select></label>
    <div class="modal-actions">
      <button id="am_cancel">Отмена</button>
      <button class="primary" id="am_save">Добавить</button>
    </div>
  </div></div>`;
  $('#am_cancel').onclick=()=>root.innerHTML='';
  $('#am_save').onclick=()=>{
    const targetId=$('#am_id').value;if(!targetId)return;
    const ref=state.issues.find(issue=>issue._backendId===targetId);if(!ref)return;
    const team=$('#am_team').value,teamRow=state.pi.teams.find(value=>value.name===team);if(!teamRow)return;
    const sprVal=$('#am_sprint').value;
    const sprint = sprVal===''? null : (+sprVal);
    if(sprint===null){toast('Выберите спринт',{type:'warn'});return;}
    const executors=prePiExecutorPayload(row,rows=>rows[ei].attractions.push({
      target_initiative_id:ref._backendId,issue_key:ref.id,target_team_id:teamRow._teamId,
      team:teamRow.name,sprint_index:sprint,approval_status:'pending',sort_order:rows[ei].attractions.length,
    }));
    root.innerHTML='';
    runPrePiUiCommand(`/initiatives/${row._backendId}`,'PATCH',{executors},'Запрос на привлечение добавлен');
  };
}

