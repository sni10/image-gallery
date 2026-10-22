# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow>=11"]
# ///
"""SEO texts written by a local vision LLM (LM Studio, OpenAI-compatible API), on the owner's PC.

Independent of the Django project, talks only HTTP:
  1. collect: photo page URLs from the site's sitemap.xml -> seo.sqlite next to this file (status 'new');
  2. photos: for each photo not done yet: GET /photos/<id> -> image as a 1024px JPEG -> LLM -> title, description, tags ->
     PATCH /ingest/photos/<id> (X-Api-Key = INGEST_API_KEY). Existing texts are overwritten;
  3. galleries: for each gallery with done photos: its photo texts -> LLM -> description ->
     PATCH /ingest/galleries/<id>. Redone when the gallery has more done photos than last time.

    uv run custom/seo.py                    # production: collect + photos + galleries
    uv run custom/seo.py photos             # only the photo queue, no sitemap
    uv run custom/seo.py --model google/gemma-4-e4b --lm http://localhost:1234

INGEST_API_KEY: from the environment, else from the repo's .env (must be the production key for production).

Safe to rerun: done photos are skipped, errors are retried on the next run. To redo everything delete seo.sqlite.
LM Studio loads the model on the first request (the model must accept images).
"""
import argparse
import base64
import io
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DB = Path(__file__).with_name('seo.sqlite')
USER_AGENT = 'artai-seo/1.0'  # the default Python-urllib agent may be challenged by Cloudflare
SITEMAP_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
GALLERY_SAMPLE = 40  # photo texts per gallery prompt: enough to see the theme, fits any context
IMAGE_SIDE = 1024  # the 400px WebP thumbnail is too small for details, and LM Studio refuses WebP anyway

SITE = ('artai.win is an 18+ gallery of erotic art: sexy girls, nude and lingerie models, glamour '
        'and boudoir. Everyone shown is an adult woman; call her a woman, girl or model'
        'Write in English for search engines and adult visitors: seductive, sexual, sexy, lust, sensual and openly erotic, with '
        'bold sexual metaphors and words people search for (sexy, hot, nude, naked, busty, curvy, seductive, girl, '
        'model, beauty, as fits the picture); concrete and vivid, natural sentences, no keyword '
        'stuffing, never mention that you see "an image".')
PHOTO_PROMPT = (SITE + ' The picture belongs to the gallery "{gallery}". Return JSON: '
                'title: 4-9 words, what is shown, no quotes, at most 70 characters; '
                'description: 90-160 words, one or two paragraphs: subject, appearance, pose, clothing, setting, '
                'light, colors, mood and art style; '
                'tags: 10-20 lowercase English tags, a multi-word tag joined with underscores (red_hair).')
GALLERY_PROMPT = (SITE + ' Write the text of the gallery page "{gallery}" from the photos below. Return JSON: '
                  'description: 150-300 words, 2-4 paragraphs: the theme, recurring characters, settings, mood and '
                  'style of the collection, what a visitor will find here. Photos:\n{photos}')
PHOTO_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['title', 'description', 'tags'],
                'properties': {'title': {'type': 'string'}, 'description': {'type': 'string'},
                               'tags': {'type': 'array', 'items': {'type': 'string'}}}}
GALLERY_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['description'],
                  'properties': {'description': {'type': 'string'}}}


def http(url, key=None, body=None, method=None, timeout=60):
    headers = {'User-Agent': USER_AGENT, 'Content-Type': 'application/json'}
    if key:
        headers['X-Api-Key'] = key
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers, method=method), timeout=timeout) as r:
        return r.read()


def llm(lm, model, content, schema):
    body = {'model': model, 'temperature': 0.5, 'messages': [{'role': 'user', 'content': content}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'seo', 'strict': True, 'schema': schema}}}
    print(f'    llm: {model} ...', end=' ', flush=True)
    started = time.monotonic()
    answer = json.loads(http(f'{lm}/v1/chat/completions', body=body, timeout=600))  # first call loads the model
    usage = answer.get('usage') or {}
    print(f'{time.monotonic() - started:.0f}s, tokens in {usage.get("prompt_tokens")} out {usage.get("completion_tokens")}')
    message = answer['choices'][0]['message']
    # thinking models (qwen3.5) in LM Studio put the schema-constrained JSON into reasoning_content
    return json.loads(message.get('content') or message.get('reasoning_content') or '')


def jpeg_base64(url):
    from PIL import Image

    raw = http(url)
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    size = image.size
    image.thumbnail((IMAGE_SIDE, IMAGE_SIDE))
    buf = io.BytesIO()
    image.save(buf, 'JPEG', quality=85)
    print(f'    image: {len(raw) // 1024} KB {size[0]}x{size[1]} -> JPEG {buf.tell() // 1024} KB '
          f'{image.size[0]}x{image.size[1]}')
    return base64.b64encode(buf.getvalue()).decode()


def connect():
    db = sqlite3.connect(DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS photos (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'new',  -- new | done | error | gone (photo deleted)
            error TEXT,
            gallery TEXT, gallery_title TEXT, title TEXT, description TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS galleries (
            id TEXT PRIMARY KEY,
            photos INTEGER NOT NULL,  -- done photos the description was written from
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);""")
    return db


def collect(db, site):
    root = ET.fromstring(http(site.rstrip('/') + '/sitemap.xml'))
    urls = [loc.text.strip() for loc in root.iter(SITEMAP_NS + 'loc') if '/photos/' in loc.text]
    with db:
        new = db.executemany('INSERT OR IGNORE INTO photos (url) VALUES (?)', [(u,) for u in urls]).rowcount
    print(f'sitemap: {len(urls)} photo links, {new} new')


def mark(db, url, status, error=None):
    with db:
        db.execute('UPDATE photos SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE url = ?',
                   (status, error, url))


def photos(db, api, key, lm, model):
    todo = [url for (url,) in db.execute("SELECT url FROM photos WHERE status IN ('new', 'error') ORDER BY rowid")]
    print(f'photos: {len(todo)} in the queue')
    for n, url in enumerate(todo, 1):
        photo_id = url.rstrip('/').rsplit('/', 1)[-1]
        print(f'\n[{n}/{len(todo)}] {url}')
        try:
            try:
                photo = json.loads(http(f'{api}/photos/{photo_id}', key))  # the key opens locked originals
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                print('    gone: the photo was deleted')
                mark(db, url, 'gone', str(exc))
                continue
            print(f'    gallery: {photo["gallery"]["title"]} | old title: {photo["title"]}')
            image = jpeg_base64(photo['url'])
            text = llm(lm, model, [
                {'type': 'text', 'text': PHOTO_PROMPT.format(gallery=photo['gallery']['title'])},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{image}'}},
            ], PHOTO_SCHEMA)
            text = {'title': text['title'].strip().strip('"')[:200], 'description': text['description'].strip()[:5000],
                    'tags': [t.strip().lower().replace(' ', '_')[:50] for t in text['tags']][:30]}
            print(f'    title: {text["title"]}\n    tags: {", ".join(text["tags"])}\n    description: {text["description"]}')
            http(f'{api}/ingest/photos/{photo_id}', key, text, method='PATCH')
            print('    saved')
        except Exception as exc:  # one bad photo must not stop the run; retried on the next run
            detail = f' {exc.read()[:300]!r}' if isinstance(exc, urllib.error.HTTPError) else ''
            print(f'    ERROR: {exc!r}{detail}')
            mark(db, url, 'error', f'{exc!r}{detail}')
            continue
        with db:
            db.execute("""UPDATE photos SET status = 'done', error = NULL, gallery = ?, gallery_title = ?, title = ?,
                          description = ?, updated_at = CURRENT_TIMESTAMP WHERE url = ?""",
                       (photo['gallery']['id'], photo['gallery']['title'], text['title'], text['description'], url))


def galleries(db, api, key, lm, model):
    todo = db.execute("""
        SELECT p.gallery, max(p.gallery_title), count(*) FROM photos p LEFT JOIN galleries g ON g.id = p.gallery
        WHERE p.status = 'done' GROUP BY p.gallery HAVING count(*) > coalesce(max(g.photos), 0)""").fetchall()
    print(f'galleries: {len(todo)} to write')
    for gallery, title, count in todo:
        rows = db.execute('SELECT title, description FROM photos WHERE gallery = ? AND status = ? ORDER BY random() '
                          'LIMIT ?', (gallery, 'done', GALLERY_SAMPLE)).fetchall()
        listing = '\n'.join(f'- {t}: {d}' for t, d in rows)
        print(f'\n[gallery] {title} ({gallery}): {count} done photos, {len(rows)} in the prompt')
        try:
            text = llm(lm, model, GALLERY_PROMPT.format(gallery=title, photos=listing), GALLERY_SCHEMA)
            http(f'{api}/ingest/galleries/{gallery}', key, {'description': text['description'].strip()[:5000]},
                 method='PATCH')
        except Exception as exc:  # retried on the next run: the row is not saved
            print(f'    ERROR: {exc!r}')
            continue
        with db:
            db.execute('INSERT OR REPLACE INTO galleries (id, photos) VALUES (?, ?)', (gallery, count))
        print(f'    description: {text["description"]}\n    saved')


def env_file_key():
    env = Path(__file__).resolve().parent.parent / '.env'
    lines = env.read_text(encoding='utf-8').splitlines() if env.exists() else []
    return next((line.split('=', 1)[1].strip().strip('"\'') for line in lines
                 if line.startswith('INGEST_API_KEY=')), '')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('step', nargs='?', choices=['all', 'collect', 'photos', 'galleries'], default='all')
    parser.add_argument('--site', default='https://artai.win', help='where sitemap.xml is')
    parser.add_argument('--api', default='https://api.artai.win', help='API base URL')
    parser.add_argument('--lm', default='http://192.168.31.171:1234', help='LM Studio base URL')
    parser.add_argument('--model', default='qwen/qwen3.5-9b', help='LM Studio model id, must accept images')
    args = parser.parse_args()
    key = os.environ.get('INGEST_API_KEY') or env_file_key()
    if args.step != 'collect' and not key:
        sys.exit('INGEST_API_KEY is not set (environment or .env)')
    db = connect()
    api, lm = args.api.rstrip('/'), args.lm.rstrip('/')
    if args.step in ('all', 'collect'):
        collect(db, args.site)
    if args.step in ('all', 'photos'):
        photos(db, api, key, lm, args.model)
    if args.step in ('all', 'galleries'):
        galleries(db, api, key, lm, args.model)
    print('status:', dict(db.execute('SELECT status, count(*) FROM photos GROUP BY status').fetchall()))


if __name__ == '__main__':
    main()
