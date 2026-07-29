/* =====================================================================
   РЕНДЕР: навигация
===================================================================== */
function renderNav(){
  const nav=$('#nav');
  const tabs=state.ui.mode==='budget' ? BUDGET_TABS : PI_TABS;
  const active=state.ui.mode==='budget' ? state.ui.budgetTab : state.ui.tab;
  nav.innerHTML=tabs.map(t=>`<div class="tab ${active===t.id?'active':''}" data-tab="${t.id}">${t.name}</div>`).join('');
  nav.querySelectorAll('.tab').forEach(el=>el.onclick=()=>{
    if(state.ui.mode==='budget') state.ui.budgetTab=el.dataset.tab;
    else state.ui.tab=el.dataset.tab;
    save();render();
  });
}

// Бейдж выбранного PI-цикла (квартал · год) для заголовков вкладок. Клик — возврат к выбору.
function cycleBadge(){
  if(!state.ui.year||!state.ui.quarter) return '';
  return `<span class="cycle-badge" title="Сменить PI-цикл" onclick="backToLanding()">${esc(state.ui.quarter)} · ${esc(state.ui.year)}</span>`;
}
function budgetBadge(){
  if(!state.ui.budgetYear) return '';
  return `<span class="cycle-badge" title="Сменить сценарий" onclick="backToLanding()">Бюджет · ${esc(state.ui.budgetYear)}</span>`;
}
function activeBadge(){ return state.ui.mode==='budget' ? budgetBadge() : cycleBadge(); }
// Возврат на главную страницу для выбора другого PI-цикла (данные текущего цикла сохраняются).
function backToLanding(){
  state.ui.mode=null;
  state.ui.year=null;
  state.ui.quarter=null;
  state.ui.budgetYear=null;
  save(); render();
}

/* ---- Сохранение позиции прокрутки и фокуса при перерисовке ----------------
   render() пересобирает #app целиком, поэтому горизонтально прокрученная таблица
   после правки любого поля «прыгала» в начало. Перед перерисовкой снимаем позиции
   всех контейнеров [data-scroll-key] и активное поле, после — возвращаем на место. */
// Признак текущего экрана: восстанавливаем позицию только если экран не сменился.
function viewSig(){
  return [state.ui.mode,state.ui.tab,state.ui.budgetTab,state.ui.backlogTribe,state.ui.backlogTeamFilter,
          state.ui.prepTribe,state.ui.prepTeamFilter,state.ui.budgetScopeTribe,state.ui.budgetScopeTeam].join('|');
}
// Селектор активного поля, переживающий перерисовку: собираем из data-атрибутов
// строки/столбца — они у новой разметки те же самые.
const FOCUS_ATTRS=['data-bk','data-bp','data-bk-exec','data-bk-comp',
                   'data-pi','data-pk','data-pi-exec','data-pi-comp','data-ba','data-bd','data-bdr','data-k',
                   'data-ei','data-c'];
function focusSelOf(el){
  if(!el || !el.getAttribute) return null;
  const parts=FOCUS_ATTRS.filter(a=>el.hasAttribute(a))
    .map(a=>`[${a}="${CSS.escape(el.getAttribute(a))}"]`);
  return parts.length ? el.tagName.toLowerCase()+parts.join('') : null;
}
function captureViewPos(){
  const pos={sig:viewSig(), boxes:{}, win:{x:window.scrollX,y:window.scrollY}};
  document.querySelectorAll('[data-scroll-key]').forEach(el=>{
    pos.boxes[el.dataset.scrollKey]={l:el.scrollLeft,t:el.scrollTop};
  });
  const a=document.activeElement;
  const sel=(a && a!==document.body) ? focusSelOf(a) : null;
  if(sel){
    pos.focus=sel;
    // selectionStart есть не у всех типов полей (например, input[type=number] бросает)
    try{ if(typeof a.selectionStart==='number'){ pos.selStart=a.selectionStart; pos.selEnd=a.selectionEnd; } }catch(_){}
  }
  return pos;
}
function restoreViewPos(pos){
  if(!pos || pos.sig!==viewSig()) return;
  if(pos.focus){
    const el=document.querySelector(pos.focus);
    if(el){
      el.focus({preventScroll:true});  // прокрутку выставим сами — ниже
      try{ if(pos.selStart!=null) el.setSelectionRange(pos.selStart,pos.selEnd); }catch(_){}
    }
  }
  document.querySelectorAll('[data-scroll-key]').forEach(el=>{
    const p=pos.boxes[el.dataset.scrollKey];
    if(p){ el.scrollLeft=p.l; el.scrollTop=p.t; }
  });
  window.scrollTo(pos.win.x,pos.win.y);
}

function render(){
  const pos=captureViewPos();
  // попап фильтра живёт на body — закрываем его при любой перерисовке;
  // контекст таблиц пересобирают view-функции ниже
  closeColFilterPop(); colFilterCtx={};
  if(state.ui.mode==='budget' && state.ui.budgetYear){
    ensureBudgetYear(state.ui.budgetYear);
    renderNav();
    const app=$('#app');
    switch(state.ui.budgetTab){
      case 'budgetData':       app.innerHTML=viewBudgetData();       bindBudgetData();       break;
      case 'backlog':          app.innerHTML=viewBacklog();          bindBacklog();          break;
      case 'budgetAssessment': app.innerHTML=viewBudgetAssessment(); bindBudgetAssessment(); break;
      case 'budget':           app.innerHTML=viewBudget();           bindBudget();           break;
      case 'budgetVadarodTeams': app.innerHTML=viewBudgetVadarodTeams(); bindBudgetVadarodTeams(); break;
      default: state.ui.budgetTab='budgetData'; save(); render(); return;
    }
    restoreViewPos(pos);
    return;
  }
  const cid=currentCycleId();
  // PI-цикл не выбран — показываем стартовую страницу выбора года/квартала
  if(state.ui.mode!=='pi' || !cid || !state.cycles[cid]){
    const nav=$('#nav'); if(nav) nav.innerHTML='';
    const app=$('#app'); app.innerHTML=viewLanding(); bindLanding();
    return;
  }
  activateCycle(cid);
  renderNav();
  const app=$('#app');
  switch(state.ui.tab){
    case 'data':    app.innerHTML=viewData();    bindData();    break;
    case 'backlog': app.innerHTML=viewBacklog(); bindBacklog(); break;
    case 'prep':  app.innerHTML=viewPrep();  bindPrep();  break;
    case 'goals': app.innerHTML=viewGoals(); bindGoals(); break;
    case 'pb':    app.innerHTML=viewPB();    bindPB();    break;
    case 'teams': app.innerHTML=viewTeams(); bindTeams(); break;
    case 'risks': app.innerHTML=viewRisks(); bindRisks(); break;
  }
  restoreViewPos(pos);
}

/* =====================================================================
   ГЛАВНАЯ СТРАНИЦА — выбор PI-цикла (год + квартал)
===================================================================== */
function viewLanding(){
  const backendYears=Object.keys(state.cycles||{}).map(id=>+String(id).split('-')[0]).filter(Number.isFinite);
  const y=state.ui.landingYear||backendYears[0]||new Date().getFullYear();
  const years=[...new Set([2026,2027,2028,y,...backendYears])].sort((a,b)=>a-b);
  const yopts=years.map(v=>`<option value="${v}" ${v===y?'selected':''}>${v}</option>`).join('');
  const qs=['Q1','Q2','Q3','Q4'].map(q=>`<button class="q-btn" data-q="${q}">${q}</button>`).join('');
  return `
  <div class="landing">
    <div class="landing-inner">
      <div class="landing-top">
        <div class="landing-title">
          <div class="landing-logo">SberPI</div>
          <h1>Выберите раздел планирования</h1>
          <p>Бюджетирование или PI-цикл</p>
        </div>
        <div class="landing-chip">Рабочий контур</div>
      </div>
      <div class="landing-choices">
        <div class="landing-card budget-card">
          <div class="landing-card-head">
            <div>
              <div class="landing-card-title">Бюджетирование</div>
              <div class="landing-card-sub">Годовой период</div>
            </div>
            <div class="landing-card-mark">BYN</div>
          </div>
          <div class="landing-card-body">
            <div class="landing-form-row">
              <label class="landing-field">
                <span>Год бюджетирования</span>
                <select id="budgetLandingYear">${yopts}</select>
              </label>
              <button class="primary" id="openBudget">Открыть</button>
            </div>
            <div class="landing-foot"><span>Оценка инициатив</span><span>Бюджет Vadarod</span><span>Бюджет Vendor</span></div>
          </div>
        </div>
        <div class="landing-card pi-card">
          <div class="landing-card-head">
            <div>
              <div class="landing-card-title">PI-цикл</div>
              <div class="landing-card-sub">Квартальный период</div>
            </div>
            <div class="landing-card-mark">PI</div>
          </div>
          <div class="landing-card-body">
            <label class="landing-field">
              <span>Год PI-цикла</span>
              <select id="landingYear">${yopts}</select>
            </label>
            <div class="landing-quarters">${qs}</div>
            <div class="landing-foot"><span>Pre PI Planning</span><span>Program Board</span><span>Командные доски</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>`;
}
function bindLanding(){
  const ys=$('#landingYear');
  if(ys) ys.onchange=()=>{ state.ui.landingYear=+ys.value; save(); };
  const by=$('#budgetLandingYear');
  if(by) by.onchange=()=>{ state.ui.landingYear=+by.value; save(); };
  const openBudget=$('#openBudget');
  if(openBudget) openBudget.onclick=()=>{
    const year=+((by&&by.value)||state.ui.landingYear||2026);
    state.ui.mode='budget';
    state.ui.budgetYear=year;
    state.ui.landingYear=year;
    state.ui.budgetTab=state.ui.budgetTab||'budgetData';
    ensureBudgetYear(year);
    save(false); render();
  };
  document.querySelectorAll('.q-btn').forEach(b=>b.onclick=async()=>{
    if(!cyclesApiReady){
      toast(cyclesApiUnavailable
        ? 'Сервер PI-циклов недоступен. Проверьте API и обновите страницу.'
        : 'PI-циклы загружаются с сервера. Попробуйте ещё раз через несколько секунд.',
        {type:cyclesApiUnavailable?'warn':'info'});
      return;
    }
    const year=+((ys&&ys.value)||state.ui.landingYear||2026);
    const q=b.dataset.q;
    const id=cycleId(year,q);
    try{
      if(state.cycles[id]){
        if(!piDataViews[id]) await loadPiDataView(id);
      }else{
        applyPiDataView(id,await cycleApi('/pi-cycle-data',{
          method:'POST',body:{year,quarter:q,start_date:null,sprint_count:6},
        }));
      }
    }
    catch(error){ reportCycleSyncError(error); return; }
    state.ui.mode='pi';
    state.ui.landingYear=year;
    state.ui.year=year; state.ui.quarter=q;
    activateCycle(id);
    try{
      await loadBacklogBoard();
      backlogApiReady=true;
    }catch(error){
      backlogApiReady=false;
      reportBacklogSyncError(error);
    }
    save(); render();
  });
}

