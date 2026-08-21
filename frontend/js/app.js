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
async function bootAuthenticated(){
  appNavigation=await authRequest('/app/navigation');
  applyNavigation(appNavigation);
  normalizeAuthorizedUi();
  scheduleSessionExpiry();
  setAuthPage(false);
  renderUserPanel();
  save(false);
  render();
}
async function boot(){
  loadState();
  renderAuthLoading();
  try{
    currentUser=await authRequest('/auth/me');
    await bootAuthenticated();
  }catch(error){
    if(error.status===401)renderLoginScreen();
    else renderLoginScreen('Сервис временно недоступен. Попробуйте ещё раз.');
  }
}
document.addEventListener('visibilitychange',()=>{
  if(!currentUser||state.ui.mode!=='pi'||state.ui.tab==='data'||!canWriteTab(state.ui.tab))return;
  if(document.visibilityState==='hidden'&&teamBoardsApiReady&&hasPermission('team_boards:write'))flushTeamBoardsSync().catch(()=>{});
  if(document.visibilityState==='hidden'&&capacityApiReady&&hasPermission('team_boards:write'))flushCapacitySync().catch(()=>{});
});
boot();
