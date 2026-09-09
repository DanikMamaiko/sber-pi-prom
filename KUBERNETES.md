# Развёртывание SberPI в Kubernetes

В репозитории подготовлены два production-образа, Helm chart и отдельный Job миграций. PostgreSQL в chart не входит: приложение подключается к внешней БД.

## Что нужно получить от администраторов

- URL Docker-репозитория Nexus и способ авторизации;
- имя `imagePullSecret` или разрешение создать его в namespace `sberpi`;
- hostname приложения, `ingressClassName` и имя TLS Secret;
- строку подключения к PostgreSQL и требования к SSL;
- подтверждение сетевого доступа из namespace `sberpi` к PostgreSQL;
- подтверждение DNS и сетевого доступа из namespace `sberpi` к `sigma-belpsb.by:389`;
- решение по миграциям: их запускает Helm или DBA применяет `deploy/db/01_sberpi_schema.sql`;
- лимиты CPU/RAM, если предложенные значения не подходят политике кластера.

## 1. Сборка на личном ноутбуке

Docker Desktop должен работать в режиме Linux containers. Версия релиза должна быть неизменяемой, например `0.1.0`, а не `latest`.

```powershell
Set-Location "C:\path\to\sberpi-pi-cycle-mvp"
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\build-images.ps1 -Version 0.1.0
```

Скрипт собирает `linux/amd64` образы и создаёт:

- `artifacts/sberpi-api-0.1.0.tar`;
- `artifacts/sberpi-frontend-0.1.0.tar`;
- `artifacts/SHA256SUMS-0.1.0.txt`.

На рабочий компьютер нужно перенести весь репозиторий либо минимум папки `deploy/helm`, `deploy/scripts`, два TAR-файла и файл контрольных сумм.

## 2. Загрузка образов в Nexus на рабочем компьютере

Сначала проверить контрольные суммы и выполнить вход в Nexus:

```powershell
Get-FileHash -Algorithm SHA256 .\artifacts\*.tar
docker login NEXUS_HOST
```

Затем загрузить и опубликовать образы:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\import-and-push-images.ps1 `
  -Version 0.1.0 `
  -NexusRepository NEXUS_HOST/REPOSITORY/sberpi
```

Перед `docker load` скрипт автоматически сверяет оба TAR-файла с `SHA256SUMS-0.1.0.txt` и останавливается при несовпадении.

## 3. Проверка доступа к кластеру

Файл `config.yaml` является kubeconfig и не должен попадать в Git или архив с исходным кодом.

```powershell
$env:KUBECONFIG = (Resolve-Path .\config.yaml).Path
kubectl config current-context
kubectl get namespace sberpi
kubectl auth can-i create deployments -n sberpi
kubectl auth can-i create jobs -n sberpi
kubectl auth can-i create ingresses -n sberpi
```

## 4. Секреты Kubernetes

Если администратор не создаёт Secret централизованно, сделать локальный файл из шаблона и заполнить его реальными значениями:

```powershell
Copy-Item .\deploy\k8s\sberpi-secrets.example.env .\sberpi.secrets.env
```

Пароль внутри `DATABASE_URL` должен быть URL-кодирован. Для ИФТ также заполнить
`LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, `JIRA_USERNAME` и `JIRA_PASSWORD`. После
заполнения создать Secret:

```powershell
kubectl -n sberpi create secret generic sberpi-secrets `
  --from-env-file=.\sberpi.secrets.env
```

Если Nexus требует авторизацию и готового pull secret нет:

```powershell
kubectl -n sberpi create secret docker-registry sberpi-nexus-pull `
  --docker-server=NEXUS_HOST `
  --docker-username=USERNAME `
  --docker-password="$env:NEXUS_PASSWORD"
```

Файл `sberpi.secrets.env` игнорируется Git. После создания Secret его следует удалить с диска по корпоративным правилам хранения секретов.

## 5. Настройка Helm

```powershell
Copy-Item .\deploy\helm\sberpi\values-corporate.example.yaml `
  .\deploy\helm\sberpi\values.local.yaml
```

В `values.local.yaml` заменить все `CHANGE_ME`:

- адреса двух образов в Nexus и реальные SHA256 digest опубликованных образов;
- разрешённые CIDR PostgreSQL, LDAP, Jira, labels ingress-контроллера и параметры DNS;
- имя Nexus pull secret;
- hostname приложения;
- Ingress class и при необходимости TLS Secret;
- доверенные CIDR ingress-прокси, если их предоставили администраторы.
- `config.jiraEnabled=true`, IFT URL и параметры проверки TLS Jira.
- `config.authProvider=ldap`; LDAP URL, база поиска и четыре DN ролевых групп уже
  заданы по параметрам ИФТ и при необходимости переопределяются в локальном values-файле.

Рабочие параметры поиска пользователей в домене Sigma:

```yaml
config:
  ldapUrl: ldap://sigma-belpsb.by:389
  ldapUserSearchBase: DC=sigma-belpsb,DC=by
  ldapUserFilter: "(sAMAccountName={username})"
  ldapUseTls: "false"
```

При входе используется короткий корпоративный логин без домена. Поиск выполняется
от корня домена во вложенных подразделениях. Старый путь `OU=Users ALL` в этом
контуре возвращал `32 noSuchObject`; с рабочей базой поиск и вход подтверждены.
Роль редактора должна быть связана с `SberPI-PlanningEditors`, роль бизнес-просмотра —
с `SberPI-BusinessViewers`. Полные DN четырёх групп заданы в `values.yaml`.

Применение изменений ConfigMap через текущий Helm chart автоматически обновляет
backend-поды. После изменения только внешнего Secret нужен перезапуск backend.
Исправления кода LDAP требуют сборки и развёртывания нового образа backend.

Проверка перед установкой:

```powershell
helm lint .\deploy\helm\sberpi `
  -f .\deploy\helm\sberpi\values.local.yaml

helm template sberpi .\deploy\helm\sberpi `
  --namespace sberpi `
  -f .\deploy\helm\sberpi\values.local.yaml | kubectl apply --dry-run=server -f -
```

## 6. Установка

```powershell
helm upgrade --install sberpi .\deploy\helm\sberpi `
  --namespace sberpi `
  --wait `
  --timeout 10m `
  -f .\deploy\helm\sberpi\values.local.yaml
```

Перед установкой и обновлением Helm запускает одноразовый Job, который сначала применяет audit-миграции, затем основные. Если DBA управляет схемой сам, установить `migrations.enabled: false` в `values.local.yaml`.

## 7. Проверка и диагностика

```powershell
kubectl -n sberpi get pods,svc,ingress
kubectl -n sberpi rollout status deployment/sberpi-api
kubectl -n sberpi rollout status deployment/sberpi-frontend
kubectl -n sberpi logs deployment/sberpi-api --tail=100
kubectl -n sberpi logs deployment/sberpi-frontend --tail=100
```

Если миграция завершилась ошибкой, Helm сохранит неуспешный Job для чтения логов:

```powershell
kubectl -n sberpi get jobs
kubectl -n sberpi logs job/sberpi-migrate
```

После успешного запуска проверить вход доменными пользователями из каждой из четырёх
групп, отказ пользователю вне этих групп, чтение и изменение данных, а также появление
записей в `audit_events`.

## Обновление и откат

Для обновления собрать новый тег, загрузить оба образа и заменить тег в `values.local.yaml`, затем повторить `helm upgrade --install`. Перед миграцией DBA должен сделать резервную копию БД.

Откат приложения:

```powershell
helm history sberpi -n sberpi
helm rollback sberpi REVISION -n sberpi --wait
```

Откат Helm не откатывает структуру БД автоматически. Изменение схемы и восстановление БД выполняются отдельно по согласованию с DBA.

## Дополнительные настройки безопасности

`api.image.digest` и `frontend.image.digest` имеют приоритет над тегом; API и миграции
используют один образ. Возьмите digest из Nexus после публикации (контрольная сумма TAR
не является digest образа). Невалидный digest блокирует Helm render. `pullPolicy: Always`
установлен по умолчанию и в корпоративном примере; другое значение — по политике платформы.
Все namespaced ресурсы получают `metadata.namespace` из `--namespace`.

По умолчанию `secrets.mode: files`: существующий Secret монтируется только для чтения
в `/run/secrets/sberpi` с правами `0440` и группой `10001`; API и Alembic читают его через
`SBERPI_SECRETS_DIR`. Имена ключей Secret не меняются. Значения файлов имеют приоритет
над env и `.env`. Настройки кэшируются при запуске: после ротации секрета перезапустите API
и используйте новый Job миграций. Для совместимости доступно `secrets.mode: env`,
которое возвращает `envFrom.secretRef` и повторно открывает соответствующие замечания.

`networkPolicy.enabled` выключен в базовых values для совместимости и включён в
корпоративном примере. Перед включением заполните все peers и подтвердите поддержку
NetworkPolicy вашим CNI. Шаблон требует хотя бы одного назначения PostgreSQL. Пустой
`ingressPeers` запрещает вход во frontend; пустой `apiExtraEgress` не разрешает LDAP/Jira.
Frontend принимает HTTP от разрешённых ingress peers, API — от frontend этого release.
API и миграции могут обращаться к заданной PostgreSQL; API дополнительно — к явно
разрешённым LDAP/Jira. Укажите отдельную аудит-БД в database.peers, если она используется
(при другом порте добавьте отдельное правило в шаблон/согласуйте values перед установкой).
DNS разрешён по UDP/TCP 53 к указанным dnsPeers; для NodeLocal DNS нужны peers вашей платформы.
Не используйте `0.0.0.0/0` вместо конкретных назначений. Kubernetes policies складываются:
существующее широкое разрешающее правило может ослабить эти ограничения.

Политика migration создаётся Helm hook с весом -10 до Job с весом -5. Она сохраняется
после Job, чтобы не снять ограничения во время миграции. Helm не удаляет hook-ресурсы
при uninstall автоматически: после удаления release или отключения политик удалите
`<release-fullname>-migration` NetworkPolicy вручную, когда миграции уже не работают.

Frontend, backend и миграции используют UID/GID 10001 и в Docker, и в Helm.
Frontend использует конфигурацию nginx-unprivileged с PID и временными файлами в `/tmp`;
образ запускает nginx напрямую без изменения конфигурации entrypoint-скриптами.
В Helm root filesystem доступна только для чтения, временные каталоги монтируются отдельно,
повышение привилегий запрещено, capabilities сняты.

Справка: [наследование NGINX headers](https://nginx.org/en/docs/http/ngx_http_headers_module.html),
[ограничения и поведение NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/).
