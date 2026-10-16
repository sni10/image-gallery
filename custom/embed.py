# /// script
# requires-python = ">=3.12"
# dependencies = ["open_clip_torch>=3.2", "timm>=1.0.20", "torch>=2.8", "pillow>=11", "numpy<2.5"]
# ///
# numpy: 2.5 breaks `import torch._dynamo` in torch 2.14 (torchvision imports it); lift when torch catches up
"""Photo vectors for visual similarity, computed on the owner's PC (the server has 1 vCPU and no room for torch).

Independent of the Django project, talks only HTTP:
  1. collect: photo page URLs from the site's sitemap.xml -> links.sqlite next to this file (status 'new');
  2. process: for each link not done yet: GET /photos/<id> -> thumbUrl -> SigLIP 2 vector ->
     POST /ingest/embeddings (X-Api-Key = INGEST_API_KEY) -> link marked 'done'.

    INGEST_API_KEY=... uv run custom/embed.py                  # production: collect + process
    INGEST_API_KEY=... uv run custom/embed.py process          # only the queue, no sitemap
    INGEST_API_KEY=... uv run custom/embed.py --site http://localhost:8080 --api http://localhost:8080

Safe to rerun: links are stored once, done ones are skipped, errors are retried on the next run.
The first run downloads the model (~800 MB) into the Hugging Face cache.
GPU: PyPI torch on Windows is CPU-only (fine for a few thousand 400px thumbnails). NVIDIA card (driver 570+):
    uv run --index https://download.pytorch.org/whl/cu128 custom/embed.py
"loading ... on cuda" in the output = the GPU is used.
"""
import argparse
import io
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

MODEL = 'siglip2-vit-b-16'  # the name the server stores; a new model = new name (and wipe links.sqlite)
HF_MODEL = 'hf-hub:timm/ViT-B-16-SigLIP2'
BATCH = 32
DB = Path(__file__).with_name('links.sqlite')
USER_AGENT = 'artai-embedder/1.0'  # the default Python-urllib agent may be challenged by Cloudflare
SITEMAP_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def http(url, key=None, body=None):
    headers = {'User-Agent': USER_AGENT, 'Content-Type': 'application/json'}
    if key:
        headers['X-Api-Key'] = key
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=60) as r:
        return r.read()


def connect():
    db = sqlite3.connect(DB)
    db.execute("""CREATE TABLE IF NOT EXISTS links (
        url TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'new',  -- new | done | error | gone (photo deleted)
        error TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    return db


def collect(db, site):
    root = ET.fromstring(http(site.rstrip('/') + '/sitemap.xml'))
    urls = [loc.text.strip() for loc in root.iter(SITEMAP_NS + 'loc') if '/photos/' in loc.text]
    with db:
        new = db.executemany('INSERT OR IGNORE INTO links (url) VALUES (?)', [(u,) for u in urls]).rowcount
    print(f'sitemap: {len(urls)} photo links, {new} new')


def mark(db, url, status, error=None):
    with db:
        db.execute('UPDATE links SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE url = ?',
                   (status, error, url))


def process(db, api, key):
    from PIL import Image  # heavy imports only when there is work: `collect` alone stays fast
    import open_clip
    import torch

    todo = [url for (url,) in db.execute("SELECT url FROM links WHERE status IN ('new', 'error') ORDER BY rowid")]
    print(f'queue: {len(todo)} links')
    if not todo:
        return
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'loading {HF_MODEL} on {device}')
    model, preprocess = open_clip.create_model_from_pretrained(HF_MODEL, device=device)
    model.eval()

    for start in range(0, len(todo), BATCH):
        batch = []  # (url, photo id, tensor)
        for url in todo[start:start + BATCH]:
            photo_id = url.rstrip('/').rsplit('/', 1)[-1]
            try:
                thumb = json.loads(http(f'{api}/photos/{photo_id}'))['thumbUrl']
                batch.append((url, photo_id, preprocess(Image.open(io.BytesIO(http(thumb))).convert('RGB'))))
            except urllib.error.HTTPError as exc:
                mark(db, url, 'gone' if exc.code == 404 else 'error', str(exc))
            except Exception as exc:  # one broken thumbnail must not stop the run
                mark(db, url, 'error', str(exc))
        if not batch:
            continue
        with torch.no_grad():
            images = torch.stack([t for _, _, t in batch]).to(device)
            vectors = model.encode_image(images, normalize=True).float().cpu().tolist()
        result = json.loads(http(f'{api}/ingest/embeddings', key, {'model': MODEL, 'items': [
            {'id': photo_id, 'vector': v} for (_, photo_id, _), v in zip(batch, vectors)
        ]}))
        unknown = set(result['unknown'])  # deleted between the GET and the POST
        for url, photo_id, _ in batch:
            mark(db, url, 'gone' if photo_id in unknown else 'done')
        print(f'  {min(start + BATCH, len(todo))}/{len(todo)}')

    print('status:', dict(db.execute('SELECT status, count(*) FROM links GROUP BY status').fetchall()))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('step', nargs='?', choices=['all', 'collect', 'process'], default='all')
    parser.add_argument('--site', default='https://artai.win', help='where sitemap.xml is')
    parser.add_argument('--api', default='https://api.artai.win', help='API base URL')
    args = parser.parse_args()
    db = connect()
    if args.step in ('all', 'collect'):
        collect(db, args.site)
    if args.step in ('all', 'process'):
        key = os.environ.get('INGEST_API_KEY') or sys.exit('Set INGEST_API_KEY (the same key as the server .env)')
        process(db, args.api.rstrip('/'), key)


if __name__ == '__main__':
    main()
