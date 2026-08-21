# Развёртывание SberPI с внешней PostgreSQL

## Схема контура

- PostgreSQL устанавливается и сопровождается отдельно от Docker Compose приложения.
- Используется одна база данных для бизнес-данных и аудита.
- Снаружи открыты только TCP 80 и 443 на системном nginx.
- Контейнер frontend публикуется только на `127.0.0.1:18080`.
- Контейнер backend доступен только во внутренней Docker-сети.

## Комплект

- `docker-compose.prod.yml` — контейнеры backend и frontend без PostgreSQL;
- `.env.production.example` — шаблон параметров без секретов;
- `deploy/db/01_sberpi_schema.sql` — структура одной пустой базы;
- `deploy/nginx-host-production.conf.example` — HTTPS-конфигурация системного nginx.

Требования к серверу: Linux x86-64, Docker Engine и Docker Compose v2. Старый
`docker-compose 1.x` не поддерживается и несовместим с актуальными версиями Docker.

## 1. Подготовка базы

DBA создаёт пустую базу и прикладного пользователя, затем выполняет:

```bash
psql -v ON_ERROR_STOP=1 -d sberpi -f deploy/db/01_sberpi_schema.sql
```

Прикладному пользователю нужны подключения, `USAGE` на схему `public` и права
`SELECT`, `INSERT`, `UPDATE`, `DELETE` на таблицы. Изменение схемы для обычного запуска
API не требуется.

## 2. Настройки

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Обязательные значения:

- `DATABASE_URL` — выданная DBA строка подключения;
- `AUDIT_DATABASE_URL=` — оставить пустым, чтобы аудит использовал ту же базу;
- `CORS_ORIGINS=https://safe.pip.sigma-belpsb.by`;
- `SESSION_COOKIE_SECURE=true`;
- уникальный случайный `SESSION_SECRET`;
- временные пилотные пользователи без демонстрационных паролей.

Секреты нельзя добавлять в Git, архив с кодом или YAML.

## 3. Сборка и запуск

Если DBA уже применил SQL-скрипт:

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d api frontend
```

Для тестового контура, где владельцу приложения разрешено менять схему, миграции можно
применить отдельной одноразовой командой:

```bash
docker compose --profile tools -f docker-compose.prod.yml run --rm migrate
```

API-контейнер сам миграции при старте не выполняет.

## 4. HTTPS

Системный nginx использует сертификат домена и проксирует запросы на
`http://127.0.0.1:18080`. За основу берётся
`deploy/nginx-host-production.conf.example`. После указания путей к сертификату:

```bash
nginx -t
systemctl reload nginx
```

Закрытый ключ сертификата остаётся только на сервере.

## 5. Проверка

```bash
curl --fail https://safe.pip.sigma-belpsb.by/api/health
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 api frontend
```

Ожидаемый health-ответ: `{"status":"ok"}`. Дополнительно проверяются вход, открытие
интерфейса, запись события в `audit_events` и восстановление после перезапуска контейнеров.

## Обновление

Перед обновлением делается резервная копия внешней БД. Затем загружается новая версия
кода/образов, DBA применяет новый SQL изменения схемы либо запускается согласованная
миграционная команда, после чего контейнеры пересоздаются. Откат приложения выполняется
на предыдущий тег образов; откат схемы согласовывается с DBA отдельно.
