## Why

Сервер (Hetzner, `2.28.193.254`) и домен `artai.win` готовы, но проект пока работает только локально: нет HTTPS, Django не знает, что стоит за HTTPS-прокси (ссылки на картинки будут `http://`), образ собирается вручную на машине разработчика, админка открыта на том же адресе, что и публичный API.

## What Changes

- Продакшен-схема на одном сервере: Caddy (HTTPS от Let's Encrypt) → gunicorn → PostgreSQL. Caddy заменяет nginx в проде и сам раздаёт `/media` и `/static`.
- Адреса: `artai.win` — фронтенд (SPA), `www.artai.win` — постоянный редирект на `artai.win`, `api.artai.win` — API и картинки, `secure.artai.win` — админка. На `api.artai.win` админка недоступна (404).
- Django корректно работает за HTTPS-прокси: абсолютные ссылки на картинки — `https://`, cookie админки — только по HTTPS при `DJANGO_DEBUG=false`.
- CI в GitHub Actions на пуш и pull request в `main`: проверка сообщений коммитов (Conventional Commits) и тесты. На пуш в `main` после зелёных тестов — автоматическое семантическое версионирование (тег `vX.Y.Z` + GitHub Release по типам коммитов) и публикация образа `ghcr.io/sni10/image-gallery:<sha коммита>` (+ `:vX.Y.Z`, если вышел релиз). В реестр не попадает образ с упавшими тестами.
- Инструкция для агента (`CLAUDE.md`): сообщения коммитов всегда в формате Conventional Commits.
- Файлы для сервера: `compose.prod.yaml`, `Caddyfile`, `.env.production.example`, скрипт деплоя (копирует файлы, `pull`, `up` с выбранным SHA).
- Первый деплой на сервер.

Вне рамок: прокси Cloudflare (этапы 2–3 из `DEPLOY.md`), бэкапы, SMTP Brevo (до его подключения письма в проде пишутся в лог `app`), сборка и выкладка фронтенда (отдельный репозиторий; Caddy отдаёт содержимое каталога фронта, пока он пуст — 404), перенос данных с локального стенда.

## Capabilities

### New Capabilities
- `production-deployment`: адреса и HTTPS в проде, разделение публичного API и админки, поведение Django за прокси, сборка и публикация образа, порядок деплоя и отката.

### Modified Capabilities
<!-- Основных спецификаций в openspec/specs/ пока нет. -->

## Impact

- **Код:** `config/settings.py` (прокси-заголовок, secure cookies).
- **Новые файлы:** `.github/workflows/ci.yml`, `commitlint.config.mjs`, `CLAUDE.md`, секция `[tool.semantic_release]` в `pyproject.toml`, `compose.prod.yaml`, `deploy/caddy/Caddyfile`, `.env.production.example`, `deploy/deploy.sh`.
- **Локальная разработка не меняется:** `compose.yaml` с nginx и Mailpit остаётся.
- **GitHub:** Actions в репозитории `sni10/image-gallery` (приватный репозиторий: расходуются бесплатные минуты), пакет в GHCR.
- **Сервер:** каталог `/srv/artai` с `compose.prod.yaml`, `Caddyfile`, `.env` (секреты генерируются на сервере и не покидают его), тома Docker.
