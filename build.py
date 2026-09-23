#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAREK CUTS — static site builder
==============================================================================

Python is the BUILD environment only. Everything this script produces (``dist/``)
is plain HTML5 + CSS3 + vanilla JavaScript that runs on any static host, including
Render Static Sites. There is no Python server, no backend, no database — after
the build you can delete Python entirely and the site still works.

Standard library only. No pip install, no Pillow, no external tooling.

Usage
-----
    python build.py              # build (downloads only the assets it is missing)
    python build.py --refresh    # re-download every remote asset
    python build.py --offline    # never touch the network (uses cached assets)

What it does
------------
1.  Validates ``content/*.json`` (and reports remaining [PLACEHOLDER]s).
2.  Asset pipeline:
      * trims the transparent padding from assets-src/logo.png and emits
        logo.png / logo-sm.png (+ favicons composited on an ink plate)
      * self-hosts the Spectral + Inter woff2 files (latin / latin-ext)
      * downloads hero / about / gallery photography at several widths
3.  Renders ``dist/index.html`` + ``dist/legal/*.html`` with Slovak baked into
    the HTML (readable with JavaScript disabled) and data-i18n hooks for the
    EN switch.
4.  Emits ``dist/site-config.js`` content, ``styles.css``, ``script.js``,
    ``sitemap.xml`` and ``robots.txt``.
5.  Cross-checks the result: every data-i18n key exists, no unreplaced tokens,
    every local url() in the CSS resolves, and every asset was written.

Directory map
-------------
    content/          <- EDIT THESE (business, services, prices, hours, i18n, legal)
    templates/        <- HTML shell with {{TOKEN}} placeholders
    src/              <- styles.css + js modules (concatenated into script.js)
    assets-src/       <- your logo.png (and any local photos you prefer)
    dist/             <- GENERATED. This is what you deploy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
LEGAL_CONTENT_DIR = CONTENT_DIR / "legal"
TEMPLATE_DIR = ROOT / "templates"
PARTIAL_DIR = TEMPLATE_DIR / "partials"
SRC_DIR = ROOT / "src"
JS_DIR = SRC_DIR / "js"
ASSET_SRC_DIR = ROOT / "assets-src"

DIST = ROOT / "dist"
DIST_ASSETS = DIST / "assets"
DIST_IMG = DIST_ASSETS / "img"
DIST_FONTS = DIST_ASSETS / "fonts"
DIST_LEGAL = DIST / "legal"

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
LOGO_TARGET_WIDTH = 900        # hero lock-up width (never upscaled)
LOGO_HERO_MAX_HEIGHT = 372     # 2x the tallest the hero renders the artwork (CSS: 186px)
LOGO_PAD_X = 0.10              # transparent margin around the trimmed artwork
LOGO_PAD_Y = 0.16              # (room for the feather to fade the soft cloud)
LOGO_SM_HEIGHT = 120           # header / drawer / footer lock-up height (CSS: 46px -> 2.5x)
HERO_WIDTHS = (960, 1600, 2200)
ABOUT_WIDTHS = (560, 900, 1300)
GALLERY_WIDTHS = (520, 900, 1400)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Display: Spectral (moderate-contrast serif, legible at card-heading sizes).
# Only weights 400 and 600 are requested because that is all the design system
# uses for the display family — see "display-font weights" in src/styles.css.
# Body: Inter as a variable font (300-700).
FONT_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Spectral:wght@400;600"
    "&family=Inter:wght@300..700"
    "&display=swap"
)
FONT_SUBSETS = ("latin", "latin-ext")
INK_PLATE = (0x0A, 0x0A, 0x0B)   # must match --ink-900 in src/styles.css
FAVICON_SVG_SIZE = 96             # embedded in favicon.svg (kept small on purpose)
ART_ALPHA_THRESHOLD = 170         # alpha above this counts as the crisp logo artwork
                                  # (the supplied logo has a soft halo that would
                                  # otherwise make the crop span the whole canvas)

# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def info(msg: str) -> None:
    print(f"  {msg}")


def step(msg: str) -> None:
    print(_c(f"\n>> {msg}", "1"))


def ok(msg: str) -> None:
    print(_c(f"   OK   {msg}", "32"))


def warn(msg: str) -> None:
    print(_c(f"   WARN {msg}", "33"))


def fail(msg: str) -> None:
    print(_c(f"   FAIL {msg}", "31"))


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def read_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing required content file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def human(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1048576:.1f} MB"


def esc(text: str) -> str:
    """Minimal HTML escaping for values coming from content files."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def is_placeholder(value: str) -> bool:
    """True for values like [PHONE NUMBER] that the operator still has to fill in."""
    return bool(value) and "[" in str(value) and "]" in str(value)


PLACEHOLDERS: list[str] = []


def track_placeholder(where: str, value: str) -> None:
    if is_placeholder(value):
        PLACEHOLDERS.append(f"{where}: {value}")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# HTTP with on-disk cache
# ---------------------------------------------------------------------------
CACHE_DIR = ROOT / ".cache"
OFFLINE = False
REFRESH = False


def http_get(url: str, *, accept: str | None = None) -> bytes:
    """GET with a simple disk cache. Raises RuntimeError when unavailable."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    cached = CACHE_DIR / key
    if cached.exists() and not REFRESH:
        return cached.read_bytes()
    if OFFLINE:
        raise RuntimeError("offline mode and no cached copy")
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{exc}") from exc
    cached.write_bytes(data)
    return data


# ---------------------------------------------------------------------------
# PNG: decode / crop / resize / encode (pure standard library)
# ---------------------------------------------------------------------------
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_chunks(blob: bytes):
    pos = 8
    while pos + 12 <= len(blob):
        (length,) = struct.unpack(">I", blob[pos : pos + 4])
        ctype = blob[pos + 4 : pos + 8]
        yield ctype, blob[pos + 8 : pos + 8 + length]
        pos += 12 + length


def png_load(path: Path):
    """Decode an 8-bit RGBA, non-interlaced PNG. Returns (width, height, bytearray)."""
    blob = path.read_bytes()
    if blob[:8] != PNG_SIG:
        return None
    ihdr = None
    idat = bytearray()
    for ctype, chunk in _png_chunks(blob):
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    if ihdr is None:
        return None
    width, height, depth, colour, _comp, _filt, interlace = ihdr
    if depth != 8 or colour != 6 or interlace != 0:
        return None

    raw = zlib.decompress(bytes(idat))
    bpp = 4
    stride = width * bpp
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos : pos + stride])
        pos += stride
        if ftype == 1:                      # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:                    # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:                    # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:                    # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up = prev[i]
                upleft = prev[i - bpp] if i >= bpp else 0
                p = left + up - upleft
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                if pa <= pb and pa <= pc:
                    pred = left
                elif pb <= pc:
                    pred = up
                else:
                    pred = upleft
                line[i] = (line[i] + pred) & 0xFF
        out[y * stride : (y + 1) * stride] = line
        prev = line
    return width, height, out


def png_encode(width: int, height: int, pixels: bytearray) -> bytes:
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)                                   # filter: none
        raw += pixels[y * stride : (y + 1) * stride]

    def chunk(ctype: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + ctype
            + payload
            + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        PNG_SIG
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def png_alpha_bbox(width: int, height: int, pixels: bytearray, threshold: int = 12):
    """
    Tight box around non-transparent pixels.

    The threshold matters: the supplied logo carries a very soft smoky halo that
    spreads to the edges of the canvas. A low threshold therefore reports the
    whole frame, which would produce a huge, mostly-empty image. Trimming uses
    ART_ALPHA_THRESHOLD so the crop lands on the crisp ivory artwork while the
    halo is reproduced in CSS (.hero__halo).
    """
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        base = y * width * 4
        row_hit = False
        for x in range(width):
            if pixels[base + x * 4 + 3] > threshold:
                if x < min_x:
                    min_x = x
                max_x = max(max_x, x)
                row_hit = True
        if row_hit:
            if y < min_y:
                min_y = y
            max_y = y
    if max_x < 0:
        return None
    return min_x, min_y, max_x + 1, max_y + 1


def png_crop(width: int, pixels: bytearray, box) -> tuple[int, int, bytearray]:
    """Crop to (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    cw, ch = x1 - x0, y1 - y0
    out = bytearray(cw * ch * 4)
    for y in range(ch):
        src = ((y0 + y) * width + x0) * 4
        out[y * cw * 4 : (y + 1) * cw * 4] = pixels[src : src + cw * 4]
    return cw, ch, out


def png_pad(width: int, height: int, pixels: bytearray, pad_x: int, pad_y: int):
    """Add transparent margin around an image (so a feather has room to fade)."""
    nw, nh = width + pad_x * 2, height + pad_y * 2
    out = bytearray(nw * nh * 4)
    row = width * 4
    for y in range(height):
        src = y * row
        dst = ((y + pad_y) * nw + pad_x) * 4
        out[dst : dst + row] = pixels[src : src + row]
    return nw, nh, out


def png_feather_border(width: int, height: int, pixels: bytearray,
                       feather_x: int, feather_y: int) -> bytearray:
    """
    Fade alpha to zero across the outer band.

    The supplied logo carries a soft smoky cloud behind the monogram. Cropping to
    the artwork therefore cuts that cloud mid-gradient, which reads as a hard
    grey rectangle. Feathering the transparent margin makes it dissolve instead,
    so the crop looks like an intentional glow on the dark hero.
    """
    for y in range(height):
        dy = min(y, height - 1 - y)
        fy = min(1.0, dy / max(1, feather_y))
        base = y * width * 4
        for x in range(width):
            dx = min(x, width - 1 - x)
            fx = min(1.0, dx / max(1, feather_x))
            f = fx if fx < fy else fy
            if f >= 1.0:
                continue
            i = base + x * 4 + 3
            if pixels[i]:
                pixels[i] = int(pixels[i] * (f * f * (3.0 - 2.0 * f)))   # smoothstep
    return pixels


def png_resize(width: int, height: int, pixels: bytearray, nw: int, nh: int) -> bytearray:
    """Area-average downscale using premultiplied alpha (avoids dark fringing)."""
    out = bytearray(nw * nh * 4)
    x_ratio = width / nw
    y_ratio = height / nh
    for oy in range(nh):
        y0 = int(oy * y_ratio)
        y1 = max(y0 + 1, min(height, int((oy + 1) * y_ratio)))
        for ox in range(nw):
            x0 = int(ox * x_ratio)
            x1 = max(x0 + 1, min(width, int((ox + 1) * x_ratio)))
            acc_a = acc_r = acc_g = acc_b = 0
            count = (x1 - x0) * (y1 - y0)
            for y in range(y0, y1):
                base = y * width * 4
                for x in range(x0, x1):
                    i = base + x * 4
                    a = pixels[i + 3]
                    if a:
                        acc_a += a
                        acc_r += pixels[i] * a
                        acc_g += pixels[i + 1] * a
                        acc_b += pixels[i + 2] * a
            o = (oy * nw + ox) * 4
            if acc_a:
                out[o] = acc_r // acc_a
                out[o + 1] = acc_g // acc_a
                out[o + 2] = acc_b // acc_a
                out[o + 3] = acc_a // count
    return out


def png_composite_plate(
    width: int, height: int, pixels: bytearray,
    plate: tuple[int, int, int], side: int, scale: float = 0.76,
) -> tuple[int, int, bytearray]:
    """Centre the mark on a square solid plate (used for favicons / touch icon)."""
    out = bytearray(side * side * 4)
    for y in range(side):
        for x in range(side):
            i = (y * side + x) * 4
            out[i] = plate[0]
            out[i + 1] = plate[1]
            out[i + 2] = plate[2]
            out[i + 3] = 255

    box = int(side * scale)
    ratio = width / height
    if ratio >= 1:
        tw, th = box, max(1, int(box / ratio))
    else:
        th, tw = box, max(1, int(box * ratio))
    if tw < 1 or th < 1:
        return side, side, out
    scaled = png_resize(width, height, pixels, tw, th)
    offset_x = (side - tw) // 2
    offset_y = (side - th) // 2
    for y in range(th):
        for x in range(tw):
            si = (y * tw + x) * 4
            alpha = scaled[si + 3]
            if not alpha:
                continue
            di = ((y + offset_y) * side + x + offset_x) * 4
            for c in range(3):
                out[di + c] = (scaled[si + c] * alpha + out[di + c] * (255 - alpha)) // 255
    return side, side, out


# ---------------------------------------------------------------------------
# JPEG dimension probe (for width/height attributes -> no layout shift)
# ---------------------------------------------------------------------------
def jpeg_size(blob: bytes):
    if blob[:2] != b"\xFF\xD8":
        return None
    pos = 2
    while pos + 9 < len(blob):
        if blob[pos] != 0xFF:
            pos += 1
            continue
        marker = blob[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        (length,) = struct.unpack(">H", blob[pos + 2 : pos + 4])
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            height, width = struct.unpack(">HH", blob[pos + 5 : pos + 9])
            return width, height
        pos += 2 + length
    return None


# ---------------------------------------------------------------------------
# Asset pipeline — logo
# ---------------------------------------------------------------------------
def build_logo() -> dict:
    """Trim the logo's transparent padding and emit the lock-up files + favicons."""
    source = ASSET_SRC_DIR / "logo.png"
    if not source.exists():
        raise SystemExit(
            f"Logo not found at {source}. Put your Marek Cuts logo there as logo.png."
        )

    hero_out = DIST_ASSETS / "logo.png"
    small_out = DIST_ASSETS / "logo-sm.png"
    trimmed_info = DIST_IMG / "logo-meta.json"
    stamp = {
        "src_mtime": source.stat().st_mtime,
        "src_size": source.stat().st_size,
        "hero_w": LOGO_TARGET_WIDTH,
        "hero_max_h": LOGO_HERO_MAX_HEIGHT,
        "pad": [LOGO_PAD_X, LOGO_PAD_Y],
        "small_h": LOGO_SM_HEIGHT,
        "art_threshold": ART_ALPHA_THRESHOLD,
        "ink_plate": list(INK_PLATE),
        "favicon_svg_size": FAVICON_SVG_SIZE,
    }

    if (
        not REFRESH
        and hero_out.exists()
        and small_out.exists()
        and trimmed_info.exists()
        and json.loads(trimmed_info.read_text(encoding="utf-8")) == stamp
    ):
        cached = json.loads((DIST_IMG / "logo-meta-full.json").read_text(encoding="utf-8"))
        info(f"logo.png reused ({cached['hero_w']}x{cached['hero_h']})")
        return cached

    info("logo.png — decoding, trimming transparent padding...")
    loaded = png_load(source)
    if loaded is None:
        raise SystemExit(
            "assets-src/logo.png must be an 8-bit RGBA PNG with transparency. "
            "Re-export it from your design tool as PNG-32, or delete the alpha."
        )
    width, height, pixels = loaded
    box = png_alpha_bbox(width, height, pixels, ART_ALPHA_THRESHOLD)
    if box:
        info(f"  art bounding box: {box} of {width}x{height} "
             f"(alpha > {ART_ALPHA_THRESHOLD}; the soft halo is CSS)")
        cw, ch, cropped = png_crop(width, pixels, box)
    else:
        warn("  logo has no transparent padding to trim")
        cw, ch, cropped = width, height, pixels

    # ---- hero lock-up -------------------------------------------------------
    # Crop -> pad -> feather, so the soft cloud behind the mark fades out instead
    # of stopping at a hard rectangle. The padding is kept proportional so the
    # artwork keeps a predictable share of the canvas on every rebuild.
    pad_x = max(6, round(cw * LOGO_PAD_X))
    pad_y = max(6, round(ch * LOGO_PAD_Y))
    pw, ph, padded = png_pad(cw, ch, cropped, pad_x, pad_y)
    png_feather_border(pw, ph, padded, pad_x, pad_y)

    # Size the *canvas* so the artwork inside it lands at 2x of the largest CSS
    # display height, then never upscale beyond what we actually have.
    art_share = ch / float(ph)
    target_h = min(ph, round(LOGO_HERO_MAX_HEIGHT / art_share))
    hero_h = target_h
    hero_w = max(1, round(pw * target_h / ph))
    hero_px = png_resize(pw, ph, padded, hero_w, hero_h)
    info(f"  padded {pad_x}/{pad_y}px, feathered, downscaled to {hero_w}x{hero_h} "
         f"(artwork ~{round(hero_h * art_share)}px tall = 2x of 186px CSS)")

    # compact lock-up for the header, drawer and footer (2.5x the 46px display size)
    small_h = min(LOGO_SM_HEIGHT, hero_h)
    small_w = max(1, round(hero_w * small_h / hero_h))
    small_px = png_resize(hero_w, hero_h, hero_px, small_w, small_h)

    write_bytes(hero_out, png_encode(hero_w, hero_h, hero_px))
    write_bytes(small_out, png_encode(small_w, small_h, small_px))

    # ---- favicons: the mark is ivory on transparency, so it needs a dark plate
    mono_box = _monogram_box(cw, ch, cropped)
    if mono_box:
        mw, mh, mono_px = png_crop(cw, cropped, mono_box)
    else:
        mw, mh, mono_px = cw, ch, cropped

    # FAVICON_SVG_SIZE is embedded (base64) in favicon.svg, so it also drives that
    # file's weight — 96px is crisp on hi-dpi tabs without bloating every page load.
    for size, scale in ((32, 0.86), (FAVICON_SVG_SIZE, 0.80), (180, 0.74)):
        side, _, plate_px = png_composite_plate(mw, mh, mono_px, INK_PLATE, size, scale)
        name = "apple-touch-icon.png" if size == 180 else f"favicon-{size}.png"
        write_bytes(DIST_IMG / name, png_encode(side, side, plate_px))

    fav_svg = _favicon_svg(DIST_IMG / f"favicon-{FAVICON_SVG_SIZE}.png")
    write_text(DIST_IMG / "favicon.svg", fav_svg)

    meta = {
        "hero_w": hero_w,
        "hero_h": hero_h,
        "small_w": small_w,
        "small_h": small_h,
        "hero_bytes": hero_out.stat().st_size,
        "small_bytes": small_out.stat().st_size,
    }
    write_text(trimmed_info, json.dumps(stamp, indent=1) + "\n")
    write_text(DIST_IMG / "logo-meta-full.json", json.dumps(meta, indent=1) + "\n")
    ok(
        f"logo.png {hero_w}x{hero_h} ({human(meta['hero_bytes'])}) · "
        f"logo-sm.png {small_w}x{small_h} ({human(meta['small_bytes'])}) · favicons"
    )
    return meta


def _monogram_box(width: int, height: int, pixels: bytearray):
    """
    Isolate the 'M' monogram from the top of the lock-up so the favicon stays
    legible at 32px. Returns None when the geometry is not convincing, in which
    case the caller falls back to the whole mark.
    """
    limit = int(height * 0.55)
    min_x, max_x, min_y, max_y = width, -1, height, -1
    for y in range(limit):
        base = y * width * 4
        for x in range(width):
            if pixels[base + x * 4 + 3] > 200:
                if x < min_x:
                    min_x = x
                max_x = max(max_x, x)
                if y < min_y:
                    min_y = y
                max_y = y
    if max_x < 0:
        return None
    bw, bh = max_x - min_x + 1, max_y - min_y + 1
    if bw < 16 or bh < 16:
        return None
    ratio = bw / bh
    if not 0.55 <= ratio <= 1.8:
        return None
    pad = int(max(bw, bh) * 0.10)
    return (
        max(0, min_x - pad),
        max(0, min_y - pad),
        min(width, max_x + 1 + pad),
        min(height, max_y + 1 + pad),
    )


def _favicon_svg(png_path: Path) -> str:
    import base64

    payload = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
        '  <rect width="64" height="64" rx="13" fill="#0A0A0B"/>\n'
        f'  <image href="data:image/png;base64,{payload}" x="0" y="0" '
        'width="64" height="64" preserveAspectRatio="xMidYMid meet"/>\n'
        "</svg>\n"
    )


# ---------------------------------------------------------------------------
# Asset pipeline — fonts
# ---------------------------------------------------------------------------
def build_fonts() -> tuple[str, list[str], str]:
    """
    Self-host Spectral + Inter.

    Returns (head markup, preload hrefs, css block).

    The @font-face block is appended to styles.css rather than inlined in the
    page, because url() inside an inline <style> resolves against the *document*,
    which differs between dist/index.html and dist/legal/*.html. Inside
    styles.css every path is simply relative to the dist root.

    Falls back to a Google Fonts <link> when the download is unavailable, so the
    build never hard-fails on a flaky network. The design system already ends
    every family with a system stack, so the site stays readable either way.
    """
    marker = DIST_FONTS / "fonts.css"
    manifest_path = DIST_FONTS / "manifest.json"
    wanted = {"Spectral": "latin", "Inter": "latin"}

    if marker.exists() and manifest_path.exists() and not REFRESH:
        css = marker.read_text(encoding="utf-8")
        preloads = json.loads(manifest_path.read_text(encoding="utf-8")).get("preload", [])
        info(f"self-hosted fonts reused ({len(preloads)} preloads)")
        return "\n".join(_preload_tags(preloads)), preloads, css

    try:
        raw_css = http_get(FONT_CSS_URL).decode("utf-8")
    except RuntimeError as exc:
        warn(f"fonts could not be downloaded ({exc}) — falling back to Google Fonts")
        head = (
            '<!-- Fonts: served by Google Fonts because the local download was '
            'unavailable. Re-run `python build.py --refresh` on a machine with '
            'network access to self-host them. -->\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link rel="stylesheet" href="{FONT_CSS_URL}">'
        )
        return head, [], ""

    # Google Fonts puts the subset name in a comment *before* each @font-face:
    #     /* latin-ext */
    #     @font-face { ... }
    # so the comment has to be captured together with the block that follows it.
    # Reading it from inside the block instead would silently default every
    # subset to "latin" and download cyrillic/vietnamese/greek we never use.
    paired = re.findall(
        r"/\*\s*([a-z0-9-]+)\s*\*/\s*@font-face\s*\{(.*?)\}", raw_css, re.S
    )
    if not paired:
        # Unrecognised stylesheet shape: keep every block rather than ship none.
        paired = [("latin", b) for b in re.findall(r"@font-face\s*\{(.*?)\}", raw_css, re.S)]

    out_blocks: list[str] = []
    preloads: list[str] = []
    downloaded = 0

    for subset, block in paired:
        family_match = re.search(r"font-family:\s*'([^']+)'", block)
        url_match = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        if not (family_match and url_match):
            continue
        if subset not in FONT_SUBSETS:
            continue
        family = family_match.group(1)
        url = url_match.group(1)
        try:
            blob = http_get(url)
        except RuntimeError as exc:
            warn(f"  {family} {subset} failed ({exc})")
            continue
        fname = f"{family.lower().replace(' ', '-')}-{subset}-{hashlib.sha256(url.encode()).hexdigest()[:8]}.woff2"
        write_bytes(DIST_FONTS / fname, blob)
        downloaded += 1
        local = f"assets/fonts/{fname}"   # styles.css lives at the dist root
        block = block.replace(url_match.group(1), local)
        block = re.sub(r"\n\s+", "\n  ", block).strip()
        out_blocks.append(
            f"/* {family} — {subset} */\n@font-face {{\n  {block}\n}}"
        )
        if wanted.get(family) == subset:
            preloads.append(f"assets/fonts/{fname}")

    if not out_blocks:
        warn("no usable @font-face blocks parsed — falling back to Google Fonts")
        return f'<link rel="stylesheet" href="{FONT_CSS_URL}">', [], ""

    css = (
        "/* Self-hosted webfonts — generated by build.py, do not edit.\n"
        "   Spectral (display) + Inter (body), latin + latin-ext subsets.\n"
        "   latin-ext carries the Slovak diacritics (ľ, ĺ, ŕ, ô, ä, ď, ť). */\n"
        + "\n".join(out_blocks)
        + "\n"
    )
    # Drop woff2 files from a previous build that the current CSS no longer uses,
    # so changing the font family does not leave orphaned weights in dist/.
    live = set(re.findall(r"assets/fonts/([\w.\-]+\.woff2)", css))
    for stale in DIST_FONTS.glob("*.woff2"):
        if stale.name not in live:
            stale.unlink()
            info(f"  pruned orphaned font {stale.name}")

    marker.write_text(css, encoding="utf-8", newline="\n")
    manifest_path.write_text(json.dumps({"preload": preloads}, indent=1) + "\n", encoding="utf-8")
    ok(f"self-hosted fonts: {downloaded} woff2 files")
    return "\n".join(_preload_tags(preloads)), preloads, css


def _preload_tags(preloads: list[str]) -> list[str]:
    return [
        f'<link rel="preload" href="{href}" as="font" type="font/woff2" crossorigin>'
        for href in preloads
    ]


# ---------------------------------------------------------------------------
# Asset pipeline — photography
# ---------------------------------------------------------------------------
def remote_variant(url: str, width: int, quality: int) -> str:
    """Build a width/quality-specific URL for the supported photo CDNs."""
    if "images.unsplash.com" in url:
        base = url.split("?")[0]
        return f"{base}?auto=format&fit=crop&fm=jpg&q={quality}&w={width}&crop=entropy"
    if "images.pexels.com" in url:
        base = url.split("?")[0]
        return f"{base}?auto=compress&cs=tinysrgb&fit=crop&fm=jpg&w={width}"
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}w={width}&q={quality}"


def fetch_image(entry: dict, width: int, quality: int, target: Path):
    """Download the first working source at the given width. Returns (w, h) or None."""
    if target.exists() and target.stat().st_size > 4096 and not REFRESH:
        blob = target.read_bytes()
        size = jpeg_size(blob)
        if size:
            return size
    for source in entry.get("sources", []):
        url = remote_variant(source["url"], width, quality)
        try:
            blob = http_get(url, accept="image/jpeg,image/*")
        except RuntimeError as exc:
            warn(f"    source unavailable ({exc})")
            continue
        if len(blob) < 4096:
            warn("    source returned an empty image")
            continue
        size = jpeg_size(blob)
        if not size:
            warn("    source is not a JPEG — skipping")
            continue
        write_bytes(target, blob)
        return size
    return None


def build_images(gallery: dict) -> dict:
    """
    Download hero / about / gallery photos at several widths.

    Returns {entry_id: {"widths": {w: (w, h)}, "sizes": ...}} used by the
    renderer to write srcset attributes.
    """
    quality = int(gallery.get("qualities", {}).get("download", 78))
    results: dict[str, dict] = {}
    manifest_path = DIST_IMG / "images.json"

    if manifest_path.exists() and not REFRESH:
        cached = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key, value in cached.items():
            value.setdefault("id", key)     # older manifests stored the id only as the key
        missing = [
            entry["id"]
            for entry in gallery["entries"]
            if entry["id"] not in cached
            or not (DIST_IMG / f"{entry['id']}-{max(_widths_for(entry)[0])}.jpg").exists()
        ]
        if not missing:
            info(f"photography reused ({len(cached)} images)")
            return cached
        info(f"re-fetching missing images: {', '.join(missing)}")

    for entry in gallery["entries"]:
        eid = entry["id"]
        role = entry.get("role", "gallery")
        widths = _widths_for(entry)[0]
        variants: dict[str, list[int]] = {}
        got_any = False
        for width in widths:
            target = DIST_IMG / f"{eid}-{width}.jpg"
            size = fetch_image(entry, width, quality, target)
            if size:
                variants[str(width)] = [size[0], size[1]]
                got_any = True
        if not got_any:
            fail(f"no image could be downloaded for '{eid}' — remove it from content/gallery.json")
            results[eid] = {"failed": True}
            continue
        results[eid] = {
            "id": eid,
            "role": role,
            "span": entry.get("span", "normal"),
            "variants": variants,
            "alt": entry["alt"],
            "attrs": {k: v for k, v in entry.items() if k in ("photographer", "credit", "page")},
        }
        info(f"  {eid}: {len(variants)} widths")

    write_text(manifest_path, json.dumps(results, indent=1, ensure_ascii=False) + "\n")
    ok(f"photography ready: {sum(1 for v in results.values() if not v.get('failed'))} images")
    return results


def _widths_for(entry: dict):
    role = entry.get("role", "gallery")
    if role == "hero":
        return HERO_WIDTHS, "100vw"
    if role == "about":
        return ABOUT_WIDTHS, "(max-width: 900px) 92vw, 44vw"
    return GALLERY_WIDTHS, "(max-width: 700px) 92vw, (max-width: 1100px) 46vw, 31vw"


def picture_markup(image: dict, alt: str, sizes: str, *, eager: bool = False,
                   css_class: str = None, extra: str = "") -> str:
    """Build an <img> with srcset/sizes from the downloaded variants."""
    variants = sorted((int(k), v) for k, v in image["variants"].items())
    if not variants:
        return ""
    largest, (lw, lh) = variants[-1]
    srcset = ", ".join(f"assets/img/{image['id']}-{w}.jpg {w}w" for w, _ in variants)
    loading = 'fetchpriority="high" decoding="async"' if eager else 'loading="lazy" decoding="async"'
    cls = f' class="{css_class}"' if css_class else ""
    return (
        f'<img{cls} src="assets/img/{image["id"]}-{largest}.jpg"\n'
        f'             srcset="{srcset}"\n'
        f'             sizes="{sizes}"\n'
        f'             alt="{esc(alt)}" width="{lw}" height="{lh}" {loading}{extra}>'
    )


# ---------------------------------------------------------------------------
# HTML fragment builders
# ---------------------------------------------------------------------------
def build_services_list(services: dict) -> str:
    rows = []
    for index, item in enumerate(services["items"], start=1):
        price = item["price"]
        rows.append(
            f'''        <li class="service" data-reveal data-reveal-delay="{min(index - 1, 4)}">
          <div class="service__top">
            <span class="service__icon" aria-hidden="true"><svg class="icon"><use href="#i-{esc(item['icon'])}"/></svg></span>
            <span class="service__num" aria-hidden="true">{index:02d}</span>
          </div>
          <h3 class="service__name">{dual(item['sk']['name'], item['en']['name'])}</h3>
          <p class="service__desc">{dual(item['sk']['description'], item['en']['description'])}</p>
          <div class="service__meta">
            <p class="service__price">{dual(f"{price} \u20ac", f"\u20ac{price}")}</p>
            <p class="service__dur"><svg class="icon" aria-hidden="true"><use href="#i-clock"/></svg><span>{dual(f"{item['duration']} min", f"{item['duration']} min")}</span></p>
          </div>
          <button type="button" class="service__book" data-book-service="{esc(item['id'])}">
            <span data-i18n="services.book">Rezervova\u0165</span>
            <svg class="icon" aria-hidden="true"><use href="#i-arrow-right"/></svg>
          </button>
        </li>'''
        )
    return "\n".join(rows)


def dual(sk: str, en: str) -> str:
    """Two spans toggled by html[data-lang] — works with JavaScript disabled."""
    return (
        f'<span data-lang-text="sk">{esc(sk)}</span>'
        f'<span data-lang-text="en">{esc(en)}</span>'
    )


def build_booking_services(services: dict) -> str:
    rows = []
    for item in services["items"]:
        rows.append(
            f'''              <li>
                <button type="button" class="pick" data-service-option="{esc(item['id'])}" aria-pressed="false">
                  <span class="pick__icon" aria-hidden="true"><svg class="icon"><use href="#i-{esc(item['icon'])}"/></svg></span>
                  <span class="pick__name">{dual(item['sk']['name'], item['en']['name'])}</span>
                  <span class="pick__meta">{dual(f"{item['duration']} min", f"{item['duration']} min")}</span>
                  <span class="pick__price">{dual(f"{item['price']} \u20ac", f"\u20ac{item['price']}")}</span>
                </button>
              </li>'''
        )
    return "\n".join(rows)


def build_gallery_list(gallery: dict, images: dict) -> str:
    rows = []
    for index, entry in enumerate(gallery["entries"]):
        if entry.get("role") != "gallery":
            continue
        image = images.get(entry["id"])
        if not image or image.get("failed"):
            continue
        _widths, sizes = _widths_for(entry)
        classes = "gallery__item"
        span = entry.get("span")
        if span in ("tall", "wide"):
            classes += f" gallery__item--{span}"
        eid = entry["id"]
        widths = sorted(int(w) for w in image["variants"])
        largest = widths[-1]
        default = min(widths, key=lambda w: abs(w - 900))
        dims = image["variants"][str(default)]
        srcset = ", ".join(f"assets/img/{eid}-{w}.jpg {w}w" for w in widths)
        alt = esc(entry["alt"]["sk"])
        rows.append(
            f'        <button type="button" class="{classes}" data-gallery-item'
            f' data-full="assets/img/{eid}-{largest}.jpg"'
            f' data-alt="{alt}" data-alt-sk="{alt}" data-alt-en="{esc(entry["alt"]["en"])}"'
            f' aria-label="{alt}">\n'
            f'          <img src="assets/img/{eid}-{default}.jpg" srcset="{srcset}" sizes="{sizes}"\n'
            f'               alt="{alt}" loading="lazy" decoding="async"'
            f' width="{dims[0]}" height="{dims[1]}">\n'
            "        </button>"
        )
    return "\n".join(rows)


def build_reviews_list(testimonials: dict) -> str:
    rows = []
    for item in testimonials["items"]:
        rating = int(item.get("rating", 5))
        stars = "".join(
            f'<svg class="icon{" is-off" if i >= rating else ""}" aria-hidden="true"><use href="#i-star"/></svg>'
            for i in range(5)
        )
        service = item.get("service") or {}
        service_markup = (
            f'<span class="review__service">{dual(service.get("sk", ""), service.get("en", ""))}</span>'
            if service
            else ""
        )
        rows.append(
            f'''          <li class="review">
            <div class="review__head">
              <span class="stars" role="img" aria-label="{esc(_rating_label(rating))}">{stars}</span>
              <span class="review__date">{esc(item.get('date', ''))}</span>
            </div>
            <p class="review__text">{dual(item['sk'], item['en'])}</p>
            <div class="review__foot">
              <div>
                <p class="review__name">{esc(item['name'])}</p>
                {service_markup}
              </div>
              <span class="review__tag" data-i18n="reviews.demoTag">Demo</span>
            </div>
          </li>'''
        )
    return "\n".join(rows)


def _rating_label(rating: int) -> str:
    return f"{rating} / 5"


def build_hours_list(hours: dict) -> str:
    rows = []
    for day in hours["days"]:
        if day.get("closed"):
            value = '<span class="hours__time" data-i18n="contact.closed">Zatvorené</span>'
            row_class = "hours__row hours__row--closed"
        else:
            placeholder = hours.get("displayPlaceholder", "XX:XX")
            value = (
                f'<span class="hours__time">{esc(placeholder)}'
                f'&#8211;{esc(placeholder)}</span>'
            )
            row_class = "hours__row"
        rows.append(
            f'''            <li class="{row_class}">
              <span class="hours__day">{dual(day['sk'], day['en'])}</span>
              {value}
            </li>'''
        )
    return "\n".join(rows)


SOCIAL_ICONS = (
    ("instagram", "Instagram", "i-instagram"),
    ("facebook", "Facebook", "i-facebook"),
    ("tiktok", "TikTok", "i-tiktok"),
)


def build_social_links(business: dict) -> str:
    links = []
    for key, label, icon in SOCIAL_ICONS:
        value = business.get(key, "")
        if not value or is_placeholder(value):
            links.append(
                f'<span class="social social--placeholder" title="[{" ".join(key.upper())} URL]" '
                f'data-i18n-attr="title:a11y.socialPlaceholder" aria-hidden="true">'
                f'<svg class="icon" aria-hidden="true"><use href="#{icon}"/></svg></span>'
            )
        else:
            links.append(
                f'<a class="social" href="{esc(value)}" target="_blank" rel="noopener noreferrer" '
                f'aria-label="{label}"><svg class="icon" aria-hidden="true"><use href="#{icon}"/></svg></a>'
            )
    return "".join(links)


def build_address_lines(business: dict) -> str:
    lines = [line for line in business.get("addressLines", []) if line]
    if not lines:
        if is_placeholder(str(business.get("address", ""))):
            return esc(business["address"])
        return esc(business.get("address", ""))
    return "<br>".join(esc(line) for line in lines)


def build_contact_value(value: str, kind: str) -> str:
    """Render phone/email as a link, or as a plain placeholder when unfilled."""
    if not value or is_placeholder(value):
        return esc(value)
    if kind == "phone":
        href = "tel:" + re.sub(r"[^\d+]", "", value)
    else:
        href = "mailto:" + value
    return f'<a class="linkish" href="{esc(href)}">{esc(value)}</a>'


def build_favicon_markup() -> str:
    return (
        '<link rel="icon" href="assets/img/favicon.svg" type="image/svg+xml">\n'
        '<link rel="icon" href="assets/img/favicon-32.png" sizes="32x32" type="image/png">\n'
        '<link rel="apple-touch-icon" href="assets/img/apple-touch-icon.png">'
    )


def build_jsonld(business: dict, services: dict, gallery: dict, images: dict) -> str:
    """
    Structured data. Fields that are still [PLACEHOLDERS] are omitted on purpose
    so no invented business data is ever published as machine-readable data.
    """
    data = {
        "@context": "https://schema.org",
        "@type": "HairSalon",
        "name": business["businessName"],
        "description": json.loads(
            (CONTENT_DIR / "i18n.json").read_text(encoding="utf-8")
        )["seo.description"]["sk"],
        "url": business["siteUrl"].rstrip("/") + "/",
        "image": business["siteUrl"].rstrip("/") + "/assets/img/hero-1600.jpg",
        "priceRange": "Demo",
    }
    address = business.get("address", "")
    if not is_placeholder(address):
        data["address"] = {"@type": "PostalAddress", "streetAddress": address}
    for key, prop in (("phone", "telephone"), ("email", "email")):
        if not is_placeholder(str(business.get(key, ""))):
            data[prop] = business[key]
    for key, prop in (("instagram", "sameAs"), ("facebook", "sameAs"), ("tiktok", "sameAs")):
        if not is_placeholder(str(business.get(key, ""))):
            data.setdefault(prop, []).append(business[key])
    data["makesOffer"] = [
        {
            "@type": "Offer",
            "itemOffered": {"@type": "Service", "name": item["sk"]["name"]},
        }
        for item in services["items"]
    ]
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(data, ensure_ascii=False, indent=2)
        + "\n</script>"
    )


# ---------------------------------------------------------------------------
# Legal pages
# ---------------------------------------------------------------------------
LEGAL_PAGES = (
    ("privacy", "legal.privacy", "Ochrana osobných údajov", "Privacy Policy"),
    ("gdpr", "legal.gdpr", "GDPR / Spracovanie osobných údajov", "GDPR / Personal Data"),
    ("cookies", "legal.cookies", "Zásady používania cookies", "Cookie Policy"),
    ("terms", "legal.terms", "Podmienky rezervácie", "Booking Terms & Conditions"),
)


def build_legal_body(doc: dict) -> str:
    """Both languages are rendered; CSS shows only the active one."""
    out = []
    for lang, other in (("sk", "en"), ("en", "sk")):
        body = [
            f'<p class="legal__intro" data-legal-lang="{lang}">{esc(doc["intro"][lang])}</p>'
        ]
        for section in doc["sections"]:
            paras = "".join(
                f"<p>{esc(para[lang])}</p>" for para in section["body"]
            )
            body.append(
                f'''<section class="legal-section" id="{esc(section['id'])}-{lang}" data-legal-lang="{lang}">
  <h2 class="legal-section__heading">{esc(section['heading'][lang])}</h2>
  {paras}
</section>'''
            )
        out.append("\n".join(body))
    return "\n".join(out)


def build_legal_toc(doc: dict) -> str:
    items = []
    for index, section in enumerate(doc["sections"], start=1):
        items.append(
            f'          <li><span class="toc__num" aria-hidden="true">{index:02d}</span>'
            f'<a href="#{esc(section["id"])}-sk" data-legal-lang="sk">{esc(section["heading"]["sk"])}</a>'
            f'<a href="#{esc(section["id"])}-en" data-legal-lang="en">{esc(section["heading"]["en"])}</a></li>'
        )
    return (
        '<nav class="toc" aria-labelledby="toc-title">\n'
        '  <h2 class="toc__title" id="toc-title" data-i18n="legal.onThisPage">Na tejto stránke</h2>\n'
        '  <ol class="toc__list">\n'
        + "\n".join(items)
        + "\n  </ol>\n</nav>"
    )


def build_operator(business: dict) -> str:
    legal = business["legal"]
    rows = (
        ("legal.legalName", legal.get("legalName", "")),
        ("legal.legalAddress", legal.get("legalAddress", "")),
        ("legal.companyId", legal.get("companyId", "")),
        ("legal.email", legal.get("email", "")),
        ("legal.phone", legal.get("phone", "")),
    )
    items = "".join(
        f'<li><dt data-i18n="{key}">{key}</dt><dd>{esc(value)}</dd></li>' for key, value in rows
    )
    return (
        '<aside class="legal__aside">\n'
        f'  <h2 class="legal__aside-title" data-i18n="legal.operatorTitle">Prev\u00e1dzkovate\u013e</h2>\n'
        f'  <ul class="legal__aside-list operator">{items}</ul>\n'
        f'  <p class="legal__notice" data-i18n="legal.operatorNotice">Toto je \u0161abl\u00f3na pr\u00e1vneho dokumentu.</p>\n'
        "</aside>"
    )


# ---------------------------------------------------------------------------
# Site config (window.MC) — the one place the runtime reads business data from
# ---------------------------------------------------------------------------
def build_site_config(business: dict, services: dict, hours: dict, availability: dict,
                      testimonials: dict, gallery: dict, i18n: dict,
                      images: dict) -> str:
    """
    Emit the centralised configuration.

    Both the spec-named globals (siteConfig, services, testimonials, availability,
    openingHours, gallery, translations) and the internal window.MC object are
    produced here, so there is exactly ONE place to edit business data and no
    drift between the HTML, the meta tags and the runtime.
    """
    gallery_public = [
        {
            "id": entry["id"],
            "role": entry.get("role", "gallery"),
            "span": entry.get("span", "normal"),
            "alt": entry["alt"],
            "full": f"assets/img/{entry['id']}-{max(int(w) for w in images[entry['id']]['variants'])}.jpg"
            if entry["id"] in images and not images[entry["id"]].get("failed")
            else None,
        }
        for entry in gallery["entries"]
    ]
    services_public = [
        {
            "id": item["id"],
            "icon": item["icon"],
            "name": {"sk": item["sk"]["name"], "en": item["en"]["name"]},
            "description": {"sk": item["sk"]["description"], "en": item["en"]["description"]},
            "price": item["price"],
            "duration": item["duration"],
        }
        for item in services["items"]
    ]
    payload = {
        "siteConfig": {
            "businessName": business["businessName"],
            "businessNameUpper": business["businessNameUpper"],
            "shopType": business["shopType"],
            "siteUrl": business["siteUrl"],
            "address": business["address"],
            "addressLines": business["addressLines"],
            "phone": business["phone"],
            "email": business["email"],
            "instagram": business["instagram"],
            "facebook": business["facebook"],
            "tiktok": business["tiktok"],
            "copyrightYear": business["copyrightYear"],
        },
        "services": services_public,
        "openingHours": [
            {
                "key": day["key"],
                "label": {"sk": day["sk"], "en": day["en"]},
                "closed": bool(day.get("closed")),
            }
            for day in hours["days"]
        ],
        "availability": availability,
        "testimonials": [
            {
                "name": item["name"],
                "rating": item.get("rating", 5),
                "date": item.get("date", ""),
                "service": item.get("service"),
                "text": {"sk": item["sk"], "en": item["en"]},
            }
            for item in testimonials["items"]
        ],
        "gallery": gallery_public,
        "translations": i18n,
    }
    header = (
        "/* ==========================================================================\n"
        "   site-config.js content — GENERATED BY build.py. DO NOT EDIT.\n"
        "   --------------------------------------------------------------------------\n"
        "   Edit content/*.json and re-run:  python build.py\n"
        "   This block is prepended to script.js, so window.MC exists before any\n"
        "   module executes. A future backend can read these same globals.\n"
        "   ========================================================================== */\n"
    )
    # window.MC is what the modules consume; it is assembled from the payload above
    # so the two can never drift apart.
    mc = {
        "businessName": business["businessName"],
        "currency": services.get("currency", "EUR"),
        "defaultLang": "sk",
        "availability": availability,
        "services": services_public,
        "i18n": i18n,
    }
    return (
        header
        + "\n/* --- Centralised business configuration (edit content/business.json) --- */\n"
        + "window.siteConfig = "
        + json.dumps(payload["siteConfig"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- Services and DEMO pricing (edit content/services.json) --- */\n"
        + "window.services = "
        + json.dumps(payload["services"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- Opening hours (edit content/hours.json) --- */\n"
        + "window.openingHours = "
        + json.dumps(payload["openingHours"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- DEMO booking availability (edit content/availability.json) --- */\n"
        + "window.availability = "
        + json.dumps(payload["availability"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- DEMO testimonials (edit content/testimonials.json)\n"
        + "       Replace with real customer reviews before public launch. --- */\n"
        + "window.testimonials = "
        + json.dumps(payload["testimonials"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- Gallery (edit content/gallery.json) --- */\n"
        + "window.gallery = "
        + json.dumps(payload["gallery"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- All SK/EN strings (edit content/i18n.json) --- */\n"
        + "window.translations = "
        + json.dumps(payload["translations"], ensure_ascii=False, indent=2)
        + ";\n"
        + "\n/* --- Consumed by the runtime modules --- */\n"
        + "window.MC = "
        + json.dumps(mc, ensure_ascii=False, indent=2)
        + ";\n"
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_tokens(template: str, tokens: dict) -> str:
    def replace(match):
        key = match.group(1)
        if key not in tokens:
            return match.group(0)
        return str(tokens[key])

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", replace, template)


def url_for(domain: str, path: str) -> str:
    return f"{domain.rstrip('/')}/{path.lstrip('/')}" if path else domain


def render_index(template: str, ctx: dict) -> str:
    business = ctx["business"]
    tokens = {
        "LANG": "sk",
        "SEO_TITLE": ctx["i18n"]["seo.title"]["sk"],
        "SEO_DESCRIPTION": ctx["i18n"]["seo.description"]["sk"],
        "SEO_OG_TITLE": ctx["i18n"]["seo.ogTitle"]["sk"],
        "SEO_OG_DESCRIPTION": ctx["i18n"]["seo.ogDescription"]["sk"],
        "SEO_OG_LOCALE": "sk_SK",
        "SEO_OG_LOCALE_ALT": "en_GB",
        "SEO_OG_IMAGE_ALT": ctx["images"]["hero"]["alt"]["sk"],
        "SEO_CANONICAL": business["siteUrl"],
        "THEME_COLOR": business["themeColor"],
        "BUSINESS_NAME": business["businessName"],
        "COPYRIGHT_YEAR": business["copyrightYear"],
        "FAVICON": build_favicon_markup(),
        "FONTS": ctx["font_head"],
        "STYLES": '<link rel="stylesheet" href="styles.css">',
        "JSONLD": build_jsonld(business, ctx["services"], ctx["gallery"], ctx["images"]),
        "LOGO_LOCKUP": "assets/logo.png",
        "LOGO_SM": "assets/logo-sm.png",
        "LOGO_W": ctx["logo"]["hero_w"],
        "LOGO_H": ctx["logo"]["hero_h"],
        "LOGO_SM_W": ctx["logo"]["small_w"],
        "LOGO_SM_H": ctx["logo"]["small_h"],
        "LOGO_ALT": ctx["i18n"]["a11y.logoAlt"]["sk"],
        "HERO_PICTURE": picture_markup(
            ctx["images"]["hero"], ctx["images"]["hero"]["alt"]["sk"],
            "100vw", eager=True,
        ),
        "ABOUT_PICTURE": picture_markup(
            ctx["images"]["about"], ctx["images"]["about"]["alt"]["sk"],
            "(max-width: 900px) 92vw, 44vw", css_class="about__img",
        ),
        "SERVICES_LIST": build_services_list(ctx["services"]),
        "GALLERY_LIST": build_gallery_list(ctx["gallery"], ctx["images"]),
        "REVIEWS_LIST": build_reviews_list(ctx["testimonials"]),
        "BOOKING_SERVICES": build_booking_services(ctx["services"]),
        "HOURS_LIST": build_hours_list(ctx["hours"]),
        "SOCIAL_LINKS": build_social_links(business),
        "ADDRESS_LINES": build_address_lines(business),
        "PHONE_LINK": build_contact_value(business["phone"], "phone"),
        "EMAIL_LINK": build_contact_value(business["email"], "email"),
        "MAPS_URL": ctx["maps_url"],
        "HOME_URL": "index.html",
        "PRIVACY_URL": "legal/privacy.html",
        "GDPR_URL": "legal/gdpr.html",
        "COOKIES_URL": "legal/cookies.html",
        "TERMS_URL": "legal/terms.html",
        "CONSENT_UI": render_tokens(ctx["consent_partial"], {
            "COOKIES_URL": "legal/cookies.html",
        }),
        "SCRIPT_URL": "script.js",
    }
    return render_tokens(template, tokens)


def render_legal_page(template: str, ctx: dict, doc: dict, slug: str,
                      title_key: str, sk_title: str, en_title: str) -> str:
    business = ctx["business"]
    canonical = url_for(business["siteUrl"], f"legal/{slug}.html")
    tokens = {
        "LANG": "sk",
        "SEO_TITLE": f"{sk_title} | {business['businessName']}",
        "SEO_DESCRIPTION": ctx["i18n"]["seo.description"]["sk"],
        "SEO_CANONICAL": canonical,
        "SEO_SITE_NAME": business["businessName"],
        "SEO_OG_LOCALE": "sk_SK",
        "SEO_OG_LOCALE_ALT": "en_GB",
        "THEME_COLOR": business["themeColor"],
        "FAVICON": build_favicon_markup(),
        "FONTS": ctx["font_head"],
        "STYLES": '<link rel="stylesheet" href="../styles.css">',
        "LOGO_LOCKUP": "../assets/logo.png",
        "LOGO_SM": "../assets/logo-sm.png",
        "LOGO_W": ctx["logo"]["hero_w"],
        "LOGO_H": ctx["logo"]["hero_h"],
        "LOGO_SM_W": ctx["logo"]["small_w"],
        "LOGO_SM_H": ctx["logo"]["small_h"],
        "LOGO_ALT": ctx["i18n"]["a11y.logoAlt"]["sk"],
        "LEGAL_TITLE": sk_title,
        "LEGAL_KIND": ctx["i18n"]["legal.pageSuffix"]["sk"],
        "TITLE_KEY": title_key,
        "LAST_UPDATED": ctx["i18n"]["legal.lastUpdated"]["sk"].replace(
            "{date}", ctx["today_display"]
        ),
        "LAST_UPDATED_DATE": ctx["today_display"],
        "TOC": build_legal_toc(doc),
        "LEGAL_BODY": build_legal_body(doc),
        "OPERATOR": build_operator(business),
        "HOME_URL": "../index.html",
        "PRIVACY_URL": "privacy.html",
        "GDPR_URL": "gdpr.html",
        "COOKIES_URL": "cookies.html",
        "TERMS_URL": "terms.html",
        "CONSENT_UI": render_tokens(ctx["consent_partial"], {
            "COOKIES_URL": "cookies.html",
        }),
        "SCRIPT_URL": "../script.js",
    }
    return render_tokens(template, tokens)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(html_files: dict, i18n: dict) -> list[str]:
    problems: list[str] = []

    # 1. no unreplaced {{TOKEN}}, and every page actually loads the design system
    for name, html in html_files.items():
        leftover = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", html)))
        if leftover:
            problems.append(f"{name}: unreplaced tokens {', '.join(leftover)}")
        if "styles.css" not in html:
            problems.append(f"{name}: no <link> to styles.css")

    # 2. every data-i18n key exists in both languages
    used: dict[str, set[str]] = {}
    for name, html in html_files.items():
        for key in re.findall(r'data-i18n="([^"]+)"', html):
            used.setdefault(key, set()).add(name)
        for spec in re.findall(r'data-i18n-attr="([^"]+)"', html):
            for pair in spec.split("|"):
                if ":" in pair:
                    used.setdefault(pair.split(":", 1)[1].strip(), set()).add(name)
    for key, where in sorted(used.items()):
        entry = i18n.get(key)
        if entry is None:
            problems.append(f"i18n key missing: '{key}' (used in {', '.join(sorted(where))})")
        else:
            for lang in ("sk", "en"):
                if not str(entry.get(lang, "")).strip():
                    problems.append(f"i18n key '{key}' has no '{lang}' value")

    # 3. every local url() in the CSS resolves inside dist/
    css = (DIST / "styles.css").read_text(encoding="utf-8")
    for raw in re.findall(r"url\(([^)]+)\)", css):
        ref = raw.strip().strip("'\"")
        if ref.startswith(("http:", "https:", "data:", "#")):
            continue
        candidate = (DIST / ref).resolve()
        if not candidate.exists():
            problems.append(f"styles.css references a missing file: {ref}")

    # 4. required output files
    for path in (
        DIST / "index.html", DIST / "styles.css", DIST / "script.js",
        DIST / "robots.txt", DIST / "sitemap.xml",
        DIST_ASSETS / "logo.png", DIST_ASSETS / "logo-sm.png",
        DIST / "legal" / "privacy.html", DIST / "legal" / "gdpr.html",
        DIST / "legal" / "cookies.html", DIST / "legal" / "terms.html",
    ):
        if not path.exists():
            problems.append(f"missing output file: {path.relative_to(ROOT)}")

    # 5. nothing in dist/ should still reference the old token syntax
    for html_path in DIST.rglob("*.html"):
        blob = html_path.read_text(encoding="utf-8")
        if "{{" in blob and "}}" in blob:
            problems.append(f"{html_path.name} still contains {{{{TOKEN}}}} syntax")

    # 6. the demo booking system must not contain any real network call.
    #    Comments are stripped first, because the documented backend seam is a
    #    commented-out fetch() that we explicitly want to keep as guidance.
    script = strip_js_comments((DIST / "script.js").read_text(encoding="utf-8"))
    for pattern in ("fetch(", "XMLHttpRequest", "sendBeacon", "new WebSocket", "EventSource("):
        if pattern in script:
            problems.append(
                f"script.js makes a network call via '{pattern}' — the demo booking "
                "system must stay offline until the operator wires up a real backend"
            )
    return problems


def strip_js_comments(source: str) -> str:
    """
    Remove // and /* */ comments while respecting string literals, so that
    https:// URLs and quoted text survive intact.
    """
    out: list[str] = []
    i = 0
    length = len(source)
    while i < length:
        char = source[i]
        nxt = source[i + 1] if i + 1 < length else ""
        if char in "\"'`":
            quote = char
            out.append(char)
            i += 1
            while i < length:
                out.append(source[i])
                if source[i] == "\\" and i + 1 < length:
                    out.append(source[i + 1])
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if char == "/" and nxt == "/":
            while i < length and source[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and nxt == "*":
            i += 2
            while i < length and not (source[i] == "*" and i + 1 < length and source[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    global OFFLINE, REFRESH
    parser = argparse.ArgumentParser(description="Build the Marek Cuts static site.")
    parser.add_argument("--offline", action="store_true",
                        help="never access the network; use cached assets only")
    parser.add_argument("--refresh", action="store_true",
                        help="re-download every remote asset")
    parser.add_argument("--clean", action="store_true",
                        help="delete dist/ and .cache/ before building")
    args = parser.parse_args()
    OFFLINE = args.offline
    REFRESH = args.refresh

    print(_c("\n  MAREK CUTS — static site build", "1"))
    print(f"  Python {sys.version.split()[0]} · {'offline' if OFFLINE else 'online'} · "
          f"{'refresh' if REFRESH else 'incremental'}")

    if args.clean:
        import shutil

        for target in (DIST, CACHE_DIR):
            if target.exists():
                shutil.rmtree(target)
        info("cleaned dist/ and .cache/")

    for directory in (DIST, DIST_ASSETS, DIST_IMG, DIST_FONTS, DIST_LEGAL):
        directory.mkdir(parents=True, exist_ok=True)

    # ---- content ----------------------------------------------------------
    step("Reading content")
    business = read_json(CONTENT_DIR / "business.json")
    services = read_json(CONTENT_DIR / "services.json")
    hours = read_json(CONTENT_DIR / "hours.json")
    availability = read_json(CONTENT_DIR / "availability.json")
    testimonials = read_json(CONTENT_DIR / "testimonials.json")
    gallery = read_json(CONTENT_DIR / "gallery.json")
    i18n = read_json(CONTENT_DIR / "i18n.json")
    info(f"{len(services['items'])} services · {len(testimonials['items'])} testimonials · "
         f"{len(gallery['entries'])} images · {len(i18n)} strings")

    for field in ("businessName", "address", "phone", "email", "instagram", "facebook", "tiktok"):
        track_placeholder(f"business.{field}", str(business.get(field, "")))
    for key, value in business.get("legal", {}).items():
        if not key.startswith("_"):
            track_placeholder(f"business.legal.{key}", str(value))

    # Keys the templates reference but that are not yet in content/i18n.json.
    # Added once, then yours to edit like any other string.
    for key, default in (
        ("contact.closed", {"sk": "Zatvorené", "en": "Closed"}),
        ("nav.homeLink", {"sk": "Marek Cuts — na \u00favodn\u00fa str\u00e1nku",
                          "en": "Marek Cuts — go to homepage"}),
    ):
        if i18n.get(key) is None:
            i18n[key] = default
            write_text(CONTENT_DIR / "i18n.json",
                       json.dumps(i18n, ensure_ascii=False, indent=1) + "\n")
            info(f"added i18n key '{key}'")

    # ---- assets -----------------------------------------------------------
    step("Assets")
    logo = build_logo()
    font_head, font_preloads, font_css_block = build_fonts()
    images = build_images(gallery)
    if "hero" not in images or images["hero"].get("failed"):
        fail("the hero image is required — check content/gallery.json")
        return 1
    if "about" not in images or images["about"].get("failed"):
        fail("the about image is required — check content/gallery.json")
        return 1

    # ---- styles + scripts -------------------------------------------------
    step("Assembling CSS and JavaScript")
    styles = (SRC_DIR / "styles.css").read_text(encoding="utf-8")
    if font_css_block:
        styles = styles.rstrip("\n") + "\n\n" + font_css_block
    write_text(DIST / "styles.css", styles)
    info(f"styles.css ({human(len(styles.encode('utf-8')))}"
         f"{' incl. self-hosted @font-face' if font_css_block else ''})")

    js_files = sorted(JS_DIR.glob("*.js"))
    if not js_files:
        fail("no JavaScript modules found in src/js/")
        return 1
    config_js = build_site_config(
        business, services, hours, availability, testimonials, gallery, i18n, images
    )
    script = config_js + "\n" + "\n".join(
        f.read_text(encoding="utf-8").strip("\n") + "\n" for f in js_files
    )
    write_text(DIST / "script.js", script)
    info(f"script.js ({human(len(script.encode('utf-8')))}, {len(js_files)} modules)")

    # ---- pages ------------------------------------------------------------
    step("Rendering pages")
    today_display = datetime.now().strftime("%d.%m.%Y")
    ctx = {
        "business": business, "services": services, "hours": hours,
        "availability": availability, "testimonials": testimonials,
        "gallery": gallery, "i18n": i18n, "images": images,
        "logo": logo, "font_head": font_head,
        "today_display": today_display,
        "consent_partial": (PARTIAL_DIR / "consent.html").read_text(encoding="utf-8"),
        "maps_url": "https://www.google.com/maps/search/?api=1&query="
                    + urllib.parse.quote(str(business.get("address", ""))),
    }

    index_template = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    legal_template = (TEMPLATE_DIR / "legal.html").read_text(encoding="utf-8")

    pages = {"index.html": render_index(index_template, ctx)}
    legal_docs = {}
    for slug, title_key, sk_title, en_title in LEGAL_PAGES:
        doc = read_json(LEGAL_CONTENT_DIR / f"{slug}.json")
        legal_docs[slug] = doc
        pages[f"legal/{slug}.html"] = render_legal_page(
            legal_template, ctx, doc, slug, title_key, sk_title, en_title
        )

    for name, html in pages.items():
        write_text(DIST / name, html)
        info(f"{name} ({human(len(html.encode('utf-8')))})")

    # ---- crawler files ----------------------------------------------------
    step("Crawler files")
    domain = business["siteUrl"].rstrip("/") + "/"
    iso_date = datetime.now().strftime("%Y-%m-%d")
    urls = ["", "legal/privacy.html", "legal/gdpr.html",
            "legal/cookies.html", "legal/terms.html"]
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(
            f"  <url>\n    <loc>{domain}{path}</loc>\n    <lastmod>{iso_date}</lastmod>\n  </url>\n"
            for path in urls
        )
        + "</urlset>\n"
    )
    write_text(DIST / "sitemap.xml", sitemap)
    write_text(
        DIST / "robots.txt",
        "User-agent: *\nAllow: /\n\nSitemap: " + domain + "sitemap.xml\n",
    )
    write_text(
        DIST / "_headers",
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "\n/assets/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n"
        "\n/assets/*\n  Cache-Control: public, max-age=604800\n",
    )
    info("robots.txt, sitemap.xml, _headers")

    # ---- validation -------------------------------------------------------
    step("Validating the build")
    problems = validate(pages, i18n)
    for problem in problems:
        fail(problem)

    # ---- report -----------------------------------------------------------
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print()
    ok(f"dist/ built — {sum(1 for f in DIST.rglob('*') if f.is_file())} files, {human(total)}")
    if PLACEHOLDERS:
        print(_c(f"   NOTE {len(PLACEHOLDERS)} operator placeholder(s) still to fill in:", "36"))
        for item in PLACEHOLDERS:
            print(f"        · {item}")
        print("        These are intentional: the site must not invent real business data.")
    if problems:
        print(_c(f"\n  Build finished with {len(problems)} problem(s).", "31"))
        return 1
    print(_c("\n  Preview it with:  python -m http.server 8080 --directory dist\n", "32"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
