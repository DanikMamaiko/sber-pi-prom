# SberPI → QRadar: настройка syslog для Sigma

По информации владельца приложение уже развёрнуто на ИФТ Sigma:
https://sberpi.apps.k8s-ift.sigma-belpsb.by. По предоставленным скриншотам используются
Kubernetes, Helm values и Secret `sberpi-secrets`. ЦКБ подтвердил UDP/514 и предоставил
владельцу IP коллектора. Закрытый контур отсюда не проверялся, сам IP в репозитории не задан.

## Kubernetes: прямая отправка UDP/514

Для этой установки добавлена прямая отправка из API-pod: API → UDP syslog → QRadar.
Это альтернативный режим тому, который описан ниже для Linux-хоста с rsyslog.
В Kubernetes не требуются rsyslog sidecar, отдельный образ агента или том с журналом.
Аудит в PostgreSQL сохраняется независимо от отправки. `SIEM_AUDIT_LOG_PATH` оставьте
пустым: файловый режим и прямой UDP взаимоисключающие, чтобы не создавать дубликаты.

1. Собрать новый образ backend и опубликовать его в корпоративном registry обычным
   порядком. Указать новый tag/digest в конфигурации релиза. Если задан digest,
   обновить его: одно изменение tag не заменяет закреплённый digest.
2. Перенести в используемый pipeline/репозиторий chart изменения:
   `deploy/helm/sberpi/templates/configmap.yaml`, `templates/networkpolicy.yaml`
   и новые значения из `values.yaml`. Только перенос Python-кода или добавление
   полей в values при старом ConfigMap не включает отправку.
3. В существующий раздел `config:` корпоративного **`ift/values.yaml`** добавить:

   ```yaml
   config:
     auditEnabled: "true"
     siemSyslogEnabled: "true"
     siemSyslogTarget: "ВСТАВИТЬ_IP_КОЛЛЕКТОРА"
     siemSyslogPort: "514"
     siemSyslogProtocol: "udp"
     siemSyslogHostname: "sberpi-sigma"
   ```

   Не создавать второй `config:` и не заменять остальные его параметры. В `target`
   нужен только числовой IPv4/IPv6, без `http://`, порта и CIDR. Поля не являются
   паролями: они идут в ConfigMap, добавлять их в `sberpi-secrets` не нужно.

   | Helm values (`config.*`) | Переменная приложения |
   | --- | --- |
   | `siemSyslogEnabled` | `SIEM_SYSLOG_ENABLED` |
   | `siemSyslogTarget` | `SIEM_SYSLOG_TARGET` |
   | `siemSyslogPort` | `SIEM_SYSLOG_PORT` |
   | `siemSyslogProtocol` | `SIEM_SYSLOG_PROTOCOL` |
   | `siemSyslogHostname` | `SIEM_SYSLOG_HOSTNAME` |

4. Выполнить обычный Helm/GitOps deploy вашего контура. Обновлённый локальный chart
   меняет checksum ConfigMap и пересоздаёт API-pod. Для другого корпоративного chart
   проверить, что pod действительно перезапущен: переменные окружения уже запущенного
   процесса сами не обновляются. Миграции БД для SIEM-доработки не нужны.
5. Проверить в ConfigMap и окружении API-pod значения `SIEM_SYSLOG_*`, новый образ,
   готовность pod и `/api/health`. Пример для стандартного имени deployment:

   ```bash
   kubectl -n sberpi rollout status deployment/sberpi-api
   kubectl -n sberpi exec deployment/sberpi-api -c api -- python -c 'import os; print({k: os.getenv(k) for k in ("SIEM_SYSLOG_ENABLED", "SIEM_SYSLOG_TARGET", "SIEM_SYSLOG_PORT", "SIEM_SYSLOG_PROTOCOL", "SIEM_SYSLOG_HOSTNAME")})'
   kubectl -n sberpi logs deployment/sberpi-api -c api --since=10m
   ```

   Имя deployment/контейнера заменить фактическим, если ваш chart использует другое.
   Не выводить весь env: он может содержать секреты. Ошибки локальной отправки
   отмечаются `siem_audit_write_failed` и `siem_audit_fallback` с JSON события.
6. Выполнить успешный и неуспешный вход тестовой учётной записью, записать время.
   Пугач/Оскирко подтверждают приём и разбор событий в QRadar; Олег Володько проверяет
   сетевой путь, правила фаервола и фактический IP исходящего трафика после NAT.
   Адрес Ingress приложения не определяет этот исходящий IP.

Если `networkPolicy.enabled=true`, обновлённый шаблон автоматически добавляет
исходящее правило API-pod на IP коллектора (/32 для IPv4, /128 для IPv6) и UDP-порт.
Существующие правила БД/LDAP/Jira сохраняются. Это не открывает корпоративный фаервол
и не изменяет внешние политики кластера. Если сеть управляется отдельным chart или
администратором, соответствующее правило нужно добавить там.

Можно сначала развернуть и затем провести совместную проверку. Прямой UDP не имеет
подтверждения доставки, очереди и автоматического повтора: при блокировке фаерволом
приложение может не увидеть ошибку, а события не появятся позже сами. Проверка
`/api/health` и отсутствие ошибок отправки не доказывают получение в QRadar.
В БД сохраняется аудит для сверки. Отключение отправки: `siemSyslogEnabled: "false"`
с последующим deploy. Не отключать `auditEnabled`, чтобы сохранить аудит в БД.

Прямая отправка поддерживает **только UDP**; значение TCP отклоняется при старте.
Сокет неблокирующий, IP валидируется без DNS/проверки доступности. Отправка не ждёт
ответа коллектора; ошибка/переполнение локального буфера приводит к fallback.
Формат JSON одинаков с файловым режимом, syslog-заголовок
содержит время самого события. UDP-датаграмма без завершающих NUL/LF. Для длинных
событий проверить отсутствие сетевой фрагментации/усечения и лимит приёмника.

## Анализ и реализация

В приложении уже есть аудит входов, выходов, чтения/изменения данных, отказов доступа
и ошибок API. Ранее обычные события записывались только в PostgreSQL `audit_events`;
в журнал backend попадал лишь fallback при ошибке БД. Поэтому простой пересылки
существующего stdout недостаточно.

Для альтернативного Linux-хоста с production Docker Compose из `DEPLOY.md` подготовлена схема:

```text
                         ┌→ PostgreSQL audit_events
API → событие аудита ─────┤
                         └→ /var/log/sberpi/audit.jsonl на хосте
                            → rsyslog imfile → очередь → TCP или UDP → QRadar
```

API пишет JSON в локальный файл в рабочем потоке; сеть обслуживает rsyslog хоста.
Записи в файл и БД независимы: ошибка одного приёмника не отключает второй и не
меняет результат бизнес-операции. Новые миграции БД и Python-зависимости не нужны.
Экспорт по умолчанию выключен (`SIEM_AUDIT_LOG_PATH` пустой).

Это прикладной аудит. Журналы ОС, nginx, PostgreSQL и всего stdout не пересылаются.
Файловая схема требует постоянного каталога и rsyslog. Compose-шаблон применим
к отдельному Linux-хосту. Для текущей установки Kubernetes использовать прямой UDP
и параметры Helm из начала этой инструкции.

В репозитории подготовлены код, Helm, Compose override, rsyslog и logrotate. Установка
на сервер Sigma и проверка с настоящим QRadar ещё не выполнены.

## Что требуется для подключения

1. Использовать IP коллектора Sigma, который ЦКБ предоставил владельцу, и UDP/514.
   Адрес Альфы из переписки не подходит как основание для настройки Sigma.
2. Определить исходящий IP отправителя, видимый коллектору после возможного NAT.
   Сообщить ЦКБ этот адрес, идентификатор `sberpi-sigma` и примеры JSON.
   `source_ip` в JSON обозначает пользователя, а не адрес syslog-отправителя.
3. Обеспечить исходящий сетевой доступ с отправителя на выданный IP:порт по согласованному
   протоколу. Входящий syslog-порт на сервере приложения не требуется.
4. Установить доработку API и включить UDP через Helm; для файлового режима вместо
   этого настроить rsyslog и ротацию.
5. ЦКБ создаёт Log Source и настраивает разбор JSON/DSM, сопоставление типов событий.
   Приём произвольного JSON не означает автоматической нормализации его полей.
6. Вместе проверить успех/ошибку входа, выход, отказ доступа и прикладную операцию:
   правильный Log Source, пользователь, IP, время, результат и причина ошибки.

## Формат сообщений

- Syslog RFC 5424; HOSTNAME=`sberpi-sigma` (предлагаемый Log Source Identifier),
  APP-NAME=`sberpi.audit`, facility=`local6`, severity=`info` для всех событий.
  Тип/результат ошибки определяются из JSON, а не severity.
- TCP: сообщения разделены LF, без NUL. UDP: отдельная датаграмма на сообщение.
- JSON: `service="SberPI API"`, `logger="sberpi.audit"`, по умолчанию
  `source_service="sberpi-api"`.
- `timestamp` — время события UTC; время заголовка — время чтения агентом.
- `event_id` совпадает с записью в БД, `request_id` возвращается API в `X-Request-ID`.
- `event_category`: `authentication`, `authorization` для отказа 403 или `application`.
- Вход: `login_success`/`login_failure`, выход: `logout_success`, проверка сессии:
  `session_check_success`/`session_check_failure`, отказ доступа: `access_denied`.
  Прикладные события: например `pi_cycle_read_success`, `initiative_update_failure`.
- `path` — шаблон маршрута. Тела запросов, значения query, пароли, cookie,
  токены и хеш сессии не экспортируются. User-Agent ограничен 512 символами,
  имя пользователя — 256. Переводы строк экранируются JSON-сериализатором.

Сокращённые примеры JSON-содержимого (пользователь и адрес вымышлены):

```json
{"service":"SberPI API","event_category":"authentication","event_type":"login_success","outcome":"success","source_ip":"192.0.2.10","method":"POST","user_agent":"Mozilla/5.0","username":"test.user","timestamp":"2026-09-18T10:00:00Z","status_code":200}
{"service":"SberPI API","event_category":"authentication","event_type":"login_failure","outcome":"failure","source_ip":"192.0.2.10","method":"POST","user_agent":"Mozilla/5.0","username":"test.user","timestamp":"2026-09-18T10:01:00Z","status_code":401,"error_code":"invalid_credentials"}
```

В полном JSON также есть `logger`, `description`, `path`, `event_id`, `request_id`,
`source_service`, `environment`, `host_name`, `host_ip`, `action`, `object_type`,
`object_id`, `duration_ms`, `error_code` (null при отсутствии).
Сетевое сообщение начинается с `<182>1 <время-rsyslog> sberpi-sigma sberpi.audit - - - {…}`.
Нескольким независимым установкам нужны собственные стабильные HOSTNAME.

## Включение на Linux-хосте

Команды выполняются администратором в каталоге проекта. Требуются rsyslog 8.x с
модулем imfile и logrotate. Не заменяйте глобальную конфигурацию rsyslog целиком.

1. Подготовить постоянный каталог для UID/GID контейнера 10001:

   ```bash
   sudo install -d -o 10001 -g 10001 -m 0750 /var/log/sberpi
   ```

   rsyslog должен читать каталог/файлы. Для процесса от root дополнительные права
   не нужны; иначе предоставить доступ через группу 10001 или ACL, включая файлы
   после ротации. На SELinux-хосте согласовать метки для контейнера и rsyslog.

2. Сохранить `AUDIT_ENABLED=true` в `.env.production`. При необходимости указать
   `AUDIT_HOST_IP` (иначе JSON содержит IP контейнера). Проверить реальные адреса
   пользователей в `source_ip`: согласовать доверие к forwarded-заголовкам между
   nginx, Uvicorn и `AUDIT_TRUSTED_PROXY_NETWORKS`; API доступен только доверенному
   прокси. `APP_ENV` обозначает среду, например `production`, а Sigma — контур.

3. Собрать/пересоздать API с дополнительным Compose-файлом:

   ```bash
   docker compose -f docker-compose.prod.yml -f docker-compose.siem.yml build api
   docker compose -f docker-compose.prod.yml -f docker-compose.siem.yml up -d api
   ```

   Override задаёт `SIEM_AUDIT_LOG_PATH=/var/log/sberpi/audit.jsonl` и bind mount.
   Использовать оба `-f` при последующих обновлениях и пересозданиях API!
   При недоступном каталоге настроенного журнала API не стартует.
   Для запуска без Docker задать этот параметр окружением и предоставить каталог
   пользователю службы API.

4. Подготовить постоянный `/var/spool/rsyslog-sberpi` с правами 0700, владельцем —
   фактическим пользователем rsyslog и свободным местом для очереди 1 GiB.
   Проверить существующий `global(workDirectory=...)`: он должен быть постоянным
   и доступным rsyslog для записи позиций imfile. В основной конфигурации установить
   `global(maxMessageSize="64k")`, учитывая уже существующие глобальные параметры.
   Проверить, что лимит сообщения в QRadar покрывает реальные события.

5. Скопировать `deploy/rsyslog/60-sberpi-qradar.conf.example` в
   `/etc/rsyslog.d/60-sberpi-qradar.conf`. Заменить **все три** `CHANGE_ME_...`:
   IP, порт, транспорт (`tcp` или `udp`). `TCP_Framing` игнорируется для UDP.
   Если imfile уже загружен, убрать повторный `module(load="imfile")`.

   ```bash
   sudo rsyslogd -N1
   sudo systemctl restart rsyslog
   sudo systemctl status rsyslog --no-pager
   ```

   Шаблон использует обычный TCP/UDP, без TLS. TLS-слушатель требует иной настройки.

6. Скопировать `deploy/rsyslog/sberpi.logrotate` в `/etc/logrotate.d/sberpi`
   (владелец root, права 0644). Проверить:

   ```bash
   sudo logrotate -d /etc/logrotate.d/sberpi
   ```

   Ротация через rename/create, без copytruncate: API открывает файл при каждой записи.
   Хранятся 14 архивов; срок зависит от частоты ротации. `maxsize` проверяется только
   при запуске logrotate, это не жёсткая квота. При большом потоке увеличить частоту
   запуска/выделить отдельный раздел; права должны сохранять доступ для rsyslog.

## Проверка и ограничения доставки

После тестовых действий проверить `sudo tail -n 10 /var/log/sberpi/audit.jsonl`
и `sudo journalctl -u rsyslog --since '-10 minutes' --no-pager`.
Подтвердить приём и разбор событий в Log Source `sberpi-sigma` у ЦКБ.
Проверка открытого порта не заменяет эту проверку; для UDP особенно нельзя считать
успешный вызов send доказательством доставки.

Очередь rsyslog дисковая, ограничена 1 GiB. TCP позволяет повторять попытки при
обнаруженных ошибках подключения, но не даёт прикладного подтверждения сохранения
в QRadar; потери при разрыве и дубли при восстановлении возможны. UDP не подтверждает
получение вообще: агент может успешно отправить датаграмму недоступному коллектору
и удалить её из очереди. Дисковая очередь не устраняет потери UDP, фрагментацию
и сетевые ограничения размера датаграмм. Если допустимы оба транспорта, TCP
предпочтительнее для аудита. Для UDP отдельно проверить самые длинные реальные события.

Контролировать свободный диск, очередь, состояние imfile и `siem_audit_write_failed`.
При ошибке записи файла событие выдаётся в stderr как `siem_audit_fallback`, БД
по-прежнему вызывается. Этот fallback не читается приведённой конфигурацией imfile,
его восстановление ручное. Дедупликация/сверка — по `event_id`.
Локальный файл закрывается после записи, но fsync на каждое событие не выполняется;
сбой питания может потерять последние записи. БД остаётся источником для сверки,
автоматический replay из БД не реализован. При переполнении очереди возможны потери.
Не оставлять rsyslog выключенным во время ротации: хвост старого файла может быть пропущен.

Проверку отказа/восстановления TCP выполнить на тестовом приёмнике или в согласованном
окне: накопить события при недоступности коллектора, восстановить доступ, сравнить ID.
Для UDP проверять получение на стороне коллектора и учитывать отсутствие повторной
доставки при необнаруженной потере.

Основание для настроек: [rsyslog imfile](https://docs.rsyslog.com/doc/configuration/modules/imfile.html),
[очереди пересылки](https://docs.rsyslog.com/doc/tutorials/reliable_forwarding.html),
[omfwd и TCP framing](https://docs.rsyslog.com/doc/configuration/modules/omfwd.html).
