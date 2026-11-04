"""Local OCR for KYC documents (Tesseract), tuned for photographed/scanned certificates.

Pipeline: red channel (drops the pink "SPECIMEN" watermark while keeping black text) →
binarise → deskew by projection profile → upscale → Tesseract. A Laplacian blur score
flags photos that are too soft to trust, so we ask for a retake instead of guessing.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

BLUR_THRESHOLD = 120.0  # variance of Laplacian on a 1000px-wide greyscale; sharp scans are well above
TESSERACT = shutil.which("tesseract") or "tesseract"


@dataclass
class OcrResult:
    text: str
    lines: list[str]
    skew_deg: float
    blur_score: float
    width: int
    height: int
    mean_confidence: float
    warnings: list[str] = field(default_factory=list)


def _load(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def blur_score(im: Image.Image) -> float:
    g = im.convert("L")
    if g.width > 1000:
        g = g.resize((1000, int(g.height * 1000 / g.width)))
    a = np.asarray(g, dtype=np.float32)
    lap = (-4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:])
    return float(lap.var())


def _binarise(im: Image.Image, cut: int = 150) -> Image.Image:
    r, _, _ = im.split()
    return r.point(lambda v: 0 if v < cut else 255)


def skew_angle(bw: Image.Image, limit: float = 15.0, step: float = 0.5) -> float:
    small = bw.resize((max(1, bw.width // 3), max(1, bw.height // 3)))
    best_a, best_s = 0.0, -1.0
    for a in np.arange(-limit, limit + 0.001, step):
        arr = np.asarray(small.rotate(float(a), fillcolor=255)) < 128
        s = float(np.var(arr.sum(axis=1)))
        if s > best_s:
            best_a, best_s = float(a), s
    return best_a


def _tesseract(img: Image.Image, psm: int = 6, extra: list[str] | None = None) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    cmd = [TESSERACT, "stdin", "stdout", "--psm", str(psm)] + (extra or [])
    out = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, timeout=60)
    return out.stdout.decode("utf-8", "replace")


def _confidence(img: Image.Image) -> float:
    tsv = _tesseract(img, 6, ["tsv"])
    confs = []
    for row in tsv.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) == 12 and parts[11].strip():
            try:
                c = float(parts[10])
            except ValueError:
                continue
            if c >= 0:
                confs.append(c)
    return float(np.mean(confs)) if confs else 0.0


def prepare(data: bytes) -> tuple[Image.Image, float, float, Image.Image]:
    im = _load(data)
    blur = blur_score(im)
    bw = _binarise(im)
    angle = skew_angle(bw)
    if abs(angle) >= 0.5:
        im = im.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)
    big = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    return _binarise(big, 160), angle, blur, im


def read(data: bytes) -> OcrResult:
    bw, angle, blur, _ = prepare(data)
    text = _tesseract(bw, 6)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    conf = _confidence(bw)
    warnings = []
    if blur < BLUR_THRESHOLD:
        warnings.append("blurry")
    if abs(angle) >= 2:
        warnings.append(f"straightened {angle:+.1f}°")
    return OcrResult(text=text, lines=lines, skew_deg=angle, blur_score=round(blur, 1), width=bw.width // 2,
                     height=bw.height // 2, mean_confidence=round(conf, 1), warnings=warnings)


def read_line_strict(data: bytes, label_pattern: str, charset: str) -> str | None:
    """Re-read one labelled field (e.g. the GSTIN line) with a character whitelist."""
    bw, _, _, _ = prepare(data)
    tsv = _tesseract(bw, 6, ["tsv"])
    rows = [r.split("\t") for r in tsv.splitlines()[1:]]
    words = [r for r in rows if len(r) == 12 and r[11].strip()]
    label = re.compile(label_pattern, re.I)
    for w in words:
        if label.search(w[11]):
            top, height = int(w[7]), int(w[9])
            line = [x for x in words if abs(int(x[7]) - top) < height and int(x[6]) > int(w[6]) + int(w[8])]
            if not line:
                return None
            left = min(int(x[6]) for x in line) - 10
            right = max(int(x[6]) + int(x[8]) for x in line) + 10
            crop = bw.crop((max(0, left), max(0, top - 12), min(bw.width, right), top + height + 12))
            txt = _tesseract(crop, 7, ["-c", f"tessedit_char_whitelist={charset}"])
            return re.sub(r"\s+", "", txt) or None
    return None
