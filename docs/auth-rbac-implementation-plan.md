# План реализации авторизации и ролевого доступа

## 1. Статус документа

Этот документ описывает согласованный и реализованный объём работ по спецификации
[`docs/auth-rbac-plan.md`](auth-rbac-plan.md). Реализация завершена после подтверждения
заказчика; фактические решения, API-контракты и настройки отражены ниже.

## 2. Согласованные решения

- Авторизация всегда включена, включая локальное окружение. Переключатель
  `AUTH_ENABLED=false` не добавляется.
- Текущий provider — `LocalAuthProvider`; пользователи и роли задаются через `.env`.
- Реальный LDAP/Active Directory provider на этом этапе не реализуется, но интерфейс
  provider, фабрика и настройки под него закладываются заранее.
- Сессия хранится в подписанной `HttpOnly` cookie и имеет абсолютный срок жизни 60 минут.
- Активность пользователя не продлевает срок сессии. Через 60 минут следующий API-запрос
  получает `401`, после чего frontend переводит пользователя на экран входа.
- Logout немедленно удаляет cookie. Таблица серверных сессий и аудит входов на первом
  этапе не создаются.
- `GET /api/health` остаётся публичным. Auth login и CORS preflight также доступны без
  пользовательской сессии. Все бизнес-endpoints защищаются.
- Отдельный интерфейс управления пользователями и ролями не создаётся: источником
  пользователей и назначений ролей остаётся `.env`.
- Вкладка «Данные PI-цикла» является административной и доступна только `admin`.
- Для PM (`business_viewer`) вкладка «Бэклог команд» полностью скрыта, а backend API
  бэклога отвечает `403`.
- «Бюджетирование» отображается красивой неактивной карточкой «В разработке / Будет
  доступно позже». Существующий код прототипа бюджетирования сохраняется, но вход в него
  из интерфейса блокируется.

## 3. Целевой пользовательский сценарий

1. При открытии страницы приложение не показывает рабочий интерфейс до проверки сессии.
2. Frontend вызывает `GET /api/auth/me` с cookie credentials.
3. При `401` отображается только экран входа; рабочий header, навигация и PI-данные скрыты.
4. Пользователь отправляет логин и пароль в `POST /api/auth/login`.
5. Backend проверяет данные через активный `AuthProvider`, создаёт подписанную cookie и
   возвращает пользователя, роли и вычисленные permissions.
6. Frontend получает `GET /api/app/navigation` и показывает главную страницу:
   - неактивное «Бюджетирование»;
   - выбор существующего PI-цикла по году и кварталу.
7. После выбора цикла загружаются только те агрегаты, на чтение которых у пользователя
   есть permission.
8. В навигации присутствуют только разрешённые вкладки. Для read-only ролей поля и
   действия изменения недоступны, но фильтры и просмотр продолжают работать.
9. После 60 минут API возвращает `401`; frontend прекращает фоновые синхронизации,
   очищает пользовательский runtime-state и показывает экран входа.
10. Кнопка выхода вызывает `POST /api/auth/logout`, после чего результат тот же: рабочее
    приложение скрывается и показывается форма входа.

## 4. Backend-архитектура

### 4.1. Auth provider

Будет добавлен отдельный auth-слой, не связанный с API вкладок:

```text
backend/app/auth/
  models.py          # AuthIdentity / CurrentUser
  providers.py       # AuthProvider, LocalAuthProvider, LdapAuthProvider skeleton
  service.py         # выбор provider и сценарий аутентификации
  session.py         # создание и проверка подписанной cookie
  dependencies.py    # require_auth / require_permission / require_any_permission
  permissions.py     # роли, permissions и единая матрица
```

Интерфейс `AuthProvider` будет отделять проверку учётных данных от RBAC. Минимальный
контракт provider:

- принять логин и пароль;
- вернуть нормализованную identity с username и ролями либо отказ;
- не формировать permissions самостоятельно — они вычисляются общей RBAC-моделью.

`LocalAuthProvider`:

- читает тестовых пользователей из `AUTH_TEST_USERS`;
- проверяет логин и пароль без раскрытия причины отказа;
- сравнивает пароль безопасным сравнением;
- валидирует дубликаты пользователей и неизвестные роли при создании provider.

`LdapAuthProvider` на первом этапе содержит тот же интерфейс и место для будущего LDAP
bind/group lookup. При выборе ещё не реализованного `AUTH_PROVIDER=ldap` login возвращает
явную сервисную ошибку без попытки локальной аутентификации и без небезопасного fallback.

### 4.2. RBAC

Проверки вида `if role == ...` в endpoints не используются. В одном модуле задаются:

- допустимые роли;
- полный список permissions;
- отображение `роль -> множество permissions`;
- объединение permissions, если будущий provider вернёт несколько ролей.

Матрица:

| Permission | `admin` | `planning_editor` | `business_viewer` | `viewer` |
|---|---:|---:|---:|---:|
| `app:navigate` | Да | Да | Да | Да |
| `pi_data:read` | Да | Нет | Нет | Нет |
| `pi_data:write` | Да | Нет | Нет | Нет |
| `backlog:read` | Да | Да | Нет | Да |
| `backlog:write` | Да | Да | Нет | Нет |
| `pre_pi:read` | Да | Да | Да | Да |
| `pre_pi:write` | Да | Да | Нет | Нет |
| `goals:read` | Да | Да | Да | Да |
| `goals:write` | Да | Нет | Нет | Нет |
| `team_boards:read` | Да | Да | Да | Да |
| `team_boards:write` | Да | Да | Нет | Нет |
| `tasks:approve` | Да | Да | Нет | Нет |
| `program_board:read` | Да | Да | Да | Да |
| `program_board:write` | Да | Да | Нет | Нет |
| `risks:read` | Да | Да | Да | Да |
| `risks:write` | Да | Да | Нет | Нет |
| `admin:users` | Да | Нет | Нет | Нет |

`admin:users` закладывается для дальнейшего развития, но отдельные endpoints и UI
управления пользователями сейчас не создаются.

### 4.3. Сессия

Сессия реализуется как подписанный, но не зашифрованный cookie-token. В payload не
помещаются пароль, секреты и полный набор permissions. Предполагаемый минимальный payload:

- версия формата;
- username;
- роли на момент входа;
- provider;
- время выпуска и абсолютное время истечения.

Backend на каждом защищённом запросе:

1. читает cookie;
2. проверяет криптографическую подпись;
3. проверяет абсолютный срок 60 минут;
4. валидирует роли;
5. заново вычисляет permissions по серверной матрице.

Параметры cookie:

- `HttpOnly=true`;
- `SameSite=Lax`;
- `Path=/`;
- `Max-Age=3600` при стандартной настройке;
- `Secure` задаётся env-переменной и должен быть `true` в HTTPS-контуре;
- срок не обновляется на `/me` или других API-запросах.

Для подписи используется проверенная небольшая библиотека, а не собственная реализация
криптографии. Зависимость будет явно закреплена в `backend/requirements.txt`.

### 4.4. FastAPI dependencies

Будут добавлены:

- `require_auth` — возвращает `CurrentUser`, при отсутствующей/битой/истёкшей сессии
  отвечает `401`;
- `require_permission("permission")` — сначала проверяет сессию, затем permission и при
  недостатке прав отвечает `403`;
- `require_any_permission(...)` — резерв для операций, допускающих несколько прав.

Проверка permission выполняется до доменной операции и не зависит от того, что скрыл
frontend.

## 5. API-контракты

### 5.1. Auth API

#### `POST /api/auth/login`

Запрос:

```json
{
  "username": "editor",
  "password": "editor123"
}
```

Успех: `200`, установка cookie и ответ:

```json
{
  "username": "editor",
  "roles": ["planning_editor"],
  "permissions": ["app:navigate", "backlog:read", "backlog:write"]
}
```

Список выше сокращён для примера; фактически возвращается полный набор роли. Неверные
учётные данные дают одинаковый `401` без уточнения, существует ли пользователь.

#### `POST /api/auth/logout`

- требует действующую сессию;
- удаляет session cookie;
- возвращает `204 No Content`.

#### `GET /api/auth/me`

- требует действующую сессию;
- возвращает username, roles, permissions и время истечения сессии;
- не продлевает сессию.

### 5.2. `GET /api/app/navigation`

Endpoint требует `app:navigate` и возвращает:

- разделы главной страницы;
- статус бюджетирования `development` и `enabled=false`;
- только доступные текущему пользователю PI-вкладки;
- для каждой вкладки признаки `can_read`, `can_write`, а для командных досок —
  `can_approve`;
- список PI-циклов только с `id`, `year`, `quarter`.

Endpoint не возвращает дату старта, спринты, ПИРы, команды, компетенции, версии агрегатов
или флаги инициализации. Необходимый для конкретной рабочей вкладки контекст продолжает
приходить только в разрешённом read model этой вкладки.

### 5.3. Создание и выбор PI-цикла

- Все авторизованные роли имеют permission `pi_cycle:select` и видят активными Q1–Q4.
- `POST /api/app/pi-cycles` по `year` и `quarter` идемпотентно возвращает существующий
  цикл или создаёт его минимальную запись при первом открытии.
- Инициализация квартала не выдаёт `pi_data:read`/`pi_data:write`: подробная вкладка
  «Данные PI-цикла» по-прежнему доступна только `admin`.
- Общий `GET /api/pi-cycles`, подробные `/setup`, `/data`, `/overview` и справочники
  PI-настройки не используются неадминистративным frontend.

## 6. Защита существующих endpoints

Публичными остаются только health/login и технические CORS preflight-запросы.

| API-группа | GET/read | POST/PUT/PATCH/DELETE |
|---|---|---|
| PI-цикл, setup/data/overview, трайбы, команды, участники | `pi_data:read` | `pi_data:write` |
| Бэклог | `backlog:read` | `backlog:write` |
| Pre PI и инициативы | `pre_pi:read` | `pre_pi:write` |
| Цели | `goals:read` | `goals:write` |
| Командные доски и ёмкость | `team_boards:read` | `team_boards:write` |
| Согласование задач | — | дополнительно `tasks:approve` |
| Program Board | `program_board:read` | `program_board:write` |
| Риски | `risks:read` | `risks:write` |

Те же permissions применяются к временно сохранённым legacy endpoints (`/goals`,
`/risks`, `/initiatives`), чтобы обход агрегатного API не обходил RBAC.

Согласование сейчас передаётся как изменение `agreed` внутри команды командной доски.
Backend будет отдельно проверять `tasks:approve`, когда payload действительно меняет этот
признак. Остальные изменения этой команды требуют `team_boards:write`.

## 7. Frontend-реализация

### 7.1. Auth-first boot

Текущий `boot()` сначала рисует приложение и загружает все агрегаты. Он будет заменён на
последовательность:

1. загрузить только UI-настройки;
2. показать нейтральное состояние загрузки, не раскрывающее приложение;
3. вызвать `/auth/me`;
4. при `401` отрисовать login screen;
5. при успехе получить `/app/navigation`;
6. нормализовать сохранённый UI-state с учётом разрешённых вкладок;
7. показать главную страницу;
8. загружать данные выбранного цикла только по разрешённым permissions.

Header с вкладками скрывается на login screen. После входа в header добавляются имя
пользователя и кнопка «Выйти».

### 7.2. HTTP-клиент

В общий wrapper `cycleApi` добавляются:

- `credentials: "include"` для всех запросов;
- единая обработка `401`;
- единая обработка `403` без fallback на локальные данные;
- запрет повторного показа нескольких login screens при серии параллельных `401`;
- остановка очередей autosave и сброс runtime read models при завершении сессии.

Auth token не записывается ни в `localStorage`, ни в `sessionStorage`. Существующий
`sessionStorage` по-прежнему содержит только UI-настройки и сохранённый прототип бюджета.

### 7.3. Навигация и вкладки

- `PI_TABS` связывается с permissions, а рендер использует разрешённый сервером список.
- Если сохранённая активная вкладка больше недоступна, выбирается первая разрешённая.
- Вкладка `data` видна только `admin`.
- Вкладка `backlog` скрыта для `business_viewer`.
- Остальные роли получают вкладки строго по согласованной матрице.
- Запрещённые агрегаты не запрашиваются даже в фоне.
- При ручной подмене UI или прямом fetch backend всё равно возвращает `403`.

### 7.4. Read-only режим

Для доступных на просмотр вкладок вводится общий helper `hasPermission(...)` и единое
обозначение DOM-элементов, требующих write-permission. В read-only режиме:

- скрываются кнопки добавления, удаления, сохранения, отправки и согласования;
- editable-поля становятся `readonly`/`disabled` в зависимости от типа;
- drag-and-drop и изменение геометрии досок не привязываются;
- не запускаются очереди `queue*Sync` и `flush*Sync`;
- фильтры, переключатели представлений, прокрутка, выбор трайба/команды и просмотр
  модальных деталей остаются доступными;
- frontend-командные helpers дополнительно проверяют permission перед отправкой запроса.

Отдельное право `tasks:approve` управляет кнопкой «Согласовать», независимо от общего
права просмотра доски.

### 7.5. Безопасная загрузка контекста цикла

Сейчас frontend строит `state.pi` из admin-only `/pi-cycles/{id}/data`. После RBAC:

- список циклов строится из минимального navigation response;
- admin продолжает получать полный PI data read model;
- остальные роли инициализируют рабочий контекст из разрешённых read models, прежде
  всего Pre PI, который уже содержит цикл, команды, компетенции и варианты целей,
  необходимые доступным рабочим экранам;
- данные одного read model не превращаются в новый browser source of truth;
- admin-only endpoint `/data` не вызывается ролями без `pi_data:read`.

### 7.6. Бюджетирование

На landing page остаётся карточка «Бюджетирование», но:

- кнопка открытия рабочего прототипа удаляется или блокируется;
- показывается аккуратный статус «В разработке» и текст «Будет доступно позже»;
- существующие `budget.js`, `BUDGET_TABS` и сохранённый код прототипа не удаляются;
- переход в budget mode из сохранённого старого UI-state блокируется при нормализации
  состояния после входа.

## 8. Конфигурация `.env`

В `.env.example` будут добавлены фактические настройки:

```env
AUTH_PROVIDER=local
AUTH_TEST_USERS=admin:admin123:admin,editor:editor123:planning_editor,pm:pm123:business_viewer,user:user123:viewer

SESSION_SECRET=replace-with-a-long-random-secret
SESSION_TTL_MINUTES=60
SESSION_COOKIE_NAME=sberpi_session
SESSION_COOKIE_SECURE=false

AD_GROUP_ADMIN=SBERPI_ADMIN
AD_GROUP_PLANNING_EDITOR=SBERPI_PLANNING_EDITOR
AD_GROUP_BUSINESS_VIEWER=SBERPI_BUSINESS_VIEWER

LDAP_URL=ldaps://ad.company.local:636
LDAP_BASE_DN=DC=company,DC=local
LDAP_USER_SEARCH_BASE=OU=Users,DC=company,DC=local
LDAP_USER_FILTER=(sAMAccountName={username})
LDAP_GROUP_SEARCH_BASE=OU=Groups,DC=company,DC=local
LDAP_GROUP_FILTER=(member={user_dn})
LDAP_BIND_DN=
LDAP_BIND_PASSWORD=
LDAP_USE_TLS=true
```

Текущий локальный `.env` будет дополнен без перезаписи существующей конфигурации БД/CORS.
Для него будет сгенерирован длинный случайный `SESSION_SECRET`. Тестовые логины из примера
будут доступны локально для проверки четырёх ролей.

`AUTH_ENABLED` намеренно отсутствует: по согласованному требованию авторизация не может
быть отключена ни локально, ни в рабочем окружении.

## 9. Планируемые изменения файлов

### Новые файлы

- `backend/app/auth/__init__.py`
- `backend/app/auth/models.py`
- `backend/app/auth/providers.py`
- `backend/app/auth/service.py`
- `backend/app/auth/session.py`
- `backend/app/auth/dependencies.py`
- `backend/app/auth/permissions.py`
- `backend/app/api/auth.py`
- `backend/app/api/navigation.py`
- `backend/app/schemas/auth.py`
- `backend/tests/test_auth_permissions.py`
- `backend/tests/test_auth_api.py`
- при необходимости отдельный integration-тест navigation/RBAC;
- `frontend/js/auth.js`

### Изменяемые backend-файлы

- `backend/app/main.py` — инициализация auth/session-компонентов и общие настройки;
- `backend/app/api/router.py` — auth/navigation routers;
- `backend/app/core/config.py` — auth, cookie, LDAP и AD settings;
- все модули `backend/app/api/*.py` — декларативные permission dependencies;
- схема команды командной доски или endpoint — отдельная проверка `tasks:approve`;
- `backend/requirements.txt` — библиотека подписи cookie;
- `backend/tests/integration/conftest.py` — admin login для существующих API-сценариев.

### Изменяемые frontend-файлы

- `frontend/index.html` — подключение auth-модуля и обновление cache-busting версий;
- `frontend/css/styles.css` — login screen, user/logout area, disabled budget card,
  read-only состояния;
- `frontend/js/state.js` — auth/navigation runtime-state и permission metadata;
- `frontend/js/api.js` — credentials, `401`/`403`, permission-aware loading;
- `frontend/js/app.js` — auth-first boot и загрузка только разрешённых агрегатов;
- `frontend/js/render.js` — login/landing/navigation/logout и фильтрация вкладок;
- `frontend/js/pi-data.js`, `backlog.js`, `pre-pi.js`, `goals.js`,
  `team-boards.js`, `program-board.js`, `risks.js` — write/read-only controls и guards;
- `frontend/js/utils.js` — общие permission/UI helpers при необходимости.

### Конфигурация и документация

- `.env.example` и локальный `.env`;
- `README.md` — тестовые логины, часовая сессия и запуск;
- `docs/api.md` — auth/navigation contracts, `401`/`403` и permission-защита;
- `docs/architecture.md` — auth provider, cookie session и RBAC;
- `docs/auth-rbac-plan.md` остаётся исходной спецификацией и не перезаписывается.

## 10. Тесты

### 10.1. Unit/API

- успешный login каждого тестового пользователя;
- неверный логин/пароль возвращает `401` и не устанавливает рабочую cookie;
- cookie имеет `HttpOnly`, корректные `SameSite`, `Path` и `Max-Age`;
- `/auth/me` возвращает текущего пользователя, роли и permissions;
- tampered cookie возвращает `401`;
- истёкшая через 60 минут cookie возвращает `401` и не продлевается активностью;
- logout удаляет cookie, повторный `/auth/me` возвращает `401`;
- полный параметризованный тест матрицы role/permission;
- неизвестная роль и некорректный `AUTH_TEST_USERS` отклоняются;
- `AUTH_PROVIDER=ldap` не выполняет локальный fallback.

### 10.2. RBAC integration

- публичный `/health` работает без сессии;
- бизнес-endpoint без сессии возвращает `401`;
- authenticated пользователь без permission получает `403`;
- `business_viewer` получает `403` на чтение и запись бэклога;
- `viewer` читает бэклог, но получает `403` на запись;
- `planning_editor` читает и изменяет planning-разделы, но получает `403` на PI data;
- `planning_editor` читает цели, но получает `403` на их изменение;
- `business_viewer` и `viewer` не могут согласовать задачу;
- `admin` проходит все read/write проверки;
- navigation возвращает только `id/year/quarter`, корректные вкладки и признаки действий;
- существующие интеграционные доменные сценарии проходят под admin-сессией.

### 10.3. Frontend contract

- boot сначала проверяет `/auth/me` и не рендерит приложение до результата;
- fetch использует `credentials: "include"`;
- auth token отсутствует в `localStorage` и `sessionStorage`;
- скрытые вкладки фильтруются по permissions;
- `business_viewer` не видит backlog, не видит и не загружает PI data;
- read-only роли не запускают mutation/autosave helpers;
- `401` переводит UI на login screen;
- бюджетная карточка не открывает существующий прототип;
- существующие контракты отсутствия PI business data в browser storage сохраняются.

### 10.4. Запуск проверок после реализации

Планируемая последовательность:

```powershell
cd backend
python -m pytest -q tests/test_auth_permissions.py tests/test_auth_api.py
python -m pytest -q tests/test_frontend_*_contract.py

cd ..
docker compose -f docker-compose.test.yml up -d --wait
cd backend
$env:TEST_DATABASE_URL='postgresql+asyncpg://sberpi:sberpi@localhost:5433/sberpi_test'
python -m pytest -q
```

При наличии доступного локального контура дополнительно выполняется ручная проверка всех
четырёх ролей в браузере, logout и автоматического возврата на login screen после истечения
сессии.

## 11. Порядок реализации

1. Добавить settings, RBAC-модель и unit-тест матрицы.
2. Реализовать provider interface, `LocalAuthProvider` и LDAP skeleton.
3. Реализовать непродлеваемую часовую cookie-сессию и auth endpoints.
4. Добавить navigation endpoint с минимальным PI-контрактом.
5. Закрыть все существующие backend endpoints permissions и обновить test fixtures.
6. Перевести frontend на auth-first boot и централизованную обработку `401`/`403`.
7. Перевести landing/navigation на серверные permissions и минимальный список циклов.
8. Реализовать read-only режим каждой доступной вкладки и прекратить запрещённые фоновые
   загрузки/записи.
9. Закрыть бюджетный прототип неактивной карточкой, не удаляя его код.
10. Обновить env-примеры и документацию.
11. Запустить auth, frontend contract и полный integration test suite; исправить регрессии.

## 12. Критерии готовности

Реализация считается завершённой, когда одновременно выполнено следующее:

- без сессии пользователь видит только экран входа;
- успешный login открывает главную страницу;
- сессия всегда истекает через 60 минут от входа и не продлевается;
- после истечения frontend возвращается на экран входа;
- вкладки и действия соответствуют permission-матрице;
- PM не видит бэклог;
- только admin видит «Данные PI-цикла»;
- прямые вызовы API дают `401` или `403` по согласованным правилам;
- navigation не раскрывает подробные PI-настройки;
- бюджетирование помечено как находящееся в разработке, а его прототип не удалён;
- архитектура позволяет заменить local provider на LDAP без изменения frontend и RBAC;
- новые и существующие релевантные тесты проходят.

## 13. Результат реализации

- Реализованы local auth-provider, каркас LDAP provider, подписанная непродлеваемая
  `HttpOnly` cookie-сессия и permission-based RBAC.
- Backend endpoints защищены независимо от frontend: без сессии возвращается `401`, без
  необходимого permission — `403`.
- Frontend переведён на auth-first загрузку, ролевую навигацию и read-only режимы;
  бюджетирование отображается как будущий раздел без удаления прототипа.
- Полный автоматизированный набор проверок: `89 passed`.
- Дополнительно выполнены проверка синтаксиса Python/JavaScript и ручная браузерная
  проверка экранов и вкладок ролей `admin`, `planning_editor` и `business_viewer`.

## 14. Открытые вопросы

Открытых вопросов, блокирующих реализацию, после согласования нет.
