let currentUser=null;
let appNavigation=null;
let authScreenActive=false;
let sessionExpiryTimer=null;

const TAB_PERMISSIONS={
  data:{read:'pi_data:read',write:'pi_data:write'},
  backlog:{read:'backlog:read',write:'backlog:write'},
  prep:{read:'pre_pi:read',write:'pre_pi:write'},
  goals:{read:'goals:read',write:'goals:write'},
  teams:{read:'team_boards:read',write:'team_boards:write',approve:'tasks:approve'},
  pb:{read:'program_board:read',write:'program_board:write'},
  risks:{read:'risks:read',write:'risks:write'},
};

function hasPermission(permission){
  return !!(currentUser&&Array.isArray(currentUser.permissions)&&currentUser.permissions.includes(permission));
}
function canReadTab(tab){
  const access=TAB_PERMISSIONS[tab];
  return !!(access&&hasPermission(access.read));
}
function canWriteTab(tab){
  const access=TAB_PERMISSIONS[tab];
  return !!(access&&hasPermission(access.write));
}
function canApproveTasks(){return hasPermission('tasks:approve');}
function availablePiTabs(){
  const allowed=new Set(((appNavigation&&appNavigation.tabs)||[]).map(tab=>tab.id));
  return PI_TABS.filter(tab=>allowed.has(tab.id)&&canReadTab(tab.id));
}

async function authRequest(path,options={}){
  const init={
    method:options.method||'GET',
    headers:{'Content-Type':'application/json','Cache-Control':'no-store','Pragma':'no-cache'},
    cache:'no-store',credentials:'include',
  };
  if(options.body!==undefined)init.body=JSON.stringify(options.body);
  const response=await fetch(API_BASE+path,init);
  if(!response.ok){
    let detail='';
    try{const body=await response.json();detail=body.detail||body;}catch(_){detail=await response.text();}
    const message=typeof detail==='string'?detail:(detail&&detail.message)||JSON.stringify(detail);
    const error=new Error(message||`HTTP ${response.status}`);
    error.status=response.status;error.detail=detail;
    throw error;
  }
  return response.status===204?null:response.json();
}

function clearBackgroundWork(){
  if(sessionExpiryTimer){clearTimeout(sessionExpiryTimer);sessionExpiryTimer=null;}
  if(cycleSyncTimer){clearTimeout(cycleSyncTimer);cycleSyncTimer=null;}
  if(teamBoardsSyncTimer){clearTimeout(teamBoardsSyncTimer);teamBoardsSyncTimer=null;}
  if(capacitySyncTimer){clearTimeout(capacitySyncTimer);capacitySyncTimer=null;}
  cyclesApiReady=false;cyclesApiUnavailable=false;backlogApiReady=false;prePiApiReady=false;
  goalsApiReady=false;teamBoardsApiReady=false;capacityApiReady=false;
  programBoardApiReady=false;risksApiReady=false;
}
function scheduleSessionExpiry(){
  if(sessionExpiryTimer){clearTimeout(sessionExpiryTimer);sessionExpiryTimer=null;}
  if(!currentUser||!Number.isFinite(+currentUser.session_expires_at))return;
  const delay=Math.max(0,+currentUser.session_expires_at*1000-Date.now());
  sessionExpiryTimer=setTimeout(()=>handleSessionExpired(),Math.min(delay,2147483647));
}
function resetAuthenticatedRuntime(clearStoredUi=false){
  clearBackgroundWork();
  currentUser=null;appNavigation=null;
  cycleBackendIds={};cycleVersions={};piDataViews={};prePiViews={};goalsBoards={};
  programBoardViews={};risksBoards={};backlogBoard=null;
  persistedCycleMetadata={};persistedTeamBoardHashes={};persistedCapacityHashes={};
  capacityComputedCycles={};
  state=structuredClone(defaultState);
  if(clearStoredUi){try{sessionStorage.removeItem('piPlanning');}catch(_){}}
}

function setAuthPage(active){
  authScreenActive=active;
  document.body.classList.toggle('auth-screen',active);
  document.body.classList.remove('auth-pending');
  const header=document.querySelector('header');
  if(header)header.hidden=active;
}
function renderAuthLoading(){
  setAuthPage(true);
  const app=document.getElementById('app');
  if(app){
    app.classList.remove('read-only-view');
    app.innerHTML='<div class="auth-shell"><div class="auth-card auth-loading"><div class="auth-logo">SberPI</div><p>Проверяем сессию…</p></div></div>';
  }
}
function renderLoginScreen(message=''){
  setAuthPage(true);
  const app=document.getElementById('app');
  if(!app)return;
  app.classList.remove('read-only-view');
  app.innerHTML=`<div class="auth-shell"><form class="auth-card" id="loginForm">
    <div class="auth-logo">SberPI</div>
    <div class="auth-kicker">Платформа планирования</div>
    <h1>Вход в систему</h1>
    <p class="auth-copy">Используйте тестовую учётную запись, назначенную администратором.</p>
    ${message?`<div class="auth-error" role="alert">${escapeAuthText(message)}</div>`:''}
    <label class="auth-field"><span>Логин</span><input id="loginUsername" name="username" autocomplete="username" required autofocus></label>
    <label class="auth-field"><span>Пароль</span><input id="loginPassword" name="password" type="password" autocomplete="current-password" required></label>
    <button class="primary auth-submit" id="loginSubmit" type="submit">Войти</button>
  </form></div>`;
  const form=document.getElementById('loginForm');
  form.onsubmit=async event=>{
    event.preventDefault();
    const button=document.getElementById('loginSubmit');
    button.disabled=true;button.textContent='Входим…';
    try{
      currentUser=await authRequest('/auth/login',{method:'POST',body:{
        username:document.getElementById('loginUsername').value.trim(),
        password:document.getElementById('loginPassword').value,
      }});
      await bootAuthenticated();
    }catch(error){
      renderLoginScreen(error.status===401?'Неверный логин или пароль.':'Не удалось выполнить вход. Проверьте доступность сервера.');
    }
  };
}
function escapeAuthText(value){
  return String(value).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function handleSessionExpired(){
  if(authScreenActive&&!currentUser)return;
  resetAuthenticatedRuntime(true);
  renderLoginScreen('Сессия завершена. Войдите снова.');
}

async function logoutCurrentUser(){
  try{await authRequest('/auth/logout',{method:'POST'});}catch(error){if(error.status!==401)console.warn('Logout failed',error);}
  resetAuthenticatedRuntime(true);
  renderLoginScreen();
}

function applyNavigation(navigation){
  appNavigation=navigation;
  const previous=state.cycles||{},loaded={};
  cycleBackendIds={};cycleVersions={};piDataViews={};
  (navigation.pi_cycles||[]).forEach(record=>{
    const id=cycleId(record.year,record.quarter);
    loaded[id]=previous[id]||blankCycle();
    cycleBackendIds[id]=record.id;
  });
  state.cycles=loaded;
  cyclesApiReady=true;cyclesApiUnavailable=false;
}
async function ensureNavigationCycle(year,quarter){
  const id=cycleId(year,quarter);
  if(state.cycles[id]&&cycleBackendIds[id])return id;
  const record=await authRequest('/app/pi-cycles',{method:'POST',body:{year,quarter}});
  state.cycles[id]=state.cycles[id]||blankCycle();
  cycleBackendIds[id]=record.id;
  appNavigation.pi_cycles=appNavigation.pi_cycles||[];
  if(!appNavigation.pi_cycles.some(item=>item.id===record.id))appNavigation.pi_cycles.push(record);
  return id;
}
function normalizeAuthorizedUi(){
  state.ui.mode=null;state.ui.year=null;state.ui.quarter=null;state.ui.budgetYear=null;
  const tabs=availablePiTabs();
  if(!tabs.some(tab=>tab.id===state.ui.tab))state.ui.tab=tabs.length?tabs[0].id:null;
}
function renderUserPanel(){
  const panel=document.getElementById('userPanel');
  if(!panel)return;
  if(!currentUser){panel.innerHTML='';return;}
  panel.innerHTML=`<span class="user-name">${escapeAuthText(currentUser.username)}</span><button class="ghost user-logout" id="logoutButton">Выйти</button>`;
  document.getElementById('logoutButton').onclick=logoutCurrentUser;
}

const WRITE_ACTION_SELECTOR=[
  '#saveData','#editData','#addPir','#addTeam','#addGoal','#addTag',
  '#bkAddIssue','#bkSend','#prepSubmit','#goalAdd','#riskAdd','#tbCap','#addCap',
  '#sm_approve','#sm_story','#sm_decomp','#m_save','#gm_save','#rm_save','#am_save',
  '#sy_save','#sy_del','#sy_decomp',
  '#w_save','#w_del','#cm_save','#vm_save','#vm_clear','#vm_add_range',
  '[data-delete-pir]','[data-delete-team]','[data-delete-goal]','[data-delete-tag]',
  '[data-bk-delrow]','[data-bk-execadd]','[data-bk-execdel]',
  '[data-pi-delrow]','[data-pi-execadd]','[data-pi-execdel]','[data-attr-add]','[data-attr-del]',
  '[data-goal-edit]','[data-goal-del]','[data-goal-status]',
  '[data-delcap]','[data-vacedit]','[data-unavailedit]','[data-vm-del]',
  '[data-delissue]','[data-delstory-i]','[data-delsub-i]','[data-delsub-s]','[data-delarrow]',
  '[data-rg-edit]','[data-rg-del]','[data-rt-edit]','[data-rt-del]','[data-rt-share]'
].join(',');
const WRITE_FIELD_SELECTOR=[
  '[data-bk]','[data-bp]','[data-bk-exec]','[data-bk-comp]',
  '[data-pi]','[data-pk]','[data-pi-exec]','[data-pi-comp]','[data-attr-aid]',
  '[data-goal-k]','[data-goal-status]','[data-ck]','[data-ci]','[data-tb-fio]',
  '[data-sm-tag]','[data-vm-k]','[data-rt-share]'
].join(',');

function applyAccessControls(root=document.getElementById('app')){
  if(!root)return;
  const readOnly=state.ui.mode==='pi'&&!canWriteTab(state.ui.tab);
  root.classList.toggle('read-only-view',readOnly);
  if(!readOnly)return;
  root.querySelectorAll('[draggable="true"],[data-drag],[data-rowdrag],[data-goaldrag],[data-riskdrag-id]').forEach(el=>{
    el.draggable=false;el.removeAttribute('draggable');
  });
  root.querySelectorAll(WRITE_ACTION_SELECTOR).forEach(el=>{el.hidden=true;el.disabled=true;});
  root.querySelectorAll(WRITE_FIELD_SELECTOR).forEach(el=>{
    if(el.matches('input,textarea'))el.readOnly=true;
    else if(el.matches('select,button'))el.disabled=true;
  });
  if(root.id==='modalRoot')root.querySelectorAll('input,textarea,select').forEach(el=>{el.disabled=true;});
}

document.addEventListener('dragstart',event=>{
  if(state&&state.ui&&state.ui.mode==='pi'&&!canWriteTab(state.ui.tab))event.preventDefault();
},true);
document.addEventListener('click',event=>{
  if(!state||state.ui.mode!=='pi'||canWriteTab(state.ui.tab))return;
  const action=event.target.closest&&event.target.closest(WRITE_ACTION_SELECTOR);
  if(action){event.preventDefault();event.stopImmediatePropagation();}
},true);
document.addEventListener('DOMContentLoaded',()=>{
  const modal=document.getElementById('modalRoot');
  if(modal)new MutationObserver(()=>applyAccessControls(modal)).observe(modal,{childList:true,subtree:true});
});
