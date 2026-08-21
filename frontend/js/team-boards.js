/* =====================================================================
   ВКЛАДКА 4 — Командные доски
===================================================================== */
function viewTeams(){
  if(!state.ui.teamSel) return viewTeamSelect();
  const t=state.pi.teams.find(x=>x.name===state.ui.teamSel);
  if(!t){state.ui.teamSel=null;return viewTeamSelect();}
  if(state.ui.teamView==='capacity') return viewCapacity(t);
  return viewBoard(t);
}
async function runBoardCommand(path,method,body,successMessage){
  try{
    await teamBoardCommand(path,method,body);
    save(false);render();
    if(successMessage)toast(successMessage,{type:'success'});
    return true;
  }catch(error){
    reportTeamBoardsSyncError(error);
    return false;
  }
}
async function runCapacityCommand(path,method,body,successMessage){
  try{
    await capacityMemberCommand(path,method,body);
    save(false);render();
    if(successMessage)toast(successMessage,{type:'success'});
    return true;
  }catch(error){
    reportCapacitySyncError(error);
    return false;
  }
}
function viewTeamSelect(){
  const tribes=allTribes();
  const sel=state.ui.teamsTribe;
  let html=`<div class="card"><div class="flex-between"><h2>Командные доски ${cycleBadge()}</h2>
    <div class="hint">Трайбы и команды сформированы автоматически из «Данных PI-цикла». Нажмите на трайб, чтобы увидеть его команды, затем выберите команду.</div></div>`;
  html+=`<div class="tribe-list">`;
  tribes.forEach(tribe=>{
    const open=sel===tribe;
    html+=`<div class="tribe-acc">
      <div class="tribe-acc-head ${open?'open':''}" data-tribe="${esc(tribe)}">
        <span class="caret">${open?'▼':'▶'}</span>${esc(tribe)}
      </div>`;
    if(open){
      const teams=state.pi.teams.filter(t=>t.tribe===tribe);
      html+=`<div class="tribe-acc-body">`+
        (teams.length
          ? teams.map(t=>`<div class="team-item" data-open="${esc(t.name)}">${esc(t.name)}</div>`).join('')
          : `<div class="muted">В трайбе нет команд</div>`)+
        `</div>`;
    }
    html+=`</div>`;
  });
  html+=`</div></div>`;
  return html;
}
function teamToolbar(t,active){
  return `<div class="team-toolbar">
    <span class="team-title">${esc(t.name)}</span>
    <button class="${active==='board'?'primary':''}" id="tbBoard">Доска</button>
    ${active!=='capacity'?'<button id="tbCap">Изменить емкость</button>':''}
    <button class="ghost" id="tbBack">← К списку команд</button>
  </div>`;
}

/* ---- 4.x Доска команды ---- */
function boardSwitch(){
  const m = state.ui.boardLayout==='lanes' ? 'lanes' : (state.ui.boardLayout==='gantt' ? 'gantt' : 'columns');
  const w = boardWeekly();
  return `<div class="board-mode-row">
    <div class="board-switch">
      <button class="${m==='columns'?'active':''}" data-layout="columns">▦ Колонки</button>
      <button class="${m==='lanes'?'active':''}" data-layout="lanes">▤ Дорожки</button>
      <button class="${m==='gantt'?'active':''}" data-layout="gantt">▥ Гант</button>
    </div>
    ${m==='gantt'?'':`<div class="board-switch">
      <button class="${!w?'active':''}" data-week-mode="off">Спринты</button>
      <button class="${w?'active':''}" data-week-mode="on">Недели</button>
    </div>`}
    <span class="muted">${m==='gantt'
      ?'Календарь команды по дням: одна строка — один сотрудник, цветные полосы — назначенные подзадачи.'
      :'Представление доски: по спринтам или по задачам; детализация — целый спринт или две недели внутри каждого спринта.'}</span>
  </div>`;
}
/* ---- 4.x Трудозатраты по спринтам в разрезе ФИО (по кнопке, скрыто по умолчанию) ---- */
function effortByFioBlock(t){
  const on=!!state.ui.showEffortFio;
  let html=`<div class="row" style="margin-bottom:12px">
    <button class="effort-fio-btn${on?' primary':''}" id="tbEffortFio">${on?'Скрыть трудозатраты по ФИО':'Показать трудозатраты по ФИО'}</button>
    <span class="muted" style="margin-left:6px">Трудозатраты по каждому сотруднику в разрезе периодов доски — <b>факт / план</b> (дн.). Факт — сумма из белых подзадач; план — доступная ёмкость сотрудника (за вычетом отпусков, церемоний и рисков). Разница — остаток ресурса; красным выделен перегруз (факт &gt; план).</span>
  </div>`;
  if(!on) return html;
  const periods=boardPeriods();
  const key=teamKey(t.tribe,t.name);
  const roster=state.capacity[key]||[];
  // карта ФИО -> {role, per:[факт по периодам], total, plan:[план по периодам], planTotal, hasPlan}
  const map=new Map();
  const ensure=(fio,role)=>{
    const name=(fio||'').trim()||'— без ФИО —';
    if(!map.has(name)) map.set(name,{role:role||'',per:periods.map(()=>0),total:0,plan:periods.map(()=>0),planTotal:0,hasPlan:false});
    const rec=map.get(name);
    if(!rec.role && role) rec.role=role;
    return rec;
  };
  // сначала — сотрудники из ёмкости команды (чтобы видеть и тех, у кого пока нет задач)
  // и заодно посчитать план (доступную ёмкость) по каждому периоду
  roster.forEach(p=>{
    const rec=ensure(p.fio,p.role);
    rec.hasPlan=true;
    periods.forEach((period,idx)=>{ const av=personAvail(p,period); rec.plan[idx]+=av; rec.planTotal+=av; });
  });
  // затем — трудозатраты из белых подзадач
  state.issues.filter(i=>issuePrimaryTeam(i)===t.name && i.onBoard).forEach(i=>{
    (i.subtasks||[]).forEach(st=>{
      if(st.sprint===null || st.sprint===undefined) return;
      const rec=ensure(st.fio,st.role);
      const idx=periods.findIndex(p=>p.index===st.sprint && (p.week===null || itemWeek(st)===p.week));
      if(idx>=0){ rec.per[idx]+=(+st.cap||0); rec.total+=(+st.cap||0); }
    });
  });
  const rows=[...map.entries()].sort((a,b)=>a[0].localeCompare(b[0],'ru'));
  const colTotals=periods.map(()=>0); let grand=0;
  const colPlan=periods.map(()=>0); let grandPlan=0;
  rows.forEach(([,rec])=>{
    rec.per.forEach((v,idx)=>colTotals[idx]+=v); grand+=rec.total;
    rec.plan.forEach((v,idx)=>colPlan[idx]+=v); grandPlan+=rec.planTotal;
  });
  // ячейка: факт / план, план серым; красным — если факт превысил план (перегруз)
  const cell=(fact,plan,hasPlan,extra='')=>{
    const ex=extra?' '+extra:'';
    if(!hasPlan) return `<td class="${fact?'':'zero'}${ex}"><span class="ef-fact">${round1(fact)}</span></td>`;
    const rem=plan-fact, over=rem<-1e-9;
    return `<td class="ef-cell${over?' over':''}${ex}" title="Осталось: ${round1(rem)} дн.">`+
      `<span class="ef-fact">${round1(fact)}</span><span class="ef-plan">/ ${round1(plan)}</span></td>`;
  };
  html+=`<div class="board-scroll" style="padding:0"><table class="effort-fio ef-planned"><thead><tr>
    <th>ФИО</th><th>Роль</th>`+
    periods.map(p=>`<th>${p.title}${p.subtitle?`<br><span class="muted">${p.subtitle}</span>`:''}</th>`).join('')+
    `<th>Итого</th></tr></thead><tbody>`;
  if(!rows.length){
    html+=`<tr><td colspan="${periods.length+3}" class="muted">Нет данных о трудозатратах</td></tr>`;
  }
  rows.forEach(([fio,rec])=>{
    html+=`<tr><td>${esc(fio)}</td><td class="muted">${esc(rec.role)}</td>`+
      rec.per.map((v,idx)=>cell(v,rec.plan[idx],rec.hasPlan)).join('')+
      cell(rec.total,rec.planTotal,rec.hasPlan,'tot')+
      `</tr>`;
  });
  html+=`</tbody><tfoot><tr><td colspan="2">Итого по команде (факт / план)</td>`+
    colTotals.map((v,idx)=>cell(v,colPlan[idx],true)).join('')+
    cell(grand,grandPlan,true,'tot')+
    `</tr></tfoot></table></div>`;
  return html;
}
function viewBoard(t){
  if(state.ui.boardLayout==='lanes') return viewBoardLanes(t);
  if(state.ui.boardLayout==='gantt') return viewBoardGantt(t);
  const periods=boardPeriods();
  let html=`<div class="card">${teamToolbar(t,'board')}`;
  html+=boardSwitch();
  html+=effortByFioBlock(t);
  html+=`<div class="row" style="margin-bottom:10px">
    <span class="muted"><b>Стикеры можно свободно перемещать:</b> перетащите стикер в любое место колонки спринта — он встанет в позицию под курсором (порядок сохраняется). Белые подзадачи больше не сгруппированы по родителю — цветные и белые можно свободно смешивать и переставлять в любом порядке (родитель белого виден по цветной плашке с ID). Стрелки декомпозиции (белый → цветной) создаются автоматически и их можно <b>редактировать</b>: кликните по стрелке — на концах появятся точки <b>○</b>, перетащите их на нужные стикеры. Так можно задать порядок выполнения белых стикеров (например, SA1 → SA2). Чтобы <b>удалить</b> стрелку — кликните по ней и нажмите красный <b style="color:#ec8a98">×</b> в середине или клавишу <b>Delete</b>. Чтобы <b>создать связь</b> — на белом стикере нажмите <b style="color:var(--accent)">+ связь</b> и потяните на нужный стикер. <b>Клик по белому стикеру</b> — карточка подзадачи (ФИО/роль/ёмкость/спринт). Если стрелка мешает — <b>потяните её за линию</b> и оттяните в сторону; двойной клик по линии выпрямляет.${state.ui.selectedArrow?` <b style="color:var(--accent)">Стрелка выбрана — перетащите ○ или удалите ×/Delete.</b>`:''}</span>
  </div>`;
  html+=`<div class="board-scroll" id="boardScroll"><svg class="arrow-layer" id="arrowLayer"></svg><div class="board-grid">`;
  // бэклог
  const backlogItems=state.issues
    .filter(i=>issuePrimaryTeam(i)===t.name && i.onBoard && i.sprint===null)
    .map(i=>({ord:(i.ord??0), html:stickerHTML(i,true,true)}))
    .concat(ownerInfoIssues(t.name).filter(i=>i.sprint===null).map(i=>({ord:(i.ord??0), html:infoStickerHTML(i)})))
    .sort((a,b)=>a.ord-b.ord);
  html+=`<div class="backlog-col dropzone" data-tb-sprint="backlog"><div class="board-col-head backlog-head"><div class="sprint-head backlog-title"><div class="num">Бэклог</div><div class="dates">Незапланированные задачи</div></div><div class="backlog-summary" aria-hidden="true"></div></div><div class="backlog-body">`+
    backlogItems.map(o=>o.html).join('')+`</div></div>`;
  // спринты / недели
  periods.forEach(p=>{
    html+=`<div class="sprint-col${p.week===null?'':' week-col'}"><div class="board-col-head"><div class="sprint-head">${periodHeadHTML(p)}</div>`;
    // сводка ёмкости
    html+=`<div class="cap-summary"><table><tbody>`+teamComps(t.name).map(r=>{
      const plan=rolePlan(t,r,p);
      const rem=plan-consumedEffort(t,r,p.index,p.week);
      return `<tr><td>${r}</td><td>${round1(plan)}</td><td class="${rem<0?'neg':''}">${round1(rem)}</td></tr>`;
    }).join('')+`</tbody></table></div></div>`;
    // тело: все стикеры (цветные + белые) одним плоским списком, свободный порядок по ord
    html+=`<div class="sprint-body dropzone" data-tb-sprint="${p.index}"${periodWeekAttr(p)}>`;
    const teamIssues=state.issues.filter(i=>issuePrimaryTeam(i)===t.name && i.onBoard);
    const cell=[];
    teamIssues.forEach(i=>{
      if(itemInBoardPeriod(i,p)) cell.push({ord:(i.ord??0), html:stickerHTML(i,true,true)});
      (i.stories||[]).forEach(sy=>{
        if(itemInBoardPeriod(sy,p)) cell.push({ord:(sy.ord??0), html:storyHTML(i,sy)});
      });
      (i.subtasks||[]).forEach((st,si)=>{
        if(itemInBoardPeriod(st,p)) cell.push({ord:(st.ord??0), html:whiteHTML(i,st,si)});
      });
    });
    ownerInfoIssues(t.name).forEach(i=>{
      if(itemInBoardPeriod(i,p)) cell.push({ord:(i.ord??0), html:infoStickerHTML(i)});
    });
    cell.sort((a,b)=>a.ord-b.ord);
    html+=cell.map(o=>o.html).join('');
    html+=`</div></div>`;
  });
  html+=`</div></div>
  <div class="legend">
    <span><i style="background:var(--blue);border:1px solid var(--blue-b)"></i>Владелец = исполнитель</span>
    <span><i style="background:var(--purple);border:1px solid var(--purple-b)"></i>Привлечение (не согласовано)</span>
    <span><i style="background:var(--red);border:1px solid var(--red-b)"></i>Привлечение согласовано</span>
    <span><i style="background:#6f7684;border:1px solid #aeb5c0"></i>Информационный стикер владельца</span>
    <span><i style="background:var(--green-st);border:1px solid var(--green-st-b)"></i>Зелёный стикер — История (декомпозиция задачи)</span>
    <span><i style="background:var(--white-st)"></i>Белый стикер — подзадача (только здесь)</span>
    <span class="muted">Задачу можно декомпозировать сразу на белые или на Истории, а Историю — на белые. Истории и белые остаются только здесь, на Program Board не выносятся. Наведите на задачу — подсветятся все её стикеры; на Историю — только её ветка. Сводка: роль · план · остаток. Клик по стикеру — карточка.</span>
  </div></div>`;
  return html;
}
/* ---- 4.x Доска команды: представление «Дорожки» (строка = задача) ---- */
function viewBoardLanes(t){
  const periods=boardPeriods();
  const issues=state.issues.filter(i=>issuePrimaryTeam(i)===t.name && i.onBoard);
  const infoIssues=ownerInfoIssues(t.name);
  let html=`<div class="card">${teamToolbar(t,'board')}`;
  html+=boardSwitch();
  html+=effortByFioBlock(t);
  html+=`<div class="row" style="margin-bottom:10px">
    <span class="muted">Каждая задача — отдельная строка. Цветной стикер и его белые подзадачи лежат в ячейках своей строки, стрелки не выходят за строку. Подзадачи можно перетаскивать между спринтами <b>в пределах своей строки</b>. Удалить стрелку: кликните по ней и нажмите <b style="color:#ec8a98">×</b> или <b>Delete</b>. Создать связь: на белом стикере нажмите <b style="color:var(--accent)">+ связь</b> и потяните на цель. Клик по белому стикеру — карточка подзадачи. Стрелку можно оттянуть в сторону — потяните за линию; двойной клик выпрямляет.${state.ui.selectedArrow?` <b style="color:var(--accent)">Стрелка выбрана — перетащите ○ или удалите ×/Delete.</b>`:''}</span>
  </div>`;
  html+=`<div class="board-scroll" id="boardScroll"><svg class="arrow-layer" id="arrowLayer"></svg>`;
  html+=`<table class="lanes"><thead><tr><th class="lane-id-head">Задача</th>`;
  html+=`<th class="lane-sp-head"><div class="num">Бэклог</div></th>`;
  periods.forEach(p=>{
    const capHtml=`<div class="cap-mini">`+teamComps(t.name).map(r=>{
        const plan=rolePlan(t,r,p); const rem=plan-consumedEffort(t,r,p.index,p.week);
        return `<span>${r}: ${round1(plan)} / <b class="${rem<0?'neg':''}">${round1(rem)}</b></span>`;
      }).join('')+`</div>`;
    html+=`<th class="lane-sp-head">${periodHeadHTML(p,{capHtml})}</th>`;
  });
  html+=`</tr></thead><tbody>`;
  if(!issues.length && !infoIssues.length){
    html+=`<tr><td class="lane-id"><span class="muted">Нет задач на доске</span></td>
      <td class="lane-cell" data-tb-sprint="backlog"></td>`+
      periods.map(p=>`<td class="lane-cell" data-tb-sprint="${p.index}"${periodWeekAttr(p)}></td>`).join('')+`</tr>`;
  }
  issues.forEach(i=>{
    const hue=issueHue(i);
    html+=`<tr><td class="lane-id" style="--lane:${hue};border-left:3px solid ${hue}">
      <div class="lane-id-top"><span class="lane-dot" style="--lane:${hue}"></span><b>${esc(i.id)}</b></div>
      ${i.name?`<div class="lane-id-name">${esc(i.name)}</div>`:''}
      <div class="lane-id-status">${COLOR_RU[issueColor(i)]}</div></td>`;
    // ячейка бэклога
    html+=`<td class="lane-cell" data-tb-sprint="backlog" data-tb-issue="${esc(i.id)}">`+
      (i.sprint===null?stickerHTML(i,true,true):'')+`</td>`;
    // ячейки спринтов / недель
    periods.forEach(p=>{
      html+=`<td class="lane-cell" data-tb-sprint="${p.index}"${periodWeekAttr(p)} data-tb-issue="${esc(i.id)}">`;
      if(itemInBoardPeriod(i,p)) html+=stickerHTML(i,true,true);
      (i.stories||[]).forEach(sy=>{ if(itemInBoardPeriod(sy,p)) html+=storyHTML(i,sy); });
      (i.subtasks||[]).forEach((st,si)=>{ if(itemInBoardPeriod(st,p)) html+=whiteHTML(i,st,si); });
      html+=`</td>`;
    });
    html+=`</tr>`;
  });
  infoIssues.forEach(i=>{
    const hue=issueHue(i);
    html+=`<tr><td class="lane-id" style="--lane:${hue};border-left:3px solid #aeb5c0">
      <div class="lane-id-top"><span class="lane-dot" style="--lane:${hue}"></span><b>${esc(i.id)}</b></div>
      ${i.name?`<div class="lane-id-name">${esc(i.name)}</div>`:''}
      <div class="lane-id-status">Информационный${i.agreed?` · ${esc(approvalLabel(i))}`:''}</div></td>`;
    html+=`<td class="lane-cell" data-tb-sprint="backlog" data-tb-issue="${esc(i.id)}">`+
      (i.sprint===null?infoStickerHTML(i):'')+`</td>`;
    periods.forEach(p=>{
      html+=`<td class="lane-cell" data-tb-sprint="${p.index}"${periodWeekAttr(p)} data-tb-issue="${esc(i.id)}">`;
      if(itemInBoardPeriod(i,p)) html+=infoStickerHTML(i);
      html+=`</td>`;
    });
    html+=`</tr>`;
  });
  html+=`</tbody></table></div>
  <div class="legend">
    <span><i style="background:var(--blue);border:1px solid var(--blue-b)"></i>Владелец = исполнитель</span>
    <span><i style="background:var(--purple);border:1px solid var(--purple-b)"></i>Привлечение (не согласовано)</span>
    <span><i style="background:var(--red);border:1px solid var(--red-b)"></i>Привлечение согласовано</span>
    <span><i style="background:#6f7684;border:1px solid #aeb5c0"></i>Информационный стикер владельца</span>
    <span><i style="background:var(--green-st);border:1px solid var(--green-st-b)"></i>Зелёный стикер — История</span>
    <span><i style="background:var(--white-st)"></i>Белый стикер — подзадача</span>
    <span class="muted">Цветная точка / рамка = цвет конкретной задачи. Истории и белые лежат в строке своей задачи. В шапке спринта: роль · план / остаток.</span>
  </div></div>`;
  return html;
}
/* ---- 4.x Доска команды: дневной Гант (строка = сотрудник, шкала = весь PI) ---- */
function ganttCalendarDays(){
  const out=[];
  computeSprints().forEach(sprint=>{
    for(let offset=0;offset<SPRINT_DAYS;offset++){
      const date=addDays(sprint.start,offset);
      out.push({date,sprint:sprint.index,week:offset<7?0:1});
    }
  });
  return out;
}
function ganttIsoDate(date){
  return `${date.getFullYear()}-${pad2(date.getMonth()+1)}-${pad2(date.getDate())}`;
}
// События ПИР/Регресс на сетке дней: проекция диапазонов в grid-column (1-индексация как у задач)
function ganttEventSegments(days,events,type){
  const out=[];
  if(!days||!days.length||!Array.isArray(events))return out;
  events.forEach(ev=>{
    if(!ev||!ev.date)return;
    let first=-1,last=-1;
    for(let i=0;i<days.length;i++){
      if(eventOverlaps(ev,days[i].date,days[i].date)){ if(first<0)first=i; last=i; }
    }
    if(first<0)return;
    out.push({start:first+1,end:last+2,ev,type});
  });
  return out;
}
// Жадная раскладка пересекающихся событий по дорожкам, чтобы они не накладывались
function ganttEventRows(segments){
  const rows=[]; // каждая строка: массив сегментов (непересекающихся по [start,end))
  const overlap=(a,b)=>a.end>b.start && b.end>a.start;
  segments.forEach(seg=>{
    let placed=false;
    for(const row of rows){
      if(!row.some(s=>overlap(seg,s))){ row.push(seg); placed=true; break; }
    }
    if(!placed)rows.push([seg]);
  });
  return rows;
}
function ganttEventMeta(type){
  return type==='regression'
    ? {label:'Регресс',title:'Регрессионное тестирование'}
    : {label:'ПИР',title:'ПИР'};
}
function ganttDayAvailability(person,date){
  const inRanges=field=>parseDateRanges(person&&person[field]).some(r=>date>=r.start&&date<=r.end);
  const weekend=date.getDay()===0||date.getDay()===6;
  const vacation=inRanges('vacation');
  const unavailable=inRanges('extraUnavailable');
  const reasons=[];
  if(weekend)reasons.push('Выходной');
  if(vacation)reasons.push('Отпуск');
  if(unavailable)reasons.push('Недоступен');
  return {weekend,vacation,unavailable,reasons};
}
function ganttMonthSegments(days){
  const out=[];
  days.forEach((day,index)=>{
    const key=`${day.date.getFullYear()}-${day.date.getMonth()}`;
    const last=out[out.length-1];
    if(last&&last.key===key)last.end=index;
    else out.push({key,start:index,end:index,label:`${MON_RU[day.date.getMonth()+1]} ${day.date.getFullYear()}`});
  });
  return out;
}
function ganttDayCapacity(person,date){
  const status=ganttDayAvailability(person,date);
  if(status.weekend||status.vacation||status.unavailable)return 0;
  if(!person)return 1;
  const rate=Math.max(0,Number.isFinite(+person.rate)?+person.rate:1);
  const focus=Math.max(0,1-(+person.ceremonyPct||0)/100-(+person.riskPct||0)/100);
  const efficiency=String(person.efficiency??'').trim()===''?1:Math.max(0,+person.efficiency||0);
  return rate*focus*efficiency;
}
function ganttFallbackStartIso(task,days){
  if(task.startDate)return task.startDate;
  const sprint=+task.sprint;
  const explicitWeek=task.week===0||task.week===1||task.week==='0'||task.week==='1';
  const match=days.find(day=>day.sprint===sprint&&(!explicitWeek||day.week===+task.week));
  return match?ganttIsoDate(match.date):'';
}
function ganttScheduleFrom(startIso,effort,person,days){
  if(!days.length)return null;
  let startIndex=days.findIndex(day=>ganttIsoDate(day.date)>=startIso);
  if(startIndex<0)return null;
  while(startIndex<days.length&&ganttDayCapacity(person,days[startIndex].date)<=1e-9)startIndex++;
  if(startIndex>=days.length)return null;
  let remaining=Math.max(0,+effort||0),endIndex=startIndex;
  if(remaining>1e-9){
    for(let index=startIndex;index<days.length;index++){
      const capacity=ganttDayCapacity(person,days[index].date);
      if(capacity<=1e-9)continue;
      remaining-=capacity;endIndex=index;
      if(remaining<=1e-9)break;
    }
  }
  const first=days[startIndex],last=days[endIndex];
  return {
    start:startIndex+1,end:endIndex+2,
    startDate:ganttIsoDate(first.date),endDate:ganttIsoDate(last.date),
    sprint:first.sprint,week:first.week,complete:remaining<=1e-9,
  };
}
function ganttTaskSchedule(task,person,days){
  return ganttScheduleFrom(ganttFallbackStartIso(task,days),task.cap,person,days);
}
function ganttPeriodStartIso(sprintIndex,weekIndex=0){
  if(!Number.isInteger(+sprintIndex)||sprintIndex===null||sprintIndex==='')return '';
  const sprint=computeSprints().find(row=>row.index===+sprintIndex);
  return sprint?ganttIsoDate(addDays(sprint.start,(+weekIndex||0)*7)):'';
}
function ganttPersonForTask(roster,task){
  return roster.find(p=>task._assigneeMemberId&&p._backendId===task._assigneeMemberId)||
    roster.find(p=>String(p.fio||'').trim()===String(task.fio||'').trim()&&(!task.role||p.role===task.role))||null;
}
function ganttScheduleLabel(schedule){
  if(!schedule)return 'Не удалось рассчитать даты';
  const start=fmt(parseISO(schedule.startDate)),end=fmt(parseISO(schedule.endDate));
  return `Начало ${start} · окончание ${end}${schedule.complete?'':' · не помещается в PI'}`;
}
function viewBoardGantt(t){
  const days=ganttCalendarDays();
  const sprints=computeSprints().map(s=>({...s,week:null}));
  const key=teamKey(t.tribe,t.name);
  const roster=state.capacity[key]||[];
  const teamIssues=state.issues.filter(i=>issuePrimaryTeam(i)===t.name && i.onBoard);
  // карта участника команды -> доступность и все назначенные ему подзадачи
  const map=new Map();
  const ensure=(memberId,fio,role)=>{
    const name=(fio||'').trim()||'— без ФИО —';
    const mapKey=memberId?`member:${memberId}`:`name:${name}|${role||''}`;
    if(!map.has(mapKey)) map.set(mapKey,{fio:name,role:role||'',people:[],tasks:[],plan:0});
    const rec=map.get(mapKey);
    if(!rec.role && role) rec.role=role;
    return rec;
  };
  // сотрудники из ёмкости видны даже при отсутствии задач
  roster.forEach(p=>{
    const rec=ensure(p._backendId||p.uid,p.fio,p.role);
    rec.people.push(p);
    rec.plan+=sprints.reduce((sum,sprint)=>sum+personAvail(p,sprint),0);
  });
  // Длина полосы определяется трудоёмкостью и реальной дневной доступностью сотрудника.
  teamIssues.forEach(iss=>{
    const hue=issueHue(iss);
    (iss.subtasks||[]).forEach((st,si)=>{
      if(st.sprint===null || st.sprint===undefined) return;
      const person=ganttPersonForTask(roster,st);
      const schedule=ganttTaskSchedule(st,person,days);if(!schedule)return;
      const rec=ensure(person&&(person._backendId||person.uid),person?person.fio:st.fio,person?person.role:st.role);
      rec.tasks.push({iss,st,si,cap:(+st.cap||0),hue,...schedule});
    });
  });
  map.forEach(rec=>rec.tasks.sort((a,b)=>a.start-b.start||a.end-b.end||String(a.iss.id).localeCompare(String(b.iss.id),'ru')));
  const rows=[...map.values()].sort((a,b)=>a.fio.localeCompare(b.fio,'ru')||a.role.localeCompare(b.role,'ru'));
  const dayWidth=34;
  const timelineWidth=Math.max(days.length*dayWidth,dayWidth);
  const today=ganttIsoDate(new Date());
  const weekNames=['вс','пн','вт','ср','чт','пт','сб'];
  const monthSegments=ganttMonthSegments(days);
  // события ПИР/Регресс на сетке дней
  const eventSegments=[
    ...ganttEventSegments(days,state.pi.pirs||[],'pir'),
    ...ganttEventSegments(days,state.pi.regressions||[],'regression'),
  ].sort((a,b)=>a.start-b.start||a.end-b.end);
  const eventRows=ganttEventRows(eventSegments);
  const pirEventCount=eventSegments.filter(seg=>seg.type==='pir').length;
  const regressionEventCount=eventSegments.filter(seg=>seg.type==='regression').length;

  let html=`<div class="card">${teamToolbar(t,'board')}`;
  html+=boardSwitch();
  html+=`<div class="gantt-summary">
    <span><i class="gantt-legend-day weekend"></i>Выходной</span>
    <span><i class="gantt-legend-day vacation"></i>Отпуск</span>
    <span><i class="gantt-legend-day unavailable"></i>Недоступен</span>
    <span><i class="gantt-legend-event"></i>ПИР</span>
    <span><i class="gantt-legend-event reg"></i>Регресс</span>
    <span class="muted">Начало задаётся точной датой. Окончание рассчитывается по трудоёмкости, ставке, КПД и доступным рабочим дням сотрудника.</span>
  </div>`;
  html+=`<div class="board-scroll gantt-scroll" id="boardScroll"><div class="gantt-calendar" style="--gantt-days:${days.length};--gantt-width:${timelineWidth}px">
    <div class="gantt-calendar-head">
      <div class="gantt-person-head"><b>Сотрудник</b><span>ФИО · должность</span></div>
      <div class="gantt-head-timeline" style="width:${timelineWidth}px">
        <div class="gantt-months">${monthSegments.map(m=>`<div style="grid-column:${m.start+1}/${m.end+2}">${esc(m.label)}</div>`).join('')}</div>
        <div class="gantt-day-heads">${days.map(day=>{
          const iso=ganttIsoDate(day.date),weekend=day.date.getDay()===0||day.date.getDay()===6;
          const cls=[weekend?'weekend':'',iso===today?'today':'',day.date.getDate()===1?'month-start':'',day.date.getDay()===1?'week-start':''].filter(Boolean).join(' ');
          return `<div class="${cls}" title="${fmt(day.date)} · Спринт ${day.sprint+1}, неделя ${day.week+1}"><b>${day.date.getDate()}</b><span>${weekNames[day.date.getDay()]}</span></div>`;
        }).join('')}</div>
      </div>
    </div>`;
  if(eventRows.length){
    const eventRowHeight=32;
    const eventsTimelineHeight=eventRows.length*eventRowHeight+16;
    html+=`<div class="gantt-events">
      <div class="gantt-events-head">
        <b>События PI</b>
        <span>ПИРы и регрессионное тестирование</span>
        <div class="gantt-event-totals">
          <i><em class="pir-dot"></em>ПИР: ${pirEventCount}</i>
          <i class="reg"><em></em>Регресс: ${regressionEventCount}</i>
        </div>
      </div>
      <div class="gantt-events-timeline" style="width:${timelineWidth}px;--event-rows:${eventRows.length};min-height:${eventsTimelineHeight}px">
        <div class="gantt-event-grid" aria-hidden="true">${days.map(day=>{
          const iso=ganttIsoDate(day.date),weekend=day.date.getDay()===0||day.date.getDay()===6;
          const cls=[weekend?'weekend':'',iso===today?'today':'',day.date.getDate()===1?'month-start':'',day.date.getDay()===1?'week-start':''].filter(Boolean).join(' ');
          return `<div class="${cls}"></div>`;
        }).join('')}</div>
        ${eventRows.map((row,rn)=>row.map(seg=>{
          const isReg=seg.type==='regression';
          const meta=ganttEventMeta(seg.type);
          const range=eventRangeText(seg.ev);
          const name=String(seg.ev.name||'').trim();
          const title=`${meta.title}${name?' · '+esc(name):''}${range?' · '+range:''}`;
          const single=seg.end-seg.start<=1;
          return `<div class="gantt-event${isReg?' reg':''}${single?' single':''}" title="${title}" style="grid-column:${seg.start}/${seg.end};grid-row:${rn+1}">
            <strong>${meta.label}</strong>
            <span>${esc(name||meta.title)}</span>
            ${range?`<i>${range}</i>`:''}
          </div>`;
        }).join('')).join('')}
      </div>
    </div>`;
  }
  if(!rows.length){
    html+=`<div class="gantt-empty">Нет данных о сотрудниках. Добавьте состав команды в разделе «Изменить ёмкость».</div>`;
  }
  rows.forEach(rec=>{
    const fio=rec.fio;
    const fact=rec.tasks.reduce((sum,task)=>sum+task.cap,0);
    const over=fact-rec.plan>1e-9;
    const rowHeight=Math.max(54,rec.tasks.length*30+18);
    const primaryPerson=rec.people[0]||null;
    html+=`<div class="gantt-person-row" style="--gantt-row-height:${rowHeight}px">
      <div class="gantt-person-cell">
        <b title="${esc(fio)}">${esc(fio)}</b>
        <span>${esc(rec.role||'Должность не указана')}</span>
        <small class="${over?'over':''}" title="Назначено / доступно за PI">${round1(fact)} / ${round1(rec.plan)} дн.${over?' · перегруз':''}</small>
      </div>
      <div class="gantt-timeline-row" style="width:${timelineWidth}px" data-tb-sprint="0" data-tb-week="0" data-tb-fio="${esc(fio)}" data-gantt-days="${days.length}">
        <div class="gantt-day-backgrounds">${days.map(day=>{
          const status=ganttDayAvailability(primaryPerson,day.date);
          const iso=ganttIsoDate(day.date);
          const cls=[status.weekend?'weekend':'',status.vacation?'vacation':'',status.unavailable?'unavailable':'',iso===today?'today':'',day.date.getDate()===1?'month-start':'',day.date.getDay()===1?'week-start':''].filter(Boolean).join(' ');
          const dayCapacity=ganttDayCapacity(primaryPerson,day.date);
          const title=[fmt(day.date),...status.reasons,`Доступно: ${round1(dayCapacity)} дн.`,`Спринт ${day.sprint+1}, неделя ${day.week+1}`].join(' · ');
          return `<div class="gantt-day-bg ${cls}" data-gantt-day data-gantt-date="${iso}" data-gantt-sprint="${day.sprint}" data-gantt-week="${day.week}" title="${esc(title)}"></div>`;
        }).join('')}</div>
        <div class="gantt-task-layer">${rec.tasks.map((task,index)=>whiteGanttHTML(task.iss,task.st,task.si,task,index+1)).join('')}</div>
      </div>
    </div>`;
  });
  html+=`</div></div></div>`;
  return html;
}
function whiteGanttHTML(iss,st,si,schedule,row){
  const hue=issueHue(iss);
  const sy=st.storyUid?storyById(iss,st.storyUid):null;
  const parentLabel = sy ? (sy.id||'История') : iss.id;
  const range=`${fmt(parseISO(schedule.startDate))}–${fmt(parseISO(schedule.endDate))}`;
  const span=schedule.end-schedule.start;
  const detail=span>=8?`${range} · ${round1(st.cap)} чел.-дн.`:(span>=4?`${round1(st.cap)} чел.-дн.`:'');
  return `<div class="white gantt-task${schedule.complete?'':' incomplete'}" draggable="true" data-drag="sub" data-id="${esc(iss.id)}" data-sub="${si}"
    data-wissue="${esc(iss.id)}" data-wsub="${si}" data-wuid="${esc(st.uid)}" data-story="${esc(st.storyUid||'')}"
    title="${esc(parentLabel)} · ${esc(st.role)} · ${round1(st.cap)} дн. · ${range}"
    style="--lane:${hue};--task-color:${hue};grid-column:${schedule.start}/${schedule.end};grid-row:${row}">
    <b>${esc(parentLabel)}</b>${detail?`<span>${detail}</span>`:''}
  </div>`;
}
function whiteHTML(iss,st,si){
  const hue=issueHue(iss);
  // родитель белого: История (её ID) — если storyUid задан, иначе сама задача (её ID)
  const sy=st.storyUid?storyById(iss,st.storyUid):null;
  const parentLabel = sy ? (sy.id||'История') : iss.id;
  return `<div class="white" draggable="true" data-drag="sub" data-id="${esc(iss.id)}" data-sub="${si}"
    data-wissue="${esc(iss.id)}" data-wsub="${si}" data-wuid="${esc(st.uid)}" data-story="${esc(st.storyUid||'')}"
    style="--lane:${hue};border-left-color:${hue}">
    <span class="x" data-delsub-i="${esc(iss.id)}" data-delsub-s="${si}">✕</span>
    <div class="wparent">${esc(parentLabel)}</div>
    <div class="wrole">${esc(st.role)} · ${st.cap}</div>
    <div>${esc(st.fio)}</div>
    <span class="w-link" data-link-kind="w" data-link-key="${esc(st.uid)}" draggable="false" title="Добавить связь: зажмите и потяните на нужный стикер">+ связь</span>
  </div>`;
}
function viewCapacity(t){
  const key=teamKey(t.tribe,t.name);
  const rows=state.capacity[key]||[];
  let html=`<div class="card">${teamToolbar(t,'capacity')}<h3>Емкость команды</h3>
    <div class="board-scroll" style="padding:0"><table><thead><tr><th>ФИО</th><th>Роль</th><th>Ставка</th><th>Плановая</th><th>Отпуск</th><th>Доп. дни недоступен</th><th>Agile-церемонии (%)</th><th>Риски (%)</th><th>КПД</th><th>Доступная</th><th></th></tr></thead><tbody>`;
  if(!rows.length) html+=`<tr><td colspan="11" class="muted">Нет сотрудников</td></tr>`;
  rows.forEach((p,i)=>{
    const avail=personCapacityTotal(p,'available');
    const vacLabel=formatVacShort(p.vacation);
    const extraLabel=formatVacShort(p.extraUnavailable);
    const planned=personCapacityTotal(p,'calendar');
    const memberRoles=teamComps(t.name).slice();
    if(p.role&&!memberRoles.includes(p.role))memberRoles.unshift(p.role);
    html+=`<tr>
      <td><input data-ci="${i}" data-ck="fio" value="${esc(p.fio)}"></td>
      <td><select data-ci="${i}" data-ck="role">${memberRoles.map(r=>`<option ${p.role===r?'selected':''}>${r}</option>`).join('')}</select></td>
      <td><input type="number" min="0" max="1" step="0.05" style="width:70px" data-ci="${i}" data-ck="rate" value="${esc(p.rate??1)}"></td>
      <td class="auto">${planned===null?'—':round1(planned)+' дн.'} <span style="font-size:10px">(сервер: раб. дни PI × ставка)</span></td>
      <td><button class="vac-chip${vacLabel?'':' empty'}" data-vacedit="${i}">
        <span class="vac-cal">📅</span>${vacLabel||'Указать даты'}
      </button></td>
      <td><button class="vac-chip${extraLabel?'':' empty'}" data-unavailedit="${i}">
        <span class="vac-cal">📅</span>${extraLabel||'Указать даты'}
      </button></td>
      <td><input type="number" min="0" max="100" style="width:70px" data-ci="${i}" data-ck="ceremonyPct" value="${esc(p.ceremonyPct)}"></td>
      <td><input type="number" min="0" max="100" style="width:70px" data-ci="${i}" data-ck="riskPct" value="${esc(p.riskPct)}"></td>
      <td><input type="number" min="0" max="1" step="0.05" style="width:70px" data-ci="${i}" data-ck="efficiency" value="${esc(p.efficiency??'')}" placeholder="1"></td>
      <td class="auto">${avail===null?'—':round1(avail)+' дн.'}</td>
      <td><button class="icon danger sm" data-delcap="${i}">✕</button></td>
    </tr>`;
  });
  html+=`</tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="plus" id="addCap">+</button></div>
    <div class="note" style="margin-top:14px">Плановая = рабочие дни PI × ставка. Доступная = Плановая − дни отпуска − доп. дни недоступности − Плановая × % церемоний − Плановая × % рисков. Если КПД заполнен, доступная дополнительно умножается на коэффициент КПД. План роли в спринте на доске = сумма «Доступной» сотрудников этой роли.</div>
    <div class="row" style="margin-top:16px"><button id="tbBack2">Вернуться на командную доску</button></div>
  </div>`;
  return html;
}
function openCapacityMemberModal(t){
  const roles=teamComps(t.name);
  if(!roles.length){
    toast('У команды не настроены компетенции в активном PI-цикле',{type:'warn'});
    return;
  }
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>Новый сотрудник · ${esc(t.name)}</h3>
    <label><span>ФИО</span><input id="cm_fio" maxlength="220" autocomplete="off" autofocus></label>
    <label><span>Роль</span><select id="cm_role">${roles.map(role=>`<option>${esc(role)}</option>`).join('')}</select></label>
    <label><span>Ставка</span><input id="cm_rate" type="number" min="0" max="1" step="0.05" value="1"></label>
    <div class="vac-err" id="cm_err"></div>
    <div class="modal-actions">
      <button id="cm_cancel">Отмена</button>
      <button class="primary" id="cm_save">Добавить</button>
    </div>
  </div></div>`;
  $('#cm_cancel').onclick=()=>root.innerHTML='';
  $('#cm_save').onclick=async()=>{
    const fullName=$('#cm_fio').value.trim();
    const rate=Number($('#cm_rate').value);
    if(!fullName){ $('#cm_err').textContent='Укажите ФИО сотрудника.'; return; }
    if(!Number.isFinite(rate)||rate<0||rate>1){ $('#cm_err').textContent='Ставка должна быть от 0 до 1.'; return; }
    const created=await runCapacityCommand('/members','POST',{
      tribe:t.tribe,team:t.name,client_uid:uid(),full_name:fullName,competency:$('#cm_role').value,
      rate,vacation_ranges:[],extra_unavailable_ranges:[],ceremony_percent:0,
      risk_percent:0,efficiency:null,sort_order:(state.capacity[teamKey(t.tribe,t.name)]||[]).length,
    });
    if(created)root.innerHTML='';
  };
  $('#cm_fio').focus();
}
// Модальное окно выбора одного или нескольких периодов дат.
function openDateRangesModal(t,i,opts){
  const key=teamKey(t.tribe,t.name);
  const person=(state.capacity[key]||[])[i]; if(!person)return;
  const field=opts.field;
  let draft=rangesToIso(person[field]);
  if(!draft.length) draft=[{start:'',end:''}];
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${esc(opts.title)} · ${esc(person.fio||'сотрудник')}</h3>
    <div class="vac-range-list" id="vm_ranges"></div>
    <button id="vm_add_range">Добавить период</button>
    <div class="vac-err" id="vm_err"></div>
    <div class="modal-actions">
      <button id="vm_clear">Очистить</button>
      <button id="vm_cancel">Отмена</button>
      <button class="primary" id="vm_save">Применить</button>
    </div>
  </div></div>`;
  const close=()=>root.innerHTML='';
  const renderRanges=()=>{
    $('#vm_ranges').innerHTML=draft.map((r,idx)=>`<div class="vac-range-row">
      <label><span>Начало</span><input type="date" data-vm-idx="${idx}" data-vm-k="start" value="${esc(r.start)}"></label>
      <label><span>Конец</span><input type="date" data-vm-idx="${idx}" data-vm-k="end" value="${esc(r.end)}"></label>
      <button class="icon danger sm" data-vm-del="${idx}" title="Удалить период">✕</button>
    </div>`).join('');
    document.querySelectorAll('[data-vm-idx]').forEach(el=>el.onchange=()=>{
      draft[+el.dataset.vmIdx][el.dataset.vmK]=el.value;
    });
    document.querySelectorAll('[data-vm-del]').forEach(btn=>btn.onclick=()=>{
      draft.splice(+btn.dataset.vmDel,1);
      if(!draft.length) draft=[{start:'',end:''}];
      renderRanges();
    });
  };
  renderRanges();
  $('#vm_cancel').onclick=close;
  $('#vm_add_range').onclick=()=>{ draft.push({start:'',end:''}); renderRanges(); };
  $('#vm_clear').onclick=async()=>{
    if(!person._backendId)return;
    const apiField=field==='vacation'?'vacation_ranges':'extra_unavailable_ranges';
    if(await runCapacityCommand(`/members/${person._backendId}`,'PATCH',{[apiField]:[]})){
      close();
      toast(`${opts.title} очищен`,{type:'info'});
    }
  };
  $('#vm_save').onclick=async()=>{
    const out=[];
    for(const r of draft){
      if(!r.start && !r.end) continue;
      if(!r.start){ $('#vm_err').textContent='Укажите дату начала периода.'; return; }
      const end=r.end||r.start;
      if(end<r.start){ $('#vm_err').textContent='Дата конца не может быть раньше начала.'; return; }
      out.push(datesToVac(r.start,end));
    }
    if(!person._backendId)return;
    const apiField=field==='vacation'?'vacation_ranges':'extra_unavailable_ranges';
    const ranges=draft.filter(r=>r.start).map(r=>({start:r.start,end:r.end||r.start}));
    if(await runCapacityCommand(`/members/${person._backendId}`,'PATCH',{[apiField]:ranges})){
      close();
      toast(`${opts.title}: ${formatRangesShort(out.join('; '))||'не указан'}`,{type:'success',title:`${opts.title} сохранён`});
    }
  };
}
function openVacationModal(t,i){
  openDateRangesModal(t,i,{field:'vacation',title:'Отпуск'});
}
function openExtraUnavailableModal(t,i){
  openDateRangesModal(t,i,{field:'extraUnavailable',title:'Доп. дни недоступен'});
}
/* ---- Свободное размещение стикеров в колонках (drop по позиции) ---- */
// id цветного стикера, перед которым нужно вставить (по вертикали курсора), либо null (в конец).
// Ключ стикера (цветного/белого) под курсором, ПЕРЕД которым вставлять, либо null (в конец).
// Формат ключа: 'i:'+id (цветной) | 'g:'+uid (История) | 's:'+uid (белый).
function stickerBeforeKey(zone,clientY){
  const kids=[...zone.querySelectorAll(':scope > .sticker[data-drag="issue"], :scope > .story[data-story-uid], :scope > .white[data-wuid]')];
  for(const el of kids){
    const r=el.getBoundingClientRect();
    if(clientY < r.top + r.height/2){
      if(el.classList.contains('white')) return 's:'+el.dataset.wuid;
      if(el.classList.contains('story')) return 'g:'+el.dataset.storyUid;
      return 'i:'+el.dataset.id;
    }
  }
  return null;
}
// Плоский список стикеров колонки (цветные + Истории + белые), отсортированный по ord.
// sprintVal — индекс спринта или null (бэклог); weekVal — null для обычного режима или 0/1 для недель.
function boardColumnItems(teamName,sprintVal,weekVal=null){
  const out=[];
  const inPlace=item=>item && item.sprint===sprintVal && (weekVal===null || itemWeek(item)===weekVal);
  state.issues.filter(i=>issuePrimaryTeam(i)===teamName && i.onBoard).forEach(i=>{
    if(inPlace(i)) out.push({key:'i:'+i.id, ord:(i.ord??0), set:v=>{i.ord=v;}});
    (i.stories||[]).forEach(sy=>{
      if(inPlace(sy)) out.push({key:'g:'+sy.uid, ord:(sy.ord??0), set:v=>{sy.ord=v;}});
    });
    (i.subtasks||[]).forEach(st=>{
      if(inPlace(st)) out.push({key:'s:'+st.uid, ord:(st.ord??0), set:v=>{st.ord=v;}});
    });
  });
  out.sort((a,b)=>a.ord-b.ord);
  return out;
}
// Свободная перестановка любого стикера внутри колонки: перед beforeKey, либо в конец.
// dragKey/beforeKey — ключи 'i:'+id / 's:'+uid. Проставляет сквозной ord 0..n по колонке.
function reorderBoardItem(teamName,sprintVal,weekVal,dragKey,beforeKey){
  if(beforeKey===dragKey) return; // отпустили перед самим собой — без изменений
  const items=boardColumnItems(teamName,sprintVal,weekVal); // dragKey уже в колонке (sprint/week выставлены ранее)
  const di=items.findIndex(o=>o.key===dragKey); if(di<0) return;
  const [d]=items.splice(di,1);
  const bi = beforeKey ? items.findIndex(o=>o.key===beforeKey) : -1;
  if(bi>=0) items.splice(bi,0,d); else items.push(d);
  items.forEach((o,idx)=>o.set(idx));
}
function boardPeriodAfter(sprint,week,parentSprint,parentWeek){
  if(sprint===null||sprint===undefined||parentSprint===null||parentSprint===undefined)return false;
  if(+sprint!==+parentSprint)return +sprint>+parentSprint;
  if(week===null||week===undefined||parentWeek===null||parentWeek===undefined)return false;
  return +week>+parentWeek;
}
function decompositionAfterIssue(iss,sprint,week){
  return boardPeriodAfter(sprint,week,iss&&iss.sprint,itemWeek(iss||{}));
}
function warnDecompositionAfterIssue(kind){
  toast(`${kind} не может быть запланирована позже главной задачи`,{type:'warn'});
}
function issueHasChildrenAfter(iss,sprint,week){
  const after=item=>boardPeriodAfter(item.sprint,itemWeek(item),sprint,week);
  return (iss.stories||[]).some(after)||(iss.subtasks||[]).some(after);
}
function equalizeBoardColumnHeaders(){
  const scroll=$('#boardScroll');if(!scroll)return;
  const heads=[...scroll.querySelectorAll('.board-grid > .backlog-col > .board-col-head, .board-grid > .sprint-col > .board-col-head')];
  if(heads.length<2)return;
  heads.forEach(head=>head.style.height='auto');
  const equalizeRows=selector=>{
    const rows=[...scroll.querySelectorAll(selector)];
    rows.forEach(row=>row.style.height='auto');
    const height=Math.max(...rows.map(row=>Math.ceil(row.getBoundingClientRect().height)));
    rows.forEach(row=>row.style.height=`${height}px`);
  };
  equalizeRows('.board-grid > .backlog-col .backlog-title, .board-grid > .sprint-col .sprint-head');
  equalizeRows('.board-grid > .backlog-col .backlog-summary, .board-grid > .sprint-col .cap-summary');
}
function bindTeams(){
  // разворачивание трайба (аккордеон)
  document.querySelectorAll('[data-tribe]').forEach(el=>el.onclick=()=>{
    state.ui.teamsTribe = state.ui.teamsTribe===el.dataset.tribe ? null : el.dataset.tribe;
    save();render();
  });
  // выбор команды
  document.querySelectorAll('[data-open]').forEach(el=>el.onclick=()=>{
    state.ui.teamSel=el.dataset.open;state.ui.teamView='board';save();render();
  });
  const t=state.pi.teams.find(x=>x.name===state.ui.teamSel);
  // тулбар
  const cap=$('#tbCap');if(cap)cap.onclick=()=>{state.ui.teamView='capacity';save();render();};
  const bd=$('#tbBoard');if(bd)bd.onclick=()=>{state.ui.teamView='board';save();render();};
  const back=$('#tbBack');if(back)back.onclick=()=>{state.ui.teamSel=null;save();render();};
  const b2=$('#tbBack2');if(b2)b2.onclick=()=>{state.ui.teamView='board';save();render();};

  if(!t) return;

  // --- Ёмкость ---
  const addCap=$('#addCap');if(addCap)addCap.onclick=()=>openCapacityMemberModal(t);
  document.querySelectorAll('[data-ci]').forEach(el=>el.onchange=async()=>{
    const key=teamKey(t.tribe,t.name);
    const member=state.capacity[key][+el.dataset.ci];if(!member||!member._backendId)return;
    const map={fio:'full_name',role:'competency',rate:'rate',ceremonyPct:'ceremony_percent',riskPct:'risk_percent',efficiency:'efficiency'};
    const field=map[el.dataset.ck];if(!field)return;
    let value=el.value;
    if(['rate','ceremony_percent','risk_percent'].includes(field))value=capacityNumber(value,0);
    if(field==='efficiency')value=String(value).trim()===''?null:capacityNumber(value,1);
    await runCapacityCommand(`/members/${member._backendId}`,'PATCH',{[field]:value});
  });
  // отпуск — открытие модального окна выбора дат
  document.querySelectorAll('[data-vacedit]').forEach(el=>el.onclick=()=>{
    openVacationModal(t,+el.dataset.vacedit);
  });
  document.querySelectorAll('[data-unavailedit]').forEach(el=>el.onclick=()=>{
    openExtraUnavailableModal(t,+el.dataset.unavailedit);
  });
  document.querySelectorAll('[data-delcap]').forEach(b=>b.onclick=async()=>{
    const key=teamKey(t.tribe,t.name),member=state.capacity[key][+b.dataset.delcap];
    if(!member||!member._backendId)return;
    try{
      await capacityMemberCommand(`/members/${member._backendId}`,'DELETE',{confirm_cascade:false});
      save(false);render();
    }catch(error){
      if(error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required'&&
          window.confirm('Сотрудник назначен на работы. Удалить сотрудника и очистить назначения?')){
        await runCapacityCommand(`/members/${member._backendId}`,'DELETE',{confirm_cascade:true});
      }else reportCapacitySyncError(error);
    }
  });

  // --- Доска: удаление стикеров/подзадач, добавление подзадач, drag ---
  // Удаление стикера = снятие с доски + синхронизация с Pre PI Planning (5.1):
  //   голубой   → задача уходит из верхней зоны в нижнюю (prePlanned=false);
  //   красный   → согласование снимается (agreed=false) → снова фиолетовый;
  //   фиолетовый → остаётся фиолетовым.
  document.querySelectorAll('[data-delissue]').forEach(b=>b.onclick=(e)=>{
    e.stopPropagation();
    const i=findIssue(b.dataset.delissue); if(!i)return;
    const col=issueColor(i);
    i.onBoard=false; setBoardPeriod(i,null,null);
    if(col==='blue') i.prePlanned=false;
    if(col==='red')  i.agreed=false;
    save();render();
  });
  document.querySelectorAll('[data-delsub-i]').forEach(b=>b.onclick=async (e)=>{
    e.stopPropagation();
    const iss=state.issues.find(i=>i.id===b.dataset.delsubI);
    const st=iss&&(iss.subtasks||[])[+b.dataset.delsubS];if(!iss||!st)return;
    try{
      await teamBoardCommand(`/initiatives/${iss._backendId}/work-items/${st._backendId}`,'DELETE',{confirm_cascade:false});
      save(false);render();
    }catch(error){
      if(error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required'&&
          window.confirm('Удалить подзадачу вместе с её связями?'))
        await runBoardCommand(`/initiatives/${iss._backendId}/work-items/${st._backendId}`,'DELETE',{confirm_cascade:true});
      else reportTeamBoardsSyncError(error);
    }
  });
  // удаление Истории: снимаем и её белые подзадачи (со связями)
  document.querySelectorAll('[data-delstory-i]').forEach(b=>b.onclick=async (e)=>{
    e.stopPropagation();
    const iss=state.issues.find(i=>i.id===b.dataset.delstoryI); if(!iss)return;
    const su=b.dataset.delstoryU;
    const story=storyById(iss,su);if(!story)return;
    try{
      await teamBoardCommand(`/initiatives/${iss._backendId}/stories/${story._backendId}`,'DELETE',{confirm_cascade:false});
      save(false);render();
    }catch(error){
      if(error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required'&&
          window.confirm('Удалить историю вместе с её подзадачами и связями?'))
        await runBoardCommand(`/initiatives/${iss._backendId}/stories/${story._backendId}`,'DELETE',{confirm_cascade:true});
      else reportTeamBoardsSyncError(error);
    }
  });
  // клик по стикеру -> карточка (поля + Согласовать для фиолетовых + декомпозиция)
  document.querySelectorAll('#boardScroll .sticker').forEach(el=>el.onclick=(e)=>{
    if(e.target.closest('.x,.c-link'))return;
    if(el.classList.contains('info'))return;
    openStickerModal(el.dataset.id);
  });
  // клик по зелёному стикеру Истории -> карточка Истории (поля + декомпозиция на белые)
  document.querySelectorAll('#boardScroll .story').forEach(el=>el.onclick=(e)=>{
    if(e.target.closest('.x,.s-link'))return;
    openStoryModal(el.dataset.storyIssue, el.dataset.storyUid);
  });
  // клик по белой подзадаче -> карточка редактирования (ФИО/роль/ёмкость/спринт)
  document.querySelectorAll('#boardScroll .white').forEach(el=>el.onclick=(e)=>{
    if(e.target.closest('.x,.w-link'))return; // ✕ удаляет, «+ связь» создаёт связь
    openWhiteModal(el.dataset.wissue, +el.dataset.wsub);
  });
  // клик по пустому месту доски -> снять выделение стрелки
  const bsEl=$('#boardScroll');
  if(bsEl) bsEl.addEventListener('click',(e)=>{
    if(e.target.closest('.sticker,.white,.story,[data-arrow],.arrow-handle'))return;
    if(state.ui.selectedArrow){ state.ui.selectedArrow=null; save(); render(); }
  });

  // переключатель вида доски (Колонки / Дорожки)
  document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>{
    state.ui.boardLayout=b.dataset.layout; save(); render();
  });
  // переключатель детализации доски (спринты / недели)
  document.querySelectorAll('[data-week-mode]').forEach(b=>b.onclick=()=>{
    state.ui.boardWeeks=b.dataset.weekMode==='on'; save(); render();
  });
  // переключатель таблицы трудозатрат по ФИО
  const effFio=$('#tbEffortFio');
  if(effFio) effFio.onclick=()=>{ state.ui.showEffortFio=!state.ui.showEffortFio; save(); render(); };

  // drag для доски (цветные + белые); zone — сама зона, чтобы знать строку в режиме дорожек
  enableDrag(document,async(payload,zone,ev)=>{
    let target=zone.dataset.tbSprint;
    let targetWeek=zone.dataset.tbWeek==='' || zone.dataset.tbWeek===undefined ? null : +zone.dataset.tbWeek;
    let targetDate='';
    // В дневном Ганте зоной является вся строка сотрудника. Определяем день по X
    // курсора и привязываем его к неделе, которую поддерживает текущая модель данных.
    if(zone.dataset.ganttDays&&ev){
      const dayCells=[...zone.querySelectorAll('[data-gantt-day]')];
      const rect=zone.getBoundingClientRect();
      const count=Math.max(1,+zone.dataset.ganttDays||dayCells.length);
      const dayIndex=Math.max(0,Math.min(dayCells.length-1,Math.floor((ev.clientX-rect.left)/(rect.width/count))));
      const day=dayCells[dayIndex];
      if(day){ target=day.dataset.ganttSprint; targetWeek=+day.dataset.ganttWeek; targetDate=day.dataset.ganttDate||''; }
    }
    const cellIssue=zone.dataset.tbIssue; // задаётся только в режиме «Дорожки»
    const cellFio=zone.dataset.tbFio; // задаётся только в режиме «Гант»
    const isColumns = cellIssue===undefined && cellFio===undefined; // «Колонки» (у «Дорожек» есть data-tb-issue, у «Ганта» — data-tb-fio)
    if(payload.kind==='issue'){
      const iss=state.issues.find(i=>i.id===payload.id);
      if(iss){
        const ns=target==='backlog'?null:+target;
        if(issueHasChildrenAfter(iss,ns,targetWeek)){
          toast('Главная задача не может быть запланирована раньше своих историй или подзадач',{type:'warn'});
          return;
        }
        const resetAgreement=iss.agreed&&ns!==iss.sprint;
        setBoardPeriod(iss,ns,targetWeek);
        // «Колонки»: свободное размещение среди всех стикеров колонки (цветных и белых)
        if(isColumns && ev){
          const beforeKey=stickerBeforeKey(zone,ev.clientY);
          reorderBoardItem(t.name,ns,targetWeek,'i:'+iss.id,beforeKey);
        }
        await runBoardCommand(`/initiatives/${iss._backendId}`,'PATCH',{
          sprint_index:ns,week_index:targetWeek,board_sort_order:iss.ord||0,
          ...(resetAgreement?{agreed:false}:{}),
        },'Позиция сохранена в Program Board');
      }
    }else if(payload.kind==='story'){
      if(target==='backlog')return; // Истории в бэклог не уходят
      // в режиме дорожек История остаётся в строке своей задачи
      if(cellIssue!==undefined && cellIssue!=='' && cellIssue!==payload.id){
        toast('Историю можно переносить только в пределах строки своей задачи',{type:'warn'}); return;
      }
      const iss=state.issues.find(i=>i.id===payload.id);
      const sy=iss?storyById(iss,payload.story):null;
      if(sy){
        if(decompositionAfterIssue(iss,+target,targetWeek)){ warnDecompositionAfterIssue('История'); return; }
        setBoardPeriod(sy,+target,targetWeek);
        if(isColumns && ev){
          const beforeKey=stickerBeforeKey(zone,ev.clientY);
          reorderBoardItem(t.name,+target,targetWeek,'g:'+sy.uid,beforeKey);
        }
        await runBoardCommand(`/initiatives/${iss._backendId}/stories/${sy._backendId}`,'PATCH',{
          sprint_index:+target,week_index:targetWeek,board_sort_order:sy.ord||0,
        });
      }
    }else if(payload.kind==='sub'){
      if(target==='backlog')return; // белые в бэклог не уходят
      // в режиме дорожек белый остаётся в строке своей задачи
      if(cellIssue!==undefined && cellIssue!=='' && cellIssue!==payload.id){
        toast('Подзадачу можно переносить только в пределах строки своей задачи',{type:'warn'}); return;
      }
      const iss=state.issues.find(i=>i.id===payload.id);
      if(iss&&iss.subtasks[payload.sub]){
        const st=iss.subtasks[payload.sub];
        // в режиме «Гант» белый остаётся в строке своего сотрудника
        if(cellFio!==undefined){
          const stFio=(st.fio||'').trim()||'— без ФИО —';
          if(stFio!==cellFio){ toast('Подзадачу можно переносить только в пределах строки своего сотрудника',{type:'warn'}); return; }
        }
        let plannedStartDate=null;
        if(targetDate){
          const team=teamObjByName(issuePrimaryTeam(iss));
          const roster=team?(state.capacity[teamKey(team.tribe,team.name)]||[]):[];
          const schedule=ganttScheduleFrom(targetDate,st.cap,ganttPersonForTask(roster,st),ganttCalendarDays());
          if(!schedule){toast('На выбранной дате сотрудник недоступен до конца PI',{type:'warn'});return;}
          if(!schedule.complete){toast('Трудоёмкость задачи не помещается в оставшиеся дни PI',{type:'warn'});return;}
          target=schedule.sprint;targetWeek=schedule.week;plannedStartDate=schedule.startDate;
        }
        if(decompositionAfterIssue(iss,+target,targetWeek)){ warnDecompositionAfterIssue('Подзадача'); return; }
        setBoardPeriod(st,+target,targetWeek);
        if(plannedStartDate)st.startDate=plannedStartDate;else delete st.startDate;
        // «Колонки»: свободное размещение среди всех стикеров колонки (цветных и белых)
        if(isColumns && ev){
          const beforeKey=stickerBeforeKey(zone,ev.clientY);
          reorderBoardItem(t.name,+target,targetWeek,'s:'+st.uid,beforeKey);
        }
        await runBoardCommand(`/initiatives/${iss._backendId}/work-items/${st._backendId}`,'PATCH',{
          planned_start_date:plannedStartDate,sprint_index:+target,week_index:targetWeek,board_sort_order:st.ord||0,
        });
      }
    }
  },'[data-tb-sprint]',zone=>zone);

  // стрелки + фокус по наведению
  const scroll=$('#boardScroll');
  if(scroll){
    scroll.querySelectorAll('.sticker[data-id],.white[data-wissue],.story[data-story-uid]').forEach(el=>{
      // Режим подсветки по наведению:
      //  задача        → 'issue'  (всё дерево задачи: Истории + все белые);
      //  История       → 'story'  (сама История + её белые + задача-родитель);
      //  белый Истории → 'story'  (та же ветка Истории);
      //  прямой белый  → 'direct' (задача-родитель + только её прямые белые, без Историй).
      const issueId = el.dataset.ownerInfoSource || el.dataset.id || el.dataset.wissue || el.dataset.storyIssue;
      let mode='issue', storyUid=null;
      if(el.classList.contains('story')){ mode='story'; storyUid=el.dataset.storyUid; }
      else if(el.classList.contains('white')){
        if(el.dataset.story){ mode='story'; storyUid=el.dataset.story; }
        else mode='direct';
      }
      el.addEventListener('mouseenter',()=>setBoardFocus(issueId,mode,storyUid));
      el.addEventListener('mouseleave',()=>setBoardFocus(null));
    });
    // создание новой связи: зажать «+ связь» на стикере и потянуть на цель
    scroll.querySelectorAll('[data-link-key]').forEach(b=>b.addEventListener('mousedown',(e)=>{
      e.preventDefault(); e.stopPropagation();
      const kind=b.dataset.linkKind, key=b.dataset.linkKey;
      const from = kind==='c' ? {kind:'c',id:key} : (kind==='g' ? {kind:'g',uid:key} : {kind:'w',uid:key});
      const srcEl = kind==='c'
        ? scroll.querySelector(`.sticker[data-sticker="${CSS.escape(key)}"]`)
        : (kind==='g'
          ? scroll.querySelector(`.story[data-story-uid="${CSS.escape(key)}"]`)
          : scroll.querySelector(`.white[data-wuid="${CSS.escape(key)}"]`));
      arrowDrag={create:true, from, anchor: srcEl?elCenterInScroll(scroll,srcEl):{x:0,y:0}};
      document.addEventListener('mousemove',onArrowMove);
      document.addEventListener('mouseup',onArrowUp);
    }));
    requestAnimationFrame(()=>{equalizeBoardColumnHeaders();drawArrows();});
    scroll.onscroll=drawArrows;
    window.onresize=()=>{equalizeBoardColumnHeaders();drawArrows();};
  }
  // удаление выбранной стрелки клавишей Delete / Backspace
  document.onkeydown=(e)=>{
    if(state.ui.tab!=='teams' || !state.ui.selectedArrow) return;
    const tag=(e.target.tagName||'').toLowerCase();
    if(tag==='input'||tag==='textarea'||tag==='select'||e.target.isContentEditable) return;
    if(e.key==='Delete'||e.key==='Backspace'){ e.preventDefault(); deleteConnection(state.ui.selectedArrow); }
  };
}

/* ---- Карточка стикера (поля + Согласовать + декомпозиция) ---- */
function openStickerModal(issueId){
  const iss=findIssue(issueId); if(!iss)return;
  const isAttr = issuePrimaryTeam(iss)!==iss.owner; // привлечение
  const tn=issuePrimaryTeam(iss);
  const comps=teamComps(tn);
  const ec=execComps(iss,tn);
  const tags=piTags();
  const selectedTags=issueTags(iss);
  const root=$('#modalRoot');
  const attractionApprovalText=approvalLabel(iss).replace(/^Согласовано/,'согласовано');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${esc(iss.id)} <span class="muted" style="font-size:12px;font-weight:400">(${COLOR_RU[issueColor(iss)]})</span></h3>
    <label><span>Название инициативы</span><input id="sm_name" value="${esc(iss.name)}"></label>
    <div class="muted" style="margin-bottom:12px">Владелец: <b>${esc(iss.owner)}</b> · Исполнитель: <b>${esc(issueExecTeams(iss).join(', '))||esc(iss.executor)}</b></div>
    <div>
      <span class="muted" style="display:block;margin-bottom:5px;font-size:12.5px">Тэги</span>
      ${tags.length
        ? `<div class="tag-picker">${tags.map(t=>`<label class="tag-check"><input type="checkbox" data-sm-tag value="${esc(t)}" ${selectedTags.includes(t)?'checked':''}>#${esc(t)}</label>`).join('')}</div>`
        : `<div class="muted" style="font-size:12px;margin-bottom:14px">Сначала добавьте тэги на вкладке «Данные PI-цикла».</div>`}
    </div>
    <div class="row" style="gap:8px">
      ${comps.map(r=>`<label style="display:flex;flex-direction:column;gap:3px"><span class="muted" style="font-size:11px">${r}</span><input type="number" min="0" style="width:70px" id="sm_${r.toLowerCase()}" value="${esc(+ec[r]||0)}"></label>`).join('')}
    </div>
    <label style="margin-top:12px"><span>Тип инициативы</span>${initiativeTypeFieldHTML(iss.type,'')}</label>
    <label><span>Комментарий</span><input id="sm_comment" value="${esc(iss.comment)}"></label>
    ${isAttr ? (iss.agreed
        ? `<div class="note" style="margin:6px 0;border-left-color:var(--red-b)">✓ Привлечение <b>${esc(attractionApprovalText)}</b>. Перенос стикера в другой спринт сбросит согласование.</div>`
        : `<div class="note" style="margin:6px 0;border-left-color:var(--purple-b)">Привлечение <b>не согласовано</b> (фиолетовый). Нажмите «Согласовать».</div>`)
      : ''}
    <div class="note" style="margin:6px 0">Задачу можно декомпозировать <b>двумя способами</b>: сразу на белые подзадачи или на <b>Истории</b> (зелёные), а каждую Историю — уже на белые. Истории и белые на Program Board не выносятся.</div>
    <div class="modal-actions" style="justify-content:space-between">
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${isAttr && !iss.agreed && canApproveTasks() ? `<button class="primary" id="sm_approve">Согласовать</button>`:''}
        <button id="sm_story">Добавить историю</button>
        <button id="sm_decomp">Добавить подзадачу</button>
      </div>
      <button id="sm_close">Закрыть</button>
    </div>
  </div></div>`;
  const sync=()=>{
    iss.name=$('#sm_name').value; iss.type=initiativeTypeValue(root); iss.comment=$('#sm_comment').value;
    iss.tags=[...root.querySelectorAll('[data-sm-tag]:checked')].map(el=>el.value);
    let entry=execEntry(iss,tn);
    if(!entry){ entry={team:tn,comps:{}}; iss.executors=iss.executors||[]; iss.executors.push(entry); }
    entry.comps=entry.comps||{};
    comps.forEach(r=>{ entry.comps[r]=+$('#sm_'+r.toLowerCase()).value||0; });
    return {title:iss.name,initiative_type:iss.type,comment:iss.comment,tags:iss.tags,effort_by_competency:{...entry.comps}};
  };
  root.querySelectorAll('[data-sm-tag]').forEach(el=>el.onchange=(e)=>{
    e.stopPropagation();
    iss.tags=[...root.querySelectorAll('[data-sm-tag]:checked')].map(x=>x.value);
    save(false);
  });
  const tagPick=root.querySelector('.tag-picker');
  if(tagPick) tagPick.onclick=e=>e.stopPropagation();
  wireInitiativeTypeField(root);
  $('#sm_close').onclick=async()=>{
    if(!canWriteTab('teams')){root.innerHTML='';return;}
    const body=sync();if(await runBoardCommand(`/initiatives/${iss._backendId}`,'PATCH',body))root.innerHTML='';
  };
  const ap=$('#sm_approve'); if(ap)ap.onclick=async()=>{ const body={...sync(),agreed:true};if(await runBoardCommand(`/initiatives/${iss._backendId}`,'PATCH',body,'Привлечение согласовано'))root.innerHTML=''; };
  $('#sm_decomp').onclick=async()=>{ const body=sync();if(await runBoardCommand(`/initiatives/${iss._backendId}`,'PATCH',body))openSubtaskModal(iss.id); };
  $('#sm_story').onclick=async()=>{ const body=sync();if(await runBoardCommand(`/initiatives/${iss._backendId}`,'PATCH',body))openStoryModal(iss.id, null); };
}

function boardAssigneeDatalist(roster){
  const seen=new Set();
  return (roster||[]).map(p=>({fio:String(p.fio||'').trim(),role:String(p.role||'').trim()}))
    .filter(p=>p.fio)
    .filter(p=>{
      const key=(p.fio+'|'+p.role).toLowerCase();
      if(seen.has(key))return false;
      seen.add(key);return true;
    })
    .map(p=>`<option value="${esc(p.fio)}" label="${esc(p.role)}"></option>`)
    .join('');
}
function boardAssigneePayload(roster,name,role,validRoles){
  const assigneeName=String(name||'').trim();
  const competency=String(role||'').trim().toUpperCase();
  const member=(roster||[]).find(p=>
    String(p.fio||'').trim().toLowerCase()===assigneeName.toLowerCase() &&
    String(p.role||'').trim().toUpperCase()===competency);
  if(member)return {assignee_member_id:member._backendId||null,assignee_name:String(member.fio||'').trim()};
  const roleTokens=new Set([...(validRoles||[]),...(roster||[]).map(p=>p.role)].map(r=>String(r||'').trim().toUpperCase()).filter(Boolean));
  return {
    assignee_member_id:null,
    assignee_name:roleTokens.has(assigneeName.toUpperCase())?'':assigneeName,
  };
}
function ganttFormPerson(roster,fio,role){
  return ganttPersonForTask(roster,{fio:String(fio||'').trim(),role:String(role||'').trim()});
}
function wireTaskSchedulePreview(prefix,roster){
  const days=ganttCalendarDays();
  const update=()=>{
    const person=ganttFormPerson(roster,$(`#${prefix}_fio`).value,$(`#${prefix}_role`).value);
    const schedule=ganttScheduleFrom($(`#${prefix}_start`).value,+$(`#${prefix}_cap`).value||0,person,days);
    const end=$(`#${prefix}_end`),hint=$(`#${prefix}_schedule`);
    end.value=schedule?schedule.endDate:'';
    hint.textContent=schedule
      ?`${ganttScheduleLabel(schedule)}. В рабочий день доступно ${round1(ganttDayCapacity(person,parseISO(schedule.startDate)))} чел.-дн.`
      :'Выберите дату внутри PI и сотрудника с ненулевой доступностью.';
    hint.classList.toggle('danger-text',!schedule||!schedule.complete);
  };
  [`${prefix}_fio`,`${prefix}_role`,`${prefix}_cap`,`${prefix}_start`].forEach(id=>{
    const el=$(`#${id}`);if(el){el.addEventListener('input',update);el.addEventListener('change',update);}
  });
  update();
  return ()=>{
    const person=ganttFormPerson(roster,$(`#${prefix}_fio`).value,$(`#${prefix}_role`).value);
    return ganttScheduleFrom($(`#${prefix}_start`).value,+$(`#${prefix}_cap`).value||0,person,days);
  };
}

/* ---- Модальное окно подзадачи ---- */
// storyUid задан → белый привязывается к Истории (её ID на плашке) + дефолтная стрелка от Истории;
// иначе → белый напрямую под задачей + дефолтная стрелка на цветной родитель.
function openSubtaskModal(issueId,storyUid){
  const iss=state.issues.find(i=>i.id===issueId);if(!iss)return;
  const sy=storyUid?storyById(iss,storyUid):null;
  const defSprint = sy ? sy.sprint : iss.sprint;
  const defWeek = sy ? itemWeek(sy) : itemWeek(iss);
  const days=ganttCalendarDays();
  const minDate=days.length?ganttIsoDate(days[0].date):'';
  const maxDate=days.length?ganttIsoDate(days[days.length-1].date):'';
  const rawDefStart=ganttPeriodStartIso(defSprint,defWeek)||minDate;
  const defStart=(ganttScheduleFrom(rawDefStart,1,null,days)||{}).startDate||rawDefStart;
  const primaryTeam=teamObjByName(issuePrimaryTeam(iss));
  const roster=primaryTeam?(state.capacity[teamKey(primaryTeam.tribe,primaryTeam.name)]||[]):[];
  const comps=teamComps(issuePrimaryTeam(iss));
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>Декомпозиция · ${esc(sy?(sy.id||'История'):iss.id)}</h3>
    ${sy?`<div class="muted" style="margin-bottom:10px">Подзадача Истории <b>${esc(sy.id||'')}</b> (задача ${esc(iss.id)})</div>`:''}
    <label><span>ФИО</span><input id="m_fio" list="m_people" placeholder="Фамилия"></label>
    <datalist id="m_people">${boardAssigneeDatalist(roster)}</datalist>
    <label><span>Компетенция</span><select id="m_role">${comps.map(r=>`<option>${r}</option>`).join('')}</select></label>
    <label><span>Трудоёмкость (чел.-дн.)</span><input id="m_cap" type="number" min="0" step="0.5" value="1"></label>
    <label><span>Дата начала</span><input id="m_start" type="date" min="${minDate}" max="${maxDate}" value="${defStart}"></label>
    <label><span>Дата окончания (расчёт)</span><input id="m_end" type="date" readonly></label>
    <div class="note task-schedule-note" id="m_schedule"></div>
    <div class="modal-actions">
      <button id="m_cancel">Отмена</button>
      <button class="primary" id="m_save">Добавить подзадачу</button>
    </div>
  </div></div>`;
  const readSchedule=wireTaskSchedulePreview('m',roster);
  $('#m_cancel').onclick=()=>{ if(sy){ root.innerHTML=''; openStoryModal(iss.id, storyUid); } else root.innerHTML=''; };
  $('#m_save').onclick=async()=>{
    const u=uid();
    const schedule=readSchedule();
    if(!schedule){toast('Не удалось рассчитать даты: проверьте сотрудника и дату начала',{type:'warn'});return;}
    if(!schedule.complete){toast('Трудоёмкость задачи не помещается в оставшиеся дни PI',{type:'warn'});return;}
    const white={uid:u,fio:$('#m_fio').value.trim(),role:$('#m_role').value,cap:+$('#m_cap').value||0,
      startDate:schedule.startDate,sprint:schedule.sprint,week:schedule.week};
    if(decompositionAfterIssue(iss,white.sprint,white.week)){ warnDecompositionAfterIssue('Подзадача'); return; }
    if(storyUid) white.storyUid=storyUid; // принадлежит Истории
    const assignee=boardAssigneePayload(roster,white.fio,white.role,comps);
    const created=await runBoardCommand(`/initiatives/${iss._backendId}/work-items`,'POST',{
      client_uid:white.uid,story_client_uid:white.storyUid||null,
      assignee_member_id:assignee.assignee_member_id,assignee_name:assignee.assignee_name,
      competency:white.role,effort:white.cap,planned_start_date:white.startDate,
      sprint_index:white.sprint,week_index:white.week,
      sort_order:(iss.subtasks||[]).length,board_sort_order:(iss.subtasks||[]).length,
    });
    if(!created)return;
    root.innerHTML='';
    // дефолтная стрелка декомпозиции: напрямую к задаче или внутри ветки истории
    const refreshed=(state.issues||[]).find(row=>row._backendId===iss._backendId);
    const item=refreshed&&(refreshed.subtasks||[]).find(row=>row.uid===u);
    if(!storyUid){
      if(item&&item._backendId){
        try{
          await programBoardCommand('/connections','POST',{
            source:{kind:'work_item',id:item._backendId},
            target:{kind:'initiative',id:iss._backendId},
            relation_type:'decomposes',
          });
        }catch(error){reportProgramBoardSyncError(error);}
      }
    }else{
      const parentStory=refreshed&&storyById(refreshed,storyUid);
      if(parentStory&&parentStory._backendId&&item&&item._backendId){
        try{
          await programBoardCommand('/connections','POST',{
            source:{kind:'story',id:parentStory._backendId},
            target:{kind:'work_item',id:item._backendId},
            relation_type:'decomposes',
          });
        }catch(error){reportProgramBoardSyncError(error);}
      }
    }
    save(false);render();
  };
}
/* ---- Модальное окно Истории (зелёный стикер): поля + декомпозиция на белые ---- */
// storyUid=null → создание новой Истории; иначе → редактирование существующей.
function openStoryModal(issueId,storyUid){
  const iss=state.issues.find(i=>i.id===issueId);if(!iss)return;
  const isNew=!storyUid;
  const sy=isNew?null:storyById(iss,storyUid);
  if(!isNew && !sy)return;
  const sprints=computeSprints();
  const scomps=teamComps(issuePrimaryTeam(iss));
  const cur=sy||{id:'',name:'',comps:{},sprint:iss.sprint,week:itemWeek(iss)};
  const curComps=(sy?storyComps(sy):{});
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${isNew?'Новая история':'История'} · задача ${esc(iss.id)}</h3>
    <label><span>ID истории</span><input id="sy_id" value="${esc(cur.id)}" placeholder="напр. ${esc(iss.id)}-S1"></label>
    <label><span>Название (необязательно)</span><input id="sy_name" value="${esc(cur.name||'')}" placeholder="Кратко о истории"></label>
    <div class="row" style="gap:8px">
      ${scomps.map(r=>`<label style="display:flex;flex-direction:column;gap:3px"><span class="muted" style="font-size:11px">${r}</span><input type="number" min="0" style="width:70px" id="sy_${r.toLowerCase()}" value="${esc(+curComps[r]||0)}"></label>`).join('')}
    </div>
    <label style="margin-top:12px"><span>Спринт</span><select id="sy_sprint">${sprints.map(s=>`<option value="${s.index}" ${s.index===cur.sprint?'selected':''}>Спринт ${s.index+1}</option>`).join('')}</select></label>
    ${weekSelectHTML('sy_week',cur.week)}
    ${isNew?`<div class="note" style="margin:6px 0">После создания Историю можно будет декомпозировать на белые подзадачи (кнопка «Добавить подзадачу» появится в её карточке).</div>`:''}
    <div class="modal-actions" style="justify-content:space-between">
      <div style="display:flex;gap:8px">
        ${isNew?'':`<button class="danger" id="sy_del">Удалить</button>`}
        ${isNew?'':`<button id="sy_decomp">Добавить подзадачу</button>`}
      </div>
      <div style="display:flex;gap:8px">
        <button id="sy_cancel">Отмена</button>
        <button class="primary" id="sy_save">${isNew?'Создать историю':'Сохранить'}</button>
      </div>
    </div>
  </div></div>`;
  const readForm=()=>{
    const comps={}; scomps.forEach(r=>{ comps[r]=+$('#sy_'+r.toLowerCase()).value||0; });
    return { id:$('#sy_id').value.trim(), name:$('#sy_name').value.trim(), comps, sprint:+$('#sy_sprint').value, week:+$('#sy_week').value };
  };
  $('#sy_cancel').onclick=()=>root.innerHTML='';
  $('#sy_save').onclick=async()=>{
    const f=readForm();
    if(!f.id){ toast('Укажите ID истории',{type:'warn'}); return; }
    if(decompositionAfterIssue(iss,f.sprint,f.week)){ warnDecompositionAfterIssue('История'); return; }
    if(isNew){
      const storyUid=uid();
      if(await runBoardCommand(`/initiatives/${iss._backendId}/stories`,'POST',{
        client_uid:storyUid,external_key:f.id,title:f.name,effort_by_competency:f.comps,
        sprint_index:f.sprint,week_index:f.week,sort_order:(iss.stories||[]).length,
        board_sort_order:(iss.stories||[]).length,
      })){
        const refreshed=(state.issues||[]).find(row=>row._backendId===iss._backendId);
        const createdStory=refreshed&&storyById(refreshed,storyUid);
        if(createdStory&&createdStory._backendId&&iss._backendId){
          try{
            await programBoardCommand('/connections','POST',{
              source:{kind:'initiative',id:iss._backendId},
              target:{kind:'story',id:createdStory._backendId},
              relation_type:'decomposes',
            });
          }catch(error){reportProgramBoardSyncError(error);}
        }
        root.innerHTML='';
        save(false);render();
      }
    }else{
      if(await runBoardCommand(`/initiatives/${iss._backendId}/stories/${sy._backendId}`,'PATCH',{
        external_key:f.id,title:f.name,effort_by_competency:f.comps,
        sprint_index:f.sprint,week_index:f.week,board_sort_order:sy.ord||0,
      }))root.innerHTML='';
    }
  };
  const del=$('#sy_del'); if(del)del.onclick=async()=>{
    try{
      await teamBoardCommand(`/initiatives/${iss._backendId}/stories/${sy._backendId}`,'DELETE',{confirm_cascade:false});
      root.innerHTML='';save(false);render();
    }catch(error){
      if(error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required'&&
          window.confirm('Удалить историю вместе с её подзадачами и связями?')){
        if(await runBoardCommand(`/initiatives/${iss._backendId}/stories/${sy._backendId}`,'DELETE',{confirm_cascade:true}))root.innerHTML='';
      }else reportTeamBoardsSyncError(error);
    }
  };
  const dec=$('#sy_decomp'); if(dec)dec.onclick=async()=>{
    // сохранить правки Истории, затем открыть добавление белой подзадачи в неё
    const f=readForm();
    if(await runBoardCommand(`/initiatives/${iss._backendId}/stories/${sy._backendId}`,'PATCH',{
      external_key:f.id,title:f.name,effort_by_competency:f.comps,
      sprint_index:f.sprint,week_index:f.week,board_sort_order:sy.ord||0,
    }))openSubtaskModal(iss.id, sy.uid);
  };
}

/* ---- Модальное окно редактирования белой подзадачи ---- */
function openWhiteModal(issueId,si){
  const iss=state.issues.find(i=>i.id===issueId); if(!iss)return;
  const st=(iss.subtasks||[])[si]; if(!st)return;
  const primaryTeam=teamObjByName(issuePrimaryTeam(iss));
  const roster=primaryTeam?(state.capacity[teamKey(primaryTeam.tribe,primaryTeam.name)]||[]):[];
  const comps=teamComps(issuePrimaryTeam(iss));
  const days=ganttCalendarDays();
  const minDate=days.length?ganttIsoDate(days[0].date):'';
  const maxDate=days.length?ganttIsoDate(days[days.length-1].date):'';
  const initialSchedule=ganttTaskSchedule(st,ganttPersonForTask(roster,st),days);
  const startDate=(initialSchedule&&initialSchedule.startDate)||ganttFallbackStartIso(st,days)||minDate;
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>Подзадача · ${esc(iss.id)}</h3>
    <label><span>ФИО</span><input id="w_fio" list="w_people" value="${esc(st.fio||'')}" placeholder="Фамилия"></label>
    <datalist id="w_people">${boardAssigneeDatalist(roster)}</datalist>
    <label><span>Компетенция</span><select id="w_role">${comps.map(r=>`<option ${r===st.role?'selected':''}>${r}</option>`).join('')}</select></label>
    <label><span>Трудоёмкость (чел.-дн.)</span><input id="w_cap" type="number" min="0" step="0.5" value="${+st.cap||0}"></label>
    <label><span>Дата начала</span><input id="w_start" type="date" min="${minDate}" max="${maxDate}" value="${startDate}"></label>
    <label><span>Дата окончания (расчёт)</span><input id="w_end" type="date" readonly></label>
    <div class="note task-schedule-note" id="w_schedule"></div>
    <div class="modal-actions" style="justify-content:space-between">
      <button class="danger" id="w_del">Удалить</button>
      <div style="display:flex;gap:8px">
        <button id="w_cancel">Отмена</button>
        <button class="primary" id="w_save">Сохранить</button>
      </div>
    </div>
  </div></div>`;
  const readSchedule=wireTaskSchedulePreview('w',roster);
  $('#w_cancel').onclick=()=>root.innerHTML='';
  $('#w_del').onclick=async()=>{
    try{
      await teamBoardCommand(`/initiatives/${iss._backendId}/work-items/${st._backendId}`,'DELETE',{confirm_cascade:false});
      root.innerHTML='';save(false);render();
    }catch(error){
      if(error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required'&&
          window.confirm('Удалить подзадачу вместе с её связями?')){
        if(await runBoardCommand(`/initiatives/${iss._backendId}/work-items/${st._backendId}`,'DELETE',{confirm_cascade:true}))root.innerHTML='';
      }else reportTeamBoardsSyncError(error);
    }
  };
  $('#w_save').onclick=async()=>{
    const assignee=boardAssigneePayload(roster,$('#w_fio').value,$('#w_role').value,comps);
    const schedule=readSchedule();
    if(!schedule){toast('Не удалось рассчитать даты: проверьте сотрудника и дату начала',{type:'warn'});return;}
    if(!schedule.complete){toast('Трудоёмкость задачи не помещается в оставшиеся дни PI',{type:'warn'});return;}
    if(decompositionAfterIssue(iss,schedule.sprint,schedule.week)){ warnDecompositionAfterIssue('Подзадача'); return; }
    const body={
      assignee_member_id:assignee.assignee_member_id,assignee_name:assignee.assignee_name,competency:$('#w_role').value,
      effort:+$('#w_cap').value||0,planned_start_date:schedule.startDate,
      sprint_index:schedule.sprint,week_index:schedule.week,board_sort_order:st.ord||0,
    };
    if(await runBoardCommand(`/initiatives/${iss._backendId}/work-items/${st._backendId}`,'PATCH',body))root.innerHTML='';
  };
}

/* ---- Геометрия краёв ----
   Точка прикрепления стрелки выбирается на той кромке стикера (верх/низ/лево/право),
   которая обращена к точке `aim` (другой конец или точка изгиба). Возвращает координаты
   точки и внешнюю нормаль кромки (nx,ny) — чтобы линия входила/выходила перпендикулярно. */
function edgePointN(box, aim){
  const c={x:box.x+box.w/2, y:box.y+box.h/2};
  const dx=aim.x-c.x, dy=aim.y-c.y;
  if(Math.abs(dx)>=Math.abs(dy)){
    return dx>=0 ? {x:box.x+box.w, y:c.y, nx:1, ny:0} : {x:box.x, y:c.y, nx:-1, ny:0};
  }
  return dy>=0 ? {x:c.x, y:box.y+box.h, nx:0, ny:1} : {x:c.x, y:box.y, nx:0, ny:-1};
}
function epElement(scope,ep){
  if(!ep)return null;
  if(ep.kind==='c')return scope.querySelector(`.sticker[data-sticker="${CSS.escape(ep.id)}"]`);
  if(ep.kind==='g')return scope.querySelector(`.story[data-story-uid="${CSS.escape(ep.uid)}"]`);
  return scope.querySelector(`.white[data-wuid="${CSS.escape(ep.uid)}"]`);
}

/* ---- Стрелки декомпозиции (по одной на белую подзадачу), редактируемые ---- */
function findConnection(id){ return (state.connections||[]).find(c=>c.id===id); }
// сравнение двух концов связи (стикеров)
function sameEp(a,b){ return !!a&&!!b&&a.kind===b.kind&&(a.kind==='c'?a.id===b.id:a.uid===b.uid); }
// задача (issue), которой принадлежит конец связи — для цвета/фокуса
function epIssue(ep){
  if(!ep) return null;
  if(ep.kind==='c') return state.issues.find(i=>i.id===ep.id)||null;
  if(ep.kind==='g'){
    return state.issues.find(i=>(i.stories||[]).some(sy=>sy.uid===ep.uid))||null;
  }
  for(const i of state.issues){ for(const st of (i.subtasks||[])){ if(st.uid===ep.uid) return i; } }
  return null;
}
function edgeIssue(edge){ return edge ? (epIssue(edge.from)||epIssue(edge.to)) : null; }
// Удаление связи по id.
async function deleteConnection(id){
  const edge=findConnection(id);if(!edge||!edge._backendId)return;
  try{
    await programBoardCommand(`/connections/${edge._backendId}`,'DELETE',{});
    if(state.ui.selectedArrow===id)state.ui.selectedArrow=null;
    save(false);render();
    toast('Связь удалена',{type:'info'});
  }catch(error){reportProgramBoardSyncError(error);}
}
function scrollPoint(scroll,clientX,clientY){
  const cr=scroll.getBoundingClientRect();
  return { x:clientX-cr.left+scroll.scrollLeft, y:clientY-cr.top+scroll.scrollTop };
}
function elCenterInScroll(scroll,el){
  const cr=scroll.getBoundingClientRect(); const r=el.getBoundingClientRect();
  return { x:r.left-cr.left+scroll.scrollLeft+r.width/2, y:r.top-cr.top+scroll.scrollTop+r.height/2 };
}
let arrowDrag=null;
let hoverFocus=null; // id задачи под курсором (для подсветки), не сохраняется в state
// Подсветка по наведению:
//  - на задачу (storyUid=null) — подсвечиваем все её стикеры (Истории + белые);
//  - на Историю (storyUid задан) — подсвечиваем только эту Историю и её белые (data-story===storyUid).
function setBoardFocus(id,mode,storyUid){
  const scroll=$('#boardScroll'); if(!scroll)return;
  hoverFocus=id||null;
  if(id){
    scroll.classList.add('lane-focus');
    scroll.querySelectorAll('.sticker,.white,.story').forEach(el=>{
      const isSticker=el.classList.contains('sticker');
      const isWhite=el.classList.contains('white');
      const sourceId=el.dataset.ownerInfoSource;
      let on;
      if(mode==='story'){
        // ветка одной Истории (сам зелёный стикер + её белые) + задача-родитель (цветной стикер)
        on = sourceId===id || el.dataset.story===storyUid || (isSticker && el.dataset.id===id);
      }else if(mode==='direct'){
        // задача-родитель (цветной) + только её прямые белые (без Истории), Истории не подсвечиваем
        on = sourceId===id || (isSticker && el.dataset.id===id) || (isWhite && el.dataset.wissue===id && !el.dataset.story);
      }else{
        const eid=sourceId||el.dataset.id||el.dataset.wissue||el.dataset.storyIssue;
        on = eid===id; // вся задача (Истории + все белые)
      }
      el.classList.toggle('lane-on', on);
    });
  }else{
    scroll.classList.remove('lane-focus');
    scroll.querySelectorAll('.lane-on').forEach(el=>el.classList.remove('lane-on'));
  }
  drawArrows();
}
function onArrowMove(e){
  if(!arrowDrag)return;
  const scroll=$('#boardScroll'); const prev=$('#arrowPreview'); if(!scroll||!prev)return;
  const p=scrollPoint(scroll,e.clientX,e.clientY);
  prev.setAttribute('d',`M ${arrowDrag.anchor.x} ${arrowDrag.anchor.y} L ${p.x} ${p.y}`);
  prev.setAttribute('opacity','1');
}
async function onArrowUp(e){
  document.removeEventListener('mousemove',onArrowMove);
  document.removeEventListener('mouseup',onArrowUp);
  const drag=arrowDrag; arrowDrag=null;
  if(!drag){return;}
  // временно скрываем svg, чтобы elementFromPoint вернул стикер под курсором
  const svg=$('#arrowLayer'); const disp=svg?svg.style.display:'';
  if(svg) svg.style.display='none';
  const el=document.elementFromPoint(e.clientX,e.clientY);
  if(svg) svg.style.display=disp;
  const target=el&&el.closest('.sticker,.story,.white');
  if(target){
    const ep = target.classList.contains('sticker')
      ? {kind:'c',id:target.dataset.id}
      : (target.classList.contains('story')
        ? {kind:'g',uid:target.dataset.storyUid}
        : {kind:'w',uid:target.dataset.wuid});
    if(drag.create){
      // создание новой связи: from — исходный стикер, to — цель
      const dup=(state.connections||[]).some(c=>sameEp(c.from,drag.from)&&sameEp(c.to,ep));
      if(!sameEp(drag.from,ep) && !dup){
        const source=programBoardEndpointPayload(drag.from),targetPayload=programBoardEndpointPayload(ep);
        if(source&&targetPayload){
          try{
            const before=new Set((state.connections||[]).map(row=>row._backendId));
            await programBoardCommand('/connections','POST',{source,target:targetPayload});
            const created=(state.connections||[]).find(row=>!before.has(row._backendId));
            state.ui.selectedArrow=created?created.id:null;save(false);
            toast('Связь создана',{type:'success'});
          }catch(error){reportProgramBoardSyncError(error);}
        }
      }
    }else if(drag.edgeId){
      // перетягивание конца существующей связи на другой стикер
      const edge=findConnection(drag.edgeId);
      if(edge){
        const otherEnd=drag.end==='from'?edge.to:edge.from;
        const endpoint=programBoardEndpointPayload(ep);
        if(!sameEp(otherEnd,ep)&&endpoint&&edge._backendId){
          try{
            await programBoardCommand(`/connections/${edge._backendId}`,'PATCH',{
              [drag.end==='from'?'source':'target']:endpoint,
            });
          }catch(error){reportProgramBoardSyncError(error);}
        }
      }
    }
  }
  render();
}
function drawArrows(){
  const scroll=$('#boardScroll');const svg=$('#arrowLayer');if(!scroll||!svg)return;
  const W=scroll.scrollWidth,H=scroll.scrollHeight;
  svg.setAttribute('width',W);svg.setAttribute('height',H);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const cr=scroll.getBoundingClientRect();
  const off=el=>{const r=el.getBoundingClientRect();return{
    x:r.left-cr.left+scroll.scrollLeft, y:r.top-cr.top+scroll.scrollTop, w:r.width, h:r.height};};
  let paths='', hits='', handles='', dels='';
  const sel=state.ui.selectedArrow;
  // одна стрелка на каждую связь из state.connections (рисуем только те, чьи оба конца на доске)
  (state.connections||[]).forEach(edge=>{
    const aEl=epElement(scroll,edge.from), bEl=epElement(scroll,edge.to);
    if(!aEl||!bEl)return;
    const A=off(aEl), B=off(bEl);
    const cA={x:A.x+A.w/2, y:A.y+A.h/2}, cB={x:B.x+B.w/2, y:B.y+B.h/2};
    // середина по центрам стикеров — база для смещения изгиба (переживает перемещение стикеров)
    const mC={x:(cA.x+cB.x)/2, y:(cA.y+cB.y)/2};
    const bent = edge.bend && (edge.bend.dx||edge.bend.dy);
    const P = bent ? {x:mC.x+edge.bend.dx, y:mC.y+edge.bend.dy} : null;
    // концы прикрепляются к кромке, обращённой к точке, куда направлена линия
    // (к другому стикеру, а при изгибе — к точке P): вход возможен сверху, снизу и по бокам
    const ps = edgePointN(A, P||cB);
    const ce = edgePointN(B, P||cA);
    let d, midPt;
    if(bent){
      // тянем линию: квадратичная кривая проходит через точку P (середина + смещение)
      const wp={x:2*P.x-(ps.x+ce.x)/2, y:2*P.y-(ps.y+ce.y)/2};
      d=`M ${ps.x} ${ps.y} Q ${wp.x} ${wp.y} ${ce.x} ${ce.y}`;
      midPt=P;
    }else{
      // плавная кубическая кривая: выходим и входим перпендикулярно выбранным кромкам
      const k=Math.max(26, Math.hypot(ce.x-ps.x, ce.y-ps.y)*0.4);
      const c1={x:ps.x+ps.nx*k, y:ps.y+ps.ny*k};
      const c2={x:ce.x+ce.nx*k, y:ce.y+ce.ny*k};
      d=`M ${ps.x} ${ps.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${ce.x} ${ce.y}`;
      midPt={x:(ps.x+ce.x)/2, y:(ps.y+ce.y)/2};
    }
    const on=sel===edge.id;
    const iss=edgeIssue(edge);
    const hue=iss?issueHue(iss):'#8893ab';              // цвет стрелки = цвет задачи
    const dim=hoverFocus && (!iss || iss.id!==hoverFocus); // приглушение при фокусе на другой задаче
    const stroke = on ? '#3fae7d' : hue;
    const op = dim ? 0.12 : 1;
    const w = on ? 1.9 : (hoverFocus && !dim ? 1.8 : 1.2);
    paths+=`<path d="${d}" stroke="${stroke}" stroke-width="${w}" fill="none" marker-end="url(#ah)" opacity="${op}" style="pointer-events:none"/>`;
    hits+=`<path d="${d}" data-arrow="${esc(edge.id)}" stroke="transparent" stroke-width="14" fill="none" style="pointer-events:stroke;cursor:grab"/>`;
    if(on){
      [['from',ps],['to',ce]].forEach(([end,pt])=>{
        handles+=`<circle class="arrow-handle" data-edge="${esc(edge.id)}" data-end="${end}" cx="${pt.x}" cy="${pt.y}" r="6"
          fill="#15151f" stroke="#3fae7d" stroke-width="2" style="pointer-events:auto;cursor:grab"/>`;
      });
      // кнопка удаления связи — рядом с точкой изгиба
      const mx=midPt.x, my=midPt.y-16;
      dels+=`<g class="arrow-del" data-delarrow="${esc(edge.id)}" style="pointer-events:auto;cursor:pointer">
        <circle cx="${mx}" cy="${my}" r="9" fill="#15151f" stroke="#d06576" stroke-width="1.6"/>
        <path d="M ${mx-3.4} ${my-3.4} L ${mx+3.4} ${my+3.4} M ${mx+3.4} ${my-3.4} L ${mx-3.4} ${my+3.4}" stroke="#ec8a98" stroke-width="1.8" stroke-linecap="round"/>
      </g>`;
    }
  });
  svg.innerHTML=`<defs>
    <marker id="ah" markerWidth="7" markerHeight="7" refX="5.5" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" fill="context-stroke"/></marker>
    </defs>${hits}${paths}<path id="arrowPreview" d="" stroke="#3fae7d" stroke-width="1.6" stroke-dasharray="4 3" fill="none" opacity="0" style="pointer-events:none"/>${handles}${dels}`;
  // линия стрелки: тянем = изгибаем (оттягиваем в сторону); клик без движения = выбор/снятие
  svg.querySelectorAll('[data-arrow]').forEach(p=>{
    p.addEventListener('mousedown',(e)=>{
      e.preventDefault(); e.stopPropagation();
      const id=p.dataset.arrow;
      const edge=findConnection(id); if(!edge)return;
      const aEl=epElement(scroll,edge.from), bEl=epElement(scroll,edge.to); if(!aEl||!bEl)return;
      const aC=elCenterInScroll(scroll,aEl), bC=elCenterInScroll(scroll,bEl);
      const mC={x:(aC.x+bC.x)/2, y:(aC.y+bC.y)/2};
      const start={x:e.clientX,y:e.clientY};
      let moved=false;
      const move=(ev)=>{
        if(!moved && Math.abs(ev.clientX-start.x)+Math.abs(ev.clientY-start.y)<4) return;
        moved=true;
        const pt=scrollPoint(scroll,ev.clientX,ev.clientY);
        edge.bend={dx:pt.x-mC.x, dy:pt.y-mC.y};
        drawArrows(); // живой предпросмотр изгиба
      };
      const up=async()=>{
        document.removeEventListener('mousemove',move);
        document.removeEventListener('mouseup',up);
        if(moved&&edge._backendId){
          try{await programBoardCommand(`/connections/${edge._backendId}`,'PATCH',{bend:edge.bend});}
          catch(error){reportProgramBoardSyncError(error);await reloadProgramBoard().catch(()=>{});render();}
        }else if(!moved){state.ui.selectedArrow=state.ui.selectedArrow===id?null:id;save(false);render();}
      };
      document.addEventListener('mousemove',move);
      document.addEventListener('mouseup',up);
    });
    // двойной клик по линии — выпрямить (сбросить изгиб)
    p.addEventListener('dblclick',async(e)=>{
      e.stopPropagation();
      const edge=findConnection(p.dataset.arrow);
      if(edge&&edge.bend&&edge._backendId){
        try{
          await programBoardCommand(`/connections/${edge._backendId}`,'PATCH',{clear_bend:true});
          render();toast('Стрелка выпрямлена',{type:'info'});
        }catch(error){reportProgramBoardSyncError(error);}
      }
    });
  });
  // удаление связи кнопкой ×
  svg.querySelectorAll('[data-delarrow]').forEach(g=>g.addEventListener('click',(e)=>{
    e.stopPropagation();
    deleteConnection(g.dataset.delarrow);
  }));
  // перетаскивание концов выбранной связи
  svg.querySelectorAll('.arrow-handle').forEach(h=>h.addEventListener('mousedown',(e)=>{
    e.preventDefault(); e.stopPropagation();
    const id=h.dataset.edge, end=h.dataset.end;
    const edge=findConnection(id); if(!edge)return;
    const otherEp = end==='from'? edge.to : edge.from;
    const otherEl = epElement(scroll,otherEp);
    arrowDrag={edgeId:id, end, anchor: otherEl?elCenterInScroll(scroll,otherEl):{x:0,y:0}};
    document.addEventListener('mousemove',onArrowMove);
    document.addEventListener('mouseup',onArrowUp);
  }));
}

