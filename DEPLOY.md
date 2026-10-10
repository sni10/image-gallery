# Деплой на хостинг

## TODO

Отмечай `[x]` по мере выполнения. «Я» — делаешь сам, «Claude» — скажи, и сделаю.

**Сейчас**
- [x] **Я:** создать администратора — `ssh deploy@2.28.193.254`, затем `cd /srv/artai && docker compose -f compose.prod.yaml exec app python manage.py createsuperuser`; войти на https://secure.artai.win/admin/
- [x] **Я:** создать категории и галереи, залить фото (через админку на `secure.artai.win`)
- [x] **Я:** закоммитить и запушить английский язык (бэкенд вышел v0.2.1, фронт — первый релиз v0.1.0)
- [x] **Claude:** выкачены бэкенд `eed0408` (v0.2.1 + тест) и фронт `2591854` (v0.1.0); проверено: сайт по умолчанию en даже для русского браузера, ru — по cookie, ошибки API и письма на английском — 09.10.2026
- [x] **Claude:** админка закрыта для роботов: `robots.txt` Disallow, `X-Robots-Tag: noindex…`, 403 ботам и скриптовым клиентам на `secure.artai.win` — 09.10.2026

Правило: коммиты, которые не должны выпускать версию (конфиги, Docker, CI, документы), — с типом `chore:` / `ci:` / `build:` / `docs:`, не `fix:` (см. `CLAUDE.md`).

**Фронт**
- [x] **Фронт:** CI как у бэкенда (commitlint, lint, типы, тесты с отчётами, semantic release, образ `ghcr.io/sni10/image-gallery-front:<sha>`), `VITE_API_URL=https://api.artai.win` вшивается в CI
- [x] **Claude:** первый выпуск фронта (SSR-контейнер `front` за Caddy), `https://artai.win` работает — 09.10.2026

**Почта (Brevo)**
- [x] **Я:** аккаунт Brevo, добавить домен `artai.win` как отправителя
- [x] **Я:** записи SPF/DKIM/DMARC от Brevo — в DNS Cloudflare (DNS only)
- [x] **Я:** SMTP-логин и ключ — вписать в `/srv/artai/.env` на сервере (`EMAIL_BACKEND=smtp`, `EMAIL_USER`, `EMAIL_PASSWORD`), не в чат
- [x] **Claude:** `EMAIL_BACKEND=smtp`, перезапуск `app`, тестовое письмо отправлено (Brevo, порт 587/STARTTLS; 465 и 25 на Hetzner закрыты) — 09.10.2026
- [x] **Я:** тестовое письмо пришло во «Входящие» Gmail (не в «Спам») — 09.10.2026
- [x] **Я:** пройти регистрацию на artai.win целиком (письмо → ссылка → вход) — 09.10.2026

**Фронт: исправления**
- [x] **Claude:** вошедший пользователь больше не видит `/login` и `/register` (переход на `/account`), фронт v0.1.1 — 09.10.2026

**HSTS** (браузер ходит на сайт только по HTTPS; срок нельзя отозвать — поднимать по ступенькам)
- [x] **Claude:** ступень 1 — `max-age=300` (5 мин) на `artai.win`, `www`, `api`, `secure` — 09.10.2026 (сниппет `(hsts)` в `Caddyfile`)
- [ ] **Claude:** ступень 2 — `max-age=604800` (неделя): ~11.10.2026, если не было проблем с HTTPS. Сказать «HSTS неделя»
- [ ] **Claude:** ступень 3 — `max-age=31536000` (год): ~через неделю после ступени 2. Сказать «HSTS год»
- [ ] Не делать без отдельного решения: `includeSubDomains` (`mail.artai.win` принадлежит Brevo) и `preload` (вшивание в браузеры, почти необратимо)

**Защита картинок от массового скачивания** (план; от простого к сильному)
Уже есть: имена файлов — SHA-256 (не перебрать), публичные id не перебрать, страница API ≤ 100 записей, админка закрыта для роботов.
- [ ] **Claude:** `robots.txt` на `artai.win` и `api.artai.win`: запретить AI-краулерам (GPTBot, ClaudeBot, CCBot, Google-Extended, Bytespider, PerplexityBot…) весь сайт и `/media/` — работает только на «вежливых» ботов
- [ ] **Claude:** лимит запросов к публичному API по IP (DRF throttling, например 120/мин). Учесть: серверный рендер фронта ходит в API с IP сервера — его исключить из лимита или передавать реальный IP клиента
- [ ] **Claude:** логи доступа Caddy + CrowdSec/fail2ban: бан IP, которые качают `/media/` сотнями в минуту
- [ ] **Claude:** оригиналы — только для вошедших: анониму API отдаёт превью и уменьшенную версию, `url` оригинала — короткоживущая подписанная ссылка. Самая сильная мера (контракт API меняется, нужна доработка фронта) — делать отдельным изменением OpenSpec
- [ ] **Я + Claude:** после включения прокси Cloudflare на `api`: Bot Fight Mode, «Block AI bots», Hotlink Protection, правило Rate Limiting на `/media/*` (бесплатный тариф — 1 правило)
- [ ] По желанию: водяной знак на превью / уменьшенной версии
- [ ] **Я:** следить за исходящим трафиком в Hetzner (лимит 20 ТБ/мес): резкий рост — признак скачивания

**Надёжность**
- [ ] **Отложено (нет бюджета на место):** хранилище для бэкапов (Hetzner Object Storage / Backblaze B2) и ключи на сервер — делать последним, но до того, как контент станет невосстановимым
- [ ] **Claude:** ежедневный `pg_dump` + копия тома `media`, ротация, проверка восстановления — после выбора хранилища

**Скрыть IP сервера** (отложено, делать вместе с бэкапами; пока `secure.artai.win` — без прокси, IP виден)
IP `2.28.193.254` уже утёк: до 09.10.2026 все записи указывали прямо на него, сервисы истории DNS это помнят.
- [ ] **Я + Claude:** `secure` → Proxied. Лимиты Cloudflare: 100 МБ на запрос, 100 с на ответ — массовая загрузка пачками ≤ ~90 МБ (15–20 фото), либо **Claude:** переделать загрузку в админке на отдельный запрос на файл (тогда пачка любая)
- [ ] **Я + Claude:** сменить IPv4/IPv6 сервера в Hetzner (Primary IP), обновить записи в Cloudflare
- [ ] **Claude:** на сервере пускать 80/443 только из сетей Cloudflare (ufw + список cloudflare.com/ips); SSH (22) — как есть
- Альтернатива без прокси: `secure` только с моих IP (`@outside not remote_ip …` в Caddy) — если IP дома постоянный
- [ ] **Я:** напоминание обновить GitHub-токен `read:packages` на сервере до истечения его срока (`docker login ghcr.io -u sni10`)

**Потом**
- [x] **Я:** прокси Cloudflare, этап 2: `artai.win` и `www` — Proxied, SSL `Full (strict)`, `Always Use HTTPS` выключен (редирект делает Caddy, продление Let's Encrypt по HTTP проходит) — 09.10.2026; проверено снаружи
- [x] **Claude + Я:** прокси Cloudflare, этап 3 (`api`) — 09.10.2026. Caddy верит `CF-Connecting-IP` только от сетей Cloudflare (`trusted_proxies` в `Caddyfile`, список — копия cloudflare.com/ips, сверять при правках прокси) и шлёт в Django один XFF = IP клиента. Проверено: картинки из кеша Cloudflare (`HIT`), JSON и `/me` не кешируются, лимит входа — по реальному IP
- [x] **Claude:** общий кеш для лимита попыток входа (`FileBasedCache` вместо памяти процесса; было ~30/мин вместо 10), выкачен `eb80dd1`, проверено: 11-я попытка → 429 — 09.10.2026
- [x] **Claude:** заархивированы 4 изменения OpenSpec, требования влиты в `openspec/specs/` (6 спецификаций, 32 требования) — 09.10.2026

## Сервер

| | |
|---|---|
| Хостинг | Hetzner Cloud, **CPX22** (2 vCPU AMD, 4 ГБ RAM, 80 ГБ SSD, 20 ТБ трафика), Nuremberg, 19.49 €/мес + IPv4 |
| Имя | `ubuntu-4gb-nbg1-1` (#169490394) |
| IPv4 / IPv6 | `2.28.193.254` / `2a01:4f8:c0c:ae3c::/64` |
| Вход | `ssh deploy@2.28.193.254` — только по ключу `~/.ssh/id_ed25519` с домашнего ПК |
| Система | Ubuntu 26.04.1 LTS |

Настроено (09.10.2026):
- система обновлена, ежедневная автоустановка обновлений безопасности (`unattended-upgrades`);
- пользователь `deploy`: `sudo` без пароля (пароля у пользователя нет), группа `docker`;
- SSH: вход по паролю запрещён, вход под `root` запрещён (`/etc/ssh/sshd_config.d/00-hardening.conf`);
- файрвол `ufw`: входящие запрещены, кроме 22/tcp, 80/tcp, 443/tcp, 443/udp;
- Docker 29.9 + Compose v5.6 из официального репозитория, автозапуск; логи контейнеров — до 3 файлов по 10 МБ (`/etc/docker/daemon.json`);
- swap 2 ГБ (`/swapfile`), `vm.swappiness=10`.

⚠ Порты из `ports:` в compose Docker открывает **в обход ufw**. В продакшен-compose наружу публикует порты только Caddy (80/443); у `db` и `app` секции `ports:` быть не должно.

Управление Hetzner с домашнего ПК: официальный CLI `hcloud` (winget `HetznerCloud.CLI`), контекст `dns`. Его токен (Read & Write) выпущен в проекте с сервером — даёт доступ ко всему проекту, не только к DNS. Отозвать: Console → Security → API Tokens.

## Домен и DNS

Домен `artai.win`: регистратор и DNS — Cloudflare (NS `eloise`/`robert.ns.cloudflare.com`). В Hetzner DNS не используется.

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | `2.28.193.254` | **Proxied** |
| AAAA | `@` | `2a01:4f8:c0c:ae3c::1` | **Proxied** |
| CNAME | `www` | `artai.win` | **Proxied** |
| A | `api` | `2.28.193.254` | **Proxied** |
| AAAA | `api` | `2a01:4f8:c0c:ae3c::1` | **Proxied** |
| A | `secure` | `2.28.193.254` | DNS only (всегда) |
| AAAA | `secure` | `2a01:4f8:c0c:ae3c::1` | DNS only (всегда) |
| TXT | `@` | `brevo-code:…` (подтверждение домена в Brevo) | — |
| CNAME | `brevo1._domainkey`, `brevo2._domainkey` | `b1`/`b2.artai-win.dkim.brevo.com` (DKIM) | DNS only |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` | — |
| CNAME | `mail` | `mail-artai-win.brand.brevosend.com` (ссылки в письмах) | DNS only |

⚠ Прокси Cloudflare («оранжевое облако») **не включать**, пока не сделано: на бесплатном тарифе он режет запросы > 100 МБ и ответы дольше 100 с (массовая загрузка в админке), подменяет IP клиента (лимит попыток входа станет общим), требует режима SSL Full (strict). Включать осознанно, по плану ниже.

### План включения прокси Cloudflare

1. **Запуск без прокси.** Везде «DNS only». Caddy сам получает сертификаты Let's Encrypt. Проверить: загрузка фото, вход/регистрация, письма.
2. **Прокси для `artai.win` и `www`.** Там только статика фронта — без загрузок и входа.
   - Cloudflare → SSL/TLS → режим **Full (strict)** (до включения прокси).
   - Включить «Proxied» у `@` и `www`.
   - Выгода: CDN для фронта, защита от DDoS.
3. **Прокси для `api.artai.win`.** Главная выгода — картинки из кеша Cloudflare (хеш-имена + `Cache-Control: immutable` уже под это сделаны). Сначала доработать:
   - **Админку — на отдельный адрес без прокси** `secure.artai.win` (DNS only), иначе массовая загрузка упрётся в лимиты Cloudflare: 100 МБ на запрос, 100 с на ответ. На сервере: Caddy отдаёт `/admin/` только на `secure.artai.win` (на `api.artai.win` — 404), Django — `secure.artai.win` в `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`. Имя поддомена не секрет (видно в журналах сертификатов): защита — пароль и, по желанию, доступ только с своих IP (одна строка в Caddy).
   - **Реальный IP клиента** из заголовка `CF-Connecting-IP` (в Caddy: доверять сетям Cloudflare и брать IP из этого заголовка), иначе лимит попыток входа станет общим для всех.
   - По желанию: на сервере пускать 80/443 только из сетей Cloudflare — тогда IP сервера не атаковать в обход защиты. Компромисс: адрес админки без прокси всё равно раскрывает IP.

Записи Brevo добавлены автоматически (Domain Connect), 09.10.2026. MX нет — почту только отправляем. DMARC `p=none` — потом можно ужесточить до `quarantine`.

✅ DNS-записи заведены и проверены снаружи (Cloudflare и Google DNS), 09.10.2026.

✅ Продакшен запущен 09.10.2026; сейчас бэкенд **v0.2.1** + `eb80dd1`, фронт **v0.1.1** (`29b4ad7`), HTTPS на всех четырёх адресах (Let's Encrypt, до 07.01.2027, продлевает Caddy). Администратор создан, контент залит. Почта через Brevo работает.

Ещё не сделано: бэкапы (отложены), HSTS ступени 2–3, защита картинок от массового скачивания.

## Что подготовить мне

1. ✅ **VPS** — Hetzner CPX22, см. «Сервер».
2. ✅ **Домен** — `artai.win`, см. «Домен и DNS».
3. ✅ **SSH** — `ssh deploy@2.28.193.254`.
4. ✅ **GitHub** — Actions работают; на сервере `docker login ghcr.io` (токен classic, `read:packages`; обновить до истечения срока).
5. ✅ **Почта (Brevo)** — домен `artai.win` подтверждён, отправитель `ArtAI <noreply@artai.win>`, SMTP-ключ в `.env` на сервере.
6. ✅ **Фронт** — собирается в CI с `VITE_API_URL=https://api.artai.win`.
7. **Позже:** хранилище для бэкапов (S3 / Backblaze B2).

Секреты (`SECRET_KEY`, пароль БД, SMTP-ключ, токены) — только в `.env` на сервере, не в чат и не в git.

---

## Схема (как работает сейчас)

```
git push / PR в main
  └─ GitHub Actions (.github/workflows/ci.yml):
       commitlint (Conventional Commits) + тесты на PostgreSQL (отчёты: артефакт test-reports-<sha>)
       только push: semantic release → тег vX.Y.Z + GitHub Release (если есть feat/fix)
                    → образ ghcr.io/sni10/image-gallery:<sha> (+ :vX.Y.Z)

Сервер /srv/artai (Docker Compose, compose.prod.yaml):
  caddy  :80/:443  HTTPS, редирект HTTP→HTTPS, /media и /static, прокси в app и front
  app    gunicorn :8000, образ из GHCR по IMAGE_TAG; при старте migrate + collectstatic
  front  SSR фронтенда (образ из GHCR по FRONT_TAG); API для серверного рендера — https://api.artai.win через Caddy (алиас в сети)
  db     postgres:16, том pgdata
  тома:  media, static, pgdata, caddy_data (сертификаты), caddy_config

artai.win         → фронт: SSR-контейнер front (Node, :5173), /assets/* — вечный кеш
www.artai.win     → 301 на artai.win
api.artai.win     → API, /media, /static, /api/docs; /admin → 404
secure.artai.win  → админка (+ /media, /static); роботам — robots.txt Disallow, X-Robots-Tag noindex, 403 ботам и скриптам

Язык: английский — основной (сайт, письма, ошибки API); русский на сайте — только по выбору в переключателе (cookie).
Почта: Brevo SMTP smtp-relay.brevo.com:587 (STARTTLS), отправитель ArtAI <noreply@artai.win>.
```

Файлы в репозитории: `compose.prod.yaml`, `deploy/caddy/Caddyfile`, `deploy/deploy.sh`, `.env.production.example`, `.github/workflows/ci.yml`, `commitlint.config.mjs`, `[tool.semantic_release]` и `[tool.coverage]` в `pyproject.toml`. На сервере дополнительно `/srv/artai/.env` (права 600, секреты сгенерированы там же; `IMAGE_TAG` записывает скрипт деплоя).

## Решения

| Вопрос | Решение | Почему |
|---|---|---|
| Docker или Kubernetes | **Docker Compose на одном VPS** | Один API, одна база, один прокси. Тот же образ потом запустится и в Kubernetes. |
| Реестр образов | **GHCR** (`ghcr.io/sni10/image-gallery`) | Приватные образы бесплатно, доступ по правам GitHub. |
| Теги образов | **SHA коммита** (+ `vX.Y.Z` при релизе) | Всегда известно, какой код запущен; откат = предыдущий SHA. `latest` не используем. |
| Версии | **python-semantic-release** по Conventional Commits | `fix` → patch, `feat` → minor, breaking → major (minor на `0.x`). Версия только в git-тегах, без коммитов в `main`. |
| HTTPS | **Caddy** вместо nginx | Сам выпускает и продлевает сертификаты; один прокси перед gunicorn (`NUM_PROXIES = 1`). Локальный `compose.yaml` с nginx — для разработки. |
| Админка | отдельный адрес `secure.artai.win` | Готово к прокси Cloudflare для `api` (лимиты загрузки) и к ограничению доступа по IP. |

## Деплой, откат, обслуживание

Деплой новой версии (SHA — из успешного запуска Actions или `git rev-parse origin/main`):
```bash
bash deploy/deploy.sh <полный sha>      # с домашнего ПК: копирует compose.prod.yaml + Caddyfile, pull, up, reload Caddy
```
Откат — та же команда с предыдущим SHA. Миграции сами не откатываются: если новая версия добавила миграцию, несовместимую со старым кодом, сначала
`docker compose -f compose.prod.yaml exec app python manage.py migrate <app> <предыдущая миграция>`, потом деплой старого SHA.

На сервере (`ssh deploy@2.28.193.254`, `cd /srv/artai`):
```bash
docker compose -f compose.prod.yaml ps                         # что запущено и какой образ
docker compose -f compose.prod.yaml logs -f app                # логи приложения (сюда же пишутся письма до Brevo)
docker compose -f compose.prod.yaml logs caddy                 # сертификаты, ошибки прокси
docker compose -f compose.prod.yaml exec app python manage.py createsuperuser   # первый администратор
```

Фронт: `bash deploy/deploy.sh <полный sha фронта>` из репозитория `image-gallery-front` — записывает `FRONT_TAG` в `.env` и перезапускает только `front`. Откат — тот же скрипт с прошлым SHA.

`manage.py check --deploy` на проде сейчас сообщает: консольная почта (до Brevo — ожидаемо), нет `SECURE_SSL_REDIRECT` (редирект делает Caddy — не нужно), нет HSTS (включить позже осознанно: `Strict-Transport-Security` в Caddy, начать с малого `max-age`).

## Бэкапы

**Сделать при запуске продакшена**, до того как в нём появится реальный контент:
- ежедневный `pg_dump` базы во внешнее хранилище (S3 / Backblaze B2 / другой сервер) с ротацией;
- копия тома `media` (оригиналы — главная ценность; превью можно пересоздать командой `rebuild_thumbs`);
- регулярная проверка восстановления из бэкапа.

## Чеклист

- [x] Доработки кода (прокси-заголовок, secure cookies, админка на `secure`)
- [x] CI: тесты, отчёты, версии, образ в GHCR
- [x] DNS указывает на сервер
- [x] `.env` на сервере, `DJANGO_DEBUG=false`
- [x] HTTPS на всех адресах, проверено снаружи
- [x] Суперпользователь создан
- [x] Фронт: CI, образ, SSR на `artai.win`
- [x] SMTP (Brevo) настроен, письмо регистрации доходит
- [ ] Бэкапы базы и `media` настроены и проверены восстановлением
- [x] HSTS ступень 1 (5 мин); ступени 2–3 — в TODO
