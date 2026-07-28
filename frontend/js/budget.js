/* =====================================================================
   БЮДЖЕТИРОВАНИЕ
===================================================================== */
function budgetYear(){ return state.ui.budgetYear || state.ui.landingYear || 2026; }
function budgetData(){ return ensureBudgetYear(budgetYear()); }
function num(v){ return +String(v??'').replace(',','.') || 0; }
function fmtNum(v,d=1){ return (Math.round((+v||0)*Math.pow(10,d))/Math.pow(10,d)).toLocaleString('ru-RU'); }
function fmtMoney(v){ return Math.round(+v||0).toLocaleString('ru-RU'); }
function fmtMoneyK(v){ return fmtNum((+v||0)/1000,1); }
function todayISO(){ const d=new Date(); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
function budgetWorkdaysTotal(b=budgetData()){
  return BUDGET_MONTHS.reduce((s,[k])=>s+(+b.workdays[k]||0),0);
}
function budgetSHE(eff,b=budgetData()){
  const wd=budgetWorkdaysTotal(b);
  return wd ? (+eff||0)/wd : 0;
}
function budgetCompSHE(v,b=budgetData()){ return budgetSHE(v,b); }
function budgetVadarodValue(eff,b=budgetData()){
  return (+eff||0) * (+b.rateVadarod||0) * (+b.utilization||0);
}
function budgetTeamObjects(b=budgetData()){
  return (b.vadarodTeams||[])
    .map(t=>({tribe:String(t.tribe||'').trim(),name:String(t.team||'').trim()}))
    .filter(t=>t.tribe && t.name);
}
function budgetTribes(){
  const seen=[];
  budgetTeamObjects().forEach(t=>{ if(!seen.includes(t.tribe)) seen.push(t.tribe); });
  return seen;
}
function budgetTeamsOfTribe(tribe){
  return budgetTeamObjects().filter(t=>t.tribe===tribe);
}
function budgetTeamByName(name){
  return budgetTeamObjects().find(t=>t.name===name)||null;
}
function budgetFirstTeam(scope=budgetScope()){
  const teams=budgetTeamObjects();
  if(scope.team) return scope.team;
  if(scope.tribe){
    const t=budgetTeamsOfTribe(scope.tribe)[0];
    if(t) return t.name;
  }
  return (teams[0]&&teams[0].name)||'';
}
function makeBudgetExecutor(name){
  const comps={}; BUDGET_COMPS.forEach(c=>{ comps[c]=0; });
  return {team:name||'', comps, attractions:[]};
}
function teamTribe(name){
  const bt=budgetTeamByName(name);
  if(bt) return bt.tribe;
  if(state.ui && state.ui.mode==='budget') return '';
  const t=allCycleTeams().find(x=>x.name===name);
  return t && t.tribe || '';
}
function budgetCompValue(comps,comp){
  const c=comps||{};
  return comp==='DES' ? ((+c.DES||0)+(+c.DEV||0)) : (+c[comp]||0);
}
function emptyBudgetComps(){
  const out={}; BUDGET_COMPS.forEach(c=>out[c]=0); return out;
}
function addBudgetComps(dst,src,scale=1){
  BUDGET_COMPS.forEach(c=>{ dst[c]+=(+src[c]||0)*scale; });
  return dst;
}
function vadarodRowKey(r){ return `${r.tribe||''}||${r.team||''}`; }
function cloneVadarodRows(rows){
  return (rows||[]).map(r=>{
    const out={tribe:r.tribe||'',team:r.team||''};
    BUDGET_COMPS.forEach(c=>out[c]=+r[c]||0);
    return out;
  });
}
function syncVadarodRows(b){
  if(!b) return;
  const old=new Map((b.vadarodRows||[]).map(r=>[vadarodRowKey(r),r]));
  b.vadarodRows=(b.vadarodTeams||[]).map(t=>{
    const key=vadarodRowKey(t);
    const prev=old.get(key)||{};
    const row={tribe:t.tribe||'',team:t.team||''};
    BUDGET_COMPS.forEach(c=>row[c]=+prev[c]||0);
    return row;
  });
}
function latestVadarodSnapshot(b){
  const snaps=(b.vadarodSnapshots||[]).filter(s=>s.date).slice().sort((a,b)=>String(b.date).localeCompare(String(a.date)));
  return snaps[0]||null;
}
function selectedVadarodSnapshot(b,date){
  const snaps=b.vadarodSnapshots||[];
  if(date){
    const exact=snaps.find(s=>s.date===date);
    if(exact) return exact;
    const prev=snaps.filter(s=>s.date && s.date<=date).sort((a,b)=>String(b.date).localeCompare(String(a.date)))[0];
    if(prev) return prev;
  }
  return latestVadarodSnapshot(b);
}
function budgetOwnerInScope(it,scope=budgetScope()){
  if(!scope.tribe && !scope.team) return !!budgetTeamByName(it.owner);
  if(scope.team) return it.owner===scope.team;
  return teamTribe(it.owner)===scope.tribe;
}
function budgetScope(){
  let tribe=state.ui.budgetScopeTribe||null;
  let team=state.ui.budgetScopeTeam||null;
  if(tribe && !budgetTribes().includes(tribe)){ tribe=null; team=null; }
  if(team && !budgetTeamsOfTribe(tribe).some(t=>t.name===team)) team=null;
  return {tribe, team};
}
function executorInScope(ex,scope=budgetScope()){
  if(!scope.tribe && !scope.team) return true;
  if(scope.team) return ex.team===scope.team;
  return teamTribe(ex.team)===scope.tribe;
}
function itemInBudgetScope(it,scope=budgetScope()){
  if(!scope.tribe && !scope.team) return true;
  if(state.ui.budgetAssessMode==='vadarod' || state.ui.budgetAssessMode==='vendor') return budgetOwnerInScope(it,scope);
  if(scope.team) return it.owner===scope.team || issueExecTeams(it).includes(scope.team);
  return teamTribe(it.owner)===scope.tribe || issueExecutors(it).some(ex=>teamTribe(ex.team)===scope.tribe);
}
function budgetEffortForScope(it,scope=budgetScope()){
  return issueExecutors(it).reduce((sum,ex)=>{
    if(!executorInScope(ex,scope)) return sum;
    const comps=ex.comps||{};
    return sum+Object.keys(comps).reduce((s,k)=>s+(+comps[k]||0),0);
  },0);
}
function budgetCompForScope(it,comp,scope=budgetScope()){
  return issueExecutors(it).reduce((sum,ex)=>sum+(executorInScope(ex,scope)?budgetCompValue(ex.comps,comp):0),0);
}
function budgetAssessmentItems(year=budgetYear()){
  ensureBudgetYear(year);
  return budgetInitiativeItems(year).concat(budgetLegacyAssessmentItems(year));
}
function budgetInitiativeItems(year=budgetYear()){
  const b=ensureBudgetYear(year);
  return (b.vadarodInitiatives||[]).map(v=>{
    ensureBudgetInitiativeShape(v);
    return {kind:'vadarod',key:v._uid,it:v,a:v};
  });
}
function budgetLegacyAssessmentItems(year=budgetYear()){
  const b=ensureBudgetYear(year);
  const out=[];
  Object.keys(b.assessments||{}).forEach(key=>{
    const found=findBacklogByBudgetKey(key);
    if(!found) return;
    ensureBacklogShape(found.it);
    out.push({kind:'legacy-vadarod',key,tribe:found.tribe,it:found.it,a:ensureAssessmentShape(b.assessments[key])});
  });
  return out;
}
function budgetVendorItems(){
  const b=budgetData();
  return (b.vendorRows||[]).map(v=>{
    ensureVendorShape(v);
    return {kind:'vendor',key:v._uid,it:v,a:v};
  });
}
function filteredBudgetAssessmentItems(){
  const statuses=state.ui.budgetStatuses && state.ui.budgetStatuses.length ? state.ui.budgetStatuses : BUDGET_STATUSES;
  const scope=budgetScope();
  if((state.ui.budgetAssessMode||'vadarod')==='vendor'){
    return budgetVendorItems().filter(r=>statuses.includes(r.a.status) && budgetOwnerInScope(r.it,scope));
  }
  return budgetAssessmentItems().filter(r=>statuses.includes(r.a.status) && itemInBudgetScope(r.it,scope));
}
function assessmentBudgetSummary(rows,scope=budgetScope()){
  const b=budgetData();
  const mode=state.ui.budgetAssessMode||'vadarod';
  const totalEff=rows.reduce((s,r)=>s+(mode==='vadarod' ? budgetBaseEffort(r.it,scope) : budgetEffortForScope(r.it,scope)),0);
  const vendorCapex=rows.reduce((s,r)=>s+(+r.a.capex||0),0);
  const vendorOpex=rows.reduce((s,r)=>s+(+r.a.opex||0),0);
  const fin=rows.reduce((s,r)=>s+(+r.a.finEffect||0),0);
  const comps={}; BUDGET_COMPS.forEach(c=>comps[c]=rows.reduce((s,r)=>s+budgetBaseComp(r.it,c,scope),0));
  return {comps,totalEff,she:budgetSHE(totalEff,b),vadarod:budgetVadarodValue(totalEff,b),capex:vendorCapex,opex:vendorOpex,vendor:vendorCapex+vendorOpex,fin};
}
function budgetBaseExecutor(ex,scope=budgetScope()){
  if(!budgetTeamByName(ex.team)) return false;
  if(!scope.tribe && !scope.team) return true;
  if(scope.team) return ex.team===scope.team;
  return teamTribe(ex.team)===scope.tribe;
}
function budgetBaseEffort(it,scope=budgetScope()){
  return issueExecutors(it).reduce((sum,ex)=>{
    if(!budgetBaseExecutor(ex,scope)) return sum;
    const comps=ex.comps||{};
    return sum+BUDGET_COMPS.reduce((s,c)=>s+budgetCompValue(comps,c),0);
  },0);
}
function budgetBaseComp(it,comp,scope=budgetScope()){
  return issueExecutors(it).reduce((sum,ex)=>sum+(budgetBaseExecutor(ex,scope)?budgetCompValue(ex.comps,comp):0),0);
}
function budgetAttractionRows(rows,scope=budgetScope()){
  if(!scope.tribe && !scope.team) return [];
  const map=new Map();
  rows.forEach(r=>issueExecutors(r.it).forEach(ex=>{
    if(budgetBaseExecutor(ex,scope)) return;
    const team=ex.team||'—';
    const tr=teamTribe(team);
    if(!tr) return;
    const key=tr+'||'+team;
    if(!map.has(key)) map.set(key,{tribe:tr,team,eff:0});
    map.get(key).eff+=BUDGET_COMPS.reduce((s,c)=>s+budgetCompValue(ex.comps,c),0);
  }));
  return [...map.values()].sort((a,b)=>a.tribe.localeCompare(b.tribe,'ru')||a.team.localeCompare(b.team,'ru'));
}
function budgetScopeButtons(){
  const tribes=budgetTribes();
  const st=budgetScope();
  let html=`<div class="budget-control-panel">
    <div class="budget-control-row">
      <div class="budget-control-label">Тип бюджета</div>
      <div class="budget-scope budget-mode">
        <button class="${(state.ui.budgetAssessMode||'vadarod')==='vadarod'?'primary':''}" data-ba-mode="vadarod">Vadarod</button>
        <button class="${state.ui.budgetAssessMode==='vendor'?'primary':''}" data-ba-mode="vendor">Вендор</button>
      </div>
    </div>
    <div class="budget-control-row">
      <div class="budget-control-label">Уровень</div>
      <div class="budget-scope-stack">
      <div class="budget-scope">
    <button class="${!st.tribe&&!st.team?'primary':''}" data-ba-scope="bank">Общий бюджет на Банк</button>`;
  tribes.forEach(tr=>{
    html+=`<button class="${st.tribe===tr&&!st.team?'primary':''}" data-ba-scope="tribe" data-tribe="${esc(tr)}">${esc(tr)}</button>`;
  });
  html+=`</div>`;
  if(st.tribe){
    const teams=budgetTeamsOfTribe(st.tribe);
    html+=`<div class="budget-scope teams-line">`+
      teams.map(t=>`<button class="${st.team===t.name?'primary':''}" data-ba-scope="team" data-tribe="${esc(st.tribe)}" data-team="${esc(t.name)}">${esc(t.name)}</button>`).join('')+
      `</div>`;
  }
  return html+`</div></div></div>`;
}
function viewBudgetData(){
  const b=budgetData();
  syncVadarodRows(b);
  if(!b.vadarodSnapshotDate) b.vadarodSnapshotDate=todayISO();
  const months=BUDGET_MONTHS.map(([k,n])=>`
    <input data-bd-month="${k}" value="${esc(n)}" readonly>
    <input data-bd="workdays" data-k="${k}" type="number" min="0" value="${esc(b.workdays[k])}">`).join('');
  const teamRows=b.vadarodTeams.map((r,i)=>`<tr>
    <td><input data-bdt="${i}" data-k="tribe" value="${esc(r.tribe)}" placeholder="Трайб"></td>
    <td><input data-bdt="${i}" data-k="team" value="${esc(r.team)}" placeholder="Команда"></td>
    <td><button class="icon danger sm" data-bdt-del="${i}">✕</button></td>
  </tr>`).join('');
  const rows=b.vadarodRows.map((r,i)=>`<tr>
    <td>${esc(r.tribe||'—')}</td>
    <td>${esc(r.team||'—')}</td>
    ${BUDGET_COMPS.map(c=>`<td><input data-bdr="${i}" data-k="${c}" type="number" min="0" value="${esc(r[c])}"></td>`).join('')}
  </tr>`).join('');
  return `<div class="card budget-shell">
    <div class="flex-between"><h2>Данные для бюджетирования ${budgetBadge()}</h2></div>
    <div class="budget-data-layout">
      <div class="budget-block">
        <h3>Параметры расчета</h3>
        <label class="fld"><span class="lab">Ставка Vadarod</span><input data-bd="rateVadarod" type="number" min="0" value="${esc(b.rateVadarod)}"></label>
        <label class="fld"><span class="lab">Коэф. утилизации</span><input data-bd="utilization" type="number" min="0" step="0.01" value="${esc(b.utilization)}"></label>
      </div>
      <div class="budget-block">
        <h3>Введите данные по рабочему времени</h3>
        <div class="budget-months">${months}</div>
      </div>
      <div class="budget-block">
        <h3>Введите данные по командам <button class="plus" id="bdAddTeam">+</button></h3>
        <div class="prep-wrap"><table class="data-teams"><thead><tr><th>Трайб</th><th>Команда</th><th></th></tr></thead><tbody>
          ${teamRows||'<tr><td colspan="3" class="muted">Нет команд — добавьте строку.</td></tr>'}
        </tbody></table></div>
      </div>
    </div>
    <div class="budget-save-row">
      <h3>Данные по Vadarod</h3>
      <label class="inline-date"><span>Выберите дату фиксации состава Трайбов</span><input id="bdSnapshotDate" type="date" value="${esc(b.vadarodSnapshotDate)}"></label>
      <button id="bdSaveSnapshot">Сохранить</button>
    </div>
    <div class="prep-wrap"><table class="data-teams"><thead><tr><th>Трайб</th><th>Команда</th>${BUDGET_COMPS.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>
      ${rows||`<tr><td colspan="${BUDGET_COMPS.length+2}" class="muted">Нет строк — добавьте команды в блоке выше.</td></tr>`}
    </tbody></table></div>
  </div>`;
}
function bindBudgetData(){
  const b=budgetData();
  document.querySelectorAll('[data-bd]').forEach(el=>el.onchange=()=>{
    if(el.dataset.bd==='workdays') b.workdays[el.dataset.k]=num(el.value);
    else b[el.dataset.bd]=num(el.value);
    save(); render();
  });
  const addTeam=$('#bdAddTeam'); if(addTeam)addTeam.onclick=()=>{ b.vadarodTeams.push({tribe:'',team:''}); syncVadarodRows(b); save(); render(); };
  document.querySelectorAll('[data-bdt]').forEach(el=>el.onchange=()=>{
    const i=+el.dataset.bdt;
    const r=b.vadarodTeams[i]; if(!r) return;
    r[el.dataset.k]=el.value;
    const vr=b.vadarodRows[i]||{SA:0,DES:0,QA:0,FE:0,BE:0};
    vr.tribe=r.tribe||''; vr.team=r.team||'';
    BUDGET_COMPS.forEach(c=>{ if(!(c in vr)) vr[c]=0; });
    b.vadarodRows[i]=vr;
    syncVadarodRows(b);
    save(); render();
  });
  document.querySelectorAll('[data-bdt-del]').forEach(btn=>btn.onclick=()=>{
    b.vadarodTeams.splice(+btn.dataset.bdtDel,1);
    syncVadarodRows(b); save(); render();
  });
  document.querySelectorAll('[data-bdr]').forEach(el=>el.onchange=()=>{
    const r=b.vadarodRows[+el.dataset.bdr]; if(!r) return;
    r[el.dataset.k]=num(el.value);
    save();
  });
  const dt=$('#bdSnapshotDate'); if(dt)dt.onchange=()=>{ b.vadarodSnapshotDate=dt.value; save(); };
  const saveSnapshot=$('#bdSaveSnapshot'); if(saveSnapshot)saveSnapshot.onclick=()=>{
    const date=(($('#bdSnapshotDate')||{}).value||b.vadarodSnapshotDate||todayISO());
    b.vadarodSnapshotDate=date;
    const snap={date,rows:cloneVadarodRows(b.vadarodRows)};
    const ix=b.vadarodSnapshots.findIndex(s=>s.date===date);
    if(ix>=0) b.vadarodSnapshots[ix]=snap; else b.vadarodSnapshots.push(snap);
    state.ui.budgetCompositionDate=date;
    save(); render();
    toast(`Состав Vadarod сохранен на ${date}`,{type:'success',title:'Состав Vadarod'});
  };
}
function budgetExecutorHTML(it){
  return issueExecutors(it).map(ex=>`<div>${esc(ex.team||'—')}</div>`).join('')||'—';
}
function budgetCompsHTML(it){
  return issueExecutors(it).map(ex=>{
    const comps=ex.comps||{};
    const vals=Object.keys(comps).filter(k=>+comps[k]).map(k=>`${esc(k)} ${esc(comps[k])}`).join(' · ')||'—';
    return `<div><b>${esc(ex.team||'—')}</b>: ${vals}</div>`;
  }).join('')||'—';
}
function viewBudgetEffectForm(rows){
  if(!state.ui.budgetEffectOpen) return `<button id="baToggleEffect">Рассчитать фин. эффект по инициативе</button>`;
  const key=state.ui.budgetEffectKey && rows.some(r=>r.key===state.ui.budgetEffectKey) ? state.ui.budgetEffectKey : (rows[0]&&rows[0].key);
  state.ui.budgetEffectKey=key||null;
  const rec=rows.find(r=>r.key===key);
  if(!rec) return `<div class="budget-form"><button id="baToggleEffect">Скрыть расчет фин. эффекта</button><div class="muted" style="margin-top:10px">Нет инициатив для расчета.</div></div>`;
  const a=rec.a;
  const dataAttr=rec.kind==='vendor' ? 'data-bv' : 'data-ba';
  return `<div class="budget-form">
    <div class="row"><button id="baToggleEffect">Скрыть расчет фин. эффекта</button>
      <select id="baEffectIssue">${rows.map(r=>`<option value="${esc(r.key)}" ${r.key===key?'selected':''}>${esc(r.it.id||r.it.name||r.key)}</option>`).join('')}</select>
    </div>
    <label class="fld"><span class="lab">Опишите инициативу</span><input ${dataAttr}="${esc(key)}" data-k="valueDescription" value="${esc(a.valueDescription || rec.it.name)}"></label>
    <label class="fld"><span class="lab">ИИ-помощник</span><input value="ИИ-помощник" readonly></label>
    <label class="fld"><span class="lab">Категория фин. эффекта</span><select ${dataAttr}="${esc(key)}" data-k="finCategory">
      <option value=""></option>${FIN_CATEGORIES.map(x=>`<option ${a.finCategory===x?'selected':''}>${esc(x)}</option>`).join('')}
    </select></label>
    <label class="fld"><span class="lab">Фин. эффект, тыс. BYN</span><input ${dataAttr}="${esc(key)}" data-k="finEffect" type="number" value="${esc(a.finEffect)}"></label>
    <label class="fld"><span class="lab">Метод расчета</span><input ${dataAttr}="${esc(key)}" data-k="finMethod" value="${esc(a.finMethod)}"></label>
  </div>`;
}
function budgetAssessmentTopTable(rows,sum,scope,mode){
  const attrs=budgetAttractionRows(rows,scope);
  const showAttractions=!!(scope.tribe || scope.team);
  const attractionHtml=attrs.length
    ? attrs.map(a=>`<div class="budget-attraction-row"><span>${esc(a.team)}</span><span>${fmtNum(budgetSHE(a.eff),3)} ШЕ</span></div>`).join('')
    : `<div class="muted" style="font-size:12px">Нет привлечения</div>`;
  if(mode==='vendor'){
    return `<div class="budget-kpi-row">
      <div class="budget-kpi-field"><div class="budget-kpi-label">Трудозатраты, ШЕ</div><div class="budget-kpi-value">—</div></div>
      <div class="budget-kpi-field"><div class="budget-kpi-label">Бюджет, тыс. BYN</div><div class="budget-kpi-value">${fmtMoneyK(sum.vendor)}</div></div>
      <div class="budget-kpi-field"><div class="budget-kpi-label">Фин. эффект, тыс. BYN</div><div class="budget-kpi-value">${fmtNum(sum.fin,1)}</div></div>
      ${showAttractions?`<div class="budget-kpi-field"><div class="budget-kpi-label">Привлечение других команд</div><div class="budget-attraction-mini"><div class="muted" style="font-size:12px">Для Vendor не рассчитывается</div></div></div>`:''}
    </div>`;
  }
  return `<div class="budget-kpi-row">
    <div class="budget-kpi-field clickable" id="baEffortBreakdown" title="Показать распределение по компетенциям"><div class="budget-kpi-label">Трудозатраты, ШЕ</div><div class="budget-kpi-value">${fmtNum(sum.she,3)}</div></div>
    <div class="budget-kpi-field"><div class="budget-kpi-label">Бюджет, тыс. BYN</div><div class="budget-kpi-value">${fmtMoneyK(sum.vadarod)}</div></div>
    <div class="budget-kpi-field"><div class="budget-kpi-label">Фин. эффект, тыс. BYN</div><div class="budget-kpi-value">${fmtNum(sum.fin,1)}</div></div>
    ${showAttractions?`<div class="budget-kpi-field"><div class="budget-kpi-label">Привлечение других команд</div><div class="budget-attraction-mini">${attractionHtml}</div></div>`:''}
  </div>`;
}
function budgetVadarodRowHTML(r,b){
  const it=r.it,a=r.a,eff=budgetBaseEffort(it,budgetScope()),she=budgetSHE(eff,b),vad=budgetVadarodValue(eff,b);
  return `<tr class="budget-assessment-row" data-ba-open-card="${esc(r.key)}" data-ba-kind="${esc(r.kind||'vadarod')}">
    <td>${esc(it.id||'—')}</td>
    <td>${esc(it.name||'—')}</td>
    <td class="budget-desc">${esc(it.description||a.valueDescription||'')}</td>
    <td>${fmtNum(she,3)}</td>
    <td>${fmtMoneyK(vad)}</td>
    <td>${fmtNum(a.finEffect,1)}</td>
    <td><select class="budget-inline-field" data-ba="${esc(r.key)}" data-ba-kind="${esc(r.kind||'vadarod')}" data-k="status">${BUDGET_STATUSES.map(x=>`<option ${a.status===x?'selected':''}>${esc(x)}</option>`).join('')}</select></td>
    <td><input class="budget-inline-field" data-ba="${esc(r.key)}" data-ba-kind="${esc(r.kind||'vadarod')}" data-k="comment" value="${esc(a.comment)}"></td>
  </tr>`;
}
function budgetVendorRowHTML(r){
  const it=r.it,a=r.a,vendor=(+a.capex||0)+(+a.opex||0);
  return `<tr class="budget-assessment-row" data-ba-open-card="${esc(r.key)}" data-ba-kind="vendor">
    <td>${esc(it.id||'—')}</td>
    <td>${esc(it.name||'—')}</td>
    <td class="budget-desc">${esc(it.description||a.workDescription||'')}</td>
    <td>—</td>
    <td>${fmtMoneyK(vendor)}</td>
    <td>${fmtNum(a.finEffect,1)}</td>
    <td><select class="budget-inline-field" data-bv="${esc(r.key)}" data-k="status">${BUDGET_STATUSES.map(x=>`<option ${a.status===x?'selected':''}>${esc(x)}</option>`).join('')}</select></td>
    <td><input class="budget-inline-field" data-bv="${esc(r.key)}" data-k="comment" value="${esc(a.comment)}"></td>
  </tr>`;
}
function newBudgetVadarodInitiative(scope=budgetScope()){
  const owner=budgetFirstTeam(scope);
  return ensureBudgetInitiativeShape({
    id:'INIT-'+uid().slice(1,6).toUpperCase(),
    name:'',
    owner,
    status:'На рассмотрении',
    executors:[makeBudgetExecutor(owner)],
  });
}
function newVendorRow(scope=budgetScope()){
  const teams=budgetTeamObjects();
  const owner=scope.team || (scope.tribe && (budgetTeamsOfTribe(scope.tribe)[0]||{}).name) || (teams[0]||{}).name || '';
  return ensureVendorShape({
    id:'VENDOR-'+uid().slice(1,6).toUpperCase(),
    name:'',
    product:'',
    owner,
    type:'',
    status:'На рассмотрении',
  });
}
const BA_FILTER_COLS=[
  {k:'status',label:'Статус оценки',val:r=>r.a.status},
];
function viewBudgetAssessment(){
  const baseRows=filteredBudgetAssessmentItems();
  const scope=budgetScope();
  const mode=state.ui.budgetAssessMode||'vadarod';
  const allRows=mode==='vendor' ? budgetVendorItems() : budgetAssessmentItems();
  const sum=assessmentBudgetSummary(baseRows,scope);
  const b=budgetData();
  colFilterCtx['ba']={rows:baseRows, cols:BA_FILTER_COLS};
  let rows=applyColFilters(baseRows,BA_FILTER_COLS,'ba');
  rows=applyColSort(rows,BA_FILTER_COLS,'ba');
  const statusHtml=BUDGET_STATUSES.map(s=>`<label><input type="checkbox" data-ba-status="${esc(s)}" ${state.ui.budgetStatuses.includes(s)?'checked':''}>${esc(s)}</label>`).join('');
  const body=mode==='vendor' ? rows.map(budgetVendorRowHTML).join('') : rows.map(r=>budgetVadarodRowHTML(r,b)).join('');
  const heads=`<th>№ Инициативы</th><th>Название инициативы</th><th>Описание инициативы</th><th>Трудозатраты, ШЕ</th><th>Бюджет (тыс. BYN)</th><th>Фин. эффект (тыс. BYN)</th>${filterThHTML(BA_FILTER_COLS[0],'ba')}<th>Комментарий</th>`;
  const colspan=8;
  return `<div class="card budget-shell">
    <div class="flex-between"><h2>Оценка инициатив ${budgetBadge()}</h2><button id="baToBudget">Сформировать бюджет</button></div>
    ${budgetScopeButtons()}
    <div class="status-checks"><span class="muted">Включить в расчет инициативы со статусом</span>${statusHtml}</div>
    ${budgetAssessmentTopTable(baseRows,sum,scope,mode)}
    <div class="row" style="justify-content:flex-end;margin:0 0 12px"><button class="primary" id="baAddInitiative">Добавить инициативу</button></div>
    ${tableToolsBarHTML('ba')}
    <div class="prep-wrap" data-scroll-key="ba"><table class="budget-table"><thead><tr>${heads}</tr></thead><tbody>${body||`<tr><td colspan="${colspan}" class="muted">${allRows.length?'Нет инициатив под выбранные статусы/уровень.':(mode==='vendor'?'Нет Vendor-инициатив — добавьте строку вручную.':'Нет инициатив — добавьте строку вручную.')}</td></tr>`}</tbody></table></div>
    <div class="note budget-wide-note" style="margin-top:8px">${mode==='vendor'?'Vendor считается как Capex + Opex; бюджет в основной таблице показан в тыс. BYN.':'Инициативы создаются на этой вкладке. Бюджет Vadarod считается автоматически: трудозатраты в чел/дн × ставка Vadarod × коэф. утилизации, затем переводится в тыс. BYN.'}</div>
  </div>`;
}
function budgetRecordByKey(kind,key){
  const b=budgetData();
  if(kind==='vendor') return budgetVendorItems().find(r=>r.key===key)||null;
  if(kind==='legacy-vadarod') return budgetLegacyAssessmentItems().find(r=>r.key===key)||null;
  return budgetInitiativeItems().find(r=>r.key===key)||null;
}
function budgetSetAssessmentField(kind,key,k,value){
  const rec=budgetRecordByKey(kind,key); if(!rec) return;
  if(kind==='vendor'){
    if(['capex','opex','finEffect'].includes(k)) rec.it[k]=num(value); else rec.it[k]=value;
    ensureVendorShape(rec.it);
  }else if(kind==='legacy-vadarod'){
    if(['finEffect'].includes(k)) rec.a[k]=num(value); else rec.a[k]=value;
    ensureAssessmentShape(rec.a);
  }else{
    if(['finEffect'].includes(k)) rec.it[k]=num(value); else rec.it[k]=value;
    ensureBudgetInitiativeShape(rec.it);
  }
}
function bindBudgetAssessment(){
  const b=budgetData();
  bindColFilters();
  const add=$('#baAddInitiative'); if(add)add.onclick=()=>{
    const mode=state.ui.budgetAssessMode||'vadarod';
    let rec;
    if(mode==='vendor'){
      rec=newVendorRow();
      b.vendorRows.push(rec);
      save(); render();
      openBudgetInitiativeModal(rec._uid,'vendor');
    }else{
      rec=newBudgetVadarodInitiative();
      b.vadarodInitiatives.push(rec);
      save(); render();
      openBudgetInitiativeModal(rec._uid,'vadarod');
    }
  };
  document.querySelectorAll('[data-ba-mode]').forEach(btn=>btn.onclick=()=>{
    state.ui.budgetAssessMode=btn.dataset.baMode;
    clearColState('ba');
    save(); render();
  });
  document.querySelectorAll('[data-ba-scope]').forEach(btn=>btn.onclick=()=>{
    const s=btn.dataset.baScope;
    if(s==='bank'){ state.ui.budgetScopeTribe=null; state.ui.budgetScopeTeam=null; }
    if(s==='tribe'){ state.ui.budgetScopeTribe=btn.dataset.tribe; state.ui.budgetScopeTeam=null; }
    if(s==='team'){ state.ui.budgetScopeTribe=btn.dataset.tribe; state.ui.budgetScopeTeam=btn.dataset.team; }
    save(); render();
  });
  document.querySelectorAll('[data-ba-status]').forEach(el=>el.onchange=()=>{
    const picked=[...document.querySelectorAll('[data-ba-status]:checked')].map(x=>x.dataset.baStatus);
    state.ui.budgetStatuses=picked.length?picked:BUDGET_STATUSES.slice();
    save(); render();
  });
  document.querySelectorAll('[data-ba]').forEach(el=>el.onchange=()=>{
    budgetSetAssessmentField(el.dataset.baKind||'vadarod',el.dataset.ba,el.dataset.k,el.value);
    save(); render();
  });
  document.querySelectorAll('[data-bv]').forEach(el=>el.onchange=()=>{
    budgetSetAssessmentField('vendor',el.dataset.bv,el.dataset.k,el.value);
    save(); render();
  });
  document.querySelectorAll('.budget-inline-field').forEach(el=>el.onclick=e=>e.stopPropagation());
  document.querySelectorAll('[data-ba-open-card]').forEach(row=>row.onclick=()=>{
    openBudgetInitiativeModal(row.dataset.baOpenCard,row.dataset.baKind||'vadarod');
  });
  const effort=$('#baEffortBreakdown'); if(effort)effort.onclick=()=>openBudgetEffortBreakdownModal(filteredBudgetAssessmentItems(),budgetScope());
  const toBudget=$('#baToBudget'); if(toBudget)toBudget.onclick=()=>{ state.ui.budgetTab='budget'; save(); render(); };
}
function budgetScopeTitle(scope=budgetScope()){
  if(scope.team) return scope.team;
  if(scope.tribe) return scope.tribe;
  return 'Общие по Банку';
}
function openBudgetEffortBreakdownModal(rows,scope=budgetScope()){
  const comps=['SA','DES','FE','BE','QA'];
  const root=$('#modalRoot');
  const body=comps.map(c=>{
    const chd=rows.reduce((s,r)=>s+budgetBaseComp(r.it,c,scope),0);
    return `<tr><td>${esc(c)}</td><td>${fmtNum(budgetSHE(chd),3)}</td></tr>`;
  }).join('');
  root.innerHTML=`<div class="overlay"><div class="modal budget-modal-mid">
    <h3>Трудозатраты · ${esc(budgetScopeTitle(scope))}</h3>
    <div class="prep-wrap"><table class="data-teams"><thead><tr><th>Компетенция</th><th>ШЕ</th></tr></thead><tbody>${body}</tbody></table></div>
    <div class="modal-actions"><button id="bem_close">Закрыть</button></div>
  </div></div>`;
  $('#bem_close').onclick=()=>root.innerHTML='';
}
function budgetIssueLinksTarget(rec){ return rec && rec.it; }
function budgetEnsureRecordExecutors(rec){
  if(!rec || rec.kind==='vendor') return;
  const it=rec.it;
  ensureBudgetInitiativeShape(it);
  if(!it.executors.length) it.executors.push(makeBudgetExecutor(it.owner||budgetFirstTeam()));
}
function budgetModalTeamOptions(selected){
  return teamOptionsHTML(budgetTeamObjects(),selected,true);
}
function budgetModalEffortHTML(rec){
  if(rec.kind==='vendor') return '';
  budgetEnsureRecordExecutors(rec);
  const it=rec.it;
  const she=!!state.ui.budgetInitiativeSheMode;
  const unit=she?'ШЕ':'ч/дн';
  const ro=she?'readonly title="В режиме ШЕ доступно только отображение"':'';
  const rows=issueExecutors(it).map((ex,ei)=>{
    const total=BUDGET_COMPS.reduce((s,c)=>s+budgetCompValue(ex.comps,c),0);
    return `<tr>
      <td><select id="bm_exec_${ei}">${budgetModalTeamOptions(ex.team)}</select>${it.executors.length>1?`<button class="icon danger sm" data-bm-exec-del="${ei}" title="Удалить исполнителя">✕</button>`:''}</td>
      ${BUDGET_COMPS.map(c=>{
        const raw=budgetCompValue(ex.comps,c);
        const val=she?budgetSHE(raw):raw;
        return `<td><input id="bm_comp_${ei}_${c}" type="number" min="0" step="${she?'0.001':'1'}" value="${esc(she?(Math.round(val*1000)/1000):raw)}" ${ro}></td>`;
      }).join('')}
      <td class="budget-effort-total">${fmtNum(she?budgetSHE(total):total,she?3:1)}</td>
    </tr>`;
  }).join('');
  return `<div class="budget-modal-section">
    <h4>Трудозатраты</h4>
    <label class="tag-check" style="margin-bottom:10px"><input id="bm_she_mode" type="checkbox" ${she?'checked':''}>Пересчитать в ШЕ</label>
    <div class="prep-wrap"><table class="budget-effort-matrix"><thead><tr><th>Команда-исполнитель</th>${BUDGET_COMPS.map(c=>`<th>${c}, ${unit}</th>`).join('')}<th>Общие, ${unit}</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="budget-link-actions"><button id="bm_add_exec" class="plus sm">+ Команда-исполнитель</button></div>
  </div>`;
}
function budgetModalVendorHTML(rec){
  if(rec.kind!=='vendor') return '';
  const a=rec.a, vendor=(+a.capex||0)+(+a.opex||0);
  return `<div class="budget-modal-section">
    <h4>Vendor</h4>
    <div class="budget-modal-grid">
      <label><span>Вендор</span><input id="bm_vendor" value="${esc(a.vendor)}"></label>
      <label><span>Бюджет, тыс. BYN</span><input value="${esc(fmtMoneyK(vendor))}" readonly></label>
      <label><span>Capex, BYN</span><input id="bm_capex" type="number" value="${esc(a.capex)}"></label>
      <label><span>Opex, BYN</span><input id="bm_opex" type="number" value="${esc(a.opex)}"></label>
    </div>
    <label><span>Описание работ</span><textarea id="bm_workDescription" rows="2">${esc(a.workDescription)}</textarea></label>
  </div>`;
}
function budgetModalEffectHTML(rec){
  const a=rec.a;
  return `<div class="budget-modal-section">
    <h4>Эффект/Ценность</h4>
    <button id="bm_calc_effect" style="margin-bottom:10px">Рассчитать фин. эффект по инициативе</button>
    <div class="budget-modal-grid">
      <label><span>Категория фин. эффекта</span><select id="bm_finCategory"><option value=""></option>${FIN_CATEGORIES.map(x=>`<option ${a.finCategory===x?'selected':''}>${esc(x)}</option>`).join('')}</select></label>
      <label><span>Фин. эффект, тыс. BYN</span><input id="bm_finEffect" type="number" value="${esc(a.finEffect)}"></label>
      <label><span>Фин. эффект (метод расчета)</span><input id="bm_finMethod" value="${esc(a.finMethod)}"></label>
      <label><span>Ценность инициативы</span><input id="bm_valueDescription" value="${esc(a.valueDescription)}"></label>
    </div>
  </div>`;
}
function budgetModalIssueLinksHTML(rec){
  const target=budgetIssueLinksTarget(rec);
  ensureIssueLinksShape(target);
  const rows=target.issueLinks.map((l,i)=>`<tr>
    <td><input id="bm_link_id_${i}" value="${esc(l.id)}" placeholder="ID Issue"></td>
    <td><input id="bm_link_total_${i}" type="number" min="0" value="${esc(l.totalEffort)}"></td>
    <td><select id="bm_link_team_${i}">${budgetModalTeamOptions(l.team)}</select></td>
    ${BUDGET_COMPS.map(c=>`<td><input id="bm_link_comp_${i}_${c}" type="number" min="0" value="${esc(l.comps[c]||0)}"></td>`).join('')}
    <td><button class="row-del" data-bm-link-del="${i}" title="Удалить связь">✕</button></td>
  </tr>`).join('');
  return `<div class="budget-modal-section">
    <h4>Связь с Issues</h4>
    <div class="budget-link-actions"><button id="bm_add_link" class="plus sm">+ Issue</button></div>
    <div class="prep-wrap"><table class="budget-issue-links"><thead><tr><th>ID Issue</th><th>Общая оценка (чел/дн)</th><th>Команда-исполнитель</th>${BUDGET_COMPS.map(c=>`<th>${c}</th>`).join('')}<th></th></tr></thead><tbody>${rows||`<tr><td colspan="${BUDGET_COMPS.length+4}" class="muted">Связи не добавлены.</td></tr>`}</tbody></table></div>
  </div>`;
}
function budgetModalHTML(rec){
  const it=rec.it,a=rec.a;
  return `<div class="overlay"><div class="modal budget-modal-wide">
    <h3>${rec.kind==='vendor'?'Vendor':'Vadarod'} · ${esc(it.id||'Новая инициатива')}</h3>
    <div class="budget-modal-grid">
      <label><span>№ Инициативы</span><input id="bm_id" value="${esc(it.id)}"></label>
      <label><span>Название</span><input id="bm_name" value="${esc(it.name)}"></label>
      <label><span>Команда-владелец</span><select id="bm_owner">${budgetModalTeamOptions(it.owner)}</select></label>
      <label><span>Тип инициативы</span><input id="bm_type" value="${esc(it.type)}"></label>
      <label><span>Продукт</span><input id="bm_product" value="${esc(it.product)}"></label>
      <label><span>Статус оценки</span><select id="bm_status">${BUDGET_STATUSES.map(x=>`<option ${a.status===x?'selected':''}>${esc(x)}</option>`).join('')}</select></label>
    </div>
    <label><span>Описание</span><textarea id="bm_description" rows="2">${esc(it.description||'')}</textarea></label>
    ${budgetModalEffortHTML(rec)}
    ${budgetModalVendorHTML(rec)}
    ${budgetModalEffectHTML(rec)}
    <div class="budget-modal-section">
      <label><span>Комментарий</span><input id="bm_comment" value="${esc(a.comment)}"></label>
    </div>
    ${budgetModalIssueLinksHTML(rec)}
    <div class="budget-modal-actions">
      <button class="danger" id="bm_delete">Удалить</button>
      <div style="display:flex;gap:10px"><button id="bm_cancel">Отмена</button><button class="primary" id="bm_save">Сохранить</button></div>
    </div>
  </div></div>`;
}
function saveBudgetInitiativeModal(rec){
  const it=rec.it,a=rec.a;
  ['id','name','description','product','owner','type'].forEach(k=>{
    const el=$('#bm_'+k); if(el) it[k]=el.value;
  });
  if($('#bm_status')) a.status=$('#bm_status').value;
  if($('#bm_finCategory')) a.finCategory=$('#bm_finCategory').value;
  if($('#bm_finEffect')) a.finEffect=num($('#bm_finEffect').value);
  if($('#bm_finMethod')) a.finMethod=$('#bm_finMethod').value;
  if($('#bm_valueDescription')) a.valueDescription=$('#bm_valueDescription').value;
  if($('#bm_comment')) a.comment=$('#bm_comment').value;
  if(rec.kind==='vendor'){
    ['vendor','workDescription'].forEach(k=>{ const el=$('#bm_'+k); if(el) a[k]=el.value; });
    if($('#bm_capex')) a.capex=num($('#bm_capex').value);
    if($('#bm_opex')) a.opex=num($('#bm_opex').value);
    ensureVendorShape(it);
  }else{
    if(!state.ui.budgetInitiativeSheMode){
      issueExecutors(it).forEach((ex,ei)=>{
        const team=$('#bm_exec_'+ei); if(team) ex.team=team.value;
        ex.comps=ex.comps||{};
        BUDGET_COMPS.forEach(c=>{ const el=$('#bm_comp_'+ei+'_'+c); if(el) ex.comps[c]=num(el.value); });
      });
    }
    if(rec.kind==='legacy-vadarod') ensureBacklogShape(it); else ensureBudgetInitiativeShape(it);
    ensureAssessmentShape(a);
  }
  const target=budgetIssueLinksTarget(rec);
  ensureIssueLinksShape(target);
  target.issueLinks.forEach((l,i)=>{
    const id=$('#bm_link_id_'+i); if(id) l.id=id.value;
    const total=$('#bm_link_total_'+i); if(total) l.totalEffort=num(total.value);
    const team=$('#bm_link_team_'+i); if(team) l.team=team.value;
    l.comps=l.comps||{};
    BUDGET_COMPS.forEach(c=>{ const el=$('#bm_link_comp_'+i+'_'+c); if(el) l.comps[c]=num(el.value); });
  });
}
function deleteBudgetRecord(rec){
  const b=budgetData();
  if(rec.kind==='vendor'){
    const ix=b.vendorRows.findIndex(x=>x._uid===rec.key); if(ix>=0) b.vendorRows.splice(ix,1);
  }else if(rec.kind==='legacy-vadarod'){
    delete b.assessments[rec.key];
  }else{
    const ix=b.vadarodInitiatives.findIndex(x=>x._uid===rec.key); if(ix>=0) b.vadarodInitiatives.splice(ix,1);
  }
}
function openBudgetInitiativeModal(key,kind){
  let rec=budgetRecordByKey(kind,key); if(!rec) return;
  if(rec.kind!=='vendor') budgetEnsureRecordExecutors(rec);
  const root=$('#modalRoot');
  root.innerHTML=budgetModalHTML(rec);
  const rerender=()=>{ rec=budgetRecordByKey(rec.kind,key); root.innerHTML=budgetModalHTML(rec); bindBudgetInitiativeModal(rec,key,rerender); };
  bindBudgetInitiativeModal(rec,key,rerender);
}
function bindBudgetInitiativeModal(rec,key,rerender){
  const root=$('#modalRoot');
  $('#bm_cancel').onclick=()=>root.innerHTML='';
  $('#bm_save').onclick=()=>{ saveBudgetInitiativeModal(rec); save(); root.innerHTML=''; render(); };
  $('#bm_delete').onclick=()=>{ deleteBudgetRecord(rec); save(); root.innerHTML=''; render(); };
  const she=$('#bm_she_mode'); if(she)she.onchange=()=>{ saveBudgetInitiativeModal(rec); state.ui.budgetInitiativeSheMode=she.checked; save(); rerender(); };
  const addExec=$('#bm_add_exec'); if(addExec)addExec.onclick=()=>{ saveBudgetInitiativeModal(rec); rec.it.executors.push(makeBudgetExecutor(budgetFirstTeam())); save(); rerender(); };
  root.querySelectorAll('[data-bm-exec-del]').forEach(btn=>btn.onclick=()=>{ saveBudgetInitiativeModal(rec); rec.it.executors.splice(+btn.dataset.bmExecDel,1); if(!rec.it.executors.length) rec.it.executors.push(makeBudgetExecutor(budgetFirstTeam())); save(); rerender(); });
  const addLink=$('#bm_add_link'); if(addLink)addLink.onclick=()=>{ saveBudgetInitiativeModal(rec); const t=budgetIssueLinksTarget(rec); t.issueLinks.push(ensureIssueLinkShape({team:budgetFirstTeam()})); save(); rerender(); };
  root.querySelectorAll('[data-bm-link-del]').forEach(btn=>btn.onclick=()=>{ saveBudgetInitiativeModal(rec); const t=budgetIssueLinksTarget(rec); t.issueLinks.splice(+btn.dataset.bmLinkDel,1); save(); rerender(); });
  const calc=$('#bm_calc_effect'); if(calc)calc.onclick=()=>toast('Расчет финансового эффекта заполняется вручную',{type:'info',title:'Фин. эффект'});
}
function compTotal(row){ return BUDGET_COMPS.reduce((s,c)=>s+(+row[c]||0),0); }
function approvedBudgetItems(){
  return budgetAssessmentItems().filter(r=>r.a.status==='Одобрена');
}
function vadarodPlanByTeam(){
  const b=budgetData();
  const wd=budgetWorkdaysTotal(b);
  const map=new Map();
  approvedBudgetItems().forEach(r=>{
    issueExecutors(r.it).forEach(ex=>{
      if(!budgetTeamByName(ex.team)) return;
      const team=ex.team||'—';
      const tribe=teamTribe(team)||r.tribe||'—';
      const key=tribe+'||'+team;
      if(!map.has(key)) map.set(key,{tribe,team,comps:emptyBudgetComps()});
      const rec=map.get(key);
      BUDGET_COMPS.forEach(c=>{ rec.comps[c]+=wd ? budgetCompValue(ex.comps,c)/wd : 0; });
    });
  });
  return map;
}
function budgetCompositionDate(b){
  if(state.ui.budgetCompositionDate) return state.ui.budgetCompositionDate;
  const latest=latestVadarodSnapshot(b);
  return latest ? latest.date : (b.vadarodSnapshotDate || todayISO());
}
function currentVadarodRowsForDate(b,date){
  const snap=selectedVadarodSnapshot(b,date);
  return cloneVadarodRows(snap ? snap.rows : b.vadarodRows);
}
function vadarodCompositionRows(){
  const b=budgetData();
  syncVadarodRows(b);
  const date=budgetCompositionDate(b);
  const current=currentVadarodRowsForDate(b,date);
  const plan=vadarodPlanByTeam();
  const map=new Map();
  current.forEach(r=>{
    const key=vadarodRowKey(r);
    map.set(key,{tribe:r.tribe||'—',team:r.team||'—',current:cloneVadarodRows([r])[0],plan:emptyBudgetComps(),vac:emptyBudgetComps()});
  });
  plan.forEach((p,key)=>{
    if(!map.has(key)){
      const row={tribe:p.tribe,team:p.team}; BUDGET_COMPS.forEach(c=>row[c]=0);
      map.set(key,{tribe:p.tribe,team:p.team,current:row,plan:emptyBudgetComps(),vac:emptyBudgetComps()});
    }
    map.get(key).plan=p.comps;
  });
  map.forEach(r=>{
    BUDGET_COMPS.forEach(c=>{ r.vac[c]=(+r.plan[c]||0)-(+r.current[c]||0); });
  });
  return [...map.values()].sort((a,b)=>a.tribe.localeCompare(b.tribe,'ru')||a.team.localeCompare(b.team,'ru'));
}
function aggregateCompositionByTribe(rows){
  const map=new Map();
  rows.forEach(r=>{
    if(!map.has(r.tribe)) map.set(r.tribe,{tribe:r.tribe,current:emptyBudgetComps(),plan:emptyBudgetComps(),vac:emptyBudgetComps()});
    const rec=map.get(r.tribe);
    addBudgetComps(rec.current,r.current);
    addBudgetComps(rec.plan,r.plan);
    addBudgetComps(rec.vac,r.vac);
  });
  return [...map.values()].sort((a,b)=>a.tribe.localeCompare(b.tribe,'ru'));
}
function totalCompositionRows(rows){
  return rows.reduce((acc,r)=>{
    addBudgetComps(acc.current,r.current);
    addBudgetComps(acc.plan,r.plan);
    addBudgetComps(acc.vac,r.vac);
    return acc;
  },{current:emptyBudgetComps(),plan:emptyBudgetComps(),vac:emptyBudgetComps()});
}
function metricClass(v,base){
  const n=+v||0;
  return `${base} ${n>0?'num-pos':(n<0?'num-neg':'num-zero')}`;
}
function compCells(row,cls='',opts={}){
  const base=opts.base||'';
  const start=opts.start?' group-start':'';
  return BUDGET_COMPS.map((c,i)=>`<td class="${cls} ${metricClass(row[c],base)}${i===0?start:''}">${fmtNum(row[c],2)}</td>`).join('')+
    `<td class="${cls} ${metricClass(compTotal(row),base)} strong-cell">${fmtNum(compTotal(row),2)}</td>`;
}
function vadarodCompositionTable(rows,byTeams,date){
  const total=totalCompositionRows(rows);
  const leading=byTeams ? '<th rowspan="2">Трайб</th><th rowspan="2">Команда</th>' : '<th rowspan="2">Трайб</th>';
  const body=rows.map(r=>`<tr>
    <td><div class="row-title">${esc(r.tribe)}</div></td>${byTeams?`<td><div class="row-title">${esc(r.team)}</div></td>`:''}
    ${compCells(r.current,'',{base:'metric-current',start:true})}${compCells(r.plan,'',{base:'metric-plan',start:true})}${compCells(r.vac,'',{base:'metric-vac',start:true})}
  </tr>`).join('');
  const totalLead=byTeams ? `<td colspan="2">Итого по Vadarod</td>` : `<td>Итого по Vadarod</td>`;
  return `<div class="prep-wrap" data-scroll-key="bvt"><table class="budget-table budget-composition-table"><thead>
    <tr>${leading}<th class="group-head group-current group-start" colspan="6">Текущий состав <input class="head-date" id="bvtDateHead" type="date" value="${esc(date)}"></th><th class="group-head group-plan group-start" colspan="6">План, ШЕ</th><th class="group-head group-vac group-start" colspan="6">Вакансии, ШЕ</th></tr>
    <tr>${['metric-current','metric-plan','metric-vac'].map((base,gi)=>BUDGET_COMPS.map((c,i)=>`<th class="${base}${i===0?' group-start':''}">${c}</th>`).join('')+`<th class="${base}">Итого</th>`).join('')}</tr>
  </thead><tbody>
    ${body||`<tr><td colspan="${byTeams?20:19}" class="muted">Нет данных Vadarod.</td></tr>`}
    <tr class="total-row">${totalLead}${compCells(total.current,'total-lite',{base:'metric-current',start:true})}${compCells(total.plan,'total-lite',{base:'metric-plan',start:true})}${compCells(total.vac,'total-strong',{base:'metric-vac',start:true})}</tr>
  </tbody></table></div>`;
}
function viewBudgetVadarodTeams(){
  const b=budgetData();
  const date=budgetCompositionDate(b);
  const byTeams=state.ui.budgetVadarodView==='team';
  const teamRows=vadarodCompositionRows();
  const rows=byTeams ? teamRows : aggregateCompositionByTribe(teamRows);
  return `<div class="card budget-shell">
    <div class="flex-between"><h2>Состав команд Vadarod ${budgetBadge()}</h2></div>
    <h3>Данные по Vadarod</h3>
    <div class="budget-control-panel">
      <div class="budget-control-row">
        <div class="budget-control-label">Представление</div>
        <div class="budget-scope">
          <button class="${!byTeams?'primary':''}" data-bvt-view="tribe">По Трайбам</button>
          <button class="${byTeams?'primary':''}" data-bvt-view="team">По командам</button>
        </div>
      </div>
    </div>
    ${vadarodCompositionTable(rows,byTeams,date)}
  </div>`;
}
function bindBudgetVadarodTeams(){
  document.querySelectorAll('[data-bvt-view]').forEach(btn=>btn.onclick=()=>{
    state.ui.budgetVadarodView=btn.dataset.bvtView;
    save(); render();
  });
  const dt=$('#bvtDateHead'); if(dt)dt.onchange=()=>{ state.ui.budgetCompositionDate=dt.value; save(); render(); };
}
function viewBudget(){
  const b=budgetData();
  const approved=budgetAssessmentItems().filter(r=>r.a.status==='Одобрена' && budgetOwnerInScope(r.it,{tribe:null,team:null}));
  const vMap=new Map();
  approved.forEach(r=>issueExecutors(r.it).forEach(ex=>{
    if(!budgetTeamByName(ex.team)) return;
    const tr=teamTribe(ex.team)||r.tribe;
    const key=tr+'||'+ex.team;
    if(!vMap.has(key)) vMap.set(key,{tribe:tr,team:ex.team,comps:{SA:0,DES:0,QA:0,FE:0,BE:0}});
    const row=vMap.get(key);
    BUDGET_COMPS.forEach(c=>row.comps[c]+=budgetCompValue(ex.comps,c));
  }));
  const vRows=[...vMap.values()];
  const vBody=vRows.map(r=>{
    const eff=BUDGET_COMPS.reduce((s,c)=>s+r.comps[c],0);
    return `<tr><td>${esc(r.tribe)}</td><td>${esc(r.team)}</td>${BUDGET_COMPS.map(c=>`<td>${fmtNum(budgetCompSHE(r.comps[c],b),3)}</td>`).join('')}<td>${fmtNum(budgetSHE(eff,b),3)}</td><td>${fmtMoneyK(budgetVadarodValue(eff,b))}</td></tr>`;
  }).join('');
  const vendorMap=new Map();
  const approvedVendor=budgetVendorItems().filter(r=>r.a.status==='Одобрена' && budgetOwnerInScope(r.it,{tribe:null,team:null}));
  approvedVendor.forEach(r=>{
    const vendor=r.a.vendor||'—';
    const key=(teamTribe(r.it.owner)||'—')+'||'+r.it.owner+'||'+vendor;
    if(!vendorMap.has(key)) vendorMap.set(key,{tribe:teamTribe(r.it.owner)||'—',team:r.it.owner,vendor,capex:0,opex:0});
    const row=vendorMap.get(key); row.capex+=(+r.a.capex||0); row.opex+=(+r.a.opex||0);
  });
  const venRows=[...vendorMap.values()];
  const venBody=venRows.map(r=>`<tr><td>${esc(r.tribe)}</td><td>${esc(r.team)}</td><td>${esc(r.vendor)}</td><td>${fmtMoneyK(r.capex)}</td><td>${fmtMoneyK(r.opex)}</td><td>${fmtMoneyK(r.capex+r.opex)}</td></tr>`).join('');
  const totalEff=vRows.reduce((s,r)=>s+BUDGET_COMPS.reduce((x,c)=>x+r.comps[c],0),0);
  const totalCapex=venRows.reduce((s,r)=>s+r.capex,0), totalOpex=venRows.reduce((s,r)=>s+r.opex,0);
  return `<div class="card budget-shell">
    <h2>Бюджет ${budgetBadge()}</h2>
    <h2 style="font-size:18px;margin-top:12px">Бюджет Vadarod</h2>
    <div class="budget-kpi"><span class="kpi">Итого ШЕ Vadarod: <b>${fmtNum(budgetSHE(totalEff,b),3)}</b></span><span class="kpi">Итого бюджет Vadarod, тыс. BYN: <b>${fmtMoneyK(budgetVadarodValue(totalEff,b))}</b></span></div>
    <div class="prep-wrap"><table><thead><tr><th>Трайб</th><th>Команда</th>${BUDGET_COMPS.map(c=>`<th>${c}, ШЕ</th>`).join('')}<th>Итого ШЕ Vadarod</th><th>Бюджет Vadarod, тыс. BYN</th></tr></thead><tbody>${vBody||`<tr><td colspan="${BUDGET_COMPS.length+4}" class="muted">Нет одобренных инициатив.</td></tr>`}</tbody></table></div>
    <h2 style="font-size:18px;margin-top:30px">Бюджет Vendor</h2>
    <div class="budget-kpi"><span class="kpi">Итого Vendor, тыс. BYN: <b>${fmtMoneyK(totalCapex+totalOpex)}</b></span><span class="kpi">Capex, тыс. BYN: <b>${fmtMoneyK(totalCapex)}</b></span><span class="kpi">Opex, тыс. BYN: <b>${fmtMoneyK(totalOpex)}</b></span></div>
    <div class="prep-wrap"><table><thead><tr><th>Трайб</th><th>Команда</th><th>Вендор</th><th>Capex, тыс. BYN</th><th>Opex, тыс. BYN</th><th>Итого, тыс. BYN</th></tr></thead><tbody>${venBody||'<tr><td colspan="6" class="muted">Нет одобренных инициатив с Vendor-бюджетом.</td></tr>'}</tbody></table></div>
  </div>`;
}
function bindBudget(){}

