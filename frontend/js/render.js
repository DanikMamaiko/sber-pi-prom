/* =====================================================================
   РЕНДЕР: навигация
===================================================================== */
function renderNav(){
  const nav=$('#nav');
  const tabs=availablePiTabs();
  const active=state.ui.tab;
  nav.innerHTML=tabs.map(t=>`<div class="tab ${active===t.id?'active':''}" data-tab="${t.id}">${t.name}</div>`).join('');
  nav.querySelectorAll('.tab').forEach(el=>el.onclick=()=>{
    state.ui.tab=el.dataset.tab;
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
  if(!currentUser){renderLoginScreen();return;}
  const pos=captureViewPos();
  // попап фильтра живёт на body — закрываем его при любой перерисовке;
  // контекст таблиц пересобирают view-функции ниже
  closeColFilterPop(); colFilterCtx={};
  if(state.ui.mode==='budget')state.ui.mode=null;
  const cid=currentCycleId();
  // PI-цикл не выбран — показываем стартовую страницу выбора года/квартала
  if(state.ui.mode!=='pi' || !cid || !state.cycles[cid]){
    const nav=$('#nav'); if(nav) nav.innerHTML='';
    const app=$('#app'); app.innerHTML=viewLanding(); bindLanding();
    return;
  }
  activateCycle(cid);
  const tabs=availablePiTabs();
  if(!tabs.some(tab=>tab.id===state.ui.tab)){
    state.ui.tab=tabs.length?tabs[0].id:null;
    save(false);
  }
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
  applyAccessControls(app);
  restoreViewPos(pos);
}

/* =====================================================================
   ГЛАВНАЯ СТРАНИЦА — выбор PI-цикла (год + квартал)
===================================================================== */
function viewLanding(){
  const backendYears=Object.keys(state.cycles||{}).map(id=>+String(id).split('-')[0]).filter(Number.isFinite);
  const y=state.ui.landingYear||backendYears[0]||new Date().getFullYear();
  const nowYear=new Date().getFullYear();
  const years=[...new Set([nowYear,nowYear+1,nowYear+2,y,...backendYears])].sort((a,b)=>a-b);
  const yopts=years.map(v=>`<option value="${v}" ${v===y?'selected':''}>${v}</option>`).join('');
  const qs=['Q1','Q2','Q3','Q4'].map(q=>{
    const exists=!!state.cycles[cycleId(y,q)];
    const title=exists?'Открыть PI-цикл':'Создать и открыть PI-цикл';
    return `<button class="q-btn" data-q="${q}" title="${title}">${q}</button>`;
  }).join('');
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
              <div class="landing-card-sub">Раздел находится в разработке</div>
            </div>
            <div class="landing-card-mark">BYN</div>
          </div>
          <div class="landing-card-body">
            <div class="coming-soon"><span class="coming-soon-badge">В разработке</span><strong>Будет доступно позже</strong><p>Готовим единый контур оценки инициатив и управления бюджетом.</p></div>
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
  if(ys) ys.onchange=()=>{ state.ui.landingYear=+ys.value; save(false); render(); };
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
    b.disabled=true;
    try{
      await ensureNavigationCycle(year,q);
      state.ui.mode='pi';
      state.ui.landingYear=year;
      state.ui.year=year;state.ui.quarter=q;
      activateCycle(id);
      const tabs=availablePiTabs();
      if(!tabs.some(tab=>tab.id===state.ui.tab))state.ui.tab=tabs[0]&&tabs[0].id;
      await loadAuthorizedCycle(id);
    }
    catch(error){
      if(error.status!==401){
        console.error('PI cycle load failed',error);
        toast(error.status===403?'Раздел недоступен для вашей роли.':'Не удалось загрузить выбранный PI-цикл.',{type:'warn'});
      }
      state.ui.mode=null;state.ui.year=null;state.ui.quarter=null;
      if(currentUser){b.disabled=false;render();}
      return;
    }
    save(false);render();
  });
}

