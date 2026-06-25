"""Safe image handling for photo greeting cards.

Validates uploads (type + size + real-image content), fixes orientation, strips
ALL metadata (EXIF/GPS) by re-encoding, flattens transparency, and produces a
display-sized JPEG plus a small thumbnail. The original upload is never stored.
"""

import io
import secrets
import warnings

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_SIDE = 1600
THUMB_SIDE = 480
_PORCELAIN = (250, 244, 234)

# Decompression-bomb guard: a tiny PNG/WEBP can declare enormous dimensions and
# blow up RAM when decoded. Cap total pixels (~50MP covers any real phone photo)
# and turn Pillow's bomb warning into a hard error so it lands in our except.
Image.MAX_IMAGE_PIXELS = 50_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)


class ImageError(Exception):
    """Carries a friendly Arabic message for an invalid upload."""


def validate_upload(f):
    """Cheap pre-checks on size and claimed type. Raises ImageError."""
    if f.size and f.size > MAX_UPLOAD_BYTES:
        raise ImageError("حجم الصورة كبير جداً — الحدّ الأقصى ٥ ميجابايت.")
    ext = (f.name.rsplit(".", 1)[-1] if "." in f.name else "").lower()
    ctype = (getattr(f, "content_type", "") or "").lower()
    # The extension must be in the allow-list; if a content-type is present it
    # must match too. Both are attacker-controlled, so process_image re-checks the
    # real decoded format — this is just the cheap first gate.
    if ext not in ALLOWED_EXTENSIONS:
        raise ImageError("صيغة الصورة غير مدعومة — استخدم JPG أو PNG أو WEBP.")
    if ctype and ctype not in ALLOWED_CONTENT_TYPES:
        raise ImageError("صيغة الصورة غير مدعومة — استخدم JPG أو PNG أو WEBP.")


def _flatten(img):
    """Honour EXIF orientation, drop metadata, flatten transparency to RGB."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, _PORCELAIN)
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def _encode(img, max_side, quality, suffix):
    out = img.copy()
    out.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=quality, optimize=True)
    return ContentFile(buf.getvalue(), name=suffix)


def process_image(uploaded):
    """Return (display_file, thumb_file) optimized JPEGs, or raise ImageError.

    Verifies real image content (guards truncated files & decompression bombs),
    strips metadata, and resizes to <=1600px (display) and <=480px (thumbnail).
    """
    try:
        uploaded.seek(0)
        with Image.open(uploaded) as probe:
            probe.verify()  # catches non-images / truncated data
        uploaded.seek(0)
        img = Image.open(uploaded)
        # Enforce the allow-list on the DECODED format (not the extension), and
        # reject pixel-floods from the header BEFORE allocating any pixels.
        if (img.format or "").upper() not in _ALLOWED_PIL_FORMATS:
            raise ImageError("صيغة الصورة غير مدعومة — استخدم JPG أو PNG أو WEBP.")
        if img.size[0] * img.size[1] > Image.MAX_IMAGE_PIXELS:
            raise ImageError("أبعاد الصورة كبيرة جداً — جرّب صورة بدقّة أقل.")
        img.load()
    except ImageError:
        raise  # keep the specific friendly message
    except Exception:  # noqa: BLE001 — any decode failure → one friendly error
        raise ImageError("تعذّر قراءة الصورة — تأكّد أنها صورة صحيحة.")

    img = _flatten(img)
    token = secrets.token_hex(10)  # unguessable filename
    display = _encode(img, MAX_SIDE, 85, f"{token}.jpg")
    thumb = _encode(img, THUMB_SIDE, 82, f"{token}_t.jpg")
    return display, thumb
