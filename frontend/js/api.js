async function cycleApi(path,options={}){
  const init={method:options.method||'GET',headers:{'Content-Type':'application/json'}};
  if(options.body!==undefined) init.body=JSON.stringify(options.body);
  const response=await fetch(API_BASE+path,init);
  if(!response.ok){
    let detail='';
    try{ const body=await response.json(); detail=body.detail||body; }
    catch(_){ detail=await response.text(); }
    const message=typeof detail==='string' ? detail : (detail.message||JSON.stringify(detail));
    const error=new Error(message||`HTTP ${response.status}`);
    error.detail=detail;
    error.status=response.status;
    throw error;
  }
  return response.status===204 ? null : response.json();
}
function optimisticConflictError(aggregate,expected,current){
  const error=new Error('Данные были изменены в другом окне');
  error.status=409;
  error.detail={aggregate,expected_version:expected,current_version:current};
  return error;
}
function reportOptimisticConflict(error){
  if(!error||error.status!==409)return false;
  console.warn('Optimistic locking conflict',error.detail||error);
  if(!error.conflictNotified&&typeof toast==='function'){
    error.conflictNotified=true;
    toast('Данные PI-цикла изменены в другом окне. Перезагрузите страницу перед продолжением редактирования.',{
      type:'warn',title:'Конфликт изменений',timeout:8000,
    });
  }
  return true;
}
function noteCycleReadVersion(id,result){
  if(!result||!Number.isInteger(result.version))return result;
  const known=cycleVersions[id];
  if(Number.isInteger(known)&&known!==result.version){
    throw optimisticConflictError('pi_cycle',known,result.version);
  }
  cycleVersions[id]=result.version;
  return result;
}
async function cycleRead(id,path){
  return noteCycleReadVersion(id,await cycleApi(path));
}
function cycleMutation(id,path,options={}){
  const run=aggregateMutationChain.then(async()=>{
    const expected=cycleVersions[id];
    if(!Number.isInteger(expected))throw new Error(`PI cycle version is not loaded: ${id}`);
    const result=await cycleApi(path,{
      method:options.method||'PUT',
      body:{...(options.body||{}),expected_version:expected},
    });
    if(result&&Number.isInteger(result.version))cycleVersions[id]=result.version;
    return result;
  });
  aggregateMutationChain=run.catch(()=>{});
  return run;
}
function backlogMutation(path,method,body={}){
  const run=aggregateMutationChain.then(async()=>{
    if(!backlogBoard||!Number.isInteger(backlogBoard.version)) throw new Error('Read model бэклога ещё не загружен');
    return cycleApi(backlogScopedPath(path),{method,body:{...body,expected_version:backlogBoard.version}});
  });
  aggregateMutationChain=run.catch(()=>{});
  return run;
}
function cycleApiPayload(id,c){
  const split=id.lastIndexOf('-');
  const year=+id.slice(0,split), quarter=id.slice(split+1);
  const sprintCount=Math.max(1,Math.min(20,parseInt(c.pi.sprintCount)||6));
  c.pi.sprintCount=sprintCount;
  return {
    year, quarter,
    start_date:c.pi.startDate||null,
    sprint_count:sprintCount,
  };
}
function stablePayloadHash(value){
  try{
    // PostgreSQL JSONB does not preserve object-key order. Stable hashes avoid
    // redundant PUT requests for normalized aggregate payloads.
    return JSON.stringify(value,(_key,item)=>{
      if(!item || typeof item!=='object' || Array.isArray(item)) return item;
      const ordered={}; Object.keys(item).sort().forEach(k=>{ordered[k]=item[k];});
      return ordered;
    });
  }catch(_){return '';}
}
function reportCycleSyncError(error){
  console.error('PI cycle API sync failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastCycleSyncErrorAt>5000 && typeof toast==='function'){
    lastCycleSyncErrorAt=now;
    toast('Не удалось сохранить PI-цикл в backend. Проверьте доступность API.',{type:'warn',timeout:5000});
  }
}
async function persistCycle(id,force=false){
  const c=state.cycles[id]; if(!c) return;
  ensureCycleShape(c);
  const payload=cycleApiPayload(id,c);
  const metadataHash=JSON.stringify([payload.start_date,payload.sprint_count]);
  let backendId=cycleBackendIds[id];
  if(!backendId){
    const created=await cycleApi('/pi-cycles',{method:'POST',body:payload});
    backendId=created.id; cycleBackendIds[id]=backendId;
    cycleVersions[id]=created.version;
    // POST возвращает существующую запись при совпадении года/квартала.
    // Business data синхронизируются только отдельными агрегатными API.
    force=(created.start_date||'')!==(payload.start_date||'') ||
      +created.sprint_count!==+payload.sprint_count;
    if(!force) persistedCycleMetadata[id]=metadataHash;
  }
  if(force || persistedCycleMetadata[id]!==metadataHash){
    await cycleMutation(id,`/pi-cycles/${backendId}`,{
      method:'PATCH',
      body:{start_date:payload.start_date,sprint_count:payload.sprint_count},
    });
  }
  persistedCycleMetadata[id]=metadataHash;
}
async function syncAllCycles(){
  for(const id of Object.keys(state.cycles||{})) await persistCycle(id);
}
function runCycleSync(){
  const run=cycleSyncChain.then(syncAllCycles);
  cycleSyncChain=run.catch(reportCycleSyncError);
  return run;
}
function queueCycleSync(){
  clearTimeout(cycleSyncTimer);
  cycleSyncTimer=setTimeout(()=>{cycleSyncTimer=null;runCycleSync().catch(()=>{});},350);
}
function flushCycleSync(){
  if(cycleSyncTimer){clearTimeout(cycleSyncTimer);cycleSyncTimer=null;}
  return runCycleSync();
}
async function loadCyclesFromApi(){
  const remote=await cycleApi('/pi-cycles');
  const loaded={};
  cycleBackendIds={}; cycleVersions={}; persistedCycleMetadata={}; piDataViews={};

  for(const rec of remote){
    const id=cycleId(rec.year,rec.quarter);
    const c=blankCycle();
    c.pi.startDate=rec.start_date||c.pi.startDate||'';
    c.pi.sprintCount=rec.sprint_count||c.pi.sprintCount||6;
    loaded[id]=c; cycleBackendIds[id]=rec.id;
    cycleVersions[id]=rec.version;
    persistedCycleMetadata[id]=JSON.stringify([rec.start_date||null,rec.sprint_count||6]);
  }
  state.cycles=loaded;
}
function applyPiDataView(id,view){
  if(!view||!view.cycle) throw new Error('Backend returned an invalid PI data view');
  piDataViews[id]=view;
  cycleBackendIds[id]=view.cycle.id;
  cycleVersions[id]=view.cycle.version;
  persistedCycleMetadata[id]=JSON.stringify([view.cycle.start_date||null,view.cycle.sprint_count]);
  const c=state.cycles[id]||blankCycle();
  ensureCycleShape(c);
  c.pi={
    startDate:view.cycle.start_date||'',
    sprintCount:view.cycle.sprint_count,
    pirs:(view.pirs||[]).map(row=>({_backendId:row.id,name:row.name,date:row.date})),
    teams:(view.teams||[]).map(row=>({
      _cycleTeamId:row.id,_teamId:row.team_id,_tribeId:row.tribe_id,
      tribe:row.tribe,name:row.name,type:row.team_type,
      excluded:!!row.excluded_from_goals,comps:(row.competencies||[]).slice(),
    })),
    goals:(view.goal_options||[]).map(row=>row.name),
    tags:(view.tags||[]).map(row=>row.name),
  };
  state.cycles[id]=c;
  if(currentCycleId()===id) activateCycle(id);
  return view;
}
async function loadPiDataView(id){
  const backendId=cycleBackendIds[id];
  if(!backendId) throw new Error(`PI cycle is not loaded: ${id}`);
  return applyPiDataView(id,await cycleApi(`/pi-cycles/${backendId}/data`));
}
async function loadPiDataViews(){
  for(const id of Object.keys(state.cycles||{})) await loadPiDataView(id);
}
function piDataCommand(path,options={}){
  const id=currentCycleId();
  const backendId=id&&cycleBackendIds[id];
  if(!id||!piDataViews[id]||!backendId) return Promise.reject(new Error('PI data is not loaded'));
  const run=aggregateMutationChain.then(async()=>{
    const view=piDataViews[id];
    if(!view) throw new Error('PI data is not loaded');
    const result=await cycleApi(`/pi-cycles/${backendId}${path}`,{
      method:options.method||'POST',
      body:{...(options.body||{}),expected_version:view.cycle.version},
    });
    return applyPiDataView(id,result);
  });
  aggregateMutationChain=run.catch(()=>{});
  return run;
}
function applyBacklogBoard(board){
  backlogBoard=board;
}
function reportBacklogSyncError(error){
  console.error('Backlog API command failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastBacklogSyncErrorAt>5000 && typeof toast==='function'){
    lastBacklogSyncErrorAt=now;
    toast(error&&error.message?error.message:'Не удалось выполнить команду бэклога',{type:'warn',timeout:6000});
  }
}
async function loadBacklogBoard(){
  const id=currentCycleId();
  if(!id||!cycleBackendIds[id]){backlogBoard=null;return null;}
  applyBacklogBoard(await cycleApi(backlogScopedPath('/backlog-board',id)));
  return backlogBoard;
}
function backlogScopedPath(path,id=currentCycleId()){
  const backendId=id&&cycleBackendIds[id];
  if(!backendId)throw new Error('PI-цикл для бэклога не выбран');
  return `${path}${path.includes('?')?'&':'?'}cycle_id=${encodeURIComponent(backendId)}`;
}
function prePiIssueFromApi(row,prior){
  const it=prior||{};
  const executors=(row.executors||[]).map(ex=>({
    _backendId:ex.id,
    teamId:ex.team_id,
    team:ex.team,
    comps:ex.effort_by_competency||{},
    attractions:(ex.attractions||[]).map(a=>({
      _backendId:a.id,
      targetInitiativeId:a.target_initiative_id,
      targetTeamId:a.target_team_id,
      id:a.issue_key,
      team:a.team||'',
      sprint:a.sprint_index===null||a.sprint_index===undefined?null:+a.sprint_index,
      status:a.approval_status||'pending',
      visualState:a.visual_state||'purple',
    })),
  }));
  Object.assign(it,{
    _backendId:row.id,
    id:row.issue_key,
    name:row.title||'',
    description:row.description||'',
    product:row.product||'',
    owner:row.owner_team||'',
    executor:(executors[0]&&executors[0].team)||'',
    executors,
    type:row.initiative_type||'',
    status:row.status||'backlog',
    cel:row.goal_text||'',
    metric:row.metric||'',
    fact:row.current_value||'',
    plan:row.target_value||'',
    hypo:row.hypothesis||'',
    redesign:row.redesign||'',
    custPrio:row.customer_priority||'',
    teamPrio:row.team_priority||'',
    estimate:row.estimate||'',
    comment:row.comment||'',
    prePlanned:!!row.pre_planned,
    onBoard:!!row.on_board,
    agreed:!!row.agreed,
    tags:Array.isArray(row.tags)?row.tags:[],
    sprint:row.sprint_index===null||row.sprint_index===undefined?null:+row.sprint_index,
    week:row.week_index===null||row.week_index===undefined?null:+row.week_index,
    sortOrder:+row.sort_order||0,
    totalEstimate:+row.total_estimate||0,
    allowedActions:Array.isArray(row.allowed_actions)?row.allowed_actions:[],
    requiredFields:Array.isArray(row.required_fields)?row.required_fields:[],
  });
  return it;
}
function applyPrePi(c,aggregate,id=currentCycleId()){
  const priorById={},priorByKey={};
  (c.issues||[]).forEach(it=>{
    if(it._backendId) priorById[it._backendId]=it;
    if(it.id) priorByKey[String(it.id).toLowerCase()]=it;
  });
  c.issues=(aggregate.initiatives||[]).map(row=>
    prePiIssueFromApi(row,priorById[row.id]||priorByKey[String(row.issue_key).toLowerCase()]));
  if(id){
    prePiViews[id]=aggregate;
    if(Number.isInteger(aggregate.version)){
      cycleVersions[id]=aggregate.version;
      if(piDataViews[id]&&piDataViews[id].cycle)piDataViews[id].cycle.version=aggregate.version;
    }
  }
}
function reportPrePiSyncError(error){
  console.error('Pre PI API command failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastPrePiSyncErrorAt>5000 && typeof toast==='function'){
    lastPrePiSyncErrorAt=now;
    toast('Не удалось сохранить Pre PI Planning в backend.',{type:'warn',timeout:5000});
  }
}
async function prePiCommand(path,method='POST',body={}){
  const id=currentCycleId(), backendId=id&&cycleBackendIds[id];
  if(!id||!backendId||!prePiViews[id])throw new Error('Pre PI ещё не загружен');
  const result=await cycleMutation(id,`/pi-cycles/${backendId}/pre-pi${path}`,{method,body});
  applyPrePi(state.cycles[id],result,id);
  activateCycle(id);
  render();
  return result;
}
async function loadPrePiCycles(){
  prePiViews={};
  for(const id of Object.keys(state.cycles||{})){
    const backendId=cycleBackendIds[id]; if(!backendId)continue;
    const aggregate=await cycleRead(id,`/pi-cycles/${backendId}/pre-pi`);
    applyPrePi(state.cycles[id],aggregate,id);
  }
  // applyPrePi заменяет массив c.issues. Обновляем активную ссылку state.issues,
  // чтобы удаление и новый порядок с backend были видны сразу, без смены вкладки.
  const active=currentCycleId();
  if(active && state.cycles[active]) activateCycle(active);
}
function goalFromApi(row,prior){
  const goal=prior||{};
  Object.assign(goal,{
    _backendId:row.id,
    id:row.id,
    tribeId:row.tribe_id||null,
    teamId:row.team_id||null,
    initiativeIds:Array.isArray(row.initiative_ids)?row.initiative_ids.slice():[],
    title:row.title||row.goal_text||'',
    owner:row.owner||'',
    businessValue:row.business_value===null||row.business_value===undefined?'':row.business_value,
    status:row.status||'planned',
    category:row.category||'committed',
    tribe:row.tribe||'',
    team:row.team||'',
    cel:row.goal_text||'',
    product:row.product||'',
    initNum:row.issue_key,
    init:row.initiative_title||'',
    metric:row.metric||'',
    fact:row.current_value||'',
    plan:row.target_value||'',
    hypo:row.hypothesis||'',
    redesign:row.redesign||'',
  });
  return goal;
}
function applyGoals(c,aggregate,id=currentCycleId()){
  const priorById={},priorByPair={};
  Object.keys(c.goals||{}).forEach(key=>(c.goals[key]||[]).forEach(g=>{
    if(g._backendId)priorById[g._backendId]=g;
    if(g.initNum)priorByPair[key+'||'+String(g.initNum).toLowerCase()]=g;
  }));
  (c.goalRows||[]).forEach(g=>{ if(g._backendId) priorById[g._backendId]=g; });
  const grouped={};
  const flat=[];
  (aggregate.goals||[]).forEach(row=>{
    const key=teamKey(row.tribe,row.team);
    const prior=priorById[row.id]||priorByPair[key+'||'+String(row.issue_key).toLowerCase()];
    const goal=goalFromApi(row,prior);
    flat.push(goal);
    (grouped[key]=grouped[key]||[]).push(goal);
  });
  c.goals=grouped;
  c.goalRows=flat;
  c.goalReference=aggregate.reference_data||{};
  if(id){
    goalsBoards[id]=aggregate;
    if(Number.isInteger(aggregate.version)){
      cycleVersions[id]=aggregate.version;
      if(piDataViews[id]&&piDataViews[id].cycle)piDataViews[id].cycle.version=aggregate.version;
    }
  }
}
function reportGoalsSyncError(error){
  console.error('Goals API sync failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastGoalsSyncErrorAt>5000 && typeof toast==='function'){
    lastGoalsSyncErrorAt=now;
    toast('Не удалось сохранить вкладку «Цели» в backend.',{type:'warn',timeout:5000});
  }
}
async function goalsBoardCommand(path,method='POST',body={}){
  const id=currentCycleId(),backendId=id&&cycleBackendIds[id];
  if(!id||!backendId)throw new Error('PI cycle is not loaded');
  const aggregate=await cycleMutation(id,`/pi-cycles/${backendId}/goals-board${path}`,{method,body});
  applyGoals(state.cycles[id],aggregate,id);
  activateCycle(id);
  render();
  return aggregate;
}
async function loadGoalsCycles(){
  goalsBoards={};
  for(const id of Object.keys(state.cycles||{})){
    const backendId=cycleBackendIds[id]; if(!backendId)continue;
    const aggregate=await cycleRead(id,`/pi-cycles/${backendId}/goals-board`);
    applyGoals(state.cycles[id],aggregate,id);
  }
  const active=currentCycleId();
  if(active&&state.cycles[active])activateCycle(active);
}
function teamBoardsPayload(id,c){
  ensureCycleShape(c);
  const assigneeId=(issue,item)=>{
    const team=(c.pi.teams||[]).find(row=>row.name===issuePrimaryTeam(issue));
    if(!team)return item._assigneeMemberId||null;
    const roster=c.capacity[teamKey(team.tribe,team.name)]||[];
    const match=roster.find(member=>
      String(member.fio||'').trim().toLowerCase()===String(item.fio||'').trim().toLowerCase() &&
      String(member.role||'').trim().toUpperCase()===String(item.role||'').trim().toUpperCase());
    return match&&match._backendId ? match._backendId : (item._assigneeMemberId||null);
  };
  return {initiatives:(c.issues||[]).filter(i=>String(i.id||'').trim()).map(i=>({
    id:i._backendId||null,
    issue_key:String(i.id).trim(),
    pre_planned:!!i.prePlanned,
    on_board:!!i.onBoard,
    agreed:!!i.agreed,
    sprint_index:Number.isInteger(i.sprint)?i.sprint:null,
    week_index:Number.isInteger(i.week)?i.week:null,
    board_sort_order:Number.isFinite(+i.ord)?Math.max(0,Math.trunc(+i.ord)):0,
    stories:(i.stories||[]).filter(s=>String(s.uid||'').trim()).map((s,sortOrder)=>({
      id:s._backendId||null,
      client_uid:String(s.uid).trim(),
      external_key:String(s.id||''),
      title:String(s.name||''),
      effort_by_competency:s.comps&&typeof s.comps==='object'?s.comps:{SA:+s.sa||0,DEV:+s.dev||0,QA:+s.qa||0},
      sprint_index:Number.isInteger(s.sprint)?s.sprint:null,
      week_index:Number.isInteger(s.week)?s.week:null,
      sort_order:sortOrder,
      board_sort_order:Number.isFinite(+s.ord)?Math.max(0,Math.trunc(+s.ord)):0,
    })),
    work_items:(i.subtasks||[]).filter(st=>String(st.uid||'').trim()).map((st,sortOrder)=>({
      id:st._backendId||null,
      client_uid:String(st.uid).trim(),
      story_client_uid:st.storyUid?String(st.storyUid):null,
      assignee_member_id:assigneeId(i,st),
      assignee_name:String(st.fio||''),
      competency:String(st.role||'SA'),
      effort:+st.cap||0,
      sprint_index:Number.isInteger(st.sprint)?st.sprint:null,
      week_index:Number.isInteger(st.week)?st.week:null,
      sort_order:sortOrder,
      board_sort_order:Number.isFinite(+st.ord)?Math.max(0,Math.trunc(+st.ord)):0,
    })),
  }))};
}
function teamBoardsPayloadHash(id,c){ return stablePayloadHash(teamBoardsPayload(id,c)); }
function applyTeamBoards(c,aggregate){
  const byId={},byKey={};
  (c.issues||[]).forEach(i=>{
    if(i._backendId)byId[i._backendId]=i;
    if(i.id)byKey[String(i.id).toLowerCase()]=i;
  });
  (aggregate.initiatives||[]).forEach(row=>{
    const issue=byId[row.id]||byKey[String(row.issue_key).toLowerCase()];
    if(!issue)return;
    issue._backendId=row.id;
    issue.prePlanned=!!row.pre_planned;
    issue.onBoard=!!row.on_board;
    issue.agreed=!!row.agreed;
    issue.sprint=row.sprint_index===null||row.sprint_index===undefined?null:+row.sprint_index;
    if(row.week_index===null||row.week_index===undefined)delete issue.week; else issue.week=+row.week_index;
    issue.ord=+row.board_sort_order||0;
    const priorStoriesById={},priorStoriesByUid={};
    (issue.stories||[]).forEach(s=>{
      if(s._backendId)priorStoriesById[s._backendId]=s;
      if(s.uid)priorStoriesByUid[String(s.uid).toLowerCase()]=s;
    });
    issue.stories=(row.stories||[]).map(s=>{
      const story=priorStoriesById[s.id]||priorStoriesByUid[String(s.client_uid).toLowerCase()]||{};
      Object.assign(story,{
        _backendId:s.id,uid:s.client_uid,id:s.external_key||'',name:s.title||'',
        comps:s.effort_by_competency||{},
        sprint:s.sprint_index===null||s.sprint_index===undefined?null:+s.sprint_index,
        ord:+s.board_sort_order||0,
      });
      if(s.week_index===null||s.week_index===undefined)delete story.week; else story.week=+s.week_index;
      return story;
    });
    const priorItemsById={},priorItemsByUid={};
    (issue.subtasks||[]).forEach(st=>{
      if(st._backendId)priorItemsById[st._backendId]=st;
      if(st.uid)priorItemsByUid[String(st.uid).toLowerCase()]=st;
    });
    issue.subtasks=(row.work_items||[]).map(w=>{
      const item=priorItemsById[w.id]||priorItemsByUid[String(w.client_uid).toLowerCase()]||{};
      Object.assign(item,{
        _backendId:w.id,uid:w.client_uid,fio:w.assignee_name||'',role:w.competency||'',
        _assigneeMemberId:w.assignee_member_id||null,
        cap:+w.effort||0,
        sprint:w.sprint_index===null||w.sprint_index===undefined?null:+w.sprint_index,
        ord:+w.board_sort_order||0,
      });
      if(w.story_client_uid)item.storyUid=w.story_client_uid; else delete item.storyUid;
      if(w.week_index===null||w.week_index===undefined)delete item.week; else item.week=+w.week_index;
      return item;
    });
  });
}
function applyTeamBoardsIdentity(c,aggregate){
  const byKey={};
  (c.issues||[]).forEach(i=>{if(i.id)byKey[String(i.id).toLowerCase()]=i;});
  (aggregate.initiatives||[]).forEach(row=>{
    const issue=byKey[String(row.issue_key).toLowerCase()]; if(!issue)return;
    issue._backendId=row.id;
    const stories={};(issue.stories||[]).forEach(s=>{if(s.uid)stories[String(s.uid).toLowerCase()]=s;});
    (row.stories||[]).forEach(s=>{const local=stories[String(s.client_uid).toLowerCase()];if(local)local._backendId=s.id;});
    const items={};(issue.subtasks||[]).forEach(st=>{if(st.uid)items[String(st.uid).toLowerCase()]=st;});
    (row.work_items||[]).forEach(w=>{const local=items[String(w.client_uid).toLowerCase()];if(local)local._backendId=w.id;});
  });
}
function reportTeamBoardsSyncError(error){
  console.error('Team boards API sync failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastTeamBoardsSyncErrorAt>5000&&typeof toast==='function'){
    lastTeamBoardsSyncErrorAt=now;
    toast('Не удалось сохранить командные доски в backend.',{type:'warn',timeout:5000});
  }
}
async function persistTeamBoardsCycle(id,force=false){
  const c=state.cycles[id];if(!c)return;
  if(!cycleBackendIds[id])await persistCycle(id);
  const hash=teamBoardsPayloadHash(id,c);
  if(!force&&persistedTeamBoardHashes[id]===hash)return;
  const aggregate=await cycleMutation(id,`/pi-cycles/${cycleBackendIds[id]}/team-boards`,{
    method:'PUT',body:teamBoardsPayload(id,c),
  });
  applyTeamBoardsIdentity(c,aggregate);
  persistedTeamBoardHashes[id]=teamBoardsPayloadHash(id,c);
  const capacity=await cycleRead(id,`/pi-cycles/${cycleBackendIds[id]}/capacity`);
  applyCapacity(c,capacity,id);
  persistedCapacityHashes[id]=capacityPayloadHash(id,c);
}
async function syncAllTeamBoards(){
  for(const id of Object.keys(state.cycles||{}))await persistTeamBoardsCycle(id);
}
function runTeamBoardsSync(){
  const run=teamBoardsSyncChain.then(syncAllTeamBoards);
  teamBoardsSyncChain=run.catch(reportTeamBoardsSyncError);
  return run;
}
function queueTeamBoardsSync(){
  clearTimeout(teamBoardsSyncTimer);
  teamBoardsSyncTimer=setTimeout(()=>{teamBoardsSyncTimer=null;runTeamBoardsSync().catch(()=>{});},350);
}
function flushTeamBoardsSync(){
  if(teamBoardsSyncTimer){clearTimeout(teamBoardsSyncTimer);teamBoardsSyncTimer=null;}
  return runTeamBoardsSync();
}
async function loadTeamBoardsCycles(){
  persistedTeamBoardHashes={};
  for(const id of Object.keys(state.cycles||{})){
    const backendId=cycleBackendIds[id];if(!backendId)continue;
    const aggregate=await cycleRead(id,`/pi-cycles/${backendId}/team-boards`);
    applyTeamBoards(state.cycles[id],aggregate);
    persistedTeamBoardHashes[id]=teamBoardsPayloadHash(id,state.cycles[id]);
  }
  const active=currentCycleId();
  if(active&&state.cycles[active])activateCycle(active);
}
async function teamBoardCommand(path,method='PATCH',body={}){
  const id=currentCycleId(),backendId=id&&cycleBackendIds[id];
  if(!id||!backendId)throw new Error('PI cycle is not loaded');
  const aggregate=await cycleMutation(id,`/pi-cycles/${backendId}/team-boards${path}`,{method,body});
  applyTeamBoards(state.cycles[id],aggregate);
  persistedTeamBoardHashes[id]=teamBoardsPayloadHash(id,state.cycles[id]);
  const capacity=await cycleRead(id,`/pi-cycles/${backendId}/capacity`);
  applyCapacity(state.cycles[id],capacity,id);
  persistedCapacityHashes[id]=capacityPayloadHash(id,state.cycles[id]);
  const programBoard=await cycleRead(id,`/pi-cycles/${backendId}/program-board`);
  applyProgramBoard(state.cycles[id],programBoard);
  persistedProgramBoardHashes[id]=programBoardPayloadHash(id,state.cycles[id]);
  activateCycle(id);
  return aggregate;
}
function capacityCycleYear(id,c){
  const fromStart=String(c&&c.pi&&c.pi.startDate||'').match(/^(\d{4})-/);
  if(fromStart)return +fromStart[1];
  const fromId=String(id||'').match(/^(\d{4})-/);
  return fromId?+fromId[1]:new Date().getFullYear();
}
function capacityRangesPayload(text,year){
  return String(text||'').split(/[;,]/).map(x=>x.trim()).filter(Boolean).map(part=>{
    const m=part.match(/^(\d{1,2})\.(\d{1,2})(?:\s*[-–—]\s*(\d{1,2})\.(\d{1,2}))?$/);
    if(!m)return null;
    const sd=+m[1],sm=+m[2],ed=m[3]?+m[3]:sd,em=m[4]?+m[4]:sm;
    const start=`${year}-${pad2(sm)}-${pad2(sd)}`,end=`${year}-${pad2(em)}-${pad2(ed)}`;
    return end<start?null:{start,end};
  }).filter(Boolean);
}
function capacityRangesText(rows){
  return (rows||[]).map(r=>datesToVac(String(r.start||''),String(r.end||r.start||''))).filter(Boolean).join('; ');
}
function capacityNumber(value,fallback=0){
  const n=parseFloat(String(value??'').replace(',','.'));
  return Number.isFinite(n)?n:fallback;
}
function capacityMemberInputKey(member,c,id){
  return JSON.stringify({
    start:c&&c.pi&&c.pi.startDate||'',sprints:+(c&&c.pi&&c.pi.sprintCount)||0,
    fio:String(member.fio||''),role:String(member.role||''),rate:capacityNumber(member.rate,1),
    vacation:String(member.vacation||''),extraUnavailable:String(member.extraUnavailable||''),
    ceremonyPct:capacityNumber(member.ceremonyPct,0),riskPct:capacityNumber(member.riskPct,0),
    efficiency:String(member.efficiency??''),cycle:id,
  });
}
function capacityPayload(id,c){
  ensureCycleShape(c);
  const year=capacityCycleYear(id,c);
  return {teams:(c.pi.teams||[]).filter(t=>String(t.tribe||'').trim()&&String(t.name||'').trim()).map(t=>{
    const key=teamKey(t.tribe,t.name);
    return {
      tribe:String(t.tribe).trim(),team:String(t.name).trim(),
      members:(c.capacity[key]||[]).map((p,sortOrder)=>({
        id:p._backendId||null,
        client_uid:String(p.uid||(p.uid=uid())),
        full_name:String(p.fio||''),
        competency:String(p.role||'SA'),
        rate:Math.max(0,Math.min(1,capacityNumber(p.rate,1))),
        vacation_ranges:capacityRangesPayload(p.vacation,year),
        extra_unavailable_ranges:capacityRangesPayload(p.extraUnavailable,year),
        ceremony_percent:Math.max(0,Math.min(100,capacityNumber(p.ceremonyPct,0))),
        risk_percent:Math.max(0,Math.min(100,capacityNumber(p.riskPct,0))),
        efficiency:String(p.efficiency??'').trim()===''?null:Math.max(0,Math.min(1,capacityNumber(p.efficiency,1))),
        sort_order:sortOrder,
      })),
    };
  })};
}
function capacityPayloadHash(id,c){return stablePayloadHash(capacityPayload(id,c));}
function cacheCapacityComputed(id,c,aggregate){
  const cache={teams:{},members:{}};
  (aggregate.teams||[]).forEach(row=>{
    const key=teamKey(row.tribe,row.team);
    cache.teams[key]={
      calendar:+row.calendar_capacity||0,available:+row.available_capacity||0,
      planned:+row.planned_effort||0,availableByRole:row.available_by_competency||{},
      plannedByRole:row.planned_by_competency||{},
      loadByRole:row.load_by_competency||{},loadBySprint:row.load_by_sprint||{},
      loadByWeek:row.load_by_week||{},
    };
    const localByUid={};(c.capacity[key]||[]).forEach(p=>{if(p.uid)localByUid[String(p.uid).toLowerCase()]=p;});
    (row.members||[]).forEach(member=>{
      const local=localByUid[String(member.client_uid).toLowerCase()];if(!local)return;
      cache.members[member.client_uid]={
        inputKey:capacityMemberInputKey(local,c,id),
        calendar:+member.calendar_capacity||0,available:+member.available_capacity||0,
        sprints:Array.isArray(member.sprints)?member.sprints:[],weeks:member.weeks||{},
      };
    });
  });
  capacityComputedCycles[id]=cache;
}
function applyCapacity(c,aggregate,id){
  (aggregate.teams||[]).forEach(row=>{
    const key=teamKey(row.tribe,row.team);
    const priorById={},priorByUid={};
    (c.capacity[key]||[]).forEach(p=>{
      if(p._backendId)priorById[p._backendId]=p;
      if(p.uid)priorByUid[String(p.uid).toLowerCase()]=p;
    });
    c.capacity[key]=(row.members||[]).map(member=>{
      const p=priorById[member.id]||priorByUid[String(member.client_uid).toLowerCase()]||{};
      Object.assign(p,{
        _backendId:member.id,uid:member.client_uid,fio:member.full_name||'',role:member.competency||'SA',
        rate:+member.rate,vacation:capacityRangesText(member.vacation_ranges),
        extraUnavailable:capacityRangesText(member.extra_unavailable_ranges),
        ceremonyPct:+member.ceremony_percent||0,riskPct:+member.risk_percent||0,
        efficiency:member.efficiency===null||member.efficiency===undefined?'':+member.efficiency,
      });
      return p;
    });
  });
  cacheCapacityComputed(id,c,aggregate);
}
function applyCapacityIdentity(c,aggregate,id){
  (aggregate.teams||[]).forEach(row=>{
    const key=teamKey(row.tribe,row.team),byUid={};
    (c.capacity[key]||[]).forEach(p=>{if(p.uid)byUid[String(p.uid).toLowerCase()]=p;});
    (row.members||[]).forEach(member=>{
      const local=byUid[String(member.client_uid).toLowerCase()];if(local)local._backendId=member.id;
    });
  });
  cacheCapacityComputed(id,c,aggregate);
}
function reportCapacitySyncError(error){
  console.error('Capacity API sync failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastCapacitySyncErrorAt>5000&&typeof toast==='function'){
    lastCapacitySyncErrorAt=now;
    toast('Не удалось сохранить ёмкость команды в backend.',{type:'warn',timeout:5000});
  }
}
async function persistCapacityCycle(id,force=false){
  const c=state.cycles[id];if(!c)return;
  if(!cycleBackendIds[id])await persistCycle(id);
  const hash=capacityPayloadHash(id,c);
  if(!force&&persistedCapacityHashes[id]===hash)return;
  const aggregate=await cycleMutation(id,`/pi-cycles/${cycleBackendIds[id]}/capacity`,{
    method:'PUT',body:capacityPayload(id,c),
  });
  if(capacityPayloadHash(id,c)===hash)applyCapacityIdentity(c,aggregate,id);
  persistedCapacityHashes[id]=capacityPayloadHash(id,c);
}
async function syncAllCapacity(){
  for(const id of Object.keys(state.cycles||{}))await persistCapacityCycle(id);
}
function runCapacitySync(){
  const run=capacitySyncChain.then(async()=>{
    await syncAllCapacity();
  });
  capacitySyncChain=run.catch(reportCapacitySyncError);
  return run;
}
function queueCapacitySync(){
  clearTimeout(capacitySyncTimer);
  capacitySyncTimer=setTimeout(()=>{capacitySyncTimer=null;runCapacitySync().catch(()=>{});},350);
}
function flushCapacitySync(){
  if(capacitySyncTimer){clearTimeout(capacitySyncTimer);capacitySyncTimer=null;}
  return runCapacitySync();
}
async function loadCapacityCycles(){
  persistedCapacityHashes={};capacityComputedCycles={};
  for(const id of Object.keys(state.cycles||{})){
    const backendId=cycleBackendIds[id];if(!backendId)continue;
    const aggregate=await cycleRead(id,`/pi-cycles/${backendId}/capacity`);
    applyCapacity(state.cycles[id],aggregate,id);
    persistedCapacityHashes[id]=capacityPayloadHash(id,state.cycles[id]);
  }
  const active=currentCycleId();if(active&&state.cycles[active])activateCycle(active);
}
async function capacityMemberCommand(path,method='PATCH',body={}){
  const id=currentCycleId(),backendId=id&&cycleBackendIds[id];
  if(!id||!backendId)throw new Error('PI cycle is not loaded');
  const aggregate=await cycleMutation(id,`/pi-cycles/${backendId}/capacity${path}`,{method,body});
  applyCapacity(state.cycles[id],aggregate,id);
  persistedCapacityHashes[id]=capacityPayloadHash(id,state.cycles[id]);
  activateCycle(id);
  return aggregate;
}
function programBoardPayload(id,c){
  ensureCycleShape(c);
  const issueIds=new Set(),workUids=new Set();
  (c.issues||[]).forEach(issue=>{
    if(String(issue.id||'').trim())issueIds.add(String(issue.id).trim().toLowerCase());
    (issue.subtasks||[]).forEach(item=>{
      if(String(item.uid||'').trim())workUids.add(String(item.uid).trim().toLowerCase());
    });
  });
  const endpoint=edge=>{
    if(!edge||!['c','w'].includes(edge.kind))return null;
    const ref=String(edge.kind==='c'?edge.id:edge.uid||'').trim();if(!ref)return null;
    const valid=edge.kind==='c'?issueIds.has(ref.toLowerCase()):workUids.has(ref.toLowerCase());
    return valid?{kind:edge.kind,ref}:null;
  };
  const rows=[],seen=new Set();
  (c.connections||[]).forEach((edge,sortOrder)=>{
    const source=endpoint(edge.from),target=endpoint(edge.to);
    if(!source||!target)return;
    const sourceKey=source.kind+'||'+source.ref.toLowerCase(),targetKey=target.kind+'||'+target.ref.toLowerCase();
    if(sourceKey===targetKey)return;
    const edgeKey=sourceKey+'>>'+targetKey;if(seen.has(edgeKey))return;seen.add(edgeKey);
    const bend=edge.bend&&Number.isFinite(+edge.bend.dx)&&Number.isFinite(+edge.bend.dy)
      ?{dx:+edge.bend.dx,dy:+edge.bend.dy}:null;
    rows.push({
      id:edge._backendId||null,
      client_uid:String(edge.id||(edge.id=newConnId())),
      source,target,
      relation_type:String(edge.relationType||'depends_on'),
      bend,sort_order:sortOrder,
    });
  });
  return {connections:rows};
}
function programBoardPayloadHash(id,c){return stablePayloadHash(programBoardPayload(id,c));}
function connectionEndpointFromApi(endpoint){
  return endpoint.kind==='c'?{kind:'c',id:endpoint.ref}:{kind:'w',uid:endpoint.ref};
}
function applyProgramBoard(c,aggregate){
  const priorById={},priorByUid={};
  (c.connections||[]).forEach(edge=>{
    if(edge._backendId)priorById[edge._backendId]=edge;
    if(edge.id)priorByUid[String(edge.id).toLowerCase()]=edge;
  });
  c.connections=(aggregate.connections||[]).map(row=>{
    const edge=priorById[row.id]||priorByUid[String(row.client_uid).toLowerCase()]||{};
    Object.assign(edge,{
      _backendId:row.id,id:row.client_uid,
      from:connectionEndpointFromApi(row.source),to:connectionEndpointFromApi(row.target),
      relationType:row.relation_type||'depends_on',
    });
    if(row.bend)edge.bend={dx:+row.bend.dx||0,dy:+row.bend.dy||0};else delete edge.bend;
    return edge;
  });
}
function applyProgramBoardIdentity(c,aggregate){
  const byUid={};(c.connections||[]).forEach(edge=>{if(edge.id)byUid[String(edge.id).toLowerCase()]=edge;});
  (aggregate.connections||[]).forEach(row=>{
    const local=byUid[String(row.client_uid).toLowerCase()];if(local)local._backendId=row.id;
  });
}
function reportProgramBoardSyncError(error){
  console.error('Program Board API sync failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastProgramBoardSyncErrorAt>5000&&typeof toast==='function'){
    lastProgramBoardSyncErrorAt=now;
    toast('Не удалось сохранить связи Program Board в backend.',{type:'warn',timeout:5000});
  }
}
async function persistProgramBoardCycle(id,force=false){
  const c=state.cycles[id];if(!c)return;
  if(!cycleBackendIds[id])await persistCycle(id);
  const hash=programBoardPayloadHash(id,c);
  if(!force&&persistedProgramBoardHashes[id]===hash)return;
  const aggregate=await cycleMutation(id,`/pi-cycles/${cycleBackendIds[id]}/program-board`,{
    method:'PUT',body:programBoardPayload(id,c),
  });
  if(programBoardPayloadHash(id,c)===hash)applyProgramBoardIdentity(c,aggregate);
  persistedProgramBoardHashes[id]=programBoardPayloadHash(id,c);
}
async function syncAllProgramBoards(){
  for(const id of Object.keys(state.cycles||{}))await persistProgramBoardCycle(id);
}
function runProgramBoardSync(){
  const run=programBoardSyncChain.then(async()=>{
    if(teamBoardsApiReady)await flushTeamBoardsSync();
    await syncAllProgramBoards();
  });
  programBoardSyncChain=run.catch(reportProgramBoardSyncError);
  return run;
}
function queueProgramBoardSync(){
  clearTimeout(programBoardSyncTimer);
  programBoardSyncTimer=setTimeout(()=>{programBoardSyncTimer=null;runProgramBoardSync().catch(()=>{});},350);
}
function flushProgramBoardSync(){
  if(programBoardSyncTimer){clearTimeout(programBoardSyncTimer);programBoardSyncTimer=null;}
  return runProgramBoardSync();
}
async function loadProgramBoardCycles(){
  persistedProgramBoardHashes={};
  for(const id of Object.keys(state.cycles||{})){
    const backendId=cycleBackendIds[id];if(!backendId)continue;
    const aggregate=await cycleRead(id,`/pi-cycles/${backendId}/program-board`);
    applyProgramBoard(state.cycles[id],aggregate);
    persistedProgramBoardHashes[id]=programBoardPayloadHash(id,state.cycles[id]);
  }
  const active=currentCycleId();if(active&&state.cycles[active])activateCycle(active);
}
function riskFromApi(row,prior){
  const risk=prior||{};
  Object.assign(risk,{
    _backendId:row.id,id:row.id,clientUid:row.client_uid,
    scope:row.scope||'general',
    tribeId:row.tribe_id||null,teamId:row.team_id||null,initiativeId:row.initiative_id||null,
    desc:row.description||'',owner:row.owner||'',impact:row.impact||'',
    control:row.control_point||'',plan:row.mitigation_plan||'',
    probability:+row.probability||1,impactLevel:+row.impact_level||1,
    criticality:+row.criticality||1,criticalityLabel:row.criticality_label||'low',
    reactionDueDate:row.reaction_due_date||'',treatmentPlan:row.treatment_plan||'',
    status:row.status||'open',roam:row.roam||'',
    link:row.link||null,
    shared:row.scope==='team'&&!!row.is_shared,
  });
  return risk;
}
function applyRisks(c,aggregate,id=currentCycleId()){
  ensureCycleShape(c);
  const priorById={},priorByUid={};
  const remember=risk=>{
    if(risk._backendId)priorById[risk._backendId]=risk;
    if(risk.clientUid)priorByUid[String(risk.clientUid).toLowerCase()]=risk;
    if(risk.id)priorByUid[String(risk.id).toLowerCase()]=risk;
  };
  (c.risks.general||[]).forEach(remember);
  Object.values(c.risks.teams||{}).forEach(list=>(list||[]).forEach(remember));
  (c.riskRows||[]).forEach(remember);
  const general=[],teams={},flat=[];
  (aggregate.risks||[]).forEach(row=>{
    const risk=riskFromApi(row,priorById[row.id]||priorByUid[String(row.client_uid).toLowerCase()]);
    flat.push(risk);
    if(row.scope==='team'&&row.team){
      const key=teamKey(row.team.tribe,row.team.name);
      if(!teams[key])teams[key]=[];
      teams[key].push(risk);
    }else general.push(risk);
  });
  c.risks={general,teams};
  c.riskRows=flat;
  c.riskReference=aggregate.reference_data||{};
  if(id){
    risksBoards[id]=aggregate;
    if(Number.isInteger(aggregate.version)){
      cycleVersions[id]=aggregate.version;
      if(piDataViews[id]&&piDataViews[id].cycle)piDataViews[id].cycle.version=aggregate.version;
    }
  }
}
function reportRisksSyncError(error){
  console.error('Risks API sync failed',error);
  if(reportOptimisticConflict(error))return;
  const now=Date.now();
  if(now-lastRisksSyncErrorAt>5000&&typeof toast==='function'){
    lastRisksSyncErrorAt=now;
    toast('Не удалось сохранить риски в backend.',{type:'warn',timeout:5000});
  }
}
async function risksBoardCommand(path,method='POST',body={}){
  const id=currentCycleId(),backendId=id&&cycleBackendIds[id];
  if(!id||!backendId)throw new Error('PI cycle is not loaded');
  const aggregate=await cycleMutation(id,`/pi-cycles/${backendId}/risks-board${path}`,{method,body});
  applyRisks(state.cycles[id],aggregate,id);
  activateCycle(id);
  render();
  return aggregate;
}
async function loadRisksCycles(){
  risksBoards={};
  for(const id of Object.keys(state.cycles||{})){
    const backendId=cycleBackendIds[id];if(!backendId)continue;
    const aggregate=await cycleRead(id,`/pi-cycles/${backendId}/risks-board`);
    applyRisks(state.cycles[id],aggregate,id);
  }
  const active=currentCycleId();if(active&&state.cycles[active])activateCycle(active);
}
