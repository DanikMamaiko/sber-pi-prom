# Развёртывание SberPI в Kubernetes

В репозитории подготовлены два production-образа, Helm chart и отдельный Job миграций. PostgreSQL в chart не входит: приложение подключается к внешней БД.

## Что нужно получить от администраторов

- URL Docker-репозитория Nexus и способ авторизации;
- имя `imagePullSecret` или разрешение создать его в namespace `sberpi`;
- hostname приложения, `ingressClassName` и имя TLS Secret;
- строку подключения к PostgreSQL и требования к SSL;
- подтверждение сетевого доступа из namespace `sberpi` к PostgreSQL;
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

Пароль внутри `DATABASE_URL` должен быть URL-кодирован. После заполнения создать Secret:

```powershell
kubectl -n sberpi create secret generic sberpi-secrets `
  --from-env-file=.\sberpi.secrets.env
```

Если Nexus требует авторизацию и готового pull secret нет:

```powershell
kubectl -n sberpi create secret docker-registry sberpi-nexus-pull `
  --docker-server=NEXUS_HOST `
  --docker-username=USERNAME `
  --docker-password=PASSWORD
```

Файл `sberpi.secrets.env` игнорируется Git. После создания Secret его следует удалить с диска по корпоративным правилам хранения секретов.

## 5. Настройка Helm

```powershell
Copy-Item .\deploy\helm\sberpi\values-corporate.example.yaml `
  .\deploy\helm\sberpi\values.local.yaml
```

В `values.local.yaml` заменить все `CHANGE_ME`:

- адреса двух образов в Nexus и их одинаковый тег;
- имя Nexus pull secret;
- hostname приложения;
- Ingress class и при необходимости TLS Secret;
- доверенные CIDR ingress-прокси, если их предоставили администраторы.

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

После успешного запуска проверить в браузере вход, чтение и изменение данных, а также появление записей в `audit_events`.

## Обновление и откат

Для обновления собрать новый тег, загрузить оба образа и заменить тег в `values.local.yaml`, затем повторить `helm upgrade --install`. Перед миграцией DBA должен сделать резервную копию БД.

Откат приложения:

```powershell
helm history sberpi -n sberpi
helm rollback sberpi REVISION -n sberpi --wait
```

Откат Helm не откатывает структуру БД автоматически. Изменение схемы и восстановление БД выполняются отдельно по согласованию с DBA.
