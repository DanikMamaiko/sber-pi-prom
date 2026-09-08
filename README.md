# SberPI PI Cycle MVP

Рабочая MVP-реализация раздела PI-цикла SberPI.

Стек:

- frontend: vanilla HTML, CSS, JavaScript;
- backend: Python, FastAPI;
- database: PostgreSQL.

В MVP реализованы локальная и LDAP/Active Directory авторизация, часовая `HttpOnly`
cookie-сессия, ролевая модель доступа и read-only импорт Epic из Jira SW IFT.

## Что входит в MVP

- PI-циклы по году и кварталу.
- Трайбы, команды и компетенции.
- Данные PI-цикла: дата старта, количество спринтов, ПИРы.
- Бэклог инициатив с загрузкой полей Jira по номеру Issue.
- Перенос инициатив в PI-цикл.
- Pre PI, цели, командные доски и Program Board как рабочие доменные сущности.
- Риски: общие и командные.
- Аудит всех пользовательских API-действий в той же PostgreSQL-базе с отдельной цепочкой миграций.

## Быстрый старт

```powershell
cd "C:\Users\User\Desktop\Сбер работа\sberpi-pi-cycle-mvp"
copy .env.example .env
docker compose up --build
```

После запуска:

- UI: http://localhost:8080
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- аудит безопасности хранится в той же PostgreSQL-базе и использует таблицу версий `audit_alembic_version`;

Тестовые пользователи по умолчанию:

| Логин | Пароль | Роль |
|---|---|---|
| `admin` | `admin123` | `admin` |
| `editor` | `editor123` | `planning_editor` |
| `po_itl` | `poitl123` | `planning_editor` |
| `pm` | `pm123` | `business_viewer` |
| `user` | `user123` | `viewer` |

Сессия истекает ровно через 60 минут от входа и не продлевается активностью. После
истечения приложение автоматически возвращает пользователя на экран входа. Перед
использованием вне локального контура обязательно замените `SESSION_SECRET`, а для HTTPS
установите `SESSION_COOKIE_SECURE=true`.

Для Jira SW IFT включите `JIRA_ENABLED=true`, задайте `JIRA_BASE_URL`, а
`JIRA_USERNAME` и `JIRA_PASSWORD` передайте через секрет контура. Запрос выполняет
только backend; учётные данные Jira не возвращаются браузеру. По умолчанию TLS
проверяется системным хранилищем, при необходимости можно указать корпоративный CA
через `JIRA_CA_BUNDLE`.

Авторизацию нельзя отключить через env. `AUTH_PROVIDER=local` читает тестовых
пользователей из `AUTH_TEST_USERS`. `AUTH_PROVIDER=ldap` проверяет пароль в Active
Directory и назначает роли по прямому членству в группах из `AD_GROUP_*`. Пользователь,
не состоящий ни в одной разрешённой группе, не получает доступ; fallback на локальные
учётные записи отсутствует.

UI обслуживается frontend-контейнером nginx на `:8080`. Backend на `:8000`
отдаёт только API/OpenAPI и не должен использоваться как точка входа в интерфейс.

## Тесты

Быстрые unit/schema-тесты:

```powershell
cd backend
python -m pytest -q tests/test_planning.py
```

Полный набор с интеграционными API-тестами на отдельном Postgres:

```powershell
cd "C:\Users\User\Desktop\Сбер работа\sberpi-pi-cycle-mvp"
docker compose -f docker-compose.test.yml up -d --wait
cd backend
$env:TEST_DATABASE_URL='postgresql+asyncpg://sberpi:sberpi@localhost:5433/sberpi_test'
python -m pytest -q
```

Полный набор включает unit-, архитектурные и интеграционные сценарии на PostgreSQL 16.
Отдельные сценарии проверяют optimistic locking PI-цикла и общего бэклога: устаревшая
версия получает 409 и не перезаписывает уже сохранённые данные.

Тестовый контур принимает только имя БД с суффиксом `_test`, применяет Alembic до `head`
и очищает бизнес-таблицы до и после каждого интеграционного сценария.

## Структура

```text
backend/
  app/
    api/        FastAPI routers
    core/       settings
    db/         database engine and base metadata
    models/     SQLAlchemy domain models
    schemas/    Pydantic DTOs
    services/   domain calculations
frontend/
  index.html
docs/
  audit.md
  architecture.md
  backlog-tab.md
  golden-standard-tab.md
  data-model.md
  regression.md
  compatibility-snapshot-removal.md
  optimistic-locking.md
  roadmap.md
```

Архитектурный шаблон для реализации следующих вкладок описан в
[`docs/golden-standard-tab.md`](docs/golden-standard-tab.md).
