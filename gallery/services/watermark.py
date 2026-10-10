"""'ArtAI.win' in a corner of full-size images (picked per image). Needs only Pillow: no Django, no project imports.

As a module: `watermark(data) -> bytes` (the app calls it on upload, see SPEC-watermark.md).
As a script: watermarks every existing full-size image in place and keeps the clean original aside:

    python watermark.py <public originals dir> <clean copies dir> [--dry-run] [--force]

    docker compose -f compose.prod.yaml exec app \\
        python gallery/services/watermark.py /app/media/original /app/originals/original

Safe to stop and re-run. A file counts as done when its clean copy exists and differs from the public file.
--force re-renders every public file from its clean copy (after changing the watermark's look).
"""
import argparse
import hashlib
import os
import shutil
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

TEXT = 'ArtAI.win'
FONT_SHARE = 0.04    # font size relative to the shorter side
MIN_FONT = 12        # px: tiny images still get a readable mark
FILL = (255, 255, 255, 150)   # semi-transparent white...
STROKE = (0, 0, 0, 110)       # ...with a dark outline, visible on light and dark backgrounds
SAVE_OPTIONS = {'JPEG': {'quality': 95}, 'WEBP': {'quality': 95}, 'AVIF': {'quality': 90}, 'PNG': {}, 'GIF': {}}


def watermark(data: bytes) -> bytes:
    """Same format, EXIF orientation applied to the pixels, ICC profile kept, other metadata dropped.
    Deterministic: the same input gives the same bytes. Animated images come back unchanged."""
    with Image.open(BytesIO(data)) as src:
        fmt = src.format
        if fmt not in SAVE_OPTIONS:
            raise ValueError(f'{fmt} is not supported')
        if getattr(src, 'is_animated', False):  # ponytail: frames are not marked; mark each frame if this matters
            return data
        icc = src.info.get('icc_profile')
        img = ImageOps.exif_transpose(src)
        alpha = img.has_transparency_data
        corner = hashlib.sha256(data).digest()[0] % 4  # random-looking but stable: re-runs give the same bytes
        marked = _draw(img.convert('RGBA'), corner)

    if fmt == 'JPEG' or not alpha:
        marked = marked.convert('RGB')
    buf = BytesIO()
    marked.save(buf, fmt, **SAVE_OPTIONS[fmt], **({'icc_profile': icc} if icc else {}))
    return buf.getvalue()


def _draw(img: Image.Image, corner: int) -> Image.Image:
    """corner: 0 bottom right, 1 bottom left, 2 top right, 3 top left; margin from the edges."""
    size = max(MIN_FONT, round(min(img.size) * FONT_SHARE))
    font = ImageFont.load_default(size=size)  # Pillow's bundled scalable font: no font file to ship
    stroke = max(1, size // 15)
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    left, top, right, bottom = draw.textbbox((0, 0), TEXT, font=font, stroke_width=stroke)
    margin = round(size * 0.8)
    x = margin - left if corner % 2 else img.width - right - margin
    y = margin - top if corner >= 2 else img.height - bottom - margin
    xy = (x, y)
    draw.text(xy, TEXT, font=font, fill=FILL, stroke_width=stroke, stroke_fill=STROKE)
    return Image.alpha_composite(img, overlay)


def backfill(public_dir: Path, clean_dir: Path, dry_run=False, force=False) -> dict:
    counts = {'marked': 0, 'done': 0, 'animated': 0, 'failed': 0}
    for public in sorted(p for p in public_dir.rglob('*') if p.is_file() and not p.name.startswith('.')):
        clean = clean_dir / public.relative_to(public_dir)
        current = public.read_bytes()
        if clean.exists() and not force and clean.read_bytes() != current:
            counts['done'] += 1
            continue
        try:
            source = clean.read_bytes() if clean.exists() else current
            result = watermark(source)
        except Exception as exc:  # a broken file must not stop the run
            print(f'FAILED {public}: {exc}', file=sys.stderr)
            counts['failed'] += 1
            continue
        if result == source:
            counts['animated'] += 1
            continue
        if not dry_run:
            if not clean.exists():  # clean copy first: a crash after this leaves public == clean -> redone
                clean.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(public, clean)
            tmp = public.with_name(public.name + '.tmp')
            tmp.write_bytes(result)
            os.replace(tmp, public)  # atomic: readers see the old or the new file, never half of it
        counts['marked'] += 1
        print(f'{"would mark" if dry_run else "marked"} {public}')
    return counts


def main():
    parser = argparse.ArgumentParser(description='Watermark existing full-size images in place, keep clean copies.')
    parser.add_argument('public_dir', type=Path, help='served originals, e.g. /app/media/original')
    parser.add_argument('clean_dir', type=Path, help='private clean copies, e.g. /app/originals/original')
    parser.add_argument('--dry-run', action='store_true', help='only list what would change')
    parser.add_argument('--force', action='store_true', help='re-render every file from its clean copy')
    args = parser.parse_args()
    if not args.public_dir.is_dir():
        parser.error(f'{args.public_dir} is not a directory')
    if args.clean_dir.resolve().is_relative_to(args.public_dir.resolve()):
        parser.error('clean_dir must be outside public_dir, or clean copies would be served and watermarked')
    counts = backfill(args.public_dir, args.clean_dir, args.dry_run, args.force)
    print(', '.join(f'{k}: {v}' for k, v in counts.items()))
    sys.exit(1 if counts['failed'] else 0)


if __name__ == '__main__':
    main()
