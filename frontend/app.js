const state = {
  apiBase: localStorage.getItem("sberpiApiBase") || "http://localhost:8000/api",
  cycle: null,
  overview: null,
  tribes: [],
  teams: [],
  backlog: [],
  initiatives: [],
  goals: [],
  risks: [],
  tab: "overview",
};

const $ = (selector, root = document) => root.querySelector(selector);
const app = $("#app");

$("#apiBase").value = state.apiBase;
$("#saveApi").addEventListener("click", () => {
  state.apiBase = $("#apiBase").value.trim().replace(/\/$/, "");
  localStorage.setItem("sberpiApiBase", state.apiBase);
  toast("Адрес API сохранён");
});

$("#tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (!button) return;
  state.tab = button.dataset.tab;
  document.querySelectorAll("#tabs button").forEach((item) => {
    item.classList.toggle("active", item.dataset.tab === state.tab);
  });
  render();
});

$("#cycleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    year: Number(form.get("year")),
    quarter: form.get("quarter"),
    start_date: form.get("start_date") || null,
    sprint_count: Number(form.get("sprint_count")),
  };
  state.cycle = await api("/pi-cycles", { method: "POST", body: payload });
  await refreshAll();
  toast(`Открыт ${state.cycle.quarter} ${state.cycle.year}`);
});

async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
  };
  if (options.body) init.body = JSON.stringify(options.body);
  const response = await fetch(`${state.apiBase}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

async function refreshAll() {
  if (!state.cycle) return;
  const [overview, tribes, teams, backlog, initiatives, goals, risks] = await Promise.all([
    api(`/pi-cycles/${state.cycle.id}/overview`),
    api("/tribes"),
    api("/teams"),
    api("/backlog"),
    api(`/pi-cycles/${state.cycle.id}/initiatives`),
    api(`/pi-cycles/${state.cycle.id}/goals`),
    api(`/pi-cycles/${state.cycle.id}/risks`),
  ]);
  Object.assign(state, { overview, tribes, teams, backlog, initiatives, goals, risks });
  render();
}

function render() {
  if (!state.cycle) {
    app.innerHTML = `<div class="empty">Создайте или откройте PI-цикл, чтобы начать работу.</div>`;
    return;
  }
  const views = {
    overview: viewOverview,
    teams: viewTeams,
    backlog: viewBacklog,
    prep: viewPrep,
    goals: viewGoals,
    board: viewBoard,
    risks: viewRisks,
  };
  app.innerHTML = views[state.tab]();
  bindView();
}

function viewOverview() {
  const o = state.overview;
  const sprints = o.sprints.map((sprint) => `
    <tr><td>${sprint.title}</td><td>${formatDate(sprint.start_date)}</td><td>${formatDate(sprint.end_date)}</td></tr>
  `).join("");
  return `
    <section class="section">
      <div class="toolbar">
        <h2>Данные PI-цикла: ${state.cycle.quarter} ${state.cycle.year}</h2>
        <span class="muted">Статус: ${state.cycle.status}</span>
      </div>
      <div class="grid">
        ${metric("Команды", o.teams_count)}
        ${metric("Бэклог", o.backlog_count)}
        ${metric("В PI", o.initiatives_count)}
        ${metric("Риски", o.risks_count)}
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Спринт</th><th>Начало</th><th>Конец</th></tr></thead>
          <tbody>${sprints || emptyRow("Спринты появятся после даты старта")}</tbody>
        </table>
      </div>
    </section>
  `;
}

function viewTeams() {
  const tribeOptions = state.tribes.map((tribe) => `<option value="${tribe.id}">${escapeHtml(tribe.name)}</option>`).join("");
  const rows = state.teams.map((team) => `
    <tr>
      <td>${escapeHtml(team.name)}</td>
      <td>${escapeHtml(tribeName(team.tribe_id))}</td>
      <td>${escapeHtml(team.team_type)}</td>
    </tr>
  `).join("");
  return `
    <section class="section">
      <h2>Команды и трайбы</h2>
      <form id="tribeForm" class="form-grid">
        <label><span>Новый трайб</span><input name="name" placeholder="Например, Розничный бизнес"></label>
        <button class="primary">Добавить трайб</button>
      </form>
      <form id="teamForm" class="form-grid">
        <label><span>Трайб</span><select name="tribe_id">${tribeOptions}</select></label>
        <label><span>Команда</span><input name="name" placeholder="СБОЛ"></label>
        <label><span>Компетенции</span><input name="competencies" value="SA, DEV, QA"></label>
        <button class="primary">Добавить команду</button>
      </form>
      <div class="table-wrap">
        <table><thead><tr><th>Команда</th><th>Трайб</th><th>Тип</th></tr></thead><tbody>${rows || emptyRow("Команд пока нет", 3)}</tbody></table>
      </div>
    </section>
  `;
}

function viewBacklog() {
  const teamOptions = optionTeams();
  const rows = state.backlog.map((item) => `
    <tr>
      <td>${escapeHtml(item.issue_key)}</td>
      <td>${escapeHtml(item.title)}</td>
      <td>${escapeHtml(teamName(item.owner_team_id))}</td>
      <td>${escapeHtml(item.target_quarter || "")} ${item.target_year || ""}</td>
      <td>${escapeHtml(item.status)}</td>
      <td><button data-send-backlog="${item.id}">В PI</button></td>
    </tr>
  `).join("");
  return `
    <section class="section">
      <h2>Бэклог команд</h2>
      <form id="backlogForm" class="form-grid">
        <label><span>№ Issue</span><input name="issue_key" placeholder="SBOL-1001" required></label>
        <label><span>Название</span><input name="title" placeholder="Оплата по QR" required></label>
        <label><span>Команда-владелец</span><select name="owner_team_id"><option value="">Не выбрана</option>${teamOptions}</select></label>
        <label><span>Год</span><input name="target_year" type="number" value="${state.cycle.year}"></label>
        <label><span>Квартал</span><select name="target_quarter"><option></option><option>Q1</option><option>Q2</option><option>Q3</option><option>Q4</option></select></label>
        <label><span>Тип</span><input name="initiative_type" placeholder="Развитие функционала"></label>
        <label class="wide"><span>Описание</span><textarea name="description"></textarea></label>
        <button class="primary">Добавить инициативу</button>
      </form>
      <div class="table-wrap">
        <table><thead><tr><th>Issue</th><th>Название</th><th>Владелец</th><th>Период</th><th>Статус</th><th></th></tr></thead><tbody>${rows || emptyRow("Бэклог пуст", 6)}</tbody></table>
      </div>
    </section>
  `;
}

function viewPrep() {
  const rows = state.initiatives.map((item) => `
    <tr>
      <td>${escapeHtml(item.issue_key)}</td>
      <td>${escapeHtml(item.title)}</td>
      <td>${escapeHtml(item.owner_team_id ? teamName(item.owner_team_id) : "")}</td>
      <td>${escapeHtml(item.goal_text || "")}</td>
      <td>${escapeHtml(item.metric || "")}</td>
      <td>${escapeHtml(item.status)}</td>
    </tr>
  `).join("");
  return `
    <section class="section">
      <h2>Pre PI Planning</h2>
      <p class="muted">В MVP сюда попадают инициативы из бэклога. Следующий шаг реализации: редактирование целей, оценок и привлечений прямо в таблице.</p>
      <div class="table-wrap">
        <table><thead><tr><th>Issue</th><th>Название</th><th>Команда</th><th>Цель/веха</th><th>Метрика</th><th>Статус</th></tr></thead><tbody>${rows || emptyRow("Инициативы ещё не перенесены в PI", 6)}</tbody></table>
      </div>
    </section>
  `;
}

function viewGoals() {
  const teamOptions = optionTeams();
  const rows = state.goals.map((goal) => `
    <tr>
      <td>${escapeHtml(goal.title)}</td>
      <td>${escapeHtml(teamName(goal.team_id) || "")}</td>
      <td>${escapeHtml(goal.metric)}</td>
      <td>${escapeHtml(goal.current_value)}</td>
      <td>${escapeHtml(goal.target_value)}</td>
    </tr>
  `).join("");
  return `
    <section class="section">
      <h2>Цели PI</h2>
      <form id="goalForm" class="form-grid">
        <label><span>Команда</span><select name="team_id"><option value="">Общая цель</option>${teamOptions}</select></label>
        <label><span>Цель/веха</span><input name="title" required></label>
        <label><span>Метрика</span><input name="metric"></label>
        <label><span>AS IS</span><input name="current_value"></label>
        <label><span>TO BE</span><input name="target_value"></label>
        <button class="primary">Добавить цель</button>
      </form>
      <div class="table-wrap">
        <table><thead><tr><th>Цель</th><th>Команда</th><th>Метрика</th><th>AS IS</th><th>TO BE</th></tr></thead><tbody>${rows || emptyRow("Целей пока нет", 5)}</tbody></table>
      </div>
    </section>
  `;
}

function viewBoard() {
  const sprintCards = state.overview.sprints.map((sprint) => {
    const cards = state.initiatives
      .filter((item) => item.sprint_index === sprint.index)
      .map((item) => `<div class="card"><b>${escapeHtml(item.issue_key)}</b>${escapeHtml(item.title)}</div>`)
      .join("");
    return `<div class="sprint"><h3>${sprint.title}</h3>${cards || `<div class="muted">Нет стикеров</div>`}</div>`;
  }).join("");
  return `
    <section class="section">
      <h2>Program Board</h2>
      <p class="muted">Сущности доски и связи уже заложены в backend-модели. В MVP-интерфейсе показан первый слой: инициативы по спринтам.</p>
      <div class="board">${sprintCards || `<div class="empty">Сначала задайте дату старта PI</div>`}</div>
    </section>
  `;
}

function viewRisks() {
  const teamOptions = optionTeams();
  const rows = state.risks.map((risk) => `
    <tr>
      <td>${risk.scope === "team" ? "Командный" : "Общий"}</td>
      <td>${escapeHtml(teamName(risk.team_id) || "")}</td>
      <td>${escapeHtml(risk.description)}</td>
      <td>${escapeHtml(risk.owner)}</td>
      <td>${escapeHtml(risk.impact)}</td>
      <td>${escapeHtml(risk.control_point)}</td>
      <td>${escapeHtml(risk.mitigation_plan)}</td>
    </tr>
  `).join("");
  return `
    <section class="section">
      <h2>Риски</h2>
      <form id="riskForm" class="form-grid">
        <label><span>Тип</span><select name="scope"><option value="general">Общий</option><option value="team">Командный</option></select></label>
        <label><span>Команда</span><select name="team_id"><option value="">Не выбрана</option>${teamOptions}</select></label>
        <label><span>Владелец</span><input name="owner"></label>
        <label class="wide"><span>Описание риска</span><textarea name="description" required></textarea></label>
        <label><span>Влияние</span><input name="impact"></label>
        <label><span>Контрольная дата/событие</span><input name="control_point"></label>
        <label><span>План работы</span><input name="mitigation_plan"></label>
        <button class="primary">Добавить риск</button>
      </form>
      <div class="table-wrap">
        <table><thead><tr><th>Тип</th><th>Команда</th><th>Риск</th><th>Владелец</th><th>Влияние</th><th>Контроль</th><th>План</th></tr></thead><tbody>${rows || emptyRow("Рисков пока нет", 7)}</tbody></table>
      </div>
    </section>
  `;
}

function bindView() {
  bindForm("#tribeForm", async (form) => {
    await api("/tribes", { method: "POST", body: Object.fromEntries(new FormData(form)) });
    await refreshAll();
  });
  bindForm("#teamForm", async (form) => {
    const data = Object.fromEntries(new FormData(form));
    data.competencies = data.competencies.split(",").map((item) => item.trim()).filter(Boolean);
    await api("/teams", { method: "POST", body: data });
    await refreshAll();
  });
  bindForm("#backlogForm", async (form) => {
    const data = Object.fromEntries(new FormData(form));
    data.owner_team_id = data.owner_team_id || null;
    data.target_year = data.target_year ? Number(data.target_year) : null;
    data.target_quarter = data.target_quarter || null;
    await api("/backlog", { method: "POST", body: data });
    await refreshAll();
  });
  bindForm("#goalForm", async (form) => {
    const data = Object.fromEntries(new FormData(form));
    data.team_id = data.team_id || null;
    await api(`/pi-cycles/${state.cycle.id}/goals`, { method: "POST", body: data });
    await refreshAll();
  });
  bindForm("#riskForm", async (form) => {
    const data = Object.fromEntries(new FormData(form));
    data.team_id = data.team_id || null;
    await api(`/pi-cycles/${state.cycle.id}/risks`, { method: "POST", body: data });
    await refreshAll();
  });
  document.querySelectorAll("[data-send-backlog]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/pi-cycles/${state.cycle.id}/initiatives/from-backlog/${button.dataset.sendBacklog}`, { method: "POST" });
      await refreshAll();
      toast("Инициатива перенесена в PI");
    });
  });
}

function bindForm(selector, handler) {
  const form = $(selector);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await handler(form);
      toast("Сохранено");
    } catch (error) {
      toast(error.message, true);
    }
  });
}

function metric(label, value) {
  return `<div class="metric"><b>${value}</b><span class="muted">${label}</span></div>`;
}

function optionTeams() {
  return state.teams.map((team) => `<option value="${team.id}">${escapeHtml(team.name)}</option>`).join("");
}

function tribeName(id) {
  const tribe = state.tribes.find((item) => item.id === id);
  return tribe ? tribe.name : "";
}

function teamName(id) {
  const team = state.teams.find((item) => item.id === id);
  return team ? team.name : "";
}

function emptyRow(text, colSpan = 3) {
  return `<tr><td colspan="${colSpan}" class="muted">${text}</td></tr>`;
}

function formatDate(value) {
  return value ? new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU") : "";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function toast(message, isError = false) {
  const root = $("#toastRoot");
  const item = document.createElement("div");
  item.className = `toast${isError ? " error" : ""}`;
  item.textContent = message;
  root.appendChild(item);
  setTimeout(() => item.remove(), 3200);
}

