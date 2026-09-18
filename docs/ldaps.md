# Подключение SberPI к LDAPS с корпоративным УЦ

Требуется обновлённый образ backend с поддержкой `LDAP_CA_BUNDLE` и обновлённый
Helm chart из этого репозитория. Изменение только values у старого образа
не включает проверку сертификата. Сертификат сервера с закрытым ключом уже должен
быть установлен на LDAP-сервере. SberPI получает только публичные сертификаты УЦ.

## 1. Подготовить ca.cer

Нужен PEM/Base64-файл с блоком `-----BEGIN CERTIFICATE-----`.
В Windows: открыть сертификат → «Состав» → «Копировать в файл» →
«X.509 в кодировке Base64 (.CER)». Расширение `.cer` можно оставить.
Для бинарного DER-файла альтернативно выполнить:

```powershell
openssl x509 -inform DER -in .\ca.cer -out .\ca.pem
```

В этом случае ниже использовать `ca.pem` вместо `ca.cer`. Если есть промежуточные
УЦ, не передаваемые сервером, включить их PEM-блоки в тот же файл.

## 2. Добавить сертификат в namespace SberPI

Если ConfigMap `sberpi-ldap-ca` с ключом `ca.pem` уже создан через Dashboard
в namespace приложения, этот шаг выполнен: повторно создавать его не нужно.

Без командной строки в Dashboard выбрать namespace SberPI, открыть создание
ресурса → Create from input и вставить YAML, заменив строку-заглушку содержимым
сертификата (сохранить четыре пробела перед каждой строкой PEM):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sberpi-ldap-ca
  namespace: sberpi
data:
  ca.pem: |
    -----BEGIN CERTIFICATE-----
    СТРОКИ_СЕРТИФИКАТА
    -----END CERTIFICATE-----
```

Ниже — альтернативный способ через kubectl.

Команды выполняются с рабочим kubeconfig для нужного кластера. Здесь namespace
и Helm-релиз называются `sberpi`; заменить, если у вашей установки другие имена.

```powershell
kubectl -n sberpi create configmap sberpi-ldap-ca --from-file=ca.pem=.\ca.cer --dry-run=client -o yaml | kubectl apply -f -
```

Ключ в ConfigMap — `ca.pem`, независимо от имени исходного файла. Chart монтирует
его в API-контейнер как `/etc/sberpi/ldap/ca.pem` только для чтения.
Установка сертификата в Windows на рабочем компьютере не меняет доверие контейнера.

## 3. Обновить существующий values.local.yaml

Добавить или заменить поля в существующих секциях; не создавать второй `config:`.
Файлы `values.yaml` и `values-corporate.example.yaml` не изменены: эти настройки
нужно внести вручную в используемый при развёртывании values-файл.

```yaml
ldapTls:
  caConfigMapName: sberpi-ldap-ca

config:
  authProvider: ldap
  ldapUrl: "ldaps://CHANGE_ME_LDAP_FQDN:636"
  ldapUseTls: "true"
  ldapCaBundle: /etc/sberpi/ldap/ca.pem
```

`CHANGE_ME_LDAP_FQDN` заменить DNS-именем из SAN сертификата LDAP-сервера.
Использовать `sigma-belpsb.by` можно только если именно это имя присутствует
в сертификате сервера. Поисковая база, фильтры, группы и bind-учётная запись
остаются прежними. Пароль хранится в существующем Secret `sberpi-secrets`.

При включённом NetworkPolicy в существующем правиле LDAP в
`networkPolicy.apiExtraEgress` заменить порт 389 на 636, сохранив согласованный
CIDR назначения. Межсетевой экран также должен разрешать TCP 636 от backend.

Backend проверяет цепочку доверия, срок действия и имя сервера. При пустом
`ldapCaBundle` LDAPS использует системные УЦ контейнера с обязательной проверкой.
`ldapUseTls` означает прямой LDAPS, а не StartTLS. Комбинация `ldap://` и
`ldapUseTls: "true"` отклоняется. Автоматические LDAP referrals отключены,
чтобы bind-пароли не пересылались по перенаправлению на другой, в том числе
незашифрованный, адрес. Поиск должен выполняться на сервере нужного домена.

## 4. Собрать и развернуть обновление

Собрать backend из текущего кода, загрузить в Nexus с новым неизменяемым тегом
по [основной инструкции](../KUBERNETES.md), затем изменить `api.image.tag` и
`api.image.digest` в локальном values. Если задан digest, именно он определяет
образ: изменение одного тега недостаточно. Новый frontend для LDAPS не требуется.

```powershell
helm lint .\deploy\helm\sberpi -f .\deploy\helm\sberpi\values.local.yaml
helm upgrade --install sberpi .\deploy\helm\sberpi --namespace sberpi --wait --timeout 10m -f .\deploy\helm\sberpi\values.local.yaml
kubectl -n sberpi rollout status deployment/sberpi-api
```

У Helm-релиза остаётся обычный Job миграций. Если схемой управляет DBA,
сохранить существующий `migrations.enabled: false`.

## 5. Проверить TLS из backend

Проверка выполняет TLS handshake с проверкой CA и имени, без LDAP-логина и пароля:

```powershell
@'
import os
import socket
import ssl
from urllib.parse import urlsplit

url = urlsplit(os.environ["LDAP_URL"])
context = ssl.create_default_context(cafile=os.environ["LDAP_CA_BUNDLE"] or None)
with socket.create_connection((url.hostname, url.port or 636), timeout=5) as raw:
    with context.wrap_socket(raw, server_hostname=url.hostname) as connection:
        print("TLS OK", connection.version())
'@ | kubectl -n sberpi exec -i deployment/sberpi-api -- python -
```

После `TLS OK` проверить вход корпоративным пользователем в SberPI: успешный
handshake сам по себе не подтверждает bind, поиск пользователя и его группы.

Типовые ошибки:

- `CERTIFICATE_VERIFY_FAILED` / unknown issuer: не тот УЦ или неполная цепочка.
- Hostname mismatch: имя в `ldapUrl` не соответствует сертификату сервера.
- Timeout / connection refused: DNS, маршрут, NetworkPolicy, firewall или LDAPS.
- Ошибка загрузки `LDAP_CA_BUNDLE`: нет файла, нет доступа или файл в DER вместо PEM.

При замене только содержимого внешнего ConfigMap повторить команду из шага 2,
затем выполнить `kubectl -n sberpi rollout restart deployment/sberpi-api` и
`kubectl -n sberpi rollout status deployment/sberpi-api`. Содержимое внешнего
ConfigMap не входит в Helm checksum, поэтому само по себе не запускает rollout.
