/* =====================================================================
   ВКЛАДКА 1 — Данные PI-цикла
===================================================================== */
// Каноническая вкладка PI Data: DOM строится только из read-model backend.
function piCascadeMessage(detail){
  const affected=detail&&detail.affected||{};
  const summary=Object.entries(affected).filter(([,count])=>count).map(([name,count])=>`${name}: ${count}`).join(', ');
  return `Изменение требует каскадной обработки связанных данных${summary?` (${summary})`:''}. Продолжить?`;
}
async function refreshPiProjectionsAfterDataCommand(){
  const reads=[];
  if(backlogApiReady) reads.push(loadBacklogBoard());
  if(prePiApiReady) reads.push(loadPrePiCycles());
  if(goalsApiReady) reads.push(loadGoalsCycles());
  if(teamBoardsApiReady) reads.push(loadTeamBoardsCycles());
  if(capacityApiReady) reads.push(loadCapacityCycles());
  if(programBoardApiReady) reads.push(loadProgramBoardCycles());
  if(risksApiReady) reads.push(loadRisksCycles());
  await Promise.all(reads);
}
async function executePiDataCommand(path,options={},cascadeBody=null){
  try{
    await piDataCommand(path,options);
  }catch(error){
    const cascade=error&&error.status===409&&error.detail&&error.detail.code==='cascade_confirmation_required';
    if(cascade&&cascadeBody&&window.confirm(piCascadeMessage(error.detail))){
      await piDataCommand(path,{...options,body:{...(options.body||{}),...cascadeBody}});
    }else{
      if(error&&error.status===409&&!cascade){
        reportOptimisticConflict(error);
        await loadPiDataView(currentCycleId()).catch(()=>{});
        render();
      }
      throw error;
    }
  }
  await refreshPiProjectionsAfterDataCommand().catch(error=>console.error('Projection refresh failed',error));
  render();
  toast('Изменения сохранены на сервере',{type:'success'});
}
function prototypePirRow(row,editable){
  const ro=editable?'':'readonly', dis=editable?'':'disabled';
  return `<div class="row" data-pir-row data-pir-id="${esc(row.id||'')}">
    <input class="pir-name" value="${esc(row.name||'')}" ${ro} placeholder="ПИР">
    <input type="date" class="pir-date" value="${esc(row.date||'')}" ${dis}>
    ${editable?'<button class="icon danger sm" data-delete-pir>✕</button>':''}
  </div>`;
}
function prototypeTeamRow(row,editable,refs){
  const ro=editable?'':'readonly', dis=editable?'':'disabled';
  const competencies=row.competencies||[];
  const compCell=editable
    ? `<details class="comp-dd"><summary><span class="dd-chips">${competencies.map(code=>`<span class="comp-tag">${esc(code)}</span>`).join('')||'<span class="comp-cells-empty">выберите…</span>'}</span><span class="dd-caret">▾</span></summary><div class="dd-panel">${(refs.competencies||[]).map(code=>`<label class="dd-opt"><input type="checkbox" class="t-comp" data-c="${esc(code)}" ${competencies.includes(code)?'checked':''}>${esc(code)}</label>`).join('')}</div></details>`
    : `<span class="dd-chips">${competencies.map(code=>`<span class="comp-tag">${esc(code)}</span>`).join('')||'<span class="comp-cells-empty">—</span>'}</span>`;
  return `<tr data-team-row data-team-id="${esc(row.id||'')}">
    <td><input class="t-tribe" value="${esc(row.tribe||'')}" ${ro} placeholder="Трайб" style="width:200px"></td>
    <td><input class="t-name" value="${esc(row.name||'')}" ${ro} placeholder="Команда" style="width:200px"></td>
    <td><select class="t-type" ${dis} style="width:140px" title="Тип команды">${(refs.team_types||[]).map(type=>`<option value="${esc(type)}" ${type===(row.team_type||'Agile')?'selected':''}>${esc(type)}</option>`).join('')}</select></td>
    <td><label class="switch" title="Есть ли у команды цель (попадает ли на вкладку «Цели»)"><input type="checkbox" class="t-plan" ${row.excluded_from_goals?'':'checked'} ${dis}><span class="track"></span><span class="switch-lab">${row.excluded_from_goals?'Нет цели':'Есть цель'}</span></label></td>
    <td>${compCell}</td>
    <td>${editable?'<button class="icon danger sm" data-delete-team>✕</button>':''}</td>
  </tr>`;
}
function prototypeNamedRow(kind,row,editable){
  const isGoal=kind==='goal';
  const ro=editable?'':'readonly';
  return `<div class="row${isGoal?'':' tag-row'}" data-${kind}-row data-${kind}-id="${esc(row.id||'')}"><input class="${isGoal?'g-name':'tag-name'}" value="${esc(row.name||'')}" ${ro} placeholder="${isGoal?'Название цели':'Название тэга'}" ${isGoal?'style="width:400px"':''}>${editable?`<button class="icon danger sm" data-delete-${kind}>✕</button>`:''}</div>`;
}
function viewData(){
  const view=piDataViews[currentCycleId()];
  if(!view) return `<div class="card"><h2>Данные PI-цикла</h2><div class="note">Данные с сервера не загружены. Локальная копия PI-цикла не используется.</div></div>`;
  const editable=!!state.ui.dataEdit;
  const dis=editable?'':'disabled';
  const refs=view.reference_data||{team_types:['Agile','ИТ-проект'],competencies:['SA','DEV','QA','FE','BE','DES'],sprint_count_min:1,sprint_count_max:20};
  const pirs=(view.pirs||[]).map(row=>prototypePirRow(row,editable)).join('');
  const teamRows=(view.teams||[]).map(row=>prototypeTeamRow(row,editable,refs)).join('');
  const goals=(view.goal_options||[]).map(row=>prototypeNamedRow('goal',row,editable)).join('');
  const tags=(view.tags||[]).map(row=>prototypeNamedRow('tag',row,editable)).join('');
  return `<div class="card" id="piDataCard">
    <div class="flex-between"><h2>Данные PI-цикла ${cycleBadge()}</h2><div>${editable?'<button class="primary" id="saveData">Сохранить</button>':'<button id="editData">Редактировать</button>'}</div></div>
    <label class="fld"><span class="lab">Дата старта PI-цикла</span><input type="date" id="startDate" value="${esc(view.cycle.start_date||'')}" ${dis}></label>
    <label class="fld"><span class="lab">Количество спринтов</span><input type="number" min="${esc(refs.sprint_count_min)}" max="${esc(refs.sprint_count_max)}" id="sprintCount" value="${esc(view.cycle.sprint_count)}" ${dis} style="width:90px"></label>
    <h3>Данные ПИРов ${editable?'<button class="plus" id="addPir">+</button>':''}</h3><div id="pirRows">${pirs||'<div class="muted" data-empty>Нет данных</div>'}</div>
    <h3>Данные по командам ${editable?'<button class="plus" id="addTeam">+</button>':''}</h3>
    <table class="data-teams"><thead><tr><th>Трайб</th><th>Команда</th><th>Тип</th><th>Наличие цели</th><th>Компетенции</th><th></th></tr></thead><tbody id="teamRows">${teamRows||'<tr data-empty><td colspan="6" class="muted">Нет данных</td></tr>'}</tbody></table>
    <h3>Цели PI ${editable?'<button class="plus" id="addGoal">+</button>':''}</h3><div id="goalRows">${goals||'<div class="muted" data-empty>Целей пока нет</div>'}</div>
    <div class="hint" style="margin-top:4px">Список целей используется на вкладке «Pre PI Planning» — в столбце «Цель» инициативы выбираются из этого списка.</div>
    <h3>Тэги стикеров ${editable?'<button class="plus" id="addTag">+</button>':''}</h3><div id="tagRows">${tags||'<div class="muted" data-empty>Тэгов пока нет</div>'}</div>
    <div class="hint" style="margin-top:4px">Список тэгов используется в карточке стикера. Выбранные тэги отображаются на «Program Board» и «Командных досках».</div>
    <div class="note" style="margin-top:14px">Переключатель <b>«Наличие цели»</b>: команды со статусом «Нет цели» не попадают на вкладку «Цели». На «Program Board» и «Командные доски» выводятся <b>все</b> трайбы и команды. Спринты формируются автоматически от даты старта (по 2 недели).<br><b>Компетенции команды</b> (SA/DEV/QA/FE/BE/DES) выбираются выпадающим списком и используются на вкладках «Бэклог команд» и «Pre PI Planning»: у команды-исполнителя показываются <b>только выбранные здесь</b> компетенции.</div>
  </div>`;
}
function piDataFormPayload(){
  return {
    start_date:$('#startDate').value||null,
    sprint_count:+$('#sprintCount').value,
    pirs:[...document.querySelectorAll('[data-pir-row]')].map(row=>({id:row.dataset.pirId||null,name:row.querySelector('.pir-name').value.trim(),date:row.querySelector('.pir-date').value})).filter(row=>row.name&&row.date),
    teams:[...document.querySelectorAll('[data-team-row]')].map(row=>({id:row.dataset.teamId||null,tribe:row.querySelector('.t-tribe').value.trim(),name:row.querySelector('.t-name').value.trim(),team_type:row.querySelector('.t-type').value,excluded_from_goals:!row.querySelector('.t-plan').checked,competencies:[...row.querySelectorAll('.t-comp:checked')].map(el=>el.dataset.c)})).filter(row=>row.tribe&&row.name),
    goal_options:[...document.querySelectorAll('[data-goal-row]')].map(row=>({id:row.dataset.goalId||null,name:row.querySelector('.g-name').value.trim()})).filter(row=>row.name),
    tags:[...document.querySelectorAll('[data-tag-row]')].map(row=>({id:row.dataset.tagId||null,name:row.querySelector('.tag-name').value.trim()})).filter(row=>row.name),
  };
}
function bindData(){
  const view=piDataViews[currentCycleId()]; if(!view)return;
  const root=$('#piDataCard'); if(!root)return;
  const refs=view.reference_data;
  root.onclick=async event=>{
    const button=event.target.closest('button'); if(!button)return;
    if(button.id==='editData'){state.ui.dataEdit=true;save(false);render();return;}
    if(button.id==='addPir'){const box=$('#pirRows');box.querySelector('[data-empty]')?.remove();box.insertAdjacentHTML('beforeend',prototypePirRow({},true));return;}
    if(button.id==='addTeam'){const box=$('#teamRows');box.querySelector('[data-empty]')?.remove();box.insertAdjacentHTML('beforeend',prototypeTeamRow({team_type:'Agile',competencies:BASE_TEAM_COMPS.slice()},true,refs));return;}
    if(button.id==='addGoal'){const box=$('#goalRows');box.querySelector('[data-empty]')?.remove();box.insertAdjacentHTML('beforeend',prototypeNamedRow('goal',{},true));return;}
    if(button.id==='addTag'){const box=$('#tagRows');box.querySelector('[data-empty]')?.remove();box.insertAdjacentHTML('beforeend',prototypeNamedRow('tag',{},true));return;}
    if(button.hasAttribute('data-delete-pir')){button.closest('[data-pir-row]').remove();return;}
    if(button.hasAttribute('data-delete-team')){button.closest('[data-team-row]').remove();return;}
    if(button.hasAttribute('data-delete-goal')){button.closest('[data-goal-row]').remove();return;}
    if(button.hasAttribute('data-delete-tag')){button.closest('[data-tag-row]').remove();return;}
    if(button.id==='saveData'){
      button.disabled=true;
      try{
        await executePiDataCommand('/data',{method:'PUT',body:piDataFormPayload()},{confirm_cascade:true});
        state.ui.dataEdit=false;save(false);render();
      }catch(error){
        if(!(error&&error.status===409))toast(error.message||'Сервер не выполнил команду',{type:'warn',timeout:7000});
        button.disabled=false;
      }
    }
  };
  root.onchange=event=>{
    if(event.target.matches('.t-plan')){const lab=event.target.parentElement.querySelector('.switch-lab');if(lab)lab.textContent=event.target.checked?'Есть цель':'Нет цели';}
    if(event.target.matches('.t-comp')){const dd=event.target.closest('.comp-dd'),chips=dd&&dd.querySelector('.dd-chips');if(!chips)return;const picked=[...dd.querySelectorAll('.t-comp:checked')].map(el=>el.dataset.c);chips.innerHTML=picked.map(code=>`<span class="comp-tag">${esc(code)}</span>`).join('')||'<span class="comp-cells-empty">выберите…</span>';}
  };
}

/* =====================================================================
   ФИЛЬТРЫ ПО СТОЛБЦАМ ТАБЛИЦ («Бэклог команд» и «Pre PI Planning»)
   Excel-подобный фильтр: в шапке столбца — воронка, по клику открывается
   список уникальных значений с чекбоксами.
   Описание столбца: {k, label, val?} — val(row) возвращает значение или
   массив значений (многозначные столбцы, напр. «АС»).
   Фильтр столбца — массив выбранных значений; пустой/отсутствует = «все».
   scope: 'bk' | 'prep:upper' | 'prep:lower'.
===================================================================== */
const FILTER_EMPTY_LABEL='(Пусто)';
// Контекст таблиц текущего рендера: scope -> {rows, cols}. Нужен обработчикам клика.
let colFilterCtx={};
function colFilters(scope){
  if(!state.ui.colFilters) state.ui.colFilters={};
  return state.ui.colFilters[scope] = state.ui.colFilters[scope] || {};
}
function clearColFilters(scope){ if(state.ui.colFilters) delete state.ui.colFilters[scope]; }

/* ---- Сортировка по столбцу ---- */
// Активна не более чем по одному столбцу таблицы: {k, dir:'asc'|'desc'}.
function colSort(scope){ return (state.ui.colSort||{})[scope]||null; }
function setColSort(scope,k,dir){
  if(!state.ui.colSort) state.ui.colSort={};
  state.ui.colSort[scope]={k,dir};
}
function clearColSort(scope){ if(state.ui.colSort) delete state.ui.colSort[scope]; }
// Подпись столбца, по которому идёт сортировка (для плашки над таблицей).
function sortColLabel(scope,k){
  const ctx=colFilterCtx[scope];
  const col=ctx && ctx.cols.find(c=>c.k===k);
  return col?col.label:k;
}
// Сброс состояния столбцов таблицы (и фильтры, и сортировка).
function clearColState(scope){ clearColFilters(scope); clearColSort(scope); }
// Оба блока Pre PI сразу: при смене трайба/команды состав строк меняется,
// поэтому фильтр и сортировку по столбцам снимаем.
function clearPrepColFilters(){ clearColState('prep:upper'); clearColState('prep:lower'); }
// Сообщение при попытке перетащить строку, когда порядок задаёт сортировка.
const SORT_DRAG_MSG='Порядок строк задаёт сортировка — сбросьте её, чтобы менять порядок вручную';
function colFiltersCount(scope){
  const f=(state.ui.colFilters||{})[scope]||{};
  return Object.keys(f).filter(k=>Array.isArray(f[k])&&f[k].length).length;
}
// Значения строки в столбце — всегда массив строк; пустое значение = ''.
function colValues(row,col){
  const raw = col.val ? col.val(row) : row[col.k];
  const arr = Array.isArray(raw) ? raw : [raw];
  const out=[];
  arr.forEach(x=>{
    const v = (x===null||x===undefined) ? '' : String(x).trim();
    if(!out.includes(v)) out.push(v);
  });
  return out.length ? out : [''];
}
// Сравнение двух значений столбца: числа — по величине, остальное — по алфавиту (ru).
// Приоритеты и оценки хранятся строками, поэтому «10» должно идти после «9», а не после «1».
function compareColVals(a,b){
  const na=parseFloat(a), nb=parseFloat(b);
  if(!isNaN(na)&&!isNaN(nb)&&String(na)===a&&String(nb)===b) return na-nb;
  return a.localeCompare(b,'ru');
}
// Уникальные значения столбца по набору строк (для списка в попапе).
function colUniqueValues(rows,col){
  const set=new Set();
  rows.forEach(r=>colValues(r,col).forEach(v=>set.add(v)));
  return [...set].sort((a,b)=>{
    if(a==='') return 1;
    if(b==='') return -1;
    return compareColVals(a,b);
  });
}
// Сортировка строк по выбранному столбцу. Пустые значения всегда внизу (как в Excel),
// независимо от направления; равные значения сохраняют исходный порядок (стабильно).
// У многозначных столбцов (напр. «АС») сортируем по первому значению.
function applyColSort(rows,cols,scope){
  const s=colSort(scope); if(!s) return rows;
  const col=cols.find(c=>c.k===s.k); if(!col) return rows;
  const dir=s.dir==='desc'?-1:1;
  return rows.map((r,i)=>({r,i})).sort((a,b)=>{
    const va=colValues(a.r,col)[0], vb=colValues(b.r,col)[0];
    if(va==='' || vb===''){ return va===vb ? a.i-b.i : (va===''?1:-1); }
    return compareColVals(va,vb)*dir || a.i-b.i;
  }).map(x=>x.r);
}
// Строка проходит фильтры по всем столбцам (кроме исключённого — для списка значений в попапе).
function rowMatchesColFilters(row,cols,filters,skipKey){
  return cols.every(c=>{
    if(c.k===skipKey) return true;
    const sel=filters[c.k];
    if(!Array.isArray(sel)||!sel.length) return true;
    return colValues(row,c).some(v=>sel.includes(v));
  });
}
function applyColFilters(rows,cols,scope){
  const f=colFilters(scope);
  if(!colFiltersCount(scope)) return rows;
  return rows.filter(r=>rowMatchesColFilters(r,cols,f));
}
// Шапка столбца с кнопкой фильтра/сортировки. Стрелка ↑/↓ показывает активную сортировку.
function filterThHTML(col,scope,extraClass){
  const on=colFiltersCount(scope) && Array.isArray(colFilters(scope)[col.k]) && colFilters(scope)[col.k].length;
  const s=colSort(scope);
  const sorted=!!(s && s.k===col.k);
  const arrow=sorted?(s.dir==='asc'?'↑':'↓'):'';
  return `<th class="${extraClass||''}"><div class="th-f"><span>${esc(col.label)}</span>`+
    (sorted?`<span class="col-s" title="Сортировка ${s.dir==='asc'?'по возрастанию':'по убыванию'}">${arrow}</span>`:'')+
    `<button class="col-f${on?' on':''}${sorted?' sorted':''}" data-fscope="${esc(scope)}" data-fcol="${esc(col.k)}" title="Фильтр и сортировка по столбцу «${esc(col.label)}»">▼</button></div></th>`;
}
// Плашка «Фильтры: N · Сортировка: столбец» над таблицей — только когда что-то активно.
function tableToolsBarHTML(scope,label){
  const n=colFiltersCount(scope), s=colSort(scope);
  if(!n && !s) return '';
  const parts=[];
  if(n) parts.push(`Фильтры${label?` (${esc(label)})`:''}: <b>${n}</b> ${n===1?'столбец':'столб.'}
    <button class="ghost colf-clear" data-fclear="${esc(scope)}">Сбросить фильтры</button>`);
  if(s) parts.push(`Сортировка: <b>${esc(sortColLabel(scope,s.k))}</b> ${s.dir==='asc'?'↑':'↓'}
    <button class="ghost colf-clear" data-sclear="${esc(scope)}">Сбросить сортировку</button>`);
  return `<div class="colf-bar">${parts.join('<span class="colf-sep">·</span>')}</div>`;
}

let colfPop=null;
function closeColFilterPop(){
  if(colfPop){ colfPop.remove(); colfPop=null; }
  document.removeEventListener('mousedown',colfOutside,true);
}
function colfOutside(e){
  if(colfPop && !colfPop.contains(e.target) && !e.target.closest('[data-fcol]')) closeColFilterPop();
}
function openColFilterPop(btn,scope,colKey){
  closeColFilterPop();
  const ctx=colFilterCtx[scope]; if(!ctx) return;
  const col=ctx.cols.find(c=>c.k===colKey); if(!col) return;
  const filters=colFilters(scope);
  const sel=Array.isArray(filters[colKey])?filters[colKey].slice():[];
  // Значения, доступные с учётом фильтров по ДРУГИМ столбцам (как в Excel),
  // плюс уже выбранные — чтобы выбор не «пропадал» из списка.
  const base=ctx.rows.filter(r=>rowMatchesColFilters(r,ctx.cols,filters,colKey));
  const vals=colUniqueValues(base,col);
  sel.forEach(v=>{ if(!vals.includes(v)) vals.push(v); });

  const s=colSort(scope);
  const sdir = (s && s.k===colKey) ? s.dir : null;

  const pop=document.createElement('div');
  pop.className='colf-pop';
  pop.innerHTML=`<div class="colf-head">${esc(col.label)}</div>
    <div class="colf-sort">
      <button class="colf-sbtn${sdir==='asc'?' on':''}" data-colf-sort="asc" title="Сортировать по возрастанию (пустые — внизу)">↑ По возрастанию</button>
      <button class="colf-sbtn${sdir==='desc'?' on':''}" data-colf-sort="desc" title="Сортировать по убыванию (пустые — внизу)">↓ По убыванию</button>
    </div>
    <input class="colf-search" placeholder="Поиск…">
    <label class="colf-item colf-all"><input type="checkbox" class="colf-allbox"><span>Выделить всё</span></label>
    <div class="colf-list">${
      vals.map(v=>`<label class="colf-item" data-v="${esc(v)}"><input type="checkbox" class="colf-box" ${sel.includes(v)?'checked':''}>
        <span class="${v===''?'muted':''}">${v===''?FILTER_EMPTY_LABEL:esc(v)}</span></label>`).join('')
      || `<div class="muted" style="padding:6px 4px">Нет значений</div>`
    }</div>
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

  const boxes=()=>[...pop.querySelectorAll('.colf-list .colf-item:not([hidden]) .colf-box')];
  const allBox=pop.querySelector('.colf-allbox');
  const syncAll=()=>{
    const b=boxes(), on=b.filter(x=>x.checked).length;
    allBox.checked = b.length>0 && on===b.length;
    allBox.indeterminate = on>0 && on<b.length;
  };
  syncAll();
  allBox.onchange=()=>{ boxes().forEach(x=>{ x.checked=allBox.checked; }); syncAll(); };
  pop.querySelectorAll('.colf-box').forEach(x=>x.onchange=syncAll);
  const search=pop.querySelector('.colf-search');
  search.oninput=()=>{
    const q=search.value.trim().toLowerCase();
    pop.querySelectorAll('.colf-list .colf-item').forEach(it=>{
      const v=it.dataset.v||'';
      const text=(v===''?FILTER_EMPTY_LABEL:v).toLowerCase();
      it.hidden = !!q && !text.includes(q);
    });
    syncAll();
  };
  // сортировка: повторный клик по активному направлению — снимает её
  pop.querySelectorAll('[data-colf-sort]').forEach(b=>b.onclick=()=>{
    const dir=b.dataset.colfSort;
    if(sdir===dir) clearColSort(scope); else setColSort(scope,colKey,dir);
    closeColFilterPop(); save(); render();
  });
  pop.querySelector('[data-colf-reset]').onclick=()=>{
    delete colFilters(scope)[colKey]; closeColFilterPop(); save(); render();
  };
  pop.querySelector('[data-colf-apply]').onclick=()=>{
    const picked=[];
    pop.querySelectorAll('.colf-list .colf-item').forEach(it=>{
      const b=it.querySelector('.colf-box');
      if(b && b.checked) picked.push(it.dataset.v||'');
    });
    // выбрано всё (или ничего) — фильтр по столбцу снимается
    if(!picked.length || picked.length===vals.length) delete colFilters(scope)[colKey];
    else colFilters(scope)[colKey]=picked;
    closeColFilterPop(); save(); render();
  };
  setTimeout(()=>{ search.focus(); document.addEventListener('mousedown',colfOutside,true); },0);
}
// Общий биндинг кнопок фильтра — вызывается из bindBacklog()/bindPrep().
function bindColFilters(){
  document.querySelectorAll('[data-fcol]').forEach(el=>el.onclick=(e)=>{
    e.stopPropagation();
    openColFilterPop(el, el.dataset.fscope, el.dataset.fcol);
  });
  document.querySelectorAll('[data-fclear]').forEach(el=>el.onclick=()=>{
    clearColFilters(el.dataset.fclear); save(); render();
  });
  document.querySelectorAll('[data-sclear]').forEach(el=>el.onclick=()=>{
    clearColSort(el.dataset.sclear); save(); render();
  });
}

