# /// script
# requires-python = ">=3.12"
# dependencies = ["open_clip_torch>=3.2", "timm>=1.0.20", "torch>=2.8", "pillow>=11"]
# ///
"""Computes SigLIP 2 vectors for photos that have none and sends them to the gallery API.

Runs on the owner's PC, not on the server (the server has 1 vCPU and no room for torch). Independent of the
Django project: only the HTTP API (GET/POST /ingest/embeddings, header X-Api-Key = INGEST_API_KEY).

    INGEST_API_KEY=... uv run embed_photos.py                       # production, https://api.artai.win
    INGEST_API_KEY=... uv run embed_photos.py --api http://localhost:8080

Safe to rerun at any time: it only asks for photos without a vector, so an interrupted run just continues.
The first run downloads the model (~800 MB) into the Hugging Face cache.
GPU: PyPI torch on Windows is CPU-only; CPU handles a few thousand 400px thumbnails in minutes. For CUDA add
`--with torch --index https://download.pytorch.org/whl/cu128` (match your CUDA) to `uv run`.
"""
import argparse
import io
import json
import os
import sys
import urllib.request

import open_clip
import torch
from PIL import Image

MODEL = 'siglip2-vit-b-16'  # the name the server stores; change it together with HF_MODEL to re-embed everything
HF_MODEL = 'hf-hub:timm/ViT-B-16-SigLIP2'
BATCH = 32
USER_AGENT = 'artai-embedder/1.0'  # the default Python-urllib agent may be challenged by Cloudflare


def request(url, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {'X-Api-Key': key, 'Content-Type': 'application/json',
                                             'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return Image.open(io.BytesIO(r.read())).convert('RGB')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--api', default='https://api.artai.win', help='API base URL')
    args = parser.parse_args()
    key = os.environ.get('INGEST_API_KEY') or sys.exit('Set INGEST_API_KEY (the same key as the server .env)')
    endpoint = args.api.rstrip('/') + '/ingest/embeddings'

    missing = request(f'{endpoint}?model={MODEL}', key)['items']
    print(f'{len(missing)} photos without a vector')
    if not missing:
        return

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'loading {HF_MODEL} on {device}')
    model, preprocess = open_clip.create_model_from_pretrained(HF_MODEL, device=device)
    model.eval()

    saved = failed = 0
    for start in range(0, len(missing), BATCH):
        ids, images = [], []
        for item in missing[start:start + BATCH]:
            try:
                images.append(preprocess(download(item['thumbUrl'])))
                ids.append(item['id'])
            except Exception as exc:  # one broken or deleted thumbnail must not stop the run
                failed += 1
                print(f'  skip {item["id"]}: {exc}', file=sys.stderr)
        if not ids:
            continue
        with torch.no_grad():
            vectors = model.encode_image(torch.stack(images).to(device), normalize=True).float().cpu().tolist()
        result = request(endpoint, key, {'model': MODEL, 'items': [
            {'id': i, 'vector': v} for i, v in zip(ids, vectors)
        ]})
        saved += result['saved']
        print(f'  {min(start + BATCH, len(missing))}/{len(missing)}: saved {saved}, failed {failed}')
    print(f'done: saved {saved}, failed {failed}')


if __name__ == '__main__':
    main()
