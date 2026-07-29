/* =====================================================================
   СОСТОЯНИЕ
===================================================================== */
// Полный справочник компетенций (заменил прежние роли SA/DEV/QA).
const COMPS = ['SA','DEV','QA','FE','BE','DES'];
// ROLES — легаси-алиас; используется как «все компетенции» там, где нет привязки к команде.
const ROLES = COMPS;
const BASE_TEAM_COMPS = ['SA','DEV','QA'];
// Возможные статусы инициативы в бэклоге трайба.
const BACKLOG_STATUSES = ['Нет оценки','Оценка проведена','Отправлена в Pre PI Planning'];
const BUDGET_STATUSES = ['Одобрена','На рассмотрении','Отклонена'];
const FIN_CATEGORIES = ['Увеличение доходов','Сокращение расходов','Нет фин. эффекта'];
const BUDGET_MONTHS = [
  ['jan','январь'],['feb','февраль'],['mar','март'],['apr','апрель'],['may','май'],['jun','июнь'],
  ['jul','июль'],['aug','август'],['sep','сентябрь'],['oct','октябрь'],['nov','ноябрь'],['dec','декабрь'],
];
const BUDGET_COMPS = ['SA','DES','QA','FE','BE'];
const DEFAULT_BUDGET_TEAMS = [
  {tribe:'Корпоративный бизнес', team:'Продажи'},
  {tribe:'Корпоративный бизнес', team:'Расчеты'},
  {tribe:'Розничный бизнес', team:'Модуль расчетов'},
  {tribe:'Розничный бизнес', team:'СБОЛ'},
];
// Типы инициатив, относящиеся к тех. повестке (сравнение по точному совпадению строки).
const TECH_TYPE_COMMON='Общая тех. повестка';
const TECH_TYPE_TEAM='Командная тех. повестка';
const PI_TABS = [
  {id:'data',    name:'Данные PI-цикла'},
  {id:'backlog', name:'Бэклог команд'},
  {id:'prep',    name:'Pre PI Planning'},
  {id:'goals',   name:'Цели'},
  {id:'teams',   name:'Командные доски'},
  {id:'pb',      name:'Program Board'},
  {id:'risks',   name:'Риски'},
];
const TABS = PI_TABS;
const BUDGET_TABS = [
  {id:'budgetData',       name:'Данные для бюджетирования'},
  {id:'backlog',          name:'Бэклог команд'},
  {id:'budgetAssessment', name:'Оценка инициатив'},
  {id:'budget',           name:'Бюджет'},
  {id:'budgetVadarodTeams', name:'Состав команд Vadarod'},
];

const defaultState = {
  // Данные по каждому PI-циклу, ключ — «<год>-<квартал>», напр. «2026-Q1».
  cycles: {},
  // Данные бюджетирования по годам.
  budgets: {},
  ui:{
    // выбор PI-цикла на главной странице; null/null — показывается стартовая страница
    mode:null, year:null, quarter:null, landingYear:2026, budgetYear:null, budgetTab:'budgetData',
    tab:'data',
    dataEdit:true,
    prepTribe:null, prepSel:null, prepTeamFilter:null,
    backlogTribe:null, backlogTeamFilter:null, backlogQuarter:null, backlogYear:null,
    budgetScopeTribe:null, budgetScopeTeam:null, budgetStatuses:['Одобрена','На рассмотрении'], budgetEffectOpen:false, budgetEffectKey:null,
    budgetAssessMode:'vadarod', budgetVadarodView:'tribe', budgetCompositionDate:null,
    // фильтры по столбцам таблиц: scope ('bk'|'prep:upper'|'prep:lower') -> {столбец: [значения]}
    colFilters:{},
    // сортировка по столбцу: тот же scope -> {k:'столбец', dir:'asc'|'desc'}; один столбец на таблицу
    colSort:{},
    goalsTribe:null, goalsTeam:null,
    teamsTribe:null, teamSel:null, teamView:'board', selectedArrow:null,
    pbOwnerFilter:null, pbExecutorFilter:null,
    riskView:'general', riskTribe:null, riskTeam:null,
  },
};

let state;
const STORAGE_VERSION = 4;
const API_BASE = (window.SBERPI_API_BASE ||
  (location.protocol==='http:' || location.protocol==='https:'
    ? (location.port==='8000' ? location.origin+'/api' : location.protocol+'//'+location.hostname+':8000/api')
    : 'http://localhost:8000/api')).replace(/\/$/,'');
let cyclesApiReady=false;
let cyclesApiUnavailable=false;
let cycleBackendIds={};
let cycleVersions={};
let piDataViews={};
let persistedCycleMetadata={};
let cycleSyncTimer=null;
let cycleSyncChain=Promise.resolve();
let aggregateMutationChain=Promise.resolve();
let lastCycleSyncErrorAt=0;
let backlogApiReady=false;
let backlogBoard=null;
let lastBacklogSyncErrorAt=0;
let prePiApiReady=false;
let prePiViews={};
let lastPrePiSyncErrorAt=0;
let goalsApiReady=false;
let goalsBoards={};
let lastGoalsSyncErrorAt=0;
let teamBoardsApiReady=false;
let persistedTeamBoardHashes={};
let teamBoardsSyncTimer=null;
let teamBoardsSyncChain=Promise.resolve();
let lastTeamBoardsSyncErrorAt=0;
let capacityApiReady=false;
let persistedCapacityHashes={};
let capacityComputedCycles={};
let capacitySyncTimer=null;
let capacitySyncChain=Promise.resolve();
let lastCapacitySyncErrorAt=0;
let programBoardApiReady=false;
let persistedProgramBoardHashes={};
let programBoardSyncTimer=null;
let programBoardSyncChain=Promise.resolve();
let lastProgramBoardSyncErrorAt=0;
let risksApiReady=false;
let risksBoards={};
let lastRisksSyncErrorAt=0;
// Ключи данных, относящиеся к конкретному PI-циклу. На верхнем уровне state.* они
// служат «активными» ссылками на выбранный цикл (чтобы не переписывать все вьюхи),
// а хранятся внутри state.cycles[<id>]. В sessionStorage дублировать их не нужно.
const CYCLE_KEYS = ['pi','goals','capacity','issues','risks','connections','meta'];
function cycleId(year,quarter){ return year+'-'+quarter; }
function currentCycleId(){
  return (state && state.ui && state.ui.year && state.ui.quarter) ? cycleId(state.ui.year,state.ui.quarter) : null;
}
function defaultBudgetData(){
  return {
    rateVadarod:705,
    utilization:0.86,
    workdays:{jan:19,feb:20,mar:22,apr:20,may:21,jun:22,jul:22,aug:20,sep:22,oct:20,nov:22,dec:22},
    vadarodTeams:cloneBudgetTeams(DEFAULT_BUDGET_TEAMS),
    vadarodTeamsInitialized:true,
    vadarodRows:[],
    vadarodSnapshotDate:'',
    vadarodSnapshots:[],
    assessments:{},
    vadarodInitiatives:[],
    vendorRows:[],
  };
}
function cloneBudgetTeams(rows){
  return (rows||[]).map(r=>({tribe:r.tribe||'',team:r.team||''}));
}
function ensureBudgetShape(b){
  const d=defaultBudgetData();
  if(!b || typeof b!=='object') b={};
  if(!('rateVadarod' in b)) b.rateVadarod=d.rateVadarod;
  if(!('utilization' in b)) b.utilization=d.utilization;
  if(!b.workdays || typeof b.workdays!=='object') b.workdays={};
  BUDGET_MONTHS.forEach(([k])=>{ if(!(k in b.workdays)) b.workdays[k]=d.workdays[k]||0; });
  if(!Array.isArray(b.vadarodTeams)) b.vadarodTeams=[];
  if(!('vadarodTeamsInitialized' in b)) b.vadarodTeamsInitialized=false;
  if(!Array.isArray(b.vadarodRows)) b.vadarodRows=[];
  if(!Array.isArray(b.vadarodSnapshots)) b.vadarodSnapshots=[];
  if(!('vadarodSnapshotDate' in b)) b.vadarodSnapshotDate='';
  b.vadarodRows.forEach(r=>{
    if(!('tribe' in r)) r.tribe='';
    if(!('team' in r)) r.team='';
    BUDGET_COMPS.forEach(c=>{ if(!(c in r)) r[c]=0; });
  });
  b.vadarodTeams.forEach(r=>{
    if(!('tribe' in r)) r.tribe='';
    if(!('team' in r)) r.team='';
  });
  if(!b.vadarodTeams.length && b.vadarodRows.length){
    b.vadarodTeams=b.vadarodRows.map(r=>({tribe:r.tribe||'',team:r.team||''}));
  }
  if(!b.vadarodTeamsInitialized && !b.vadarodTeams.length && !b.vadarodRows.length){
    b.vadarodTeams=cloneBudgetTeams(DEFAULT_BUDGET_TEAMS);
  }
  b.vadarodTeamsInitialized=true;
  b.vadarodSnapshots.forEach(s=>{
    if(!('date' in s)) s.date='';
    if(!Array.isArray(s.rows)) s.rows=[];
    s.rows.forEach(r=>{
      if(!('tribe' in r)) r.tribe='';
      if(!('team' in r)) r.team='';
      BUDGET_COMPS.forEach(c=>{ if(!(c in r)) r[c]=0; });
    });
  });
  syncVadarodRows(b);
  if(!b.assessments || typeof b.assessments!=='object') b.assessments={};
  Object.values(b.assessments).forEach(a=>ensureAssessmentShape(a));
  if(!Array.isArray(b.vadarodInitiatives)) b.vadarodInitiatives=[];
  b.vadarodInitiatives.forEach(v=>ensureBudgetInitiativeShape(v));
  if(!Array.isArray(b.vendorRows)) b.vendorRows=[];
  b.vendorRows.forEach(v=>ensureVendorShape(v));
  return b;
}
function ensureIssueLinkShape(l){
  if(!l || typeof l!=='object') l={};
  if(!l._uid) l._uid=uid();
  ['id','team'].forEach(k=>{ if(!(k in l)) l[k]=''; });
  if(!l.comps || typeof l.comps!=='object') l.comps={};
  BUDGET_COMPS.forEach(c=>{ if(!(c in l.comps)) l.comps[c]=0; });
  l.totalEffort=+l.totalEffort||0;
  return l;
}
function ensureIssueLinksShape(o){
  if(!Array.isArray(o.issueLinks)) o.issueLinks=[];
  o.issueLinks=o.issueLinks.map(l=>ensureIssueLinkShape(l));
  return o.issueLinks;
}
function ensureBudgetInitiativeShape(v){
  if(!v || typeof v!=='object') v={};
  if(!v._uid) v._uid=uid();
  ['id','name','description','product','owner','type','finCategory','finMethod','valueDescription','comment'].forEach(k=>{ if(!(k in v)) v[k]=''; });
  if(!BUDGET_STATUSES.includes(v.status)) v.status='На рассмотрении';
  v.finEffect=+v.finEffect||0;
  if(!Array.isArray(v.executors)) v.executors=[];
  v.executors.forEach(e=>{
    if(!('team' in e)) e.team='';
    if(!e.comps || typeof e.comps!=='object') e.comps={};
  });
  ensureIssueLinksShape(v);
  return v;
}
function ensureAssessmentShape(a){
  if(!a || typeof a!=='object') a={};
  if(!BUDGET_STATUSES.includes(a.status)) a.status='На рассмотрении';
  ['vendor','workDescription','finCategory','finMethod','valueDescription','comment'].forEach(k=>{ if(!(k in a)) a[k]=''; });
  ensureIssueLinksShape(a);
  ['capex','opex','finEffect'].forEach(k=>{ a[k]=+a[k]||0; });
  return a;
}
function ensureVendorShape(v){
  if(!v || typeof v!=='object') v={};
  if(!v._uid) v._uid=uid();
  ['id','name','description','product','owner','type','vendor','workDescription','finCategory','finMethod','valueDescription','comment'].forEach(k=>{ if(!(k in v)) v[k]=''; });
  if(!BUDGET_STATUSES.includes(v.status)) v.status='На рассмотрении';
  ensureIssueLinksShape(v);
  ['capex','opex','finEffect'].forEach(k=>{ v[k]=+v[k]||0; });
  return v;
}
function ensureBudgetYear(year){
  const y=String(year||state.ui.budgetYear||state.ui.landingYear||new Date().getFullYear());
  if(!state.budgets || typeof state.budgets!=='object') state.budgets={};
  state.budgets[y]=ensureBudgetShape(state.budgets[y]);
  return state.budgets[y];
}
// Гарантировать наличие всех структур в объекте цикла.
function ensureCycleShape(c){
  if(!c.pi) c.pi={startDate:'',sprintCount:6,pirs:[],goals:[],tags:[],teams:[]};
  if(!Array.isArray(c.pi.tags)) c.pi.tags=[];
  if(!c.goals || typeof c.goals!=='object') c.goals={};
  if(!c.capacity || typeof c.capacity!=='object') c.capacity={};
  if(!Array.isArray(c.issues)) c.issues=[];
  if(!c.risks) c.risks={general:[],teams:{}};
  if(!Array.isArray(c.connections)) c.connections=[];
  if(!c.meta) c.meta={};
  return c;
}
function blankCycle(){ return ensureCycleShape({}); }
// Связать «активные» ссылки верхнего уровня (state.pi, state.issues, …) с выбранным циклом.
function activateCycle(id){
  const c=state.cycles[id]; if(!c) return;
  ensureCycleShape(c);
  CYCLE_KEYS.forEach(k=>{ state[k]=c[k]; });
}
function loadState(){
  let saved={};
  try{
    const s = sessionStorage.getItem('piPlanning');
    saved = s ? JSON.parse(s) : {};
  }catch(e){}
  state=structuredClone(defaultState);
  if(saved.budgets&&typeof saved.budgets==='object') state.budgets=saved.budgets;
  if(saved.ui&&typeof saved.ui==='object') state.ui={...state.ui,...saved.ui};
}
function save(syncCycles=true){
  try{
    // В браузере сохраняются только UI-настройки и пока не разрабатываемый бюджет.
    // Любые PI business data загружаются заново из backend.
    const out={storageVersion:STORAGE_VERSION,ui:state.ui,budgets:state.budgets};
    sessionStorage.setItem('piPlanning', JSON.stringify(out));
  }catch(e){}
  // save(false) используется только при редактировании setup. Пока пользователь
  // не нажал «Сохранить», команды ещё не входят в нормализованный PI, поэтому
  // синхронизация зависимых агрегатов дала бы ложные 422 и могла бы затереть
  // незавершённый ввод ответом от более раннего запроса.
  if(syncCycles && state.ui.mode==='pi' && state.ui.tab!=='data'){
    if(teamBoardsApiReady) queueTeamBoardsSync();
    if(capacityApiReady) queueCapacitySync();
    if(programBoardApiReady) queueProgramBoardSync();
  }
}

