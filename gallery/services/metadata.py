"""Remove metadata from an original without re-encoding it.

Removed: EXIF (camera, GPS, ...), XMP, IPTC, comments, PNG text (ComfyUI writes its prompt and the whole workflow,
including node fields such as API keys, there). Kept: the ICC profile (colors) and the EXIF orientation (rotation),
rewritten as a minimal EXIF block. JPEG/PNG/WebP/GIF are cleaned at the byte level, pixels stay bit for bit the same.
Cleaning is idempotent: cleaning an already clean file returns the same bytes (file names are content hashes).
"""
import struct
import zlib
from io import BytesIO

from PIL import Image

ORIENTATION = 0x0112
EXIF_HEADER = b'Exif\x00\x00'


def strip_metadata(data: bytes, image_format: str) -> bytes:
    """`image_format` is Pillow's format name (a key of SUPPORTED_FORMATS). ValueError if the file is broken."""
    try:
        return _STRIPPERS[image_format](data)
    except (IndexError, struct.error, OSError) as exc:  # truncated file: a length points past the end
        raise ValueError(f'broken {image_format} file') from exc


def _orientation(data: bytes) -> int:
    with Image.open(BytesIO(data)) as img:
        return img.getexif().get(ORIENTATION, 1)


def _minimal_exif(orientation: int) -> bytes:
    """TIFF-structured EXIF with only the orientation tag, without the 'Exif\\0\\0' prefix."""
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    return exif.tobytes().removeprefix(EXIF_HEADER)


# --- JPEG: segments before the first SOS; everything after the image's EOI (e.g. MPF extra images) is dropped

def _strip_jpeg(data: bytes) -> bytes:
    if data[:2] != b'\xff\xd8':
        raise ValueError('not a JPEG')
    orientation = _orientation(data)
    out = bytearray(b'\xff\xd8')
    if orientation != 1:
        payload = EXIF_HEADER + _minimal_exif(orientation)
        out += b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
    pos = 2
    while True:
        if data[pos] != 0xFF:
            raise ValueError('broken JPEG segment')
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker == 0xDA:  # SOS: entropy-coded data up to the end of the image
            end = data.find(b'\xff\xd9', pos)
            return bytes(out + data[pos:end + 2 if end != -1 else len(data)])
        length = struct.unpack('>H', data[pos + 2:pos + 4])[0]
        segment = data[pos:pos + 2 + length]
        if _keep_jpeg_segment(marker, segment[4:]):
            out += segment
        pos += 2 + length


def _keep_jpeg_segment(marker: int, payload: bytes) -> bool:
    if marker == 0xFE:  # COM
        return False
    if 0xE0 <= marker <= 0xEF:  # APPn: keep JFIF/JFXX (APP0), ICC (APP2) and Adobe color transform (APP14)
        return (marker == 0xE0 or (marker == 0xE2 and payload.startswith(b'ICC_PROFILE\x00'))
                or (marker == 0xEE and payload.startswith(b'Adobe')))
    return True


# --- PNG: chunk list; text and EXIF chunks dropped, orientation written back as eXIf

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_DROP = {b'tEXt', b'zTXt', b'iTXt', b'eXIf', b'tIME'}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def _strip_png(data: bytes) -> bytes:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('not a PNG')
    orientation = _orientation(data)
    out, pos = bytearray(PNG_SIGNATURE), len(PNG_SIGNATURE)
    exif_pending = orientation != 1
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if kind == b'IDAT' and exif_pending:  # eXIf must come before the image data
            out += _png_chunk(b'eXIf', _minimal_exif(orientation))
            exif_pending = False
        if kind not in PNG_DROP:
            out += data[pos:end]
        pos = end
        if kind == b'IEND':
            break
    return bytes(out)


# --- WebP: RIFF chunks; EXIF/XMP dropped (VP8X flags updated), orientation written back as EXIF

WEBP_EXIF_FLAG, WEBP_XMP_FLAG = 0x08, 0x04


def _riff_chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack('<I', len(payload)) + payload + (b'\x00' if len(payload) % 2 else b'')


def _strip_webp(data: bytes) -> bytes:
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        raise ValueError('not a WebP')
    chunks, pos = [], 12
    while pos + 8 <= len(data):
        kind, size = data[pos:pos + 4], struct.unpack('<I', data[pos + 4:pos + 8])[0]
        chunks.append((kind, data[pos + 8:pos + 8 + size]))
        pos += 8 + size + size % 2
    if not any(kind == b'VP8X' for kind, _ in chunks):  # simple WebP: no metadata possible
        return data
    orientation = _orientation(data)
    body = bytearray()
    for kind, payload in chunks:
        if kind in (b'EXIF', b'XMP '):
            continue
        if kind == b'VP8X':
            flags = payload[0] & ~(WEBP_EXIF_FLAG | WEBP_XMP_FLAG) | (WEBP_EXIF_FLAG if orientation != 1 else 0)
            payload = bytes([flags]) + payload[1:]
        body += _riff_chunk(kind, payload)
    if orientation != 1:  # EXIF goes after the image data
        body += _riff_chunk(b'EXIF', _minimal_exif(orientation))
    return b'RIFF' + struct.pack('<I', len(body) + 4) + b'WEBP' + bytes(body)


# --- GIF: comment and application extensions dropped, except the animation loop count (NETSCAPE2.0)

GIF_LOOP_APPS = (b'NETSCAPE2.0', b'ANIMEXTS1.0')


def _gif_sub_blocks_end(data: bytes, pos: int) -> int:
    while data[pos]:
        pos += data[pos] + 1
    return pos + 1


def _strip_gif(data: bytes) -> bytes:
    if data[:3] != b'GIF':
        raise ValueError('not a GIF')
    pos = 13
    if data[10] & 0x80:  # global color table
        pos += 3 * 2 ** ((data[10] & 0x07) + 1)
    out = bytearray(data[:pos])
    while pos < len(data):
        block = data[pos]
        if block == 0x3B:  # trailer
            return bytes(out + b'\x3b')
        if block == 0x2C:  # image descriptor (+ local color table) + LZW data
            start, flags = pos, data[pos + 9]
            pos += 10 + (3 * 2 ** ((flags & 0x07) + 1) if flags & 0x80 else 0) + 1
            pos = _gif_sub_blocks_end(data, pos)
            out += data[start:pos]
        elif block == 0x21:  # extension
            start, label = pos, data[pos + 1]
            pos = _gif_sub_blocks_end(data, pos + 2)
            app_id = data[start + 3:start + 14] if label == 0xFF else b''
            if label != 0xFE and (label != 0xFF or app_id in GIF_LOOP_APPS):
                out += data[start:pos]
        else:
            raise ValueError('broken GIF block')
    return bytes(out + b'\x3b')


# --- AVIF: metadata lives in ISOBMFF items with absolute offsets; editing bytes is fragile, so re-encode,
# but only when there is something to remove (clean files stay untouched and idempotent)
# ponytail: byte-level AVIF cleanup if re-encoding quality ever matters

def _strip_avif(data: bytes) -> bytes:
    with Image.open(BytesIO(data)) as img:
        if not (img.info.get('exif') or img.info.get('xmp')):
            return data
        orientation = img.getexif().get(ORIENTATION, 1)
        buf = BytesIO()
        img.save(buf, 'AVIF', quality=90, save_all=getattr(img, 'is_animated', False),
                 icc_profile=img.info.get('icc_profile'),
                 exif=EXIF_HEADER + _minimal_exif(orientation) if orientation != 1 else b'')
        return buf.getvalue()


_STRIPPERS = {'JPEG': _strip_jpeg, 'PNG': _strip_png, 'WEBP': _strip_webp, 'GIF': _strip_gif, 'AVIF': _strip_avif}
