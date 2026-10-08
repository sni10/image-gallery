## Context

- Галереи живут в приложении `gallery`; чтение — через `GalleryQueries.with_stats()` (число фото и обложка подзапросами, без `GROUP BY`) и `attach_covers()`; ответ — `GallerySerializer`.
- Каталог `GET /galleries` — `GalleryListView` с `PageLimitPagination`.
- Админка галереи — своя форма `GalleryAdminForm` (поле `title`, загрузка фото, сетка обложки/выбора) и `GalleryAdmin.fields = ['title', 'new_images']`.
- В базе compose две тестовые галереи, их данные можно удалить; в проде данных пока нет.

## Goals / Non-Goals

**Goals:** реализовать `gallery-categories` без изменения остальных контрактов галереи; не добавлять N+1 в каталог.

**Non-Goals:** кеширование списка категорий, сортировка каталога по категориям, многоязычные названия.

## Decisions

### Модель и связь
`Category(title, slug [SlugField, unique], position [int, default 0], created_at)`, `Meta.ordering = ['position', 'title']`. `Gallery.category = ForeignKey(Category, on_delete=PROTECT, related_name='galleries')`, обязательное.
- `PROTECT` — БД и Django сами не дадут удалить категорию с галереями; админка показывает стандартное сообщение со списком мешающих объектов.
- *Альтернатива:* `SET_NULL` / `CASCADE` — противоречат «галерея всегда с категорией» и грозят потерей галерей.
- Slug — `SlugField` (латиница, цифры, `-`, `_`); в админке `prepopulated_fields = {'slug': ('title',)}` — JS админки транслитерирует кириллицу. Хранится и сравнивается как есть; ввод в верхнем регистре валидатор `SlugField` пропускает, поэтому slug приводится к нижнему регистру в `clean()` модели.

### Миграция
Одна миграция `0008_category`: `CreateModel Category` + `AddField gallery.category` сразу обязательным, без значения по умолчанию. Существующие галереи не переносятся: по решению владельца данные галереи (галереи, фото с файлами, избранное) обнуляются перед обновлением и контент перезаливается. На базе, где галереи остались, миграция упадёт — это ожидаемо.
- *Альтернатива (отклонена):* создавать категорию «Разное» и переносить в неё существующие галереи — лишний код для данных, которые всё равно удаляются.

### Чтение
- `GET /categories`: `Category.objects.annotate(galleries_count=Count('galleries')).filter(galleries_count__gt=0)` — один запрос; `GROUP BY` здесь безопасен (нет случайных подзапросов). Без пагинации: категорий единицы-десятки.
- Каталог: `with_stats()` получает `select_related('category')`; фильтр — `filter(category__slug=...)` в `GalleryListView.get_queryset` по параметру `category`. Неизвестный slug даёт пустой queryset → `{"items": [], "total": 0}` без отдельной проверки.
- `GallerySerializer.category` — вложенный `CategorySerializer` (`id` строкой, `slug`, `title`). Отдельный `CategoryListSerializer` добавляет `galleriesCount`.
- Код чтения категорий — в `services/category_queries.py` (`CategoryQueries.non_empty()`), по образцу `GalleryQueries`.

### Админка
- `CategoryAdmin`: `list_display` (title, slug, position, число галерей), `list_editable = ['position']`, `prepopulated_fields`, поиск по названию.
- `GalleryAdminForm.Meta.fields = ['title', 'category']`, `GalleryAdmin.fields = ['title', 'category', 'new_images']`; `list_display`/`list_filter` + `category`, `list_select_related` для категории.

## Risks / Trade-offs

- [`?category=` с неизвестным slug не отличить от пустой категории] → по spec это 200 с пустым списком; фронт узнаёт существующие категории из `GET /categories`.
- [`GET /categories` скрывает пустые категории, админ может удивиться, что новой категории нет на сайте] → поведение из spec; в админке видно число галерей.

## Migration Plan

1. Очистить данные галереи: `TRUNCATE gallery_favorite, gallery_photo, gallery_gallery RESTART IDENTITY` и файлы `media/original`, `media/thumb`. Пользователи остаются.
2. Применить миграции (контейнер `app` делает это при старте).
3. Откат: `migrate gallery 0007` удаляет поле и таблицу категорий.
