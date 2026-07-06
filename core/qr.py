"""Inline SVG QR codes for invitation links (panel).

Rendered inline (no media file) so a token never lands under the public,
unauthenticated /media/ path. Degrades gracefully to "" if the optional
``qrcode`` package is unavailable, so the panel never breaks over a missing QR.
"""

import io
import re

try:  # optional dependency — see requirements.txt
    import qrcode
    from qrcode.image.svg import SvgPathImage
    _HAS_QR = True
except Exception:  # noqa: BLE001
    _HAS_QR = False

_SIZE_RE = re.compile(r'\swidth="[^"]*"\sheight="[^"]*"')


def qr_svg(data, *, fill="#4f1822"):
    """Return a responsive, recolored inline SVG string for ``data`` (or "")."""
    if not (_HAS_QR and data):
        return ""
    q = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(data)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(image_factory=SvgPathImage).save(buf)
    svg = buf.getvalue().decode("utf-8")
    svg = svg.split("?>", 1)[-1].lstrip()                       # drop the XML prolog
    # Fixed mm size → responsive; fill is inherited by the (unfilled) path.
    svg = _SIZE_RE.sub("", svg, count=1)
    svg = svg.replace("<svg ", f'<svg width="100%" height="100%" fill="{fill}" ', 1)
    return svg
