# ТЗ: `GET /photos/{photo_id}` для страницы фото

## Зачем

У каждой картинки появляется своя страница на сайте: `/photos/:id`. Сервер фронта рендерит её (SSR) и кладёт в `<head>`
title, description, og:image и canonical, а на странице выводит хлебные крошки «категория → галерея».
Данные для этого берутся из нового эндпоинта. Сейчас есть только `/photos` (случайные фото) и `/galleries/{id}/photos`.

## Эндпоинт

`GET /photos/{photo_id}`, путь тот же, что у `DELETE /photos/{photo_id}`.

- `photo_id` — публичный id фото (поле `id`), не pk.
- Доступ публичный: GET разрешён всем, DELETE по-прежнему только `IsAdminUser`. Разрешения задаются по методу,
  например через `get_permissions`.
- `isFavorite` заполняется как в списках (`PhotoQueries.with_is_favorite`): для анонима `false`.
- Один запрос к БД: `select_related('gallery__category')`.

### Ответ 200

Поля `PhotoSerializer` и вложенная галерея с категорией:

```json
{
  "id": "…", "title": "Neon cat", "description": "", "tags": ["cat"],
  "url": "https://api.artai.win/media/original/…", "thumbUrl": "https://api.artai.win/media/thumb/….webp",
  "width": 1024, "height": 1536, "isFavorite": false,
  "gallery": {
    "id": "…", "title": "Cats",
    "category": { "id": "…", "slug": "ai", "title": "AI" }
  }
}
```

### Коды

| Код | Когда |
| --- | --- |
| 200 | Фото найдено |
| 404 | Фото с таким id нет: удалено или id перевыпущен (`reissue_links`). Так и задумано, отдельной обработки не нужно |

- Описать в OpenAPI (`extend_schema`), как соседние эндпоинты, и добавить путь в `PATHS` в `test_openapi.py`
  (если `/photos/{photo_id}` там ещё нет).

## Тесты

- Аноним получает 200 и все поля выше, включая `gallery.category`.
- Неизвестный id даёт 404.
- Существующие тесты DELETE остаются зелёными: GET не должен открыть удаление.

Сообщение для коммита: `feat(api): add photo detail endpoint for the photo page`.

## Фронт

Фронт уже сделан под этот контракт (тип `PhotoDetail` в `src/api.ts`). Пока эндпоинта нет, страница `/photos/:id`
показывает ошибку. Лайтбокс и сетка работают как раньше.
