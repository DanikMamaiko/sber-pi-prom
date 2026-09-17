/* =====================================================================
   DRAG & DROP (общий механизм)
   onDrop(payload,target,event,placement); placement — позиция визуального индикатора
   targetSel — селектор зон ; targetVal — функция значения
===================================================================== */
function enableDrag(scope,onDrop,targetSel,targetVal,placementOptions=null){
  let draggedEl=null,draggedPayload=null,dropIndicator=null;
  const clearDropIndicator=()=>{
    if(dropIndicator)dropIndicator.remove();
    dropIndicator=null;
  };
  const placementContainer=zone=>placementOptions&&placementOptions.container
    ? placementOptions.container(zone)
    : zone;
  const updateDropIndicator=(zone,clientY)=>{
    if(!placementOptions||!draggedPayload||
      (placementOptions.accepts&&!placementOptions.accepts(draggedPayload,zone))){
      clearDropIndicator();return null;
    }
    const container=placementContainer(zone);if(!container){clearDropIndicator();return null;}
    const items=[...container.children].filter(el=>el!==draggedEl&&el.matches(placementOptions.itemSelector));
    const before=items.find(el=>{
      const rect=el.getBoundingClientRect();
      return clientY<rect.top+rect.height/2;
    })||null;
    if(!dropIndicator){
      dropIndicator=document.createElement('div');
      dropIndicator.className='sticker-drop-indicator';
      dropIndicator.setAttribute('aria-hidden','true');
    }
    container.insertBefore(dropIndicator,before);
    return {before,index:before?items.indexOf(before):items.length};
  };
  scope.querySelectorAll('[data-drag]').forEach(el=>{
    el.addEventListener('dragstart',e=>{
      const payload={kind:el.dataset.drag,id:el.dataset.id,sub:el.dataset.sub!==undefined?+el.dataset.sub:undefined,story:el.dataset.storyUid};
      e.dataTransfer.setData('text/plain',JSON.stringify(payload));
      e.dataTransfer.effectAllowed='move';
      draggedEl=el;draggedPayload=payload;
      setTimeout(()=>{el.style.opacity='.4';el.classList.add('dragging');},0);
    });
    el.addEventListener('dragend',()=>{
      el.style.opacity='1';el.classList.remove('dragging');
      draggedEl=null;draggedPayload=null;clearDropIndicator();
    });
  });
  scope.querySelectorAll(targetSel).forEach(zone=>{
    zone.addEventListener('dragover',e=>{
      e.preventDefault();zone.classList.add('dragover');
      updateDropIndicator(zone,e.clientY);
    });
    zone.addEventListener('dragleave',e=>{
      if(e.relatedTarget&&zone.contains(e.relatedTarget))return;
      const rect=zone.getBoundingClientRect();
      if(e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom)return;
      zone.classList.remove('dragover');clearDropIndicator();
    });
    zone.addEventListener('drop',e=>{
      e.preventDefault();zone.classList.remove('dragover');
      const placement=updateDropIndicator(zone,e.clientY);
      clearDropIndicator();
      try{const payload=JSON.parse(e.dataTransfer.getData('text/plain'));onDrop(payload,targetVal(zone),e,placement);}catch(err){}
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
