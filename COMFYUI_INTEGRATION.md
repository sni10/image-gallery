# ComfyUI → artai.win: автопубликация картинок

Цель: workflow в ComfyUI генерирует картинку, нода-описатель выдаёт `title` / `description` / `tags`,
новая нода **Send to artai.win** отправляет картинку и эти данные в API, фото сразу появляется на сайте.

Две части:

1. **API** (этот репозиторий) — эндпоинт загрузки фото по API-ключу + поля `description` и `tags` у фото.
2. **Нода** (новый пакет в `ComfyUI/custom_nodes/artai_sender`) — по образцу `telegram_sender` / `DWA`.

---

## Часть 1. API

### 1.1. Что есть сейчас и чего не хватает

| Что | Сейчас | Нужно |
|---|---|---|
| Связи | `Category` ← `Gallery` ← `Photo`. У фото нет категории, она берётся от галереи | Без изменений. Нода указывает **галерею** (или категорию + название галереи, см. 1.4) |
| `Photo.title` | есть, 200 символов, пусто → имя файла | без изменений |
| `Photo.description` | нет | **добавить** |
| `Photo.tags` | нет | **добавить** |
| Даты | `created_at` (auto), `link_date` (из неё публичный id) | без изменений: сервер ставит «сейчас», клиенту передавать даты не нужно |
| Загрузка фото | только админка (`GalleryAdmin.save_model` → `PhotoService.create`) | **API-эндпоинт**, который вызывает тот же `PhotoService.create` |
| Авторизация для скриптов | только JWT пользователя (15 минут, логин/refresh) — для автомата неудобно | **статический API-ключ** из env |

### 1.2. Модель

```python
# gallery/models.py — Photo
from django.contrib.postgres.fields import ArrayField

description = models.TextField(blank=True, default='')
tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
```

- Миграция `0010_photo_description_tags` — только добавление полей с дефолтами, без даунтайма.
- `ArrayField`, а не отдельная модель `Tag` (M2M): БД — PostgreSQL, фильтр `tags__contains=['cat']` работает сразу.
  `ponytail:` модель `Tag` + GIN-индекс — когда понадобятся страница тега / облако тегов / поиск по тегам.
- `PhotoService.create(file, gallery, title='')` получает `description=''` и `tags=()` — единая точка записи остаётся одна.

### 1.3. Авторизация: API-ключ

- Новая секция настроек `config/app_settings/schema.py`:

  ```python
  class IngestSettings(Section):
      model_config = SettingsConfigDict(env_prefix='INGEST_')
      api_key: SecretStr | None = None  # пусто → эндпоинт выключен (всегда 403)
  ```

  Валидация: если задан — не короче 32 символов. Генерация на сервере: `openssl rand -hex 32` → `INGEST_API_KEY` в `/srv/artai/.env`
  (и строка-пример в `.env.example` / `.env.production.example`).
- Заголовок **`X-Api-Key: <key>`**, а не `Authorization: Bearer`: Bearer уже занят JWT
  (`BearerAccessTokenAuthentication` ответит 401 на «не-JWT»).
- Реализация — одна permission-класса, у view `authentication_classes = []`:

  ```python
  class HasIngestKey(BasePermission):
      def has_permission(self, request, view):
          key = settings.INGEST_API_KEY
          given = request.headers.get('X-Api-Key', '')
          return bool(key) and hmac.compare_digest(given.encode(), key.encode())
  ```

- Один ключ на всё. `ponytail:` ключи в БД (несколько клиентов, отзыв по одному, `last_used_at`) — когда клиентов станет больше одного.
- Хост: **`api.artai.win`** (проксируется Cloudflare, лимит тела 100 МБ на free-плане — для одной картинки с запасом).
  `secure.artai.win` не подходит: Caddy отдаёт 403 всем `python`/`requests` User-Agent.

### 1.4. Эндпоинт

```
POST /ingest/photos
X-Api-Key: <key>
Content-Type: multipart/form-data
```

Отдельный префикс `/ingest/`, а не `POST /photos`: публичное API остаётся только на чтение, а у загрузки своя авторизация.

**Поля формы**

| Поле | Тип | Обязательно | Правила |
|---|---|---|---|
| `image` | файл | да | JPEG/PNG/WebP/GIF/AVIF (`SUPPORTED_FORMATS`), проверка через `ImageProcessor` |
| `gallery` | string | одно из двух | публичный id галереи (26 символов) |
| `category` + `galleryTitle` | string | одно из двух | slug категории + название галереи: найти галерею с таким названием в категории, нет — создать |
| `title` | string | нет | ≤ 200, пусто → имя файла (как сейчас) |
| `description` | string | нет | ≤ 5000 |
| `tags` | string | нет | через запятую: `cat, cyberpunk, neon`. Сервер: trim, убрать `#`, lower-case, без дублей, пустые выкинуть, ≤ 50 символов на тег, ≤ 30 тегов (лишнее → 400, не молча режем) |

Почему `category` + `galleryTitle`: тогда в ComfyUI не нужно заранее создавать галерею в админке и копировать её id —
нода может слать, например, `galleryTitle = "AI 2026-10"`, и галереи заводятся сами.
`ponytail:` поиск по `(category, title)` без уникального индекса — гонка при параллельных запросах может создать две
одноимённые галереи; ComfyUI шлёт последовательно, так что не важно. Если станет важно — `UniqueConstraint(category, title)`.

**Повторная отправка (идемпотентность)**: файлы уже хранятся по SHA-256 (`store_once`). Если в этой галерее уже есть фото
с тем же хешем (`image` начинается с `original/<sharded_path(sha)>.`), новое не создаётся — ответ **200** с существующим фото.
Значит, ноду можно безопасно перезапускать/ретраить, дублей не будет.

**Ответы**

| Код | Когда | Тело |
|---|---|---|
| 201 | фото создано | `{ "photo": PhotoSerializer, "gallery": { "id", "title", "category" } }` |
| 200 | такое фото уже есть в галерее | то же тело, существующее фото |
| 400 | нет `image`, неподдерживаемый формат, нет/оба способа выбора галереи, лимиты полей/тегов | `{ "field": ["message"] }` (как в остальном API) |
| 403 | нет/неверный `X-Api-Key` или ключ не настроен | `{ "detail": ... }` |
| 404 | галерея по `gallery` или категория по `category` не найдена | `{ "detail": ... }` |
| 413 | файл больше лимита прокси | от Caddy/Cloudflare |

Пример:

```bash
curl -X POST https://api.artai.win/ingest/photos \
  -H "X-Api-Key: $INGEST_API_KEY" \
  -F image=@out.png -F category=ai -F galleryTitle="AI 2026-10" \
  -F title="Neon Fox" -F description="..." -F tags="fox, neon, cyberpunk"
```

### 1.5. Код (где что)

| Файл | Изменение |
|---|---|
| `gallery/models.py` | `description`, `tags` у `Photo` |
| `gallery/migrations/0010_…` | `makemigrations` |
| `gallery/services/photo_service.py` | `create(..., description='', tags=())`; `find_duplicate(file, gallery) -> Photo \| None` по SHA |
| `gallery/services/gallery_queries.py` (или там же) | `get_or_create_by_title(category, title)` |
| `gallery/api/serializers.py` | `PhotoIngestSerializer` (вход, нормализация тегов, «одно из двух» для галереи); в `PhotoSerializer` добавить `description`, `tags` |
| `gallery/api/views.py` | `PhotoIngestView(APIView)`: `authentication_classes = []`, `permission_classes = [HasIngestKey]`, `parser_classes = [MultiPartParser]`, `@extend_schema` как у соседей |
| `gallery/api/permissions.py` | `HasIngestKey` |
| `gallery/api/urls.py` | `path('ingest/photos', PhotoIngestView.as_view(), name='photo-ingest')` |
| `config/app_settings/schema.py`, `config/settings.py` | `IngestSettings` → `INGEST_API_KEY` |
| `.env.example`, `.env.production.example`, `compose*.yaml` | `INGEST_API_KEY=` |

Нюанс: `PhotoSerializer.isFavorite` берёт аннотацию `is_favorite`; у только что созданного объекта её нет —
перед сериализацией выставить `photo.is_favorite = False`.

Публичные `PhotoSerializer` получают `description` и `tags` — это добавление полей, не ломающее контракт.
Фронт (`../image-gallery-front`) показывает их отдельной задачей.

### 1.6. Тесты (`gallery/tests/test_ingest_api.py`)

- без ключа / неверный ключ / ключ не настроен → 403;
- по `gallery` → 201, фото в галерее, `title`/`description`/`tags` сохранены, есть thumb;
- по `category` + `galleryTitle`: первая отправка создаёт галерею, вторая (другая картинка) кладёт в ту же;
- повтор того же файла → 200, фото одно;
- неизвестные галерея/категория → 404; оба способа или ни одного → 400; неподдерживаемый формат → 400;
- нормализация тегов (`"#Cat, cat , ,Neon"` → `["cat", "neon"]`), лимиты → 400;
- `PhotoSerializer` в `GET /galleries/<id>/photos` отдаёт `description`, `tags`;
- OpenAPI-схема строится (`test_openapi.py` уже это ловит).

### 1.7. Коммиты

- `feat(gallery): add description and tags to photos`
- `feat(api): add photo upload endpoint for automation with api key`
- `build(deploy): add INGEST_API_KEY to env examples`

`feat` → minor-релиз (0.x → 0.3.0).

---

## Часть 2. Нода ComfyUI «Send to artai.win»

### 2.1. Расположение и структура

```
ComfyUI/custom_nodes/artai_sender/
  __init__.py        # NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
  artai_node.py      # класс ноды
  artai_api.py       # upload(...) → requests.post; без зависимостей от comfy (тестируется отдельно)
  requirements.txt   # requests
  tests/test_api.py  # нормализация тегов, сборка формы, разбор ответов/ошибок
```

Отдельный пакет, а не правка `telegram_sender`: разные назначения, один упавший сервис не должен ронять второй.
В workflow обе ноды стоят рядом и берут одни и те же `title`/`description`.

### 2.2. Откуда брать картинку: последний файл в папке

Как в `telegram_sender` и `DWA`: `time.sleep(3)`, затем самый новый файл в `output_folder`
(`max(glob(...), key=os.path.getctime)`), расширения как в DWA — `png/jpg/jpeg/webp`. Файл отправляется как есть,
без перекодирования. Вход `images` нужен только чтобы нода стояла в графе после SaveImage и запускалась.

### 2.3. Входы

| Вход | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `images` | IMAGE | — | связь с пайплайном (как у Telegram/DeviantArt) |
| `output_folder` | STRING | `output` | папка, где SaveImage сохраняет картинки |
| `api_url` | STRING | `https://api.artai.win` | база API |
| `api_key` | STRING | `""` | значение `INGEST_API_KEY` с сервера |
| `gallery` | STRING | `""` | публичный id галереи; если задан — `category`/`gallery_title` игнорируются |
| `category` | STRING | `"ai"` | slug категории |
| `gallery_title` | STRING | `""` | название галереи; поддерживает `{date}` → `2026-10` (галерея на месяц) |
| `title` | STRING (multiline) | `""` | подключается выходом ноды-описателя |
| `description` | STRING (multiline) | `""` | то же |
| `tags` | STRING (multiline) | `""` | то же; запятые/переводы строк/`#` допустимы |
| `enabled` | BOOLEAN | `True` | быстро выключить публикацию, не разбирая граф |

### 2.4. Выход и поведение

- `RETURN_TYPES = ("STRING",)`, `RETURN_NAMES = ("photo_id",)`, `OUTPUT_NODE = True`, `CATEGORY = "output"`.
  Возвращает публичный id фото — можно вывести в Show Text или передать дальше.
- `comfy.utils.ProgressBar(2)` — найти файл, отправить (как в Telegram-ноде).
- Запрос: `requests.post(f"{api_url}/ingest/photos", headers={"X-Api-Key": api_key, "User-Agent": "artai-comfyui/1.0"},
  files={"image": open(latest, "rb")}, data={...}, timeout=(10, 120))`.
  Пустой `title` — сервер возьмёт имя файла.
- 200 и 201 — успех (200 = уже было, сервер дедуплицирует). Лог: `Published: <id>`.
- Любая другая ошибка → `raise RuntimeError(текст ответа API)`: нода краснеет в UI. Картинка к этому моменту уже
  сохранена SaveImage, ничего не теряется.
- `ponytail:` без автоповторов: сервер идемпотентен, так что повтор = просто перезапустить очередь.

### 2.5. Каркас

```python
SUPPORTED_EXTENSIONS = ["*.png", "*.jpg", "*.jpeg", "*.webp"]


class ArtaiSender:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "output_folder": ("STRING", {"default": "output"}),
                "api_url": ("STRING", {"default": "https://api.artai.win"}),
                "api_key": ("STRING", {"default": ""}),
                "category": ("STRING", {"default": "ai"}),
                "gallery_title": ("STRING", {"default": "AI {date}"}),
                "enabled": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "gallery": ("STRING", {"default": ""}),
                "title": ("STRING", {"default": "", "multiline": True}),
                "description": ("STRING", {"default": "", "multiline": True}),
                "tags": ("STRING", {"default": "", "multiline": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("photo_id",)
    FUNCTION = "send"
    OUTPUT_NODE = True
    CATEGORY = "output"

    def send(self, images, output_folder, api_url, api_key, category, gallery_title, enabled,
             gallery="", title="", description="", tags=""):
        if not enabled:
            return ("",)
        if not api_key:
            raise RuntimeError("api_key is required")
        time.sleep(3)

        pbar = comfy.utils.ProgressBar(2)
        files = [f for ext in SUPPORTED_EXTENSIONS for f in glob.glob(os.path.join(output_folder, ext))]
        if not files:
            raise RuntimeError(f"No images in {output_folder}")
        latest = max(files, key=os.path.getctime)
        pbar.update(1)

        photo_id = upload(api_url, api_key, latest,
                          gallery=gallery, category=category,
                          gallery_title=gallery_title.replace("{date}", date.today().strftime("%Y-%m")),
                          title=title, description=description, tags=tags)
        pbar.update(1)
        return (photo_id,)

NODE_CLASS_MAPPINGS = {"ArtaiSender": ArtaiSender}
NODE_DISPLAY_NAME_MAPPINGS = {"ArtaiSender": "🖼️ Send to artai.win"}
```

### 2.6. Workflow

```
KSampler → VAE Decode ─┬─> Save Image
                       ├─> [нода-описатель] ─ title / description / tags ─┐
                       ├─> Send to Telegram   <───────────────────────────┤
                       └─> Send to artai.win  <───────────────────────────┘
```

---

## Порядок работ

1. API: модель + миграция → `PhotoService` → эндпоинт + ключ → тесты → релиз (`feat`).
2. На сервере: `INGEST_API_KEY` в `/srv/artai/.env`, деплой, проверка `curl` из 1.4.
3. Нода: `artai_api.py` + тесты → `artai_node.py` → прогон на тестовой галерее.
4. Фронт: показать `description` и `tags` на фото (отдельная задача в `image-gallery-front`).

## Вне рамок (добавить, когда понадобится)

- Модель `Tag`, страницы/фильтр по тегам на сайте.
- Редактирование `description`/`tags` в админке (сейчас фото правятся только сеткой в галерее; простой `PhotoAdmin` — когда
  понадобится руками поправить подпись).
- Отложенная публикация (`published_at` / черновики) — сейчас фото видно сразу.
- Несколько API-ключей в БД.
