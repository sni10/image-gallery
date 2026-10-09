## Context

- Сервер: Hetzner CPX22, Ubuntu 26.04, пользователь `deploy` (ключ, sudo, группа `docker`), ufw 22/80/443, Docker 29.9 + Compose v5.6, `docker login ghcr.io` выполнен (токен `read:packages`).
- DNS: `artai.win`, `www`, `api`, `secure` → `2.28.193.254` / `2a01:4f8:c0c:ae3c::1`, Cloudflare «DNS only».
- Локально: `compose.yaml` (nginx + app + db + mailpit), `Dockerfile` (uv, gunicorn, entrypoint: migrate + collectstatic), настройки из env с валидацией (`config/app_settings`), `NUM_PROXIES = 1`.
- Подробный план и решения (Compose вместо Kubernetes, GHCR, теги по SHA, Caddy) — `DEPLOY.md`.

## Goals / Non-Goals

**Goals:** реализовать `production-deployment`; локальная разработка без изменений; минимум кода в приложении.

**Non-Goals:** прокси Cloudflare, бэкапы, SMTP, фронтенд, автодеплой из Actions по SSH (деплой запускается вручную скриптом).

## Decisions

### Caddy вместо nginx в проде
Один прокси перед gunicorn — `NUM_PROXIES = 1` остаётся верным (клиентский IP = последний адрес `X-Forwarded-For`, который дописывает Caddy). Caddy сам получает сертификаты (HTTP-01 через открытый 80) и делает редирект HTTP→HTTPS. Caddy по умолчанию не доверяет входящим `X-Forwarded-*` и выставляет их сам — подделать `X-Forwarded-Proto` клиент не может.

Сайты в `Caddyfile`:
- `artai.win`: `root /srv/frontend`, `try_files {path} /index.html`, `file_server`.
- `www.artai.win`: `redir https://artai.win{uri} permanent`.
- `api.artai.win`: `/media/*` (immutable кеш), `/static/*`, `/admin*` → 404, остальное → `app:8000`.
- `secure.artai.win`: `/media/*`, `/static/*`, остальное → `app:8000`. Отдельная сущность сайта, чтобы потом проще было добавить ограничение по IP.
- `request_body max_size 500MB` на `api` и `secure` (массовая загрузка).

### Django
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` — всегда. Безопасно, потому что перед приложением всегда наш прокси, выставляющий заголовок сам (локально — nginx, в проде — Caddy). `request.is_secure()` → `build_absolute_uri` даёт `https://`, CSRF-проверка Origin `https://secure.artai.win` совпадает с хостом без `CSRF_TRUSTED_ORIGINS`.
- `SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG`.
- Ограничение админки по хосту — только в Caddy (отдельного middleware не делаем): приложение недоступно извне иначе как через Caddy.

### Образ и CI
- `.github/workflows/build.yml`: job `test` (service `postgres:16-alpine`, `uv sync --locked`, `manage.py test`, переменные окружения для валидатора настроек) → job `image` (`needs: test`, `docker/login-action` с `GITHUB_TOKEN`, `docker/build-push-action`, тег `ghcr.io/${{ github.repository }}:${{ github.sha }}`).
- В тестах CI письма — `console`, `FRONTEND_URL` по умолчанию.

### Версионирование и коммиты
- **python-semantic-release** 10.7 (GitHub Action, родной для Python-проектов): по Conventional Commits с прошлого тега считает версию, создаёт тег `vX.Y.Z` и GitHub Release. Настройки — `[tool.semantic_release]` в `pyproject.toml`; `commit: false` — версия живёт только в тегах, коммитов-«бампов» в `main` нет (не нужен обход защиты ветки и нет повторных запусков CI). Перед релизом `git reset --hard <sha>`, чтобы релизить ровно протестированный коммит. Первая версия на текущей истории — `v0.1.0` (проверено пробным запуском).
- **commitlint** (`@commitlint/cli` 21 через `npx`, без стороннего экшена — популярная обёртка не обновлялась с 2025): `commitlint.config.mjs` на базе `config-conventional`, заголовок ≤ 150 символов, без ограничений длины тела/футера. Проверяются коммиты PR (base..head) и пуша (before..after).
- Отчёты тестов: `coverage run manage.py test` (настройки `[tool.coverage.*]` в `pyproject.toml`), JUnit через `XMLTestRunner`, включаемый переменной `TEST_REPORTS_DIR` (локально вывод тестов прежний). Артефакт `test-reports-<sha>` (`junit.xml`, `coverage.xml`, `coverage-html/`), сводка покрытия в `GITHUB_STEP_SUMMARY`. `coverage` и `unittest-xml-reporting` — dev-группа, в образ (`--no-dev`) не попадают.
- `CLAUDE.md` в корне — инструкция агенту: всегда Conventional Commits.
- Порядок в `ci.yml`: `commits` + `test` (push и PR) → `release` (push) → `image` (push; теги `<sha>` и `v<version>` при релизе).

### Сервер
- Каталог `/srv/artai` (владелец `deploy`): `compose.prod.yaml`, `Caddyfile`, `.env`, `frontend/` (пусто до выкладки фронта).
- `.env` создаётся на сервере из `.env.production.example`: `DJANGO_SECRET_KEY` и `DB_PASSWORD` генерируются там же (`openssl rand`), в чат и git не попадают. `EMAIL_BACKEND=console` до подключения Brevo.
- `deploy/deploy.sh <sha>` (запускается с ПК разработчика): копирует `compose.prod.yaml` и `Caddyfile` по SSH, на сервере `IMAGE_TAG=<sha> docker compose pull app && up -d` (миграции — в entrypoint контейнера до старта gunicorn), затем показывает статус. Откат — тот же скрипт с прошлым SHA.
- В `compose.prod.yaml` порты публикует только `caddy` (80, 443/tcp, 443/udp); у `db` и `app` секции `ports` нет — Docker открывает опубликованные порты в обход ufw.

## Risks / Trade-offs

- [Let's Encrypt не выдаст сертификат, если DNS или порт 80 недоступны] → DNS проверен снаружи, 80 открыт в ufw; лимиты LE на неудачные попытки — при ошибке сначала проверить через `caddy` логи, не перезапускать в цикле.
- [Пустой каталог фронта → `artai.win` отдаёт 404 до выкладки фронта] → ожидаемо, фронт — отдельная задача.
- [Письма в проде пока только в логах] → регистрация на проде до Brevo — только для проверки; подтверждение можно взять из `docker compose logs app`.
- [Минуты GitHub Actions для приватного репозитория] → сборка на каждый пуш в `main`, не на каждую ветку; кеш слоёв Docker (`cache-from/to: type=gha`).

## Migration Plan

1. Слить изменения в `main` → Actions публикует образ.
2. На сервере: `/srv/artai`, `.env` с секретами.
3. `deploy/deploy.sh <sha>`; `createsuperuser` выполняет владелец сам (`ssh` + `docker compose exec`).
4. Проверки из specs. Откат — `deploy.sh <предыдущий sha>`; при полном откате — `docker compose down` (тома сохраняются).
