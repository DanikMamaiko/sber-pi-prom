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
python deploy/scripts/init-local-env.py
docker compose up --build
```

После запуска:

- UI: http://localhost:8080
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- аудит безопасности хранится в той же PostgreSQL-базе и использует таблицу версий `audit_alembic_version`;

Генератор создаёт `.env` с уникальными случайными паролями и ключом сессии.
Существующий `.env` он не перезаписывает. Пароли смотрите в `AUTH_TEST_USERS`
своего локального файла; приведённые ниже значения — только placeholders.
Пользователей и паролей по умолчанию в приложении нет.

| Логин | Пароль | Роль |
|---|---|---|
| `admin` | `CHANGE_ME_ADMIN_PASSWORD` | `admin` |
| `editor` | `CHANGE_ME_EDITOR_PASSWORD` | `planning_editor` |
| `po_itl` | `CHANGE_ME_POITL_PASSWORD` | `planning_editor` |
| `pm` | `CHANGE_ME_PM_PASSWORD` | `business_viewer` |
| `user` | `CHANGE_ME_USER_PASSWORD` | `viewer` |

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

Быстрые unit/schema-тесты (без внешней БД):

```powershell
cd backend
python -m pytest -q tests --ignore=tests/integration
```

Полный набор с интеграционными API-тестами на отдельном Postgres:

```powershell
cd "C:\Users\User\Desktop\Сбер работа\sberpi-pi-cycle-mvp"
$env:POSTGRES_PASSWORD = python -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose -f docker-compose.test.yml up -d --wait
cd backend
$env:TEST_DATABASE_URL="postgresql+asyncpg://sberpi:$env:POSTGRES_PASSWORD@localhost:5433/sberpi_test"
python -m pytest -q
```

Без `TEST_DATABASE_URL` интеграционные тесты пропускаются с явной причиной.

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

## Настройки после исправлений безопасности

При обновлении существующего локального `.env` добавьте `POSTGRES_PASSWORD`, совпадающий
с паролем базы в `DATABASE_URL`, и явно задайте `AUTH_TEST_USERS` и `SESSION_SECRET`.
Изменение env не меняет пароль в уже созданном PostgreSQL volume: для такой базы пароль
нужно согласованно менять в PostgreSQL и настройках. Генератор рассчитан на новый запуск.
При ручном заполнении `.env.example` замените все `CHANGE_ME`; пароль в URL должен быть
URL-кодирован. Ключ сессии генерируйте случайно, рекомендуемая длина — не менее 32 символов.
Скрипт `backend/verify_regressions.py` требует `VERIFY_USERNAME` и `VERIFY_PASSWORD`;
он изменяет данные выбранного PI-цикла, поэтому предназначен для тестового контура.

Итоги исправлений и статусы замечаний: [SECURITY_FINDINGS_RESOLUTION.md](SECURITY_FINDINGS_RESOLUTION.md).
