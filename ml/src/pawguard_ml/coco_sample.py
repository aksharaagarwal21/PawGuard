"""Build a small, licence-filtered COCO val2017 sample for detector checks.

- Only images whose per-image licence is CC BY (4), CC BY-SA (5), "No known copyright restrictions" (7) or
  "United States Government Work" (8). Images stay in data/raw (gitignored) and are never redistributed or shown
  in the product; the manifest records ids, licence, source URLs, checksums and ground-truth boxes.
- Dog positives (COCO category 18 = "dog"; YOLOX's contiguous index for it is 16) and dog-free negatives.
- Deterministic (seeded) split into a *verification* subset — used only to confirm the artefact's preprocessing
  contract — and an *evaluation* subset that is not used for any choice.
COCO val2017 was not part of the detector's training split (train2017), but it is the benchmark the authors
reported on and may have influenced their model selection; and it is not Indian street-dog imagery.
"""

import hashlib
import json
import random
import zipfile
from pathlib import Path

import httpx

ALLOWED_LICENSES = {4, 5, 7, 8}
COCO_DOG_CATEGORY = 18


def build(zip_path: Path, out_dir: Path, manifest_path: Path, n_pos: int = 60, n_neg: int = 25,
          n_verify: int = 15, seed: int = 20261006) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        data = json.loads(z.read("annotations/instances_val2017.json"))
    licenses = {lic["id"]: lic for lic in data["licenses"]}
    images = {im["id"]: im for im in data["images"] if im["license"] in ALLOWED_LICENSES}
    boxes: dict[int, list[list[float]]] = {}
    crowd_or_dog: set[int] = set()
    for ann in data["annotations"]:
        if ann["image_id"] not in images:
            continue
        if ann["category_id"] == COCO_DOG_CATEGORY:
            crowd_or_dog.add(ann["image_id"])
            if not ann.get("iscrowd"):
                boxes.setdefault(ann["image_id"], []).append([round(v, 2) for v in ann["bbox"]])
    has_crowd_dog = {a["image_id"] for a in data["annotations"] if a["category_id"] == COCO_DOG_CATEGORY
                     and a.get("iscrowd")}
    positives = sorted(i for i in boxes if i not in has_crowd_dog)
    negatives = sorted(i for i in images if i not in crowd_or_dog)
    rng = random.Random(seed)
    pos = rng.sample(positives, min(n_pos, len(positives)))
    neg = rng.sample(negatives, min(n_neg, len(negatives)))
    verify = set(pos[:n_verify])
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for image_id in pos + neg:
            im = images[image_id]
            dest = out_dir / im["file_name"]
            if not dest.exists():
                r = client.get(im["coco_url"])
                r.raise_for_status()
                dest.write_bytes(r.content)
            entries.append({
                "image_id": image_id, "file_name": im["file_name"], "width": im["width"], "height": im["height"],
                "license_id": im["license"], "license": licenses[im["license"]]["name"],
                "flickr_url": im.get("flickr_url"), "coco_url": im["coco_url"],
                "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                "dog_boxes_xywh": boxes.get(image_id, []),
                "split": "verification" if image_id in verify else "evaluation",
                "kind": "positive" if image_id in boxes else "negative",
            })
    manifest = {
        "name": "coco-val2017-dog-sample", "version": "1", "seed": seed,
        "source": "COCO 2017 val (https://cocodataset.org); annotations CC BY 4.0; images per-image licence",
        "allowed_license_ids": sorted(ALLOWED_LICENSES),
        "counts": {"positives": len(pos), "negatives": len(neg), "verification": len(verify),
                   "dog_boxes": sum(len(e["dog_boxes_xywh"]) for e in entries)},
        "limitations": ["Pet/street photos from Flickr, not Indian community-dog field imagery",
                        "val2017 is the authors' benchmark split", "Crowd-annotated dog images excluded"],
        "images": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest["counts"]
