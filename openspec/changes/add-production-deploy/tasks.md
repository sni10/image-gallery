## 1. Приложение

- [x] 1.1 `SECURE_PROXY_SSL_HEADER` и `SESSION/CSRF_COOKIE_SECURE = not DEBUG` в `config/settings.py`; проверить тестами: с `X-Forwarded-Proto: https` ссылки на картинки `https://`, без него — `http://`; при `DEBUG=false` cookie `Secure`; все тесты в контейнере проходят

## 2. Сборка образа

- [x] 2.1 `.github/workflows/ci.yml` (тесты на PostgreSQL → сборка → push в GHCR с тегом SHA, кеш gha); проверить: workflow валиден (`actionlint` или пробный запуск после пуша владельцем), образ появляется в GHCR
- [x] 2.2 Семантическое версионирование и формат коммитов: python-semantic-release (тег + GitHub Release, `commit: false`), commitlint на push и PR в `main`, тег образа `vX.Y.Z`, инструкция в `CLAUDE.md`; проверить: `actionlint`, commitlint принимает историю и отвергает `added stuff`, пробный расчёт версии даёт `0.1.0`, после пуша владельцем — тег `v0.1.0`, Release и образ `:v0.1.0`

- [x] 2.3 Отчёты тестов в CI: coverage (HTML + XML, сводка покрытия на странице запуска) и JUnit (`unittest-xml-reporting` через `TEST_REPORTS_DIR`), артефакт `test-reports-<sha>` на 14 дней, загружается и при упавших тестах; dev-зависимости не попадают в образ; проверить: прогон в контейнере создаёт `junit.xml`, `coverage.xml`, `coverage-html/`, `actionlint` чист

## 3. Файлы для сервера

- [x] 3.1 `deploy/caddy/Caddyfile` (4 сайта по design.md) и `compose.prod.yaml` (db, app из GHCR по `IMAGE_TAG`, caddy; порты только у caddy); проверить: `caddy validate` в контейнере и `docker compose -f compose.prod.yaml config` проходят
- [x] 3.2 `.env.production.example` и `deploy/deploy.sh <sha>` (копирование файлов, pull, up, статус); проверить: `bash -n`, справка при запуске без аргумента

## 4. Первый деплой

- [x] 4.1 На сервере `/srv/artai` и `.env` с секретами, сгенерированными на сервере; проверить: валидатор настроек проходит (`docker compose run --rm app python manage.py check --deploy`)
- [x] 4.2 Деплой образа из GHCR; проверить снаружи все сценарии из specs: HTTPS и сертификаты на 4 адресах, HTTP→HTTPS, `www` → `artai.win`, `/admin/` на `api` → 404, на `secure` — страница входа со стилями, `https://` в ссылках API
- [ ] 4.3 Обновить `DEPLOY.md` (фактическая схема, команды деплоя/отката) и передать владельцу команду `createsuperuser`
