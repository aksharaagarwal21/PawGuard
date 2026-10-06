"""Measure certificate reading (OCR + parsing) on SYNTHETIC certificates with known answers.

This is not field accuracy: real certificates (handwriting, stamps, glare, folds) will do worse, and we have none to
test on yet. It tells us whether the pipeline works per language and which fields fail.

    uv run python scripts/ocr_eval.py --n 20      # writes docs/evidence/ocr-synthetic-eval.json

Needs Tesseract with eng/hin/tam language data (docs/FREE_SERVICES_SETUP.md) and a font with Devanagari and Tamil
(Windows: Nirmala UI).
"""

import argparse
import io
import json
import random
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pawguard_api.domain.certificate_parse import parse
from pawguard_api.integrations import ocr
from pawguard_api.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
FONTS = [r"C:\Windows\Fonts\Nirmala.ttc", r"C:\Windows\Fonts\Nirmala.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"]
PRODUCTS = [("p-rabies", "Rabies vaccine"), ("p-dhppi", "DHPPi combination"), ("p-tricat", "Feline tricat combination")]
VACCINES = {"en": [("Anti-Rabies Vaccine", "p-rabies"), ("DHPPi + L", "p-dhppi"), ("Feline Tricat", "p-tricat")],
            "hi": [("रेबीज टीका", "p-rabies"), ("डिस्टेंपर पार्वो", "p-dhppi")],
            "ta": [("ரேபிஸ் தடுப்பூசி", "p-rabies"), ("பார்வோ தடுப்பூசி", "p-dhppi")]}
LABELS = {"en": ("Date of vaccination", "Vaccine", "Batch No", "Next due date"),
          "hi": ("टीकाकरण दिनांक", "टीका", "बैच", "अगली तारीख"),
          "ta": ("தடுப்பூசி தேதி", "தடுப்பூசி", "லாட்", "அடுத்த தேதி")}


def font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    raise SystemExit("No font with Devanagari/Tamil found (Nirmala UI or Noto Sans).")


def make(lang: str, rng: random.Random, today: date) -> tuple[bytes, dict[str, object]]:
    given = today - timedelta(days=rng.randint(1, 300))
    due = given + timedelta(days=365)
    vaccine, pid = rng.choice(VACCINES[lang])
    lot = f"{rng.choice('ABKMR')}{rng.randint(100, 999)}{rng.choice('XYZ')}{rng.randint(10, 99)}"
    lab = LABELS[lang]
    lines = ["PET VACCINATION CERTIFICATE (SYNTHETIC TEST)", f"{lab[0]}: {given:%d/%m/%Y}", f"{lab[1]}: {vaccine}",
             f"{lab[2]}: {lot}", f"{lab[3]}: {due:%d/%m/%Y}", "Clinic: Demo clinic (fictional)"]
    im = Image.new("RGB", (1200, 700), (250, 248, 240))
    d = ImageDraw.Draw(im)
    f_big, f = font(40), font(34)
    y = 50
    for i, ln in enumerate(lines):
        d.text((60, y), ln, fill=(25, 25, 30), font=f_big if i == 0 else f)
        y += 90
    im = im.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=(250, 248, 240))
    im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0, 1.2)))
    im = im.resize((int(im.width * 0.8), int(im.height * 0.8)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=rng.randint(55, 85))
    return buf.getvalue(), {"given": given, "due": due, "product_id": pid, "lot": lot}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="certificates per language")
    ap.add_argument("--seed", type=int, default=20261007)
    args = ap.parse_args()
    s = get_settings()
    st = ocr.status(s)
    if not st["available"]:
        raise SystemExit(f"OCR not available: {st['reason']}")
    rng = random.Random(args.seed)  # noqa: S311 - reproducible test data, not security
    today = date.today()
    results: dict[str, dict[str, object]] = {}
    for lang in ("en", "hi", "ta"):
        if lang != "en" and {"en": "eng", "hi": "hin", "ta": "tam"}[lang] not in st["languages"]:  # type: ignore[operator]
            results[lang] = {"skipped": "language data not installed"}
            continue
        hits = {"given": 0, "due": 0, "product": 0, "lot": 0, "all_four": 0}
        confs: list[float] = []
        for _ in range(args.n):
            image, truth = make(lang, rng, today)
            r = ocr.extract(s, image, demo_org=True)
            if r.confidence is not None:
                confs.append(r.confidence)
            dft = parse(r.text, PRODUCTS, today)
            ok = {"given": dft.administered_on == truth["given"], "due": dft.next_due_on == truth["due"],
                  "product": dft.product_id == truth["product_id"], "lot": dft.lot_text == truth["lot"]}
            for k, v in ok.items():
                hits[k] += int(v)
            hits["all_four"] += int(all(ok.values()))
        results[lang] = {"n": args.n, **{f"{k}_correct": round(v / args.n, 3) for k, v in hits.items()},
                         "mean_ocr_confidence": round(sum(confs) / len(confs), 3) if confs else None}
    out = {"what": "Synthetic printed certificates with known answers (blur, slight rotation, JPEG). NOT field "
                   "accuracy: no real certificates were available.",
           "engine": st["engine"], "languages": st["languages"], "seed": args.seed, "date": str(today),
           "results": results}
    path = ROOT / "docs/evidence/ocr-synthetic-eval.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
