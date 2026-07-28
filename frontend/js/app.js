/* =====================================================================
   DRAG & DROP (общий механизм)
   onDrop(payload,target) ; targetSel — селектор зон ; targetVal — функция значения
===================================================================== */
function enableDrag(scope,onDrop,targetSel,targetVal){
  scope.querySelectorAll('[data-drag]').forEach(el=>{
    el.addEventListener('dragstart',e=>{
      const payload={kind:el.dataset.drag,id:el.dataset.id,sub:el.dataset.sub!==undefined?+el.dataset.sub:undefined,story:el.dataset.storyUid};
      e.dataTransfer.setData('text/plain',JSON.stringify(payload));
      e.dataTransfer.effectAllowed='move';
      setTimeout(()=>el.style.opacity='.4',0);
    });
    el.addEventListener('dragend',()=>el.style.opacity='1');
  });
  scope.querySelectorAll(targetSel).forEach(zone=>{
    zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('dragover');});
    zone.addEventListener('dragleave',()=>zone.classList.remove('dragover'));
    zone.addEventListener('drop',e=>{
      e.preventDefault();zone.classList.remove('dragover');
      try{const payload=JSON.parse(e.dataTransfer.getData('text/plain'));onDrop(payload,targetVal(zone),e);}catch(err){}
    });
  });
}

/* ===================================================================== */
// Клик по логотипу — возврат к выбору PI-цикла (работает и на вкладках, и на главной).
(function(){
  const brand=document.getElementById('brand');
  if(brand) brand.onclick=()=>backToLanding();
})();
async function boot(){
  loadState();
  render();
  try{
    await loadCyclesFromApi();
    await loadPiDataViews();
    cyclesApiReady=true;
    cyclesApiUnavailable=false;
  }catch(error){
    cyclesApiReady=false;
    cyclesApiUnavailable=true;
    reportCycleSyncError(error);
  }
  try{
    await loadBacklogBoard();
    backlogApiReady=true;
  }catch(error){
    backlogApiReady=false;
    reportBacklogSyncError(error);
  }
  try{
    await loadPrePiCycles();
    prePiApiReady=true;
  }catch(error){
    prePiApiReady=false;
    reportPrePiSyncError(error);
  }
  try{
    await loadGoalsCycles();
    goalsApiReady=true;
  }catch(error){
    goalsApiReady=false;
    reportGoalsSyncError(error);
  }
  try{
    await loadTeamBoardsCycles();
    teamBoardsApiReady=true;
  }catch(error){
    teamBoardsApiReady=false;
    reportTeamBoardsSyncError(error);
  }
  try{
    await loadCapacityCycles();
    capacityApiReady=true;
  }catch(error){
    capacityApiReady=false;
    reportCapacitySyncError(error);
  }
  try{
    await loadProgramBoardCycles();
    programBoardApiReady=true;
  }catch(error){
    programBoardApiReady=false;
    reportProgramBoardSyncError(error);
  }
  try{
    await loadRisksCycles();
    risksApiReady=true;
  }catch(error){
    risksApiReady=false;
    reportRisksSyncError(error);
  }
  save();
  render();
}
document.addEventListener('visibilitychange',()=>{
  if(state.ui.mode!=='pi' || state.ui.tab==='data') return;
  if(document.visibilityState==='hidden' && teamBoardsApiReady) flushTeamBoardsSync().catch(()=>{});
  if(document.visibilityState==='hidden' && capacityApiReady) flushCapacitySync().catch(()=>{});
  if(document.visibilityState==='hidden' && programBoardApiReady) flushProgramBoardSync().catch(()=>{});
});
boot();
