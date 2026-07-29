/* =====================================================================
   ВКЛАДКА 6 — Риски
   Модель: state.risks = { general:[...], teams:{ 'Трайб||Команда':[...] } }
   Запись риска: { id, desc, owner, impact, control, plan, shared? }
   - Риски с вкладки «Общие риски» лежат в state.risks.general.
   - Командные риски лежат в state.risks.teams[ключ команды].
   - Командный риск с флагом shared=true («Общий риск») ЗЕРКАЛИТСЯ на вкладку
     «Общие риски» (единый источник данных, без копий): снятие галочки убирает
     его из общих, правка на командной вкладке отражается в общих.
   Ролевая модель (на будущее): общие риски правят только админы
   (Отдел развития гибких практик), командные — Product Owner команды.
   До внедрения ролевой модели ограничений нет.
===================================================================== */
const RISK_COLS=[
  ['desc','Описание риска'],
  ['owner','Владелец'],
  ['impact','Влияние'],
  ['control','Контрольная дата/событие'],
  ['plan','План работы с риском'],
];
// Список рисков текущего контекста (общие либо выбранная команда) или null,
// если на командной под-вкладке команда ещё не выбрана.
function currentRiskList(){
  if(state.ui.riskView==='general') return riskRows().filter(r=>r.scope==='general');
  const team=selectedRiskTeam();
  if(!team)return null;
  return riskRows().filter(r=>r.scope==='team'&&String(r.teamId)===String(team.id));
}
// Командные риски, отмеченные как общебанковские (shared) — для зеркала на «Общие риски»
function sharedTeamRisks(){
  return riskRows().filter(r=>r.scope==='team'&&r.shared).map(r=>{
    const team=riskTeamOptions().find(t=>String(t.id)===String(r.teamId));
    return {r,team:team?team.name:'Команда'};
  });
}

function legacyViewRisksLocal(){
  if(state.ui.riskView==='team'&&state.ui.riskTeam){
    const selectedExists=(state.pi.teams||[]).some(team=>
      team.tribe===state.ui.riskTribe&&team.name===state.ui.riskTeam
    );
    if(!selectedExists){state.ui.riskTeam=null;state.ui.riskTribe=null;}
  }
  const v=state.ui.riskView;
  let html=`<div class="card"><h2>Риски ${cycleBadge()}</h2>`;
  // Переключатель под-вкладок
  html+=`<div style="margin-bottom:18px">
    <span class="pill ${v==='general'?'sel':''}" data-risk-view="general">Общие риски</span>
    <span class="pill ${v==='team'?'sel':''}" data-risk-view="team">Командные риски</span>
  </div>`;

  if(v==='team' && !state.ui.riskTeam){
    html+=viewRiskTeamSelect();
    html+=`</div>`;
    return html;
  }

  // Командная под-вкладка с выбранной командой — плашка + смена команды
  if(v==='team'){
    html+=`<div class="team-toolbar">
      <span class="team-title">${esc(state.ui.riskTeam)}</span>
      <button class="ghost" id="riskTeamBack">← Выбор команды</button>
    </div>`;
  }

  html+=`<div class="row" style="margin-bottom:14px">
    <button class="plus" id="riskAdd">+</button>
    <span>Добавить риск</span>
  </div>`;

  html += v==='team' ? viewTeamRiskTable() : viewGeneralRiskTable();
  html+=`</div>`;
  return html;
}
// Таблица «Общие риски»: собственные общие риски + зеркало отмеченных командных
function viewGeneralRiskTable(){
  const gen=riskRows().filter(r=>r.scope==='general');
  const shared=sharedTeamRisks();
  let html=`<table><thead><tr><th style="width:40px">N</th>`+
    RISK_COLS.map(c=>`<th>${c[1]}</th>`).join('')+
    `<th style="width:120px"></th></tr></thead><tbody>`;
  if(!gen.length && !shared.length){
    html+=`<tr><td colspan="${RISK_COLS.length+2}" class="muted">Рисков пока нет</td></tr>`;
  }else{
    let n=0;
    gen.forEach(r=>{
      n++;
      html+=`<tr><td>${n}</td>`+
        RISK_COLS.map(c=>`<td>${esc(r[c[0]])||'<span class=auto>—</span>'}</td>`).join('')+
        `<td style="white-space:nowrap">
           <button class="icon sm" data-rg-edit="${esc(r.id)}">Изменить</button>
           <button class="icon danger sm" data-rg-del="${esc(r.id)}">✕</button>
         </td></tr>`;
    });
    shared.forEach(({r,team})=>{
      n++;
      html+=`<tr><td>${n}</td>`+
        RISK_COLS.map((c,ci)=> ci===0
          ? `<td>${esc(r.desc)||'<span class=auto>—</span>'}<div class="muted" style="font-size:11px;margin-top:2px">↳ из команды: ${esc(team)}</div></td>`
          : `<td>${esc(r[c[0]])||'<span class=auto>—</span>'}</td>`
        ).join('')+
        `<td class="auto" style="font-size:11px">правится в команде</td></tr>`;
    });
  }
  html+=`</tbody></table>`;
  return html;
}
// Таблица «Командные риски»: + столбец-чекбокс «Общий риск»
function viewTeamRiskTable(){
  const list=currentRiskList()||[];
  let html=`<table><thead><tr><th style="width:40px">N</th>`+
    RISK_COLS.map(c=>`<th>${c[1]}</th>`).join('')+
    `<th style="width:90px;text-align:center">Общий риск</th>`+
    `<th style="width:120px"></th></tr></thead><tbody>`;
  if(!list.length){
    html+=`<tr><td colspan="${RISK_COLS.length+3}" class="muted">Рисков пока нет</td></tr>`;
  }else{
    list.forEach((r,i)=>{
      html+=`<tr><td>${i+1}</td>`+
        RISK_COLS.map(c=>`<td>${esc(r[c[0]])||'<span class=auto>—</span>'}</td>`).join('')+
        `<td style="text-align:center"><input type="checkbox" data-rt-share="${esc(r.id)}" ${r.shared?'checked':''}></td>`+
        `<td style="white-space:nowrap">
           <button class="icon sm" data-rt-edit="${esc(r.id)}">Изменить</button>
           <button class="icon danger sm" data-rt-del="${esc(r.id)}">✕</button>
         </td></tr>`;
    });
  }
  html+=`</tbody></table>
    <div class="note" style="margin-top:14px">Отметьте «Общий риск», если риск общебанковский — он продублируется на вкладке «Общие риски». Снятие галочки убирает его из общих.</div>`;
  return html;
}

// Выбор команды для командных рисков (аккордеон трайбов → команды, как 5.0)
function viewRiskTeamSelect(){
  const tribes=riskTribeOptions();
  const sel=String(state.ui.riskTribeId||'');
  let html=`<div class="hint" style="margin-bottom:10px">Выберите команду. Трайбы и команды сформированы автоматически из «Данных PI-цикла».</div>`;
  html+=`<div class="tribe-list">`;
  tribes.forEach(tribe=>{
    const open=sel===String(tribe.id);
    html+=`<div class="tribe-acc">
      <div class="tribe-acc-head ${open?'open':''}" data-risk-tribe-id="${esc(tribe.id)}" data-risk-tribe-name="${esc(tribe.name)}">
        <span class="caret">${open?'▼':'▶'}</span>${esc(tribe.name)}
      </div>`;
    if(open){
      const teams=riskTeamOptions().filter(t=>String(t.tribe_id)===String(tribe.id));
      html+=`<div class="tribe-acc-body">`+
        (teams.length
          ? teams.map(t=>`<div class="team-item" data-risk-open-id="${esc(t.id)}" data-risk-open-name="${esc(t.name)}">${esc(t.name)}</div>`).join('')
          : `<div class="muted">В трайбе нет команд</div>`)+
        `</div>`;
    }
    html+=`</div>`;
  });
  html+=`</div>`;
  return html;
}

function legacyBindRisksLocal(){
  // переключение под-вкладок
  document.querySelectorAll('[data-risk-view]').forEach(el=>el.onclick=()=>{
    state.ui.riskView=el.dataset.riskView;save();render();
  });
  // выбор команды
  document.querySelectorAll('[data-risk-tribe]').forEach(el=>el.onclick=()=>{
    state.ui.riskTribe = state.ui.riskTribe===el.dataset.riskTribe ? null : el.dataset.riskTribe;
    save();render();
  });
  document.querySelectorAll('[data-risk-open]').forEach(el=>el.onclick=()=>{
    state.ui.riskTeam=el.dataset.riskOpen;save();render();
  });
  const back=$('#riskTeamBack'); if(back)back.onclick=()=>{state.ui.riskTeam=null;save();render();};
  // добавление
  const add=$('#riskAdd'); if(add)add.onclick=()=>openRiskModal(null);
  // общие риски — правка/удаление собственных записей
  document.querySelectorAll('[data-rg-edit]').forEach(b=>b.onclick=()=>openRiskModal(+b.dataset.rgEdit));
  document.querySelectorAll('[data-rg-del]').forEach(b=>b.onclick=()=>{
    state.risks.general.splice(+b.dataset.rgDel,1);save();render();
    toast('Риск удалён',{type:'info'});
  });
  // командные риски — правка/удаление
  document.querySelectorAll('[data-rt-edit]').forEach(b=>b.onclick=()=>openRiskModal(+b.dataset.rtEdit));
  document.querySelectorAll('[data-rt-del]').forEach(b=>b.onclick=()=>{
    const list=currentRiskList(); if(!list)return;
    list.splice(+b.dataset.rtDel,1);save();render();
    toast('Риск удалён',{type:'info'});
  });
  // чекбокс «Общий риск» — зеркалирование на «Общие риски»
  document.querySelectorAll('[data-rt-share]').forEach(el=>el.onchange=()=>{
    const list=currentRiskList(); if(!list)return;
    list[+el.dataset.rtShare].shared=el.checked;save();render();
    toast(el.checked?'Риск продублирован в «Общие риски»':'Риск убран из «Общих рисков»',{type:'info'});
  });
}

// Модальное окно добавления / редактирования риска.
// idx===null → добавление; иначе — редактирование записи списка.
function legacyOpenRiskModalLocal(idx){
  const list=currentRiskList(); if(!list)return;
  const isEdit=idx!==null && idx!==undefined;
  const isTeam = state.ui.riskView==='team';
  const r=isEdit ? list[idx] : {desc:'',owner:'',impact:'',control:'',plan:'',shared:false};
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${isEdit?'Редактирование риска':'Новый риск'}</h3>
    <label><span>Описание риска</span><textarea id="rm_desc" rows="2">${esc(r.desc)}</textarea></label>
    <label><span>Владелец</span><input id="rm_owner" value="${esc(r.owner)}"></label>
    <label><span>Влияние</span><input id="rm_impact" value="${esc(r.impact)}"></label>
    <label><span>Контрольная дата/событие</span><input id="rm_control" value="${esc(r.control)}"></label>
    <label><span>План работы с риском</span><textarea id="rm_plan" rows="2">${esc(r.plan)}</textarea></label>
    ${isTeam?`<label style="display:flex;align-items:center;gap:9px;cursor:pointer">
      <input type="checkbox" id="rm_shared" ${r.shared?'checked':''} style="width:auto;margin:0">
      <span style="margin:0;color:var(--text)">Общий риск — продублировать на «Общие риски»</span>
    </label>`:''}
    <div class="modal-actions">
      <button id="rm_cancel">Отмена</button>
      <button class="primary" id="rm_save">Сохранить</button>
    </div>
  </div></div>`;
  const close=()=>root.innerHTML='';
  $('#rm_cancel').onclick=close;
  $('#rm_save').onclick=()=>{
    const data={
      desc:$('#rm_desc').value.trim(),
      owner:$('#rm_owner').value.trim(),
      impact:$('#rm_impact').value.trim(),
      control:$('#rm_control').value.trim(),
      plan:$('#rm_plan').value.trim(),
    };
    if(isTeam) data.shared=$('#rm_shared').checked;
    if(!data.desc){ toast('Укажите описание риска',{type:'warn'}); return; }
    if(isEdit){ Object.assign(list[idx],data); }
    else{ list.push({id:uid(),...data}); }
    close();save();render();
    toast(isEdit?'Риск обновлён':'Риск добавлен',{type:'success'});
  };
}

const RISK_STATUS_LABELS={open:'Открыт',watching:'Наблюдение',closed:'Закрыт'};
const RISK_ROAM_LABELS={resolved:'Resolved',owned:'Owned',accepted:'Accepted',mitigated:'Mitigated'};
function riskRef(){const c=activeCycle();return (c&&c.riskReference)||{};}
function riskRows(){const c=activeCycle();return (c&&Array.isArray(c.riskRows))?c.riskRows:[];}
function riskTribeOptions(){return riskRef().tribes||[];}
function riskTeamOptions(){return riskRef().teams||[];}
function riskInitiativeOptions(){return riskRef().initiatives||[];}
function selectedRiskTeam(){
  const teams=riskTeamOptions();
  if(state.ui.riskTeamId){
    const byId=teams.find(t=>String(t.id)===String(state.ui.riskTeamId));
    if(byId)return byId;
  }
  return teams.find(t=>t.name===state.ui.riskTeam&&t.tribe===state.ui.riskTribe)||null;
}
function riskLinkLabel(r){
  if(r.scope==='team'){
    const t=riskTeamOptions().find(x=>String(x.id)===String(r.teamId));
    return t?`${t.tribe} / ${t.name}`:'Команда';
  }
  if(r.scope==='tribe'){
    const t=riskTribeOptions().find(x=>String(x.id)===String(r.tribeId));
    return t?t.name:'Трайб';
  }
  if(r.scope==='initiative'){
    const i=riskInitiativeOptions().find(x=>String(x.id)===String(r.initiativeId));
    return i?`${i.issue_key} · ${i.title}`:'Инициатива';
  }
  return 'Общий риск';
}
function viewRisks(){
  const teams=riskTeamOptions(),tribes=riskTribeOptions();
  const selectedTeam=selectedRiskTeam();
  if(state.ui.riskView==='team'&&state.ui.riskTeam&&!selectedTeam){
    state.ui.riskTeam=null;
    state.ui.riskTeamId='';
  }
  const view=state.ui.riskView==='team'?'team':'general';
  let html=`<div class="card"><h2>Риски ${cycleBadge()}</h2>`;
  if(!risksApiReady&&!risksBoards[currentCycleId()])return html+`<div class="muted">Загрузка рисков с сервера...</div></div>`;
  if(!cycleBackendIds[currentCycleId()])return html+`<div class="muted">Сервер недоступен или PI-цикл не выбран.</div></div>`;
  if(!teams.length&&!tribes.length)return html+`<div class="muted">Добавьте трайбы и команды на вкладке «Данные PI-цикла». Риски не создаются из демонстрационных данных.</div></div>`;
  html+=`<div style="margin-bottom:18px">
    <span class="pill ${view==='general'?'sel':''}" data-risk-view="general">Общие риски</span>
    <span class="pill ${view==='team'?'sel':''}" data-risk-view="team">Командные риски</span>
  </div>`;
  if(view==='team'&&!selectedTeam){
    html+=viewRiskTeamSelect()+`</div>`;
    return html;
  }
  if(view==='team'){
    html+=`<div class="team-toolbar"><span class="team-title">${esc(selectedTeam.name)}</span><button class="ghost" id="riskTeamBack">← Выбор команды</button></div>`;
  }
  html+=`<div class="row" style="margin-bottom:14px"><button class="plus" id="riskAdd">+</button><span>Добавить риск</span></div>`;
  html+=view==='team'?viewTeamRiskTable():viewGeneralRiskTable();
  html+=`</div>`;
  return html;
}
function bindRisks(){
  document.querySelectorAll('[data-risk-view]').forEach(el=>el.onclick=()=>{
    state.ui.riskView=el.dataset.riskView;save();render();
  });
  document.querySelectorAll('[data-risk-tribe-id]').forEach(el=>el.onclick=()=>{
    const same=String(state.ui.riskTribeId||'')===String(el.dataset.riskTribeId);
    state.ui.riskTribeId=same?'':el.dataset.riskTribeId;
    state.ui.riskTribe=same?null:el.dataset.riskTribeName;
    save();render();
  });
  document.querySelectorAll('[data-risk-open-id]').forEach(el=>el.onclick=()=>{
    const team=riskTeamOptions().find(t=>String(t.id)===String(el.dataset.riskOpenId));
    state.ui.riskTeamId=el.dataset.riskOpenId;
    state.ui.riskTeam=el.dataset.riskOpenName;
    if(team){state.ui.riskTribeId=String(team.tribe_id);state.ui.riskTribe=team.tribe;}
    save();render();
  });
  const back=$('#riskTeamBack'); if(back)back.onclick=()=>{state.ui.riskTeam=null;state.ui.riskTeamId='';save();render();};
  const add=$('#riskAdd'); if(add)add.onclick=()=>openRiskModal(null);
  document.querySelectorAll('[data-rg-edit]').forEach(b=>b.onclick=()=>openRiskModal(b.dataset.rgEdit));
  document.querySelectorAll('[data-rt-edit]').forEach(b=>b.onclick=()=>openRiskModal(b.dataset.rtEdit));
  document.querySelectorAll('[data-rg-del]').forEach(b=>b.onclick=()=>deleteRiskUi(b.dataset.rgDel));
  document.querySelectorAll('[data-rt-del]').forEach(b=>b.onclick=()=>deleteRiskUi(b.dataset.rtDel));
  document.querySelectorAll('[data-rt-share]').forEach(el=>el.onchange=async()=>{
    const run=()=>risksBoardCommand(`/risks/${el.dataset.rtShare}`,'PATCH',{is_shared:el.checked});
    try{await run();toast(el.checked?'Риск продублирован в «Общие риски»':'Риск убран из «Общих рисков»',{type:'info'});}
    catch(error){handleCommandError(error,run);}
  });
}
function riskPayloadFromModal(){
  const isTeam=state.ui.riskView==='team';
  const team=selectedRiskTeam();
  return {
    scope:isTeam?'team':'general',
    tribe_id:null,
    team_id:isTeam&&team?team.id:null,
    initiative_id:null,
    is_shared:isTeam&&$('#rm_shared')&&$('#rm_shared').checked,
    description:$('#rm_desc').value.trim(),
    owner:$('#rm_owner').value.trim(),
    impact:$('#rm_impact').value.trim(),
    control_point:$('#rm_control').value.trim(),
    mitigation_plan:$('#rm_plan').value.trim(),
  };
}
function openRiskModal(riskId){
  const r=riskRows().find(x=>x.id===riskId)||{};
  const isTeam=state.ui.riskView==='team';
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${riskId?'Редактирование риска':'Новый риск'}</h3>
    <label><span>Описание риска</span><textarea id="rm_desc" rows="2">${esc(r.desc||'')}</textarea></label>
    <label><span>Владелец</span><input id="rm_owner" value="${esc(r.owner||'')}"></label>
    <label><span>Влияние</span><input id="rm_impact" value="${esc(r.impact||'')}"></label>
    <label><span>Контрольная дата/событие</span><input id="rm_control" value="${esc(r.control||'')}"></label>
    <label><span>План работы с риском</span><textarea id="rm_plan" rows="2">${esc(r.plan||'')}</textarea></label>
    ${isTeam?`<label style="display:flex;align-items:center;gap:9px;cursor:pointer"><input type="checkbox" id="rm_shared" ${r.shared?'checked':''} style="width:auto;margin:0"><span style="margin:0;color:var(--text)">Общий риск — продублировать на «Общие риски»</span></label>`:''}
    <div class="modal-actions"><button id="rm_cancel">Отмена</button><button class="primary" id="rm_save">Сохранить</button></div>
  </div></div>`;
  $('#rm_cancel').onclick=()=>root.innerHTML='';
  $('#rm_save').onclick=async()=>{
    const payload=riskPayloadFromModal();
    if(!payload.description){toast('Укажите описание риска',{type:'warn'});return;}
    const run=()=>risksBoardCommand(riskId?`/risks/${riskId}`:'/risks',riskId?'PATCH':'POST',payload);
    try{await run();root.innerHTML='';toast(riskId?'Риск обновлён':'Риск создан',{type:'success'});}
    catch(error){handleCommandError(error,run);}
  };
}
function deleteRiskUi(riskId){
  showConfirm('Удаление риска','Риск будет удалён из активного PI-цикла.',[],async()=>{
    try{await risksBoardCommand(`/risks/${riskId}`,'DELETE',{});toast('Риск удалён',{type:'info'});}
    catch(error){handleCommandError(error,()=>risksBoardCommand(`/risks/${riskId}`,'DELETE',{}));}
  });
}
function bindRiskRowDrag(){
  let dragId=null;
  document.querySelectorAll('tr[data-riskdrag-id]').forEach(tr=>{
    tr.addEventListener('dragstart',e=>{
      if(e.target.closest('select,button')){e.preventDefault();return;}
      dragId=tr.dataset.riskdragId; e.dataTransfer.effectAllowed='move'; tr.classList.add('dragging');
    });
    tr.addEventListener('dragend',()=>{tr.classList.remove('dragging');clearPrepRowDropMarkers();});
    tr.addEventListener('dragover',e=>{
      e.preventDefault();
      const after=isPrepDropAfter(tr,e);
      tr.classList.toggle('rowdragover-before',!after);
      tr.classList.toggle('rowdragover-after',after);
    });
    tr.addEventListener('dragleave',()=>clearPrepRowDropMarkers(tr));
    tr.addEventListener('drop',e=>{
      e.preventDefault(); e.stopPropagation(); clearPrepRowDropMarkers(tr);
      moveRisk(dragId,tr.dataset.riskdragId,isPrepDropAfter(tr,e));
    });
  });
}
async function moveRisk(fromId,targetId,after){
  if(!fromId||!targetId||fromId===targetId)return;
  const ids=riskRows().map(r=>r.id);
  const from=ids.indexOf(fromId),target=ids.indexOf(targetId);
  if(from<0||target<0)return;
  const [item]=ids.splice(from,1);
  let insertAt=after?target+1:target;
  if(from<insertAt)insertAt--;
  ids.splice(insertAt,0,item);
  try{await risksBoardCommand('/order','PUT',{risk_ids:ids});toast('Порядок рисков обновлён',{type:'success'});}
  catch(error){handleCommandError(error,()=>risksBoardCommand('/order','PUT',{risk_ids:ids}));}
}

