/* =====================================================================
   ВКЛАДКА 3 — Program Board
===================================================================== */
function goalTeamBySelection(){
  const teams=goalTeamOptions();
  if(state.ui.goalsTeamId){
    const byId=teams.find(t=>String(t.id)===String(state.ui.goalsTeamId));
    if(byId)return byId;
  }
  return teams.find(t=>t.name===state.ui.goalsTeam && t.tribe===state.ui.goalsTribe)||null;
}
function selectedGoalTribe(){
  const tribes=goalTribeOptions();
  if(state.ui.goalsTribeId){
    const byId=tribes.find(t=>String(t.id)===String(state.ui.goalsTribeId));
    if(byId)return byId;
  }
  return tribes.find(t=>t.name===state.ui.goalsTribe)||null;
}
function goalGroupName(g){
  const issue=findIssue(g.initNum)||{};
  return String(g.cel||g.title||issue.cel||'');
}
function goalPatchForField(field,value){
  const map={metric:'metric',fact:'current_value',plan:'target_value',hypo:'hypothesis',redesign:'redesign'};
  return {[map[field]||field]:value};
}
function goalRowsForTeam(team){
  if(!team)return [];
  return goalRows().filter(g=>String(g.teamId||'')===String(team.id));
}
function viewGoals(){
  const cycleId=currentCycleId();
  let html=`<div class="card"><h2>Цели ${cycleBadge()}</h2>`;
  if(!goalsApiReady&&!goalsBoards[cycleId])return html+`<div class="muted">Загрузка целей с backend...</div></div>`;
  if(!cycleBackendIds[cycleId])return html+`<div class="muted">Backend недоступен или PI-цикл не выбран.</div></div>`;

  const tribes=goalTribeOptions();
  if(!tribes.length){
    return html+`<div class="muted">Нет трайбов и команд для целей. Добавьте их на вкладке «Данные PI-цикла».</div></div>`;
  }

  const tribe=selectedGoalTribe();
  const tribeId=tribe?String(tribe.id):'';
  html+=`<div>`+tribes.map(t=>`<span class="pill tribe ${tribeId===String(t.id)?'sel':''}" data-goal-tribe-id="${esc(t.id)}" data-goal-tribe-name="${esc(t.name)}">${esc(t.name)}</span>`).join('')+`</div>`;

  if(!tribe){
    html+=`<div class="muted" style="margin-top:14px">Выберите трайб.</div></div>`;
    return html;
  }

  const teams=goalTeamOptions().filter(t=>String(t.tribe_id)===tribeId);
  const selectedTeam=goalTeamBySelection();
  const teamId=selectedTeam&&teams.some(t=>String(t.id)===String(selectedTeam.id))?String(selectedTeam.id):'';
  html+=`<div style="margin-top:6px">`+teams.map(t=>`<span class="pill ${teamId===String(t.id)?'sel':''}" data-goal-team-id="${esc(t.id)}" data-goal-team-name="${esc(t.name)}">${esc(t.name)}</span>`).join('')+`</div>`;

  if(!teamId){
    html+=`<div class="muted" style="margin-top:14px">Выберите команду.</div></div>`;
    return html;
  }

  const team=teams.find(t=>String(t.id)===teamId);
  const isIT=teamType(team)==='ИТ-проект';
  const rows=goalRowsForTeam(team);
  const COLS=GOAL_COLS, EDIT=GOAL_EDIT;
  html+=`<div class="goals-wrap"><table class="goals"><thead><tr><th>№</th>`+
    COLS.map(c=>`<th>${c[1]}</th>`).join('')+`</tr></thead><tbody>`;
  const colCount=COLS.length+1;
  if(!rows.length){
    html+=`<tr><td colspan="${colCount}" class="muted">Целей пока нет — добавьте их на вкладке «Pre PI Planning» кнопкой «Отправить на доски».</td></tr>`;
  }else{
    const byGoal=new Map();
    rows.forEach(g=>{
      const key=goalGroupName(g);
      if(!byGoal.has(key))byGoal.set(key,[]);
      byGoal.get(key).push(g);
    });
    const order=[];
    (state.pi.goals||[]).forEach(name=>{if(byGoal.has(name))order.push(name);});
    [...byGoal.keys()].forEach(name=>{if(name&&!order.includes(name))order.push(name);});
    if(byGoal.has(''))order.push('');
    let n=0;
    const emptyLabel=isIT?'Без вехи':'Без цели';
    const groupIcon=isIT?'🏁 ':'🎯 ';
    order.forEach(group=>{
      html+=`<tr class="goal-group"><td colspan="${colCount}">${group?(groupIcon+esc(group)):emptyLabel}</td></tr>`;
      byGoal.get(group).forEach(g=>{
        n++;
        html+=`<tr draggable="true" data-goaldrag-id="${esc(g.id)}"><td><span class="g-handle" title="Перетащите, чтобы изменить порядок">⠿</span>${n}</td>`+
          COLS.map(c=>EDIT.includes(c[0])
            ? `<td><input data-goal-field-id="${esc(g.id)}" data-goal-k="${c[0]}" value="${esc(g[c[0]]||'')}"></td>`
            : `<td>${esc(g[c[0]]||'')||'<span class=auto>—</span>'}</td>`
          ).join('')+`</tr>`;
      });
    });
  }
  html+=`</tbody></table></div>
    <div class="note" style="margin-top:14px">${isIT
      ? 'Инициативы сгруппированы по <b>вехам ИТ-проекта</b> — веха вписывается вручную в столбец «Цель/Веха» на «Pre PI Planning». Поля метрика / AS IS / TO BE / гипотезы / редизайн можно редактировать прямо здесь — изменения синхронизируются с «Pre PI Planning»; для ИТ-проектов они необязательны. Перетаскивайте строки за <b>⠿</b>, чтобы менять порядок.'
      : 'Инициативы сгруппированы по <b>Цели</b>. Цель выбирается у инициативы на «Pre PI Planning» из справочника («Данные PI-цикла») либо вводится вручную. Поля метрика / AS IS / TO BE / гипотезы / редизайн можно редактировать прямо здесь — изменения синхронизируются с «Pre PI Planning». Перетаскивайте строки за <b>⠿</b>, чтобы менять порядок.'}</div></div>`;
  return html;
}
function bindGoals(){
  document.querySelectorAll('[data-goal-tribe-id]').forEach(el=>el.onclick=()=>{
    state.ui.goalsTribeId=el.dataset.goalTribeId;
    state.ui.goalsTribe=el.dataset.goalTribeName;
    state.ui.goalsTeamId='';
    state.ui.goalsTeam=null;
    save();render();
  });
  document.querySelectorAll('[data-goal-team-id]').forEach(el=>el.onclick=()=>{
    state.ui.goalsTeamId=el.dataset.goalTeamId;
    state.ui.goalsTeam=el.dataset.goalTeamName;
    save();render();
  });
  document.querySelectorAll('[data-goal-field-id]').forEach(el=>el.onchange=async()=>{
    const goalId=el.dataset.goalFieldId;
    try{
      await goalsBoardCommand(`/goals/${goalId}`,'PATCH',goalPatchForField(el.dataset.goalK,el.value));
      toast('Цель обновлена',{type:'success'});
    }catch(error){
      handleCommandError(error,()=>goalsBoardCommand(`/goals/${goalId}`,'PATCH',goalPatchForField(el.dataset.goalK,el.value)));
    }
  });
  bindGoalRowDrag();
}
function bindGoalRowDrag(){
  let dragId=null;
  document.querySelectorAll('tr[data-goaldrag-id]').forEach(tr=>{
    tr.addEventListener('dragstart',e=>{
      if(e.target.closest('input,button')){e.preventDefault();return;}
      dragId=tr.dataset.goaldragId;
      e.dataTransfer.effectAllowed='move';
      try{e.dataTransfer.setData('text/plain',String(dragId));}catch(_){}
      tr.classList.add('dragging');
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
      e.preventDefault(); e.stopPropagation();
      clearPrepRowDropMarkers(tr);
      moveGoal(dragId,tr.dataset.goaldragId,isPrepDropAfter(tr,e));
    });
  });
}
async function moveGoal(fromId,targetId,after){
  if(!fromId||!targetId||fromId===targetId)return;
  const selected=goalTeamBySelection();
  const selectedIds=goalRowsForTeam(selected).map(g=>g.id);
  const from=selectedIds.indexOf(fromId),target=selectedIds.indexOf(targetId);
  if(from<0||target<0)return;
  const [item]=selectedIds.splice(from,1);
  let insertAt=after?target+1:target;
  if(from<insertAt)insertAt--;
  selectedIds.splice(insertAt,0,item);
  const selectedSet=new Set(selectedIds);
  let selectedIndex=0;
  const ids=goalRows().map(g=>selectedSet.has(g.id)?selectedIds[selectedIndex++]:g.id);
  try{await goalsBoardCommand('/order','PUT',{goal_ids:ids});toast('Порядок целей обновлён',{type:'success'});}
  catch(error){handleCommandError(error,()=>goalsBoardCommand('/order','PUT',{goal_ids:ids}));}
}

function pbTeamFilterOptions(){
  const board=programBoardViews[currentCycleId()];
  return board?(board.teams||[]).map(team=>team.name):[];
}
function pbFiltersActive(){
  return !!(state.ui.pbOwnerFilter || state.ui.pbExecutorFilter);
}
function issueMatchesPBFilters(card){
  const owner=state.ui.pbOwnerFilter;
  const executor=state.ui.pbExecutorFilter;
  if(owner && card.owner_team!==owner) return false;
  if(executor && !(card.executors||[]).some(row=>row.team===executor)) return false;
  return true;
}
function pbFiltersHTML(){
  const teams=pbTeamFilterOptions();
  const opt=selected=>`<option value="">Все команды</option>`+
    teams.map(t=>`<option value="${esc(t)}" ${selected===t?'selected':''}>${esc(t)}</option>`).join('');
  const active=pbFiltersActive();
  return `<div class="pb-filters">
    <label>Команда-владелец
      <select id="pbOwnerFilter">${opt(state.ui.pbOwnerFilter)}</select>
    </label>
    <label>Команда-исполнитель
      <select id="pbExecutorFilter">${opt(state.ui.pbExecutorFilter)}</select>
    </label>
    ${active?`<button class="ghost" id="pbFilterClear">Сбросить</button>`:''}
  </div>`;
}
function pbDate(value){
  const parts=String(value||'').split('-');
  return parts.length===3?`${parts[2]}.${parts[1]}.${parts[0]}`:'—';
}
function pbCardHTML(card,extraClass=''){
  const primary=(card.executors||[]).find(row=>row.team_id===card.primary_team_id)||card.executors[0];
  const effort=primary?Object.entries(primary.effort_by_competency||{}).map(([key,value])=>`${key} ${round1(value)}`).join(' · '):'—';
  const tags=(card.tags||[]).map(tag=>`<span class="sttag">#${esc(tag)}</span>`).join('');
  const conflict=(card.conflict_codes||[]).length?`<span class="pb-conflict-mark" title="Есть предупреждение">!</span>`:'';
  return `<div class="sticker ${esc(card.visual_state)}${extraClass?' '+extraClass:''}" draggable="true"
    data-drag="pb-initiative" data-id="${esc(card.id)}" data-pb-card="${esc(card.id)}" data-issue-key="${esc(card.issue_key)}">
    <div class="stid">${esc(card.issue_key)}${conflict}</div>
    ${tags?`<div class="sttags">${tags}</div>`:''}
    <div class="stteam"><span>Владелец: <b>${esc(card.owner_team)||'—'}</b></span><span>Исполнитель: <b>${esc((card.executors||[]).map(row=>row.team).join(', '))||'—'}</b></span></div>
    <div class="eff">${esc(effort)}</div>
  </div>`;
}
function pbConflictsHTML(board){
  const conflicts=board.conflicts||[];
  if(!conflicts.length)return '';
  return `<div class="pb-conflicts"><b>Предупреждения плана: ${conflicts.length}</b>`+
    conflicts.slice(0,6).map(row=>`<span class="${row.severity==='error'?'error':''}">${esc(row.message)}</span>`).join('')+
    (conflicts.length>6?`<span>Ещё ${conflicts.length-6}</span>`:'')+`</div>`;
}
function viewPB(){
  const board=programBoardViews[currentCycleId()];
  if(!programBoardApiReady||!board){
    return `<div class="card"><h2>Program Board ${cycleBadge()}</h2><div class="muted">Загрузка Program Board с backend...</div></div>`;
  }
  const sprints=board.sprints||[];
  const tribes=board.tribes||[];
  const activeFilter=pbFiltersActive();
  let html=`<div class="card"><div class="flex-between"><h2>Program Board ${cycleBadge()}</h2>
    <div class="hint">Сформировано backend из активного PI, Pre PI Planning и «Командных досок». Перетаскивайте стикеры между спринтами — позиция сохраняется атомарно и сразу видна на командной доске.</div></div>`;
  html+=pbConflictsHTML(board);
  html+=pbFiltersHTML();
  html+=`<div class="pb-wrap${activeFilter?' lane-focus':''}"><table class="pb"><thead><tr>
    <th>Трайб</th><th>Команда</th>`+
    sprints.map(s=>`<th class="sp"><div class="sp-head"><div class="num">Спринт ${s.number}</div>
      <div class="dates">${pbDate(s.start_date)}–${pbDate(s.end_date)}</div>
      ${(s.events||[]).map(event=>`<div class="pir">${esc(event.name)} ${pbDate(event.event_date)}</div>`).join('')}</div></th>`).join('')+
    `</tr></thead><tbody>`;
  tribes.forEach(tribe=>{
    const teams=(board.teams||[]).filter(team=>team.tribe_id===tribe.id);
    teams.forEach((t,ti)=>{
      html+=`<tr>`;
      if(ti===0) html+=`<td class="tribe-cell" rowspan="${teams.length}">${esc(tribe.name)}</td>`;
      html+=`<td class="team-cell">${esc(t.name)}</td>`;
      sprints.forEach(s=>{
        const cards=(board.cards||[]).filter(card=>card.primary_team_id===t.id&&card.sprint_index===s.index);
        html+=`<td class="pb-cell dropzone" data-pb-sprint="${s.index}" data-pb-team="${esc(t.id)}">`+
          cards.map(card=>pbCardHTML(card,activeFilter&&issueMatchesPBFilters(card)?'lane-on':'')).join('')+`</td>`;
      });
      html+=`</tr>`;
    });
  });
  html+=`</tbody></table></div>
  <div class="legend">
    <span><i style="background:var(--blue);border:1px solid var(--blue-b)"></i>Владелец = исполнитель</span>
    <span><i style="background:var(--purple);border:1px solid var(--purple-b)"></i>Привлечение (не согласовано)</span>
    <span><i style="background:var(--red);border:1px solid var(--red-b)"></i>Привлечение согласовано</span>
  </div></div>`;
  return html;
}
// Сумма ёмкости подзадач по ролям (сколько уже разобрано декомпозицией)
function decompByRole(iss){
  const d={}; (iss.subtasks||[]).forEach(st=>{ d[st.role]=(d[st.role]||0)+(+st.cap||0); }); return d;
}
// Компетенции истории (чел/дн) — с миграцией со старых sa/dev/qa.
function storyComps(sy){
  if(sy.comps && typeof sy.comps==='object') return sy.comps;
  sy.comps={SA:+sy.sa||0,DEV:+sy.dev||0,QA:+sy.qa||0};
  return sy.comps;
}
function stickerHTML(iss,withDel,showDecomp,showTeams,extraClass){
  if(showTeams===undefined) showTeams=true;
  extraClass=extraClass?` ${extraClass}`:'';
  const tn=issuePrimaryTeam(iss);
  const comps=teamComps(tn);
  let decomp='';
  if(showDecomp){
    const subs=iss.subtasks||[];
    if(subs.length){
      const d=decompByRole(iss);
      const cell=r=>{
        const plan = issueTeamEffort(iss,tn,r);
        const done = d[r]||0;
        const cls = done>plan ? 'over' : (plan>0 && done>=plan ? 'ok' : 'under');
        return `<span class="${cls}">${r} ${round1(done)}/${round1(plan)}</span>`;
      };
      decomp=`<div class="deff" title="Разобрано декомпозицией / план по компетенциям">↳ разобрано: ${comps.map(cell).join(' · ')}</div>`;
    }else{
      decomp=`<div class="deff none">↳ не декомпозирована</div>`;
    }
  }
  return `<div class="sticker ${issueColor(iss)}${extraClass}" draggable="true" data-drag="issue" data-id="${esc(iss.id)}" data-sticker="${esc(iss.id)}" style="--lane:${issueHue(iss)}">
    ${withDel?`<span class="x" data-delissue="${esc(iss.id)}">✕</span>`:''}
    <div class="stid"><span class="lane-dot"></span>${esc(iss.id)}</div>
    ${issueTagsHTML(iss)}
    ${showTeams?issueTeamsHTML(iss):''}
    <div class="eff">${issueEffortLabel(iss)}</div>
    ${decomp}
  </div>`;
}
// Серый информационный стикер на доске команды-владельца.
function infoStickerHTML(iss){
  return `<div class="sticker info" data-id="${esc(iss.id)}" data-sticker="${esc(iss.id)}" data-info-sticker="${esc(iss.id)}" style="--lane:${issueHue(iss)}">
    <div class="stid"><span class="lane-dot"></span>${esc(iss.id)}</div>
    ${issueTagsHTML(iss)}
    ${issueTeamsHTML(iss)}
    <div class="eff">${esc(iss.name)||'Информационный стикер'}</div>
    <span class="st-badge">Информационный</span>
    ${iss.agreed?`<span class="st-badge ok">Согласовано</span>`:''}
  </div>`;
}
// Найти Историю задачи по uid
function storyById(iss,uid){ return (iss.stories||[]).find(s=>s.uid===uid)||null; }
// Сумма ёмкости белых подзадач конкретной Истории по ролям
function storyDecompByRole(iss,storyUid){
  const d={}; (iss.subtasks||[]).forEach(st=>{ if(st.storyUid===storyUid) d[st.role]=(d[st.role]||0)+(+st.cap||0); }); return d;
}
// Зелёный стикер «История»: свои компетенции + сводка разбора по белым.
function storyHTML(iss,sy){
  const hue=issueHue(iss);
  const tn=issuePrimaryTeam(iss);
  const comps=teamComps(tn);
  const sc=storyComps(sy);
  const hasSubs=(iss.subtasks||[]).some(st=>st.storyUid===sy.uid);
  let decomp;
  if(hasSubs){
    const d=storyDecompByRole(iss,sy.uid);
    const cell=r=>{
      const plan = +sc[r]||0;
      const done = d[r]||0;
      const cls = done>plan ? 'over' : (plan>0 && done>=plan ? 'ok' : 'under');
      return `<span class="${cls}">${r} ${round1(done)}/${round1(plan)}</span>`;
    };
    decomp=`<div class="deff" title="Разобрано декомпозицией / план по компетенциям">↳ разобрано: ${comps.map(cell).join(' · ')}</div>`;
  }else{
    decomp=`<div class="deff none">↳ не декомпозирована</div>`;
  }
  return `<div class="story" draggable="true" data-drag="story" data-id="${esc(iss.id)}" data-story-uid="${esc(sy.uid)}"
    data-story-issue="${esc(iss.id)}" data-story="${esc(sy.uid)}" style="--lane:${hue}">
    <span class="x" data-delstory-i="${esc(iss.id)}" data-delstory-u="${esc(sy.uid)}">✕</span>
    <div class="sparent">${esc(iss.id)}</div>
    <div class="stid">${esc(sy.id)||'История'}</div>
    ${sy.name?`<div class="sname">${esc(sy.name)}</div>`:''}
    <div class="eff">${comps.map(k=>`${k} ${+sc[k]||0}`).join(' · ')}</div>
    ${decomp}
  </div>`;
}
function bindPB(){
  const ownerFilter=$('#pbOwnerFilter');
  if(ownerFilter) ownerFilter.onchange=()=>{
    state.ui.pbOwnerFilter=ownerFilter.value||null;
    save(); render();
  };
  const executorFilter=$('#pbExecutorFilter');
  if(executorFilter) executorFilter.onchange=()=>{
    state.ui.pbExecutorFilter=executorFilter.value||null;
    save(); render();
  };
  const clear=$('#pbFilterClear');
  if(clear) clear.onclick=()=>{
    state.ui.pbOwnerFilter=null;
    state.ui.pbExecutorFilter=null;
    save(); render();
  };
  document.querySelectorAll('.pb-cell .sticker').forEach(el=>el.onclick=e=>{
    if(e.target.closest('.x')) return;
    openStickerModal(el.dataset.issueKey);
  });
  enableDrag(document,async(payload,sprint)=>{
    if(payload.kind!=='pb-initiative')return;
    try{
      await programBoardMoveInitiative(payload.id,+sprint,999999);
      render();
      toast('Инициатива перемещена. Командная доска обновлена.',{type:'success'});
    }catch(error){
      reportProgramBoardSyncError(error);
      if(error&&error.status===409)await reloadProgramBoard().catch(()=>{});
      render();
    }
  }, '[data-pb-sprint]', el=>el.dataset.pbSprint);
}

