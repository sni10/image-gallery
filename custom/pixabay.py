# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28"]
# ///
"""Fill the site with free Pixabay clipart: GALLERIES below, PER_GALLERY images each, through POST /ingest/photos.

    uv run custom/pixabay.py                       # keys: PIXABAY_API_KEY, INGEST_API_KEY in .env
    ... uv run custom/pixabay.py --api http://localhost:8080

Categories: created by the server if missing (or in the admin). Galleries are found or created by title. Safe to rerun: the server dedupes
identical files within a gallery (200 instead of 201). Pixabay links expire and must not be hotlinked, so files
are downloaded and uploaded right away. The author goes into the description (the license doesn't require it).
"""
import argparse
import os
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

# Keys: env vars, else the project's .env (gitignored)
_ENV_FILE = Path(__file__).resolve().parent.parent / '.env'
_DOTENV = dict(line.split('=', 1) for line in _ENV_FILE.read_text(encoding='utf-8').splitlines()
               if '=' in line and not line.lstrip().startswith('#')) if _ENV_FILE.exists() else {}
PIXABAY_API_KEY = os.environ.get('PIXABAY_API_KEY') or _DOTENV.get('PIXABAY_API_KEY', '').strip().strip('"\'')
INGEST_API_KEY = os.environ.get('INGEST_API_KEY') or _DOTENV.get('INGEST_API_KEY', '').strip().strip('"\'')

DONE = Path(__file__).with_name('pixabay_done.txt')  # uploaded Pixabay ids, one per line: reruns skip them
DOWNLOAD_PAUSE = 1.5  # seconds between image downloads (the CDN limits them too)
PER_GALLERY = 50  # Pixabay per_page allows up to 200, so one search per gallery
CATEGORIES = ['demo', 'testing', 'additional']  # round-robin: 1st gallery -> demo, 2nd -> testing, 3rd -> additional, ...
GALLERIES = {  # title -> Pixabay query; 30 galleries, realistic photos
    'Mountains': 'mountains',
    'Beaches': 'beaches',
    'Forests': 'forests',
    'Waterfalls': 'waterfalls',
    'Deserts': 'deserts',
    'Sunsets': 'sunsets',
    'Night Sky': 'night sky',
    'Autumn': 'autumn',
    'Winter Snow': 'winter snow',
    'Roses': 'roses',
    'Cats': 'cats',
    'Dogs': 'dogs',
    'Horses': 'horses',
    'Birds': 'birds',
    'Wild Animals': 'wild animals',
    'Underwater': 'underwater',
    'Butterflies': 'butterflies',
    'Fruits': 'fruits',
    'Desserts': 'desserts',
    'Coffee': 'coffee',
    'Cities': 'cities',
    'Night City': 'night city',
    'Architecture': 'architecture',
    'Castles': 'castles',
    'Bridges': 'bridges',
    'Cars': 'cars',
    'Trains': 'trains',
    'Airplanes': 'airplanes',
    'Portraits': 'portraits',
    'Technology': 'technology',
}


def search(http, key, query, image_type):
    """One API request per gallery (30 total), far below 100/60 s; image downloads go to the CDN, not the API.
    Still honours the limit headers: waits out the window on 429 or when it is about to run out."""
    while True:
        r = http.get('https://pixabay.com/api/', params={
            'key': key, 'q': query, 'image_type': image_type, 'safesearch': 'true', 'per_page': PER_GALLERY})
        reset = int(r.headers.get('X-RateLimit-Reset', 60))
        if r.status_code == 429:
            print(f'Pixabay rate limit, waiting {reset} s', flush=True)
            time.sleep(reset + 1)
            continue
        if int(r.headers.get('X-RateLimit-Remaining', 100)) < 2:
            time.sleep(reset + 1)
        break
    if r.status_code != 200:  # httpx errors carry the URL and with it the key: say less
        sys.exit(f'Pixabay: {r.status_code} {r.text[:200]}')
    return r.json()['hits']


def upload(http, api, key, category, gallery, hit):
    # The image CDN has its own rate limit (429 "Rate limit exceeded"): pace downloads, wait it out on 429.
    # ponytail: fixed pause + waits; tune DOWNLOAD_PAUSE if 429s still show up
    for attempt in range(10):
        time.sleep(DOWNLOAD_PAUSE)
        image = http.get(hit['largeImageURL'])
        if image.status_code != 429:
            break
        wait = int(image.headers.get('Retry-After') or 30 * (attempt + 1))
        print(f'  CDN rate limit, waiting {wait} s', flush=True)
        time.sleep(wait)
    image.raise_for_status()
    tags = [t.strip() for t in hit['tags'].split(',') if t.strip()][:30]
    author = f'https://pixabay.com/users/{hit["user"]}-{hit["user_id"]}/'
    r = http.post(f'{api}/ingest/photos', headers={'X-Api-Key': key}, data={
        'category': category, 'galleryTitle': gallery,
        'title': (tags[0] if tags else gallery).capitalize(),
        'description': f'Author: {hit["user"]} ({author}). Source: {hit["pageURL"]} (Pixabay License).',
        'tags': ', '.join(t[:50] for t in tags),
    }, files={'image': (f'pixabay-{hit["id"]}{PurePosixPath(urlsplit(hit["largeImageURL"]).path).suffix}',
                        image.content)})
    r.raise_for_status()
    return r.status_code


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--api', default='https://api.artai.win', help='API base URL')
    parser.add_argument('--type', default='photo', choices=['illustration', 'vector', 'photo', 'all'],
                        help='Pixabay image_type')
    args = parser.parse_args()
    pixabay_key, ingest_key = PIXABAY_API_KEY, INGEST_API_KEY
    if not (pixabay_key and ingest_key):
        sys.exit('Set PIXABAY_API_KEY and INGEST_API_KEY in .env')

    # the default Python agent may be challenged by Cloudflare (see embed.py)
    with httpx.Client(timeout=60, headers={'User-Agent': 'artai-pixabay/1.0'}, follow_redirects=True) as http:
        done = set(DONE.read_text().split()) if DONE.exists() else set()
        for i, (gallery, query) in enumerate(GALLERIES.items()):
            category = CATEGORIES[i % len(CATEGORIES)]
            new = old = failed = 0
            for hit in search(http, pixabay_key, query, args.type):
                if str(hit['id']) in done:  # uploaded before: don't spend the CDN limit on it again
                    old += 1
                    continue
                try:
                    if upload(http, args.api, ingest_key, category, gallery, hit) == 201:
                        new += 1
                    else:
                        old += 1
                    done.add(str(hit['id']))
                    with DONE.open('a') as f:
                        f.write(f'{hit["id"]}\n')
                    print(f'{gallery} {new + old + failed}/{PER_GALLERY}: pixabay-{hit["id"]} by {hit["user"]}',
                          flush=True)
                except httpx.HTTPError as exc:
                    failed += 1
                    body = exc.response.text[:200] if isinstance(exc, httpx.HTTPStatusError) else ''
                    print(f'  pixabay-{hit["id"]}: {type(exc).__name__} {body}', file=sys.stderr)
            print(f'{category}/{gallery}: {new} new, {old} already there, {failed} failed')


if __name__ == '__main__':
    main()
