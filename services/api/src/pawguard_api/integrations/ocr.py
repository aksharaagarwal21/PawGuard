"""OCR adapter for vaccination certificates: Tesseract (local, eng+hin+tam) or, for demo organisations only, Gemini
vision. The output is raw text for `domain/certificate_parse.py`; it is never stored.

Gemini vision is limited to demo organisations because real certificates carry people's names and addresses and the
free tier's terms say not to submit personal information.
"""

import base64
import io
import os
import shutil
from dataclasses import dataclass

from pawguard_api.settings import Settings

WINDOWS_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
WANTED_LANGS = ("eng", "hin", "tam")


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float | None  # mean word confidence 0..1 (Tesseract); None when the engine gives none
    engine: str
    languages: tuple[str, ...]


class OcrUnavailable(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def tesseract_cmd(s: Settings) -> str | None:
    for candidate in (s.tesseract_cmd, shutil.which("tesseract"), WINDOWS_DEFAULT):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def status(s: Settings) -> dict[str, object]:
    if s.ocr_engine == "off":
        return {"available": False, "engine": "off", "languages": [], "reason": "OCR is switched off"}
    if s.ocr_engine == "gemini":
        ok = bool(s.gemini_api_key and s.gemini_model)
        return {"available": ok, "engine": "gemini", "languages": ["any"],
                "reason": None if ok else "Gemini key or model not set"}
    cmd = tesseract_cmd(s)
    if not cmd:
        return {"available": False, "engine": "tesseract", "languages": [],
                "reason": "Tesseract is not installed (see docs/FREE_SERVICES_SETUP.md)"}
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        have = set(pytesseract.get_languages(config=_config(s)))
    except Exception:
        return {"available": False, "engine": "tesseract", "languages": [], "reason": "Tesseract did not start"}
    langs = [lang for lang in WANTED_LANGS if lang in have]
    return {"available": "eng" in langs, "engine": "tesseract", "languages": langs,
            "reason": None if "eng" in langs else "English language data missing"}


def _config(s: Settings) -> str:
    return f'--tessdata-dir "{s.tessdata_dir}"' if s.tessdata_dir else ""


def _prepare(image: bytes) -> "object":
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(image))
    im = ImageOps.exif_transpose(im).convert("L")
    if im.width < 1400:  # small photos read much better when enlarged
        factor = 1400 / im.width
        im = im.resize((int(im.width * factor), int(im.height * factor)), Image.Resampling.LANCZOS)
    return ImageOps.autocontrast(im, cutoff=1)


def extract(s: Settings, image: bytes, *, demo_org: bool) -> OcrResult:
    if s.ocr_engine == "gemini":
        if not demo_org:
            raise OcrUnavailable("gemini_demo_only", "Gemini vision is only used for demo organisations")
        return _gemini(s, image)
    st = status(s)
    if not st["available"]:
        raise OcrUnavailable("ocr_unavailable", str(st["reason"]))
    import pytesseract

    langs = "+".join(st["languages"])  # type: ignore[arg-type]
    data = pytesseract.image_to_data(_prepare(image), lang=langs, config=_config(s),
                                     output_type=pytesseract.Output.DICT, timeout=30)
    lines: dict[tuple[int, int, int], list[str]] = {}
    confs: list[float] = []
    for i, word in enumerate(data["text"]):
        if not str(word).strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(str(word))
        try:
            c = float(data["conf"][i])
            if c >= 0:
                confs.append(c / 100)
        except (TypeError, ValueError):
            pass
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    return OcrResult(text, sum(confs) / len(confs) if confs else None, "tesseract", tuple(st["languages"]))  # type: ignore[arg-type]


def _gemini(s: Settings, image: bytes) -> OcrResult:
    import httpx

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}},
        {"text": "Transcribe all text on this vaccination certificate exactly, line by line. "
                 "Do not add, correct or interpret anything."}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1500}}
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": s.gemini_api_key or ""}, timeout=40)
    except httpx.HTTPError as exc:
        raise OcrUnavailable("ocr_unreachable", "Gemini not reachable") from exc
    if r.status_code == 429:
        raise OcrUnavailable("ocr_busy", "Gemini free-tier limit reached")
    if r.status_code >= 400:
        raise OcrUnavailable("ocr_unreachable", f"Gemini HTTP {r.status_code}")
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, ValueError) as exc:
        raise OcrUnavailable("ocr_unreachable", "Unexpected Gemini response") from exc
    return OcrResult(text, None, "gemini", ("any",))
