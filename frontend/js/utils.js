function uid(){ return 's'+Math.random().toString(36).slice(2,9); }
function normalizeTags(list){
  const out=[];
  (Array.isArray(list)?list:[]).forEach(t=>{
    const v=String(t||'').trim();
    if(v && !out.includes(v)) out.push(v);
  });
  return out;
}
function cleanIssueTags(){
  const allowed=piTags();
  (state.issues||[]).forEach(i=>{
    i.tags=normalizeTags(i.tags).filter(t=>allowed.includes(t));
  });
}
/* =====================================================================
   ВСПОМОГАТЕЛЬНЫЕ
===================================================================== */
const $ = (sel,root=document)=>root.querySelector(sel);
const esc = s => String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const teamKey = (tribe,name)=>tribe+'||'+name;
// Красивое всплывающее уведомление вместо alert()
function toast(msg,opts={}){
  const type=opts.type||'success';
  const title=opts.title||({success:'Готово',info:'Информация',warn:'Внимание'}[type]||'');
  const ico=({success:'✓',info:'i',warn:'!'}[type]||'i');
  const root=document.getElementById('toastRoot'); if(!root)return;
  const el=document.createElement('div');
  el.className='toast '+type;
  el.innerHTML=`<div class="t-ico">${ico}</div>
    <div class="t-bd"><div class="t-title">${esc(title)}</div><div class="t-msg">${esc(msg)}</div></div>
    <button class="t-close" aria-label="Закрыть">×</button>`;
  const remove=()=>{ el.classList.add('out'); setTimeout(()=>el.remove(),220); };
  el.querySelector('.t-close').onclick=remove;
  root.appendChild(el);
  setTimeout(remove,opts.duration||4000);
}
const SPRINT_DAYS = 14;

function pad(n){return String(n).padStart(2,'0');}
function fmt(d){return pad(d.getDate())+'.'+pad(d.getMonth()+1)+'.'+d.getFullYear();}
function addDays(d,n){const x=new Date(d);x.setDate(x.getDate()+n);return x;}
function parseISO(s){const[y,m,dd]=s.split('-').map(Number);return new Date(y,m-1,dd);}
const pad2=n=>String(n).padStart(2,'0');
// год PI для выбора дат отпуска (отпуск хранится без года — «дд.мм-дд.мм»)
function piYear(){ return state.pi.startDate ? parseISO(state.pi.startDate).getFullYear() : new Date().getFullYear(); }
// «20.07-01.08» → {start:'2026-07-20', end:'2026-08-01'} (для <input type="date">)
function vacToDates(vac){
  const m=(vac||'').match(/(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})/);
  if(!m) return {start:'',end:''};
  const y=piYear();
  return {start:`${y}-${pad2(m[2])}-${pad2(m[1])}`, end:`${y}-${pad2(m[4])}-${pad2(m[3])}`};
}
// два ISO-значения дат → «20.07-01.08» (день.месяц)
function datesToVac(s,e){
  if(!s||!e) return '';
  const a=s.split('-'), b=e.split('-');
  if(a[2]===b[2] && a[1]===b[1]) return `${a[2]}.${a[1]}`;
  return `${a[2]}.${a[1]}-${b[2]}.${b[1]}`;
}
const MON_RU=['','янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
// «20.07-01.08» → «20 июл — 1 авг» (для чипа отпуска)
function formatVacShort(vac){
  return formatRangesShort(vac);
}
function parseDateRanges(text){
  const y=piYear();
  return String(text||'').split(/[;,]/).map(x=>x.trim()).filter(Boolean).map(part=>{
    const m=part.match(/^(\d{1,2})\.(\d{1,2})(?:\s*[-–—]\s*(\d{1,2})\.(\d{1,2}))?$/);
    if(!m) return null;
    const start=new Date(y,+m[2]-1,+m[1]);
    const end=m[3] ? new Date(y,+m[4]-1,+m[3]) : new Date(start);
    return end<start ? null : {start,end};
  }).filter(Boolean);
}
function rangesToIso(text){
  return parseDateRanges(text).map(r=>({
    start:`${r.start.getFullYear()}-${pad2(r.start.getMonth()+1)}-${pad2(r.start.getDate())}`,
    end:`${r.end.getFullYear()}-${pad2(r.end.getMonth()+1)}-${pad2(r.end.getDate())}`,
  }));
}
function formatRangesShort(text){
  const ranges=parseDateRanges(text);
  if(!ranges.length) return '';
  return ranges.map(r=>{
    const a=`${r.start.getDate()} ${MON_RU[r.start.getMonth()+1]}`;
    const b=`${r.end.getDate()} ${MON_RU[r.end.getMonth()+1]}`;
    return r.start.getTime()===r.end.getTime() ? a : `${a} — ${b}`;
  }).join('; ');
}
function weekdaysBetween(a,b){
  if(b<a) return 0;
  let c=0,d=new Date(a);
  while(d<=b){const w=d.getDay();if(w!==0&&w!==6)c++;d=addDays(d,1);}
  return c;
}
function computeSprints(){
  const out=[]; const n=Math.max(0,parseInt(state.pi.sprintCount)||0);
  if(!state.pi.startDate) return out;
  let start=parseISO(state.pi.startDate);
  for(let i=0;i<n;i++){
    const s=addDays(start,i*SPRINT_DAYS);
    const e=addDays(s,SPRINT_DAYS-1);
    const pirs=state.pi.pirs.filter(p=>{
      if(!p.date)return false;const pd=parseISO(p.date);return pd>=s&&pd<=e;
    });
    out.push({index:i,start:s,end:e,workdays:weekdaysBetween(s,e),pirs});
  }
  return out;
}
function sprintWeekPeriod(s,week){
  const start=week===1 ? addDays(s.start,7) : s.start;
  const end=week===1 ? s.end : addDays(s.start,6);
  const pirs=s.pirs.filter(p=>{
    if(!p.date)return false;const pd=parseISO(p.date);return pd>=start&&pd<=end;
  });
  return {
    index:s.index, week, start, end, pirs,
    workdays:weekdaysBetween(start,end),
    key:`${s.index}:${week}`,
    title:`Спринт ${s.index+1}`,
    subtitle:`Неделя ${week+1}`
  };
}
function boardWeekly(){ return !!state.ui.boardWeeks; }
function boardPeriods(){
  const sprints=computeSprints();
  if(!boardWeekly()) return sprints.map(s=>({
    ...s,
    week:null,
    key:String(s.index),
    title:`Спринт ${s.index+1}`,
    subtitle:''
  }));
  return sprints.flatMap(s=>[sprintWeekPeriod(s,0),sprintWeekPeriod(s,1)]);
}
function itemWeek(item){ return item && +item.week===1 ? 1 : 0; }
function itemInBoardPeriod(item,period){
  return item && item.sprint===period.index && (period.week===null || itemWeek(item)===period.week);
}
function setBoardPeriod(item,sprintVal,weekVal){
  item.sprint=sprintVal;
  if(sprintVal===null || sprintVal===undefined){
    delete item.week;
  }else if(weekVal===0 || weekVal===1){
    item.week=weekVal;
  }else{
    delete item.week;
  }
}
function periodWeekAttr(period){ return period.week===null ? '' : ` data-tb-week="${period.week}"`; }
function periodHeadHTML(period,opts={}){
  const capHtml=opts.capHtml||'';
  return `<div class="num">${period.title}</div>
    ${period.subtitle?`<div class="week-label">${period.subtitle}</div>`:''}
    <div class="dates">${fmt(period.start)}–${fmt(period.end)}</div>
    ${period.pirs.map(p=>`<div class="pir">${esc(p.name)} ${fmt(parseISO(p.date))}</div>`).join('')}
    ${capHtml}`;
}
function weekSelectHTML(id,selected){
  const w=itemWeek({week:selected});
  return `<label><span>Неделя</span><select id="${id}">
    <option value="0" ${w===0?'selected':''}>Неделя 1</option>
    <option value="1" ${w===1?'selected':''}>Неделя 2</option>
  </select></label>`;
}
// трайбы для вкладки «Цели»: те, где есть команды без чекбокса (чекбокс НЕ проставлен)
function tribesForGoals(){
  const seen=[];
  state.pi.teams.forEach(t=>{ if(!t.excluded && !seen.includes(t.tribe)) seen.push(t.tribe); });
  return seen;
}
function teamsOfTribeForGoals(tribe){
  return state.pi.teams.filter(t=>t.tribe===tribe && !t.excluded);
}
function allTribes(){
  const seen=[]; state.pi.teams.forEach(t=>{if(!seen.includes(t.tribe))seen.push(t.tribe);});
  return seen;
}
// Глобальные (кросс-квартальные) структуры команд — для вкладки «Бэклог команд»,
// данные которой не зависят от выбранного PI-цикла. Собираются из всех циклов по имени команды.
function allCycleTeams(){
  const map=new Map();
  Object.values(state.cycles||{}).forEach(c=>{
    ((c.pi && c.pi.teams) || []).forEach(t=>{ if(t && t.name && !map.has(t.name)) map.set(t.name,t); });
  });
  return [...map.values()];
}
function allTribesGlobal(){
  const seen=[]; allCycleTeams().forEach(t=>{ if(t.tribe && !seen.includes(t.tribe)) seen.push(t.tribe); });
  return seen;
}
function tribeTeamsGlobal(tribe){ return allCycleTeams().filter(t=>t.tribe===tribe); }
// Тип команды: 'Agile' (по умолчанию) или 'ИТ-проект'. Определяет представление Pre PI и «Целей».
function teamType(t){ return (t && t.type==='ИТ-проект') ? 'ИТ-проект' : 'Agile'; }

/* ---- Модель компетенций и команд-исполнителей ---- */
// Объект команды по имени (в активном цикле).
function teamObjByName(name){ return (state.pi.teams||[]).find(t=>t.name===name)||null; }
// Настроенные компетенции команды берутся только из активного PI-цикла.
function teamComps(name){
  const t=teamObjByName(name);
  return t && Array.isArray(t.comps) ? t.comps.slice() : [];
}
// Компетенции команды-исполнителя с учётом «Квартала реализации» (quarter+year).
// Если целевой цикл существует и в нём есть команда — берём его набор; иначе — глобальный дефолт.
function teamCompsFor(name, quarter, year){
  if(quarter && year){
    const c=state.cycles && state.cycles[cycleId(year,quarter)];
    if(c && Array.isArray(c.pi && c.pi.teams)){
      const t=c.pi.teams.find(x=>x.name===name);
      if(t && Array.isArray(t.comps)) return t.comps.slice();
    }
  }
  // только год → берём Q1 этого года
  if(!quarter && year){
    const c=state.cycles && state.cycles[cycleId(year,'Q1')];
    if(c && c.pi && Array.isArray(c.pi.teams)){
      const t=c.pi.teams.find(x=>x.name===name);
      if(t && Array.isArray(t.comps)) return t.comps.slice();
    }
  }
  return [];
}
// Нормализованный список исполнителей инициативы: [{team, comps:{SA:..,DEV:..}}].
function issueExecutors(iss){
  if(Array.isArray(iss.executors)) return iss.executors;
  return [];
}
// Имена команд-исполнителей инициативы.
function issueExecTeams(iss){ return issueExecutors(iss).map(e=>e.team).filter(Boolean); }
// Является ли команда исполнителем инициативы.
function issueOnTeam(iss,name){ return issueExecTeams(iss).includes(name); }
// Запись исполнителя по имени команды.
function execEntry(iss,name){ return issueExecutors(iss).find(e=>e.team===name)||null; }
// Объект компетенций исполнителя (чел/дн по компетенциям).
function execComps(iss,name){ const e=execEntry(iss,name); return (e&&e.comps)||{}; }
// Чел/дн команды по одной компетенции.
function issueTeamEffort(iss,name,comp){ const c=execComps(iss,name); return +c[comp]||0; }
// Сумма чел/дн команды по всем её компетенциям.
function issueTeamTotal(iss,name){
  const c=execComps(iss,name); let s=0; for(const k in c) s+=(+c[k]||0); return s;
}
// Общая оценка инициативы (чел/дн) = сумма по всем исполнителям и компетенциям.
function issueTotalEffort(iss){
  return issueExecutors(iss).reduce((s,e)=>{
    let t=0; const c=e.comps||{}; for(const k in c) t+=(+c[k]||0); return s+t;
  },0);
}
// Создать пустого исполнителя для команды (набор компетенций — из настроек команды).
function makeExecutor(name,quarter,year){
  const comps={}; teamCompsFor(name,quarter,year).forEach(c=>{ comps[c]=0; });
  return {team:name, comps, attractions:[]};
}
function teamOptionObjects(list){
  const map=new Map();
  (list||[]).forEach(t=>{
    const name=typeof t==='string' ? t : (t.name||t.team||'');
    const tribe=typeof t==='string' ? teamTribe(t) : (t.tribe||'');
    if(name && !map.has(name)) map.set(name,{name,tribe});
  });
  return [...map.values()].sort((a,b)=>(a.tribe||'').localeCompare(b.tribe||'','ru')||a.name.localeCompare(b.name,'ru'));
}
function teamOptionsHTML(teamOptions,selected,withTribe=false){
  const teams=teamOptionObjects(teamOptions);
  if(!withTribe){
    return teams.map(t=>`<option value="${esc(t.name)}" ${t.name===selected?'selected':''}>${esc(t.name)}</option>`).join('');
  }
  const groups=new Map();
  teams.forEach(t=>{
    const tribe=t.tribe||'Без трайба';
    if(!groups.has(tribe)) groups.set(tribe,[]);
    groups.get(tribe).push(t);
  });
  return [...groups.entries()].map(([tribe,items])=>
    `<optgroup label="${esc(tribe)}">`+
      items.map(t=>`<option value="${esc(t.name)}" ${t.name===selected?'selected':''}>${esc(t.name)}</option>`).join('')+
    `</optgroup>`
  ).join('');
}
// Ячейка «Команда-исполнитель и компетенции» для одного исполнителя (2 уровня: команда / компетенции).
// kind: 'bk' | 'pi'. teamOptions — список команд для выпадающего списка.
function execBlockHTML(iss, ex, ei, kind, teamOptions){
  const total=iss.executors.length;
  const idAttr = kind==='bk' ? iss._uid : iss.id;
  const avail = kind==='bk' ? backlogTeamCompetencies(ex.team) : teamCompsFor(ex.team);
  const selAttr = kind==='bk' ? `data-bk-exec="${esc(idAttr)}"` : `data-pi-exec="${esc(idAttr)}"`;
  const delAttr = kind==='bk' ? `data-bk-execdel="${esc(idAttr)}"` : `data-pi-execdel="${esc(idAttr)}"`;
  const addAttr = kind==='bk' ? `data-bk-execadd="${esc(idAttr)}"` : `data-pi-execadd="${esc(idAttr)}"`;
  return `<td class="exec-cell">
    <div class="exec-block">
      <div class="exec-team-line">
        <select ${selAttr} data-ei="${ei}" class="exec-team">${kind==='bk'?'<option value="">—</option>':''}${teamOptionsHTML(teamOptions,ex.team,kind==='bk')}</select>
        ${total>1?`<button class="icon danger sm" ${delAttr} data-ei="${ei}" title="Убрать исполнителя">✕</button>`:''}
      </div>
      ${compFieldsHTML(avail, ex.comps, kind, idAttr, ei)}
      ${ei===total-1?`<div class="exec-add-line"><button class="plus sm" ${addAttr} title="Добавить команду-исполнителя">+ Команда-исполнитель</button></div>`:''}
    </div>
  </td>`;
}
// Первичная команда-исполнитель (для размещения на досках/ёмкости).
function issuePrimaryTeam(iss){ return issueExecTeams(iss)[0]||iss.executor||''; }
// Подпись трудозатрат стикера по компетенциям первичной команды.
function issueEffortLabel(iss){
  const tn=issuePrimaryTeam(iss); const c=execComps(iss,tn);
  return teamComps(tn).map(k=>`${k} ${+c[k]||0}`).join(' · ') || '—';
}
// Инлайн-поля компетенций команды-исполнителя (только её компетенции).
// kind: 'bk' (Бэклог команд) | 'pi' (Pre PI). id — идентификатор инициативы, ei — индекс исполнителя.
function compFieldsHTML(avail, comps, kind, id, ei){
  if(!avail || !avail.length) return `<span class="comp-cells-empty">нет компетенций у команды</span>`;
  const attr=c=> kind==='bk'
    ? `data-bk-comp="${esc(id)}" data-ei="${ei}" data-c="${c}"`
    : `data-pi-comp="${esc(id)}" data-ei="${ei}" data-c="${c}"`;
  return `<div class="comp-cells">`+avail.map(c=>{
    const v=(comps&&comps[c])||0;
    return `<label class="comp-cell"><span class="cc-lab">${c}</span><input type="number" min="0" ${attr(c)} value="${esc(v)}"></label>`;
  }).join('')+`</div>`;
}
// Цвет стикера/чипа привлечения:
//  голубой   — владелец = исполнитель (своя задача);
//  фиолетовый — привлечение (владелец ≠ исполнитель), ещё НЕ согласовано;
//  красный   — привлечение согласовано (нажата «Согласовать»).
function issueColor(iss){
  const pt=issuePrimaryTeam(iss);
  if(!pt || pt===iss.owner) return 'blue';
  return iss.agreed ? 'red' : 'purple';
}
function isOwnerInfoIssue(iss,teamName){
  const pt=issuePrimaryTeam(iss);
  return !!(iss && teamName && iss.onBoard && iss.owner===teamName && pt && pt!==teamName);
}
function ownerInfoIssues(teamName){
  return state.issues.filter(i=>isOwnerInfoIssue(i,teamName));
}
function issueTeamsHTML(iss){
  return `<div class="stteam"><span>Владелец: <b>${esc(iss.owner)||'—'}</b></span><span>Исполнитель: <b>${esc(issueExecTeams(iss).join(', '))||esc(iss.executor)||'—'}</b></span></div>`;
}
function piTags(){ return normalizeTags(state.pi && state.pi.tags); }
function issueTags(iss){
  const allowed=piTags();
  return normalizeTags(iss && iss.tags).filter(t=>allowed.includes(t));
}
function issueTagsHTML(iss){
  const tags=issueTags(iss);
  return tags.length ? `<div class="sttags">${tags.map(t=>`<span class="sttag">#${esc(t)}</span>`).join('')}</div>` : '';
}
const COLOR_RU = {blue:'Голубой', red:'Красный', purple:'Фиолетовый'};
// Цвет-идентификатор задачи (lane hue): детерминированный по id.
// Один и тот же оттенок получают цветной стикер, его белые подзадачи и стрелки —
// сразу видно, что к чему относится и откуда идёт стрелка.
const LANE_HUES = [205, 12, 145, 268, 32, 188, 330, 96, 248, 56, 165, 300];
function issueHue(iss){
  const id = String((iss && iss.id) || '');
  let h = 0; for(let k=0;k<id.length;k++) h = (h*31 + id.charCodeAt(k)) >>> 0;
  return `hsl(${LANE_HUES[h % LANE_HUES.length]} 68% 56%)`;
}
function findIssue(id){ return state.issues.find(i=>i.id===id); }
// Поля, синхронизируемые между инициативой (Pre PI Planning) и целью (Цели).
// Правка на любой из вкладок отражается на другой (единый источник — по № инициативы).
const GOAL_SYNC_FIELDS=['cel','metric','fact','plan','hypo','redesign','product'];
// Все строки-цели (по всем командам), относящиеся к инициативе id.
function goalsForIssue(id){
  const out=[];
  Object.values(state.goals||{}).forEach(rows=>rows.forEach(g=>{ if(g.initNum===id) out.push(g); }));
  return out;
}
// issue → цели
function syncIssueToGoals(iss){
  goalsForIssue(iss.id).forEach(g=>{ GOAL_SYNC_FIELDS.forEach(k=>{ g[k]=iss[k]; }); });
}
// цель → issue
function syncGoalToIssue(g){
  const iss=findIssue(g.initNum); if(!iss) return;
  // копируем только присутствующие в строке-цели поля (у старых строк новых полей нет)
  GOAL_SYNC_FIELDS.forEach(k=>{ if(k in g) iss[k]=g[k]; });
  // Одна инициатива может быть целью нескольких команд-исполнителей.
  // Поддерживаем все её строки синхронными до отправки агрегата в backend.
  syncIssueToGoals(iss);
}
// Трудозатраты (sa/dev/qa): было ли значение внесено/изменено вручную (не из Jira).
//  - в Jira не было данных (jira[role] = null) → любое ненулевое значение = ручной ввод;
//  - в Jira было значение → отличие текущего от него = ручное изменение.
function isEffortEdited(iss,role){
  const jira = iss.jira ? iss.jira[role] : undefined;
  const cur = +iss[role]||0;
  if(jira===undefined || jira===null) return cur!==0;
  return cur !== (+jira||0);
}
// Подсказка (tooltip) для ячейки трудозатрат — что было в Jira и изменено ли вручную.
function effortTitle(iss,role){
  const jira = iss.jira ? iss.jira[role] : undefined;
  const hasJira = !(jira===undefined || jira===null);
  if(!hasJira) return isEffortEdited(iss,role) ? 'Внесено вручную (в Jira данных не было)' : 'В Jira данных нет';
  return isEffortEdited(iss,role) ? `Из Jira: ${+jira||0} · изменено вручную` : `Из Jira: ${+jira||0}`;
}

function round1(n){ return Math.round((+n||0)*10)/10; }
// доступная ёмкость человека в конкретном спринте
//   Доступная = Плановая − отпуск − Плановая×%церемоний − Плановая×%рисков (проценты от Плановой)
function personAvail(person,sprint){
  const id=currentCycleId(),cycle=id&&state.cycles&&state.cycles[id];
  const cached=id&&person.uid&&capacityComputedCycles[id]&&capacityComputedCycles[id].members[person.uid];
  if(cached&&cycle&&cached.inputKey===capacityMemberInputKey(person,cycle,id)){
    if(sprint.week===null||sprint.week===undefined){
      const row=(cached.sprints||[]).find(x=>+x.sprint_index===+sprint.index);
      return row ? (+row.available_capacity||0) : 0;
    }
    const rows=(cached.weeks||{})[sprint.index]||(cached.weeks||{})[String(sprint.index)]||[];
    const row=rows.find(x=>+x.week_index===+sprint.week);
    return row ? (+row.available_capacity||0) : 0;
  }
  return 0;
}
function personCapacityTotal(person,field){
  const id=currentCycleId(),cycle=id&&state.cycles&&state.cycles[id];
  const cached=id&&person.uid&&capacityComputedCycles[id]&&capacityComputedCycles[id].members[person.uid];
  if(!cached||!cycle||cached.inputKey!==capacityMemberInputKey(person,cycle,id))return null;
  return +(cached[field]||0);
}
// план роли в спринте = сумма доступной по всем людям этой роли
function rolePlan(team,role,sprint){
  const cap=state.capacity[teamKey(team.tribe,team.name)]||[];
  return cap.filter(p=>p.role===role).reduce((s,p)=>s+personAvail(p,sprint),0);
}
// потреблённая ёмкость роли в спринте:
//  - если issue НЕ декомпозирован (нет белых) — берём значение роли с цветного стикера в его спринте;
//  - если декомпозирован (есть ≥1 белый) — значения цветного игнорируются, считаем по белым.
function consumedEffort(team,role,sprintIndex,weekIndex=null){
  const id=currentCycleId(),cache=id&&capacityComputedCycles[id];
  const summary=cache&&cache.teams[teamKey(team.tribe,team.name)];
  if(!summary)return 0;
  if(weekIndex===null||weekIndex===undefined){
    const row=(summary.loadBySprint||{})[sprintIndex]||(summary.loadBySprint||{})[String(sprintIndex)]||{};
    return +row[role]||0;
  }
  const sprint=(summary.loadByWeek||{})[sprintIndex]||(summary.loadByWeek||{})[String(sprintIndex)]||{};
  const row=sprint[weekIndex]||sprint[String(weekIndex)]||{};
  return +row[role]||0;
}

