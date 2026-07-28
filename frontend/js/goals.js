/* =====================================================================
   ВКЛАДКА 2 — Цели
===================================================================== */
// «Цель» вынесена в заголовок группы (задаётся справочником, выбирается на Pre PI Planning),
// поэтому среди строковых столбцов её нет.
const GOAL_COLS=[
  ['product','Продукт'],['initNum','№ Инициативы'],['init','Инициатива'],
  ['metric','Метрика'],['fact','AS IS (текущее)'],['plan','TO BE (прогноз)'],['hypo','Гипотезы'],['redesign','Редизайн']
];
// Редактируемые на вкладке «Цели» столбцы (синхронизируются с Pre PI Planning).
const GOAL_EDIT=['metric','fact','plan','hypo','redesign'];
function legacyViewGoalsLocal(){
  const tribes=tribesForGoals();
  const tr=state.ui.goalsTribe && tribes.includes(state.ui.goalsTribe)?state.ui.goalsTribe:null;
  let html=`<div class="card"><h2>Цели ${cycleBadge()}</h2>`;
  if(!tribes.length){ html+=`<div class="muted">Нет трайбов без чекбокса. Снимите чекбокс на вкладке «Данные PI-цикла».</div></div>`; return html; }

  html+=`<div>`+tribes.map(t=>`<span class="pill tribe ${tr===t?'sel':''}" data-tribe="${esc(t)}">${esc(t)}</span>`).join('')+`</div>`;

  if(tr){
    const teams=teamsOfTribeForGoals(tr);
    const tm=state.ui.goalsTeam && teams.some(x=>x.name===state.ui.goalsTeam)?state.ui.goalsTeam:null;
    html+=`<div style="margin-top:6px">`+teams.map(t=>`<span class="pill ${tm===t.name?'sel':''}" data-team="${esc(t.name)}">${esc(t.name)}</span>`).join('')+`</div>`;

    if(tm){
      const key=teamKey(tr,tm);
      const rows=state.goals[key]||[];
      // Столбцы одинаковы для обоих типов команд — как и таблица на Pre PI.
      // Тип влияет только на подпись группы: Agile группируется по цели, ИТ-проект — по вехе.
      // Значение и там и там берётся из общего поля «Цель/Веха» (cel).
      const isIT=teamType(teams.find(x=>x.name===tm))==='ИТ-проект';
      const COLS=GOAL_COLS;
      const EDIT=GOAL_EDIT;
      // фолбэк на связанную инициативу — для строк, созданных до объединения полей
      const groupVal=g=>String(g.cel || (findIssue(g.initNum)||{}).cel || '');
      html+=`<div class="goals-wrap"><table class="goals"><thead><tr><th>№</th>`+
        COLS.map(c=>`<th>${c[1]}</th>`).join('')+`</tr></thead><tbody>`;
      const colCount=COLS.length+1; // +столбец «№»
      if(!rows.length){
        html+=`<tr><td colspan="${colCount}" class="muted">Целей пока нет — добавьте их на вкладке «Pre PI Planning» кнопкой «Отправить на доски».</td></tr>`;
      }else{
        // группировка инициатив: индексы строк по значению «Цель/Веха»
        const byGoal=new Map();
        rows.forEach((g,idx)=>{
          const gk=groupVal(g);
          if(!byGoal.has(gk)) byGoal.set(gk,[]);
          byGoal.get(gk).push(idx);
        });
        // порядок групп: сначала по справочнику целей; затем прочие непустые (в т.ч. вехи,
        // введённые вручную, — их в справочнике нет); пустая группа в конце
        const order=[];
        (state.pi.goals||[]).forEach(name=>{ if(byGoal.has(name)) order.push(name); });
        [...byGoal.keys()].forEach(k=>{ if(k && !order.includes(k)) order.push(k); });
        if(byGoal.has('')) order.push('');
        const emptyLabel=isIT?'Без вехи':'Без цели';
        const groupIcon=isIT?'🏁 ':'🎯 ';
        let n=0; // сквозная нумерация строк в порядке отображения
        order.forEach(gname=>{
          html+=`<tr class="goal-group"><td colspan="${colCount}">${gname?(groupIcon+esc(gname)):emptyLabel}</td></tr>`;
          byGoal.get(gname).forEach(idx=>{
            const g=rows[idx]; n++;
            html+=`<tr draggable="true" data-goaldrag="${idx}"><td><span class="g-handle" title="Перетащите, чтобы изменить порядок">⠿</span>${n}</td>`+
              COLS.map(c=> EDIT.includes(c[0])
                ? `<td><input data-goal-i="${idx}" data-goal-k="${c[0]}" value="${esc(g[c[0]])}"></td>`
                : `<td>${esc(g[c[0]])||'<span class=auto>—</span>'}</td>`
              ).join('')+`</tr>`;
          });
        });
      }
      html+=`</tbody></table></div>
      <div class="note" style="margin-top:14px">${isIT
        ? 'Инициативы сгруппированы по <b>вехам ИТ-проекта</b> — веха вписывается вручную в столбец «Цель/Веха» на «Pre PI Planning». Поля метрика / AS IS / TO BE / гипотезы / редизайн можно редактировать прямо здесь — изменения синхронизируются с «Pre PI Planning»; для ИТ-проектов они необязательны. Перетаскивайте строки за <b>⠿</b>, чтобы менять порядок.'
        : 'Инициативы сгруппированы по <b>Цели</b>. Цель выбирается у инициативы на «Pre PI Planning» из справочника («Данные PI-цикла») либо вводится вручную. Поля метрика / AS IS / TO BE / гипотезы / редизайн можно редактировать прямо здесь — изменения синхронизируются с «Pre PI Planning». Перетаскивайте строки за <b>⠿</b>, чтобы менять порядок.'}</div>`;
    }else{
      html+=`<div class="muted" style="margin-top:14px">Выберите команду.</div>`;
    }
  }else{
    html+=`<div class="muted" style="margin-top:14px">Выберите трайб.</div>`;
  }
  html+=`</div>`;
  return html;
}
function legacyBindGoalsLocal(){
  document.querySelectorAll('[data-tribe]').forEach(el=>el.onclick=()=>{
    state.ui.goalsTribe=el.dataset.tribe;state.ui.goalsTeam=null;save();render();
  });
  document.querySelectorAll('[data-team]').forEach(el=>el.onclick=()=>{
    state.ui.goalsTeam=el.dataset.team;save();render();
  });
  // ключ выбранной команды (для правки и переупорядочивания целей)
  const tr=state.ui.goalsTribe, tm=state.ui.goalsTeam;
  if(!tr || !tm) return;
  const key=teamKey(tr,tm);
  // правка полей цели (Цель — локально; остальные — синхронизируются с Pre PI Planning)
  document.querySelectorAll('[data-goal-i]').forEach(el=>el.onchange=()=>{
    const rows=state.goals[key]||[]; const g=rows[+el.dataset.goalI]; if(!g)return;
    g[el.dataset.goalK]=el.value;
    syncGoalToIssue(g); // → вкладка «Pre PI Planning»
    save();render();
  });
  // drag&drop строк — изменение порядка целей
  bindGoalRowDrag(key);
}
// Перетаскивание строк на вкладке «Цели»
function legacyBindGoalRowDragLocal(key){
  let dragIdx=null;
  document.querySelectorAll('tr[data-goaldrag]').forEach(tr=>{
    tr.addEventListener('dragstart',e=>{
      if(e.target.closest('input,button')){ e.preventDefault(); return; } // не мешаем правке полей
      dragIdx=+tr.dataset.goaldrag;
      e.dataTransfer.effectAllowed='move';
      try{e.dataTransfer.setData('text/plain',String(dragIdx));}catch(_){}
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
      moveGoal(key,dragIdx,+tr.dataset.goaldrag,isPrepDropAfter(tr,e));
    });
  });
}
function legacyMoveGoalLocal(key,from,targetIdx,after){
  if(from==null || from===undefined) return;
  const rows=state.goals[key]; if(!rows) return;
  if(from===targetIdx) return;
  const [item]=rows.splice(from,1);
  let insertAt = after ? targetIdx+1 : targetIdx;
  if(from < insertAt) insertAt--; // компенсируем сдвиг после удаления
  rows.splice(insertAt,0,item);
  save();render();
}

const GOAL_STATUS_LABELS={planned:'Запланирована',in_progress:'В работе',done:'Готова',cancelled:'Отменена'};
const GOAL_CATEGORY_LABELS={committed:'Обязательная',stretch:'Дополнительная'};
function activeCycle(){const id=currentCycleId();return id&&state.cycles[id]?state.cycles[id]:null;}
function goalRef(){const c=activeCycle();return (c&&c.goalReference)||{};}
function goalRows(){const c=activeCycle();return (c&&Array.isArray(c.goalRows))?c.goalRows:[];}
function goalTeamOptions(){return (goalRef().teams||[]).filter(t=>!t.excluded_from_goals);}
function goalTribeOptions(){
  const allowed=new Set(goalTeamOptions().map(t=>String(t.tribe_id)));
  return (goalRef().tribes||[]).filter(t=>allowed.has(String(t.id)));
}
function goalInitiativeText(id){
  const item=(goalRef().initiatives||[]).find(i=>String(i.id)===String(id));
  return item?`${item.issue_key} · ${item.title}`:'';
}
function selectOptions(rows,value,{empty='Все',label=r=>r.name,val=r=>r.id}={}){
  return `<option value="">${esc(empty)}</option>`+rows.map(r=>{
    const v=String(val(r)||'');
    return `<option value="${esc(v)}" ${String(value||'')===v?'selected':''}>${esc(label(r))}</option>`;
  }).join('');
}
function showConfirm(title,message,details,onConfirm){
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${esc(title)}</h3>
    <div class="note" style="margin-bottom:12px">${esc(message)}</div>
    ${details&&details.length?`<ul style="margin:0 0 14px 18px;color:var(--muted)">${details.map(d=>`<li>${esc(d.issue_key||d.title||d.id||'')}</li>`).join('')}</ul>`:''}
    <div class="modal-actions"><button id="confirmCancel">Отмена</button><button class="primary" id="confirmOk">Подтвердить</button></div>
  </div></div>`;
  $('#confirmCancel').onclick=()=>root.innerHTML='';
  $('#confirmOk').onclick=async()=>{root.innerHTML='';await onConfirm();};
}
function handleCommandError(error,repeat){
  if(error&&error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required'){
    showConfirm('Подтверждение последствий',error.detail.message||'Нужно подтверждение',error.detail.affected||[],repeat);
    return true;
  }
  if(reportOptimisticConflict(error))return true;
  toast(error&&error.message?error.message:'Команда не выполнена',{type:'warn'});
  return true;
}
function legacyViewGoalsCrud(){
  const tribes=goalTribeOptions(),teams=goalTeamOptions();
  let html=`<div class="card"><h2>Цели ${cycleBadge()}</h2>`;
  if(!goalsApiReady&&!goalsBoards[currentCycleId()])return html+`<div class="muted">Загрузка целей с backend...</div></div>`;
  if(!cycleBackendIds[currentCycleId()])return html+`<div class="muted">Backend недоступен или PI-цикл не выбран.</div></div>`;
  if(!teams.length)return html+`<div class="muted">Добавьте трайбы и команды на вкладке «Данные PI-цикла». Цели не создаются из демонстрационных данных.</div></div>`;
  const tribeFilter=state.ui.goalsTribeId||'',teamFilter=state.ui.goalsTeamId||'',statusFilter=state.ui.goalsStatus||'';
  const filteredTeams=tribeFilter?teams.filter(t=>String(t.tribe_id)===String(tribeFilter)):teams;
  const rows=goalRows().filter(g=>
    (!tribeFilter||String(g.tribeId)===String(tribeFilter))&&
    (!teamFilter||String(g.teamId)===String(teamFilter))&&
    (!statusFilter||g.status===statusFilter)
  );
  html+=`<div class="row" style="align-items:flex-end">
    <label>Трайб<br><select id="goalFilterTribe">${selectOptions(tribes,tribeFilter,{empty:'Все трайбы'})}</select></label>
    <label>Команда<br><select id="goalFilterTeam">${selectOptions(filteredTeams,teamFilter,{empty:'Все команды'})}</select></label>
    <label>Статус<br><select id="goalFilterStatus"><option value="">Все статусы</option>${Object.entries(GOAL_STATUS_LABELS).map(([k,v])=>`<option value="${k}" ${statusFilter===k?'selected':''}>${v}</option>`).join('')}</select></label>
    <button class="primary" id="goalAdd">Создать цель</button>
  </div>`;
  html+=`<div class="goals-wrap"><table class="goals"><thead><tr>
    <th>№</th><th>Цель</th><th>Трайб / команда</th><th>Инициативы</th><th>Владелец</th><th>БЦ</th><th>Статус</th><th>Тип</th><th>Метрика</th><th></th>
  </tr></thead><tbody>`;
  if(!rows.length){
    html+=`<tr><td colspan="10" class="muted">Целей пока нет. Создайте первую цель или измените фильтры.</td></tr>`;
  }else{
    rows.forEach((g,i)=>{
      html+=`<tr draggable="true" data-goaldrag-id="${esc(g.id)}">
        <td><span class="g-handle" title="Изменить порядок">⠿</span>${i+1}</td>
        <td><b>${esc(g.title)}</b><div class="muted" style="font-size:11px">${esc(g.product||'')}</div></td>
        <td>${esc(g.tribe||'')}<div class="muted" style="font-size:11px">${esc(g.team||'')}</div></td>
        <td>${(g.initiativeIds||[]).map(id=>`<div>${esc(goalInitiativeText(id)||id)}</div>`).join('')||'<span class=auto>—</span>'}</td>
        <td>${esc(g.owner)||'<span class=auto>—</span>'}</td>
        <td>${g.businessValue!==''?esc(g.businessValue):'<span class=auto>—</span>'}</td>
        <td><select data-goal-status="${esc(g.id)}">${Object.entries(GOAL_STATUS_LABELS).map(([k,v])=>`<option value="${k}" ${g.status===k?'selected':''}>${v}</option>`).join('')}</select></td>
        <td>${GOAL_CATEGORY_LABELS[g.category]||g.category}</td>
        <td>${esc(g.metric)||'<span class=auto>—</span>'}</td>
        <td style="white-space:nowrap"><button class="sm" data-goal-edit="${esc(g.id)}">Изменить</button><button class="sm danger" data-goal-del="${esc(g.id)}">×</button></td>
      </tr>`;
    });
  }
  html+=`</tbody></table></div></div>`;
  return html;
}
function legacyBindGoalsCrud(){
  const ft=$('#goalFilterTribe'); if(ft)ft.onchange=()=>{state.ui.goalsTribeId=ft.value;state.ui.goalsTeamId='';save();render();};
  const fteam=$('#goalFilterTeam'); if(fteam)fteam.onchange=()=>{state.ui.goalsTeamId=fteam.value;save();render();};
  const fs=$('#goalFilterStatus'); if(fs)fs.onchange=()=>{state.ui.goalsStatus=fs.value;save();render();};
  const add=$('#goalAdd'); if(add)add.onclick=()=>openGoalModal(null);
  document.querySelectorAll('[data-goal-edit]').forEach(b=>b.onclick=()=>openGoalModal(b.dataset.goalEdit));
  document.querySelectorAll('[data-goal-del]').forEach(b=>b.onclick=()=>deleteGoalUi(b.dataset.goalDel));
  document.querySelectorAll('[data-goal-status]').forEach(el=>el.onchange=async()=>{
    try{await goalsBoardCommand(`/goals/${el.dataset.goalStatus}/status`,'PATCH',{status:el.value});toast('Статус цели обновлён',{type:'success'});}
    catch(error){handleCommandError(error,()=>goalsBoardCommand(`/goals/${el.dataset.goalStatus}/status`,'PATCH',{status:el.value}));}
  });
  bindGoalRowDrag();
}
function goalPayloadFromModal(){
  const selected=[...document.querySelectorAll('#gm_initiatives option:checked')].map(o=>o.value).filter(Boolean);
  const teamId=$('#gm_team').value||null;
  const team=goalTeamOptions().find(t=>String(t.id)===String(teamId));
  return {
    tribe_id:team?team.tribe_id:($('#gm_tribe').value||null),
    team_id:teamId,
    title:$('#gm_title').value.trim(),
    owner:$('#gm_owner').value.trim(),
    business_value:$('#gm_bv').value===''?null:+$('#gm_bv').value,
    status:$('#gm_status').value,
    category:$('#gm_category').value,
    product:$('#gm_product').value.trim(),
    metric:$('#gm_metric').value.trim(),
    current_value:$('#gm_current').value.trim(),
    target_value:$('#gm_target').value.trim(),
    hypothesis:$('#gm_hypothesis').value.trim(),
    redesign:$('#gm_redesign').value.trim(),
    initiative_ids:selected,
  };
}
function legacyOpenGoalModal(goalId){
  const g=goalRows().find(x=>x.id===goalId)||{};
  const ref=goalRef(),teams=goalTeamOptions();
  const teamValue=g.teamId||state.ui.goalsTeamId||'';
  const tribeValue=g.tribeId||state.ui.goalsTribeId||'';
  const root=$('#modalRoot');
  root.innerHTML=`<div class="overlay"><div class="modal">
    <h3>${goalId?'Редактирование цели':'Новая цель'}</h3>
    <label><span>Цель</span><input id="gm_title" value="${esc(g.title||'')}"></label>
    <label><span>Трайб</span><select id="gm_tribe">${selectOptions(goalTribeOptions(),tribeValue,{empty:'Без трайба'})}</select></label>
    <label><span>Команда</span><select id="gm_team">${selectOptions(teams,teamValue,{empty:'Без команды',label:t=>`${t.tribe} / ${t.name}`})}</select></label>
    <label><span>Инициативы</span><select id="gm_initiatives" multiple size="6">${(ref.initiatives||[]).map(i=>`<option value="${esc(i.id)}" ${(g.initiativeIds||[]).includes(i.id)?'selected':''}>${esc(i.issue_key)} · ${esc(i.title)}</option>`).join('')}</select></label>
    <label><span>Владелец</span><input id="gm_owner" value="${esc(g.owner||'')}"></label>
    <label><span>Бизнес-ценность</span><input id="gm_bv" type="number" min="0" max="100" value="${esc(g.businessValue||'')}"></label>
    <label><span>Статус</span><select id="gm_status">${Object.entries(GOAL_STATUS_LABELS).map(([k,v])=>`<option value="${k}" ${(g.status||'planned')===k?'selected':''}>${v}</option>`).join('')}</select></label>
    <label><span>Тип цели</span><select id="gm_category">${Object.entries(GOAL_CATEGORY_LABELS).map(([k,v])=>`<option value="${k}" ${(g.category||'committed')===k?'selected':''}>${v}</option>`).join('')}</select></label>
    <label><span>Продукт</span><input id="gm_product" value="${esc(g.product||'')}"></label>
    <label><span>Метрика</span><input id="gm_metric" value="${esc(g.metric||'')}"></label>
    <label><span>AS IS</span><input id="gm_current" value="${esc(g.fact||'')}"></label>
    <label><span>TO BE</span><input id="gm_target" value="${esc(g.plan||'')}"></label>
    <label><span>Гипотеза</span><textarea id="gm_hypothesis" rows="2">${esc(g.hypo||'')}</textarea></label>
    <label><span>Редизайн</span><textarea id="gm_redesign" rows="2">${esc(g.redesign||'')}</textarea></label>
    <div class="modal-actions"><button id="gm_cancel">Отмена</button><button class="primary" id="gm_save">Сохранить</button></div>
  </div></div>`;
  $('#gm_cancel').onclick=()=>root.innerHTML='';
  $('#gm_save').onclick=async()=>{
    const payload=goalPayloadFromModal();
    if(!payload.title){toast('Укажите цель',{type:'warn'});return;}
    const run=confirm_cascade=>goalsBoardCommand(goalId?`/goals/${goalId}`:'/goals',goalId?'PATCH':'POST',{...payload,confirm_cascade});
    try{await run(false);root.innerHTML='';toast(goalId?'Цель обновлена':'Цель создана',{type:'success'});}
    catch(error){handleCommandError(error,async()=>{await run(true);root.innerHTML='';toast('Цель обновлена',{type:'success'});});}
  };
}
function deleteGoalUi(goalId){
  showConfirm('Удаление цели','Цель будет удалена из активного PI-цикла. Если есть связанные инициативы, backend потребует отдельное подтверждение.',[],async()=>{
    const run=confirm_cascade=>goalsBoardCommand(`/goals/${goalId}`,'DELETE',{confirm_cascade});
    try{await run(false);toast('Цель удалена',{type:'info'});}
    catch(error){handleCommandError(error,async()=>{await run(true);toast('Цель удалена',{type:'info'});});}
  });
}
function legacyBindGoalRowDragCrud(){
  let dragIdx=null;
  document.querySelectorAll('tr[data-goaldrag-id]').forEach(tr=>{
    tr.addEventListener('dragstart',e=>{
      if(e.target.closest('select,button')){ e.preventDefault(); return; }
      dragIdx=tr.dataset.goaldragId;
      e.dataTransfer.effectAllowed='move';
      try{e.dataTransfer.setData('text/plain',String(dragIdx));}catch(_){}
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
      legacyMoveGoalCrud(dragIdx,tr.dataset.goaldragId,isPrepDropAfter(tr,e));
    });
  });
}
async function legacyMoveGoalCrud(fromId,targetId,after){
  if(!fromId||!targetId||fromId===targetId)return;
  const ids=goalRows().map(g=>g.id);
  const from=ids.indexOf(fromId),target=ids.indexOf(targetId);
  if(from<0||target<0)return;
  const [item]=ids.splice(from,1);
  let insertAt=after?target+1:target;
  if(from<insertAt)insertAt--;
  ids.splice(insertAt,0,item);
  try{await goalsBoardCommand('/order','PUT',{goal_ids:ids});toast('Порядок целей обновлён',{type:'success'});}
  catch(error){handleCommandError(error,()=>goalsBoardCommand('/order','PUT',{goal_ids:ids}));}
}

