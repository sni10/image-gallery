# production-deployment Specification

## Purpose
Продакшен-развёртывание: на каких адресах и по какому протоколу доступны сайт, API и админка, как Django ведёт себя за HTTPS-прокси, как собирается и выкатывается образ приложения.

## Requirements

### Requirement: HTTPS на всех адресах
Сервис SHALL быть доступен только по HTTPS с действительным сертификатом на `artai.win`, `www.artai.win`, `api.artai.win` и `secure.artai.win`. Запросы по HTTP MUST перенаправляться на HTTPS.

#### Scenario: HTTP-запрос
- **WHEN** клиент открывает `http://api.artai.win/galleries`
- **THEN** ответ — перенаправление на `https://api.artai.win/galleries`

#### Scenario: Сертификат
- **WHEN** клиент подключается к любому из четырёх адресов по HTTPS
- **THEN** сертификат действителен для этого имени и проверяется без ошибок

### Requirement: Назначение адресов
`artai.win` SHALL отдавать фронтенд (SPA: неизвестные пути отдают `index.html`). `www.artai.win` MUST постоянно (301/308) перенаправлять на тот же путь на `artai.win`. `api.artai.win` SHALL отдавать API, `/media/` и OpenAPI-документацию; путь `/admin/` на нём MUST отвечать `404`. `secure.artai.win` SHALL отдавать админку вместе с её статикой и превью из `/media/`.

#### Scenario: www
- **WHEN** клиент открывает `https://www.artai.win/galleries/abc`
- **THEN** ответ — постоянный редирект на `https://artai.win/galleries/abc`

#### Scenario: Админка только на secure
- **WHEN** клиент открывает `https://api.artai.win/admin/`
- **THEN** ответ `404`
- **WHEN** клиент открывает `https://secure.artai.win/admin/`
- **THEN** открывается страница входа в админку со стилями

### Requirement: Django за HTTPS-прокси
Абсолютные ссылки, которые строит API (`url`, `thumbUrl`), SHALL начинаться с `https://`, когда запрос пришёл по HTTPS через прокси. При `DJANGO_DEBUG=false` cookie сессии и CSRF MUST помечаться `Secure`. Вход в админку на `secure.artai.win` по HTTPS MUST проходить проверку CSRF.

#### Scenario: Ссылки на картинки
- **WHEN** клиент запрашивает `https://api.artai.win/galleries/{id}/photos`
- **THEN** все `url` и `thumbUrl` начинаются с `https://api.artai.win/media/`

#### Scenario: Вход в админку
- **WHEN** суперпользователь входит в `https://secure.artai.win/admin/`
- **THEN** вход проходит, cookie сессии имеет флаг `Secure`

### Requirement: Сборка и публикация образа
Каждый пуш в ветку `main` SHALL запускать тесты на PostgreSQL; только при их успехе образ приложения MUST собираться и публиковаться в `ghcr.io/sni10/image-gallery` с тегом, равным полному SHA коммита. Тег `latest` для деплоя MUST NOT использоваться.

#### Scenario: Успешный пуш
- **WHEN** в `main` пушится коммит с проходящими тестами
- **THEN** в GHCR появляется образ `ghcr.io/sni10/image-gallery:<sha>`

#### Scenario: Упавшие тесты
- **WHEN** тесты коммита падают
- **THEN** образ для этого коммита не публикуется

### Requirement: Семантическое версионирование и формат коммитов
Сообщения коммитов SHALL следовать Conventional Commits. На пуш и pull request в `main` сообщения коммитов MUST проверяться, нарушение MUST останавливать CI. На пуш в `main` после успешных проверок SHALL автоматически определяться следующая версия по коммитам с прошлого релиза: `fix`/`perf` — patch, `feat` — minor, изменение с `!` или `BREAKING CHANGE` — major (пока версия `0.x` — minor). При новой версии MUST создаваться тег `vX.Y.Z` и GitHub Release, а образ MUST дополнительно получать тег `vX.Y.Z`. Коммиты без значимых типов (`docs`, `chore`, `ci`, …) релиз MUST NOT выпускать. Версия MUST NOT записываться коммитом обратно в `main`.

#### Scenario: Новая функция
- **WHEN** в `main` пушится `feat(api): …` при последнем релизе `v0.1.0`
- **THEN** создаются тег `v0.2.0`, GitHub Release и образ `ghcr.io/sni10/image-gallery:v0.2.0` рядом с тегом по SHA

#### Scenario: Только документация
- **WHEN** в `main` пушится `docs: …`
- **THEN** новый тег не создаётся, образ публикуется только с тегом SHA

#### Scenario: Неверное сообщение коммита
- **WHEN** в pull request в `main` есть коммит `added stuff`
- **THEN** проверка коммитов падает, CI красный

### Requirement: Деплой и откат по SHA
Сервер SHALL запускать образ, указанный явным SHA коммита. Деплой MUST применять миграции до приёма запросов новой версией. Откат MUST выполняться тем же способом с предыдущим SHA. Секреты (`.env`) MUST храниться только на сервере.

#### Scenario: Деплой версии
- **WHEN** выполняется деплой с SHA `abc…`
- **THEN** на сервере работает образ `ghcr.io/sni10/image-gallery:abc…`, миграции применены, API отвечает

#### Scenario: Откат
- **WHEN** выполняется деплой с предыдущим SHA
- **THEN** сервер работает на предыдущей версии образа
