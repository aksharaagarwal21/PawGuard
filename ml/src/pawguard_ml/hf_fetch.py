"""Pinned, checksum-verified download of Hugging Face model files (no remote code, no pickle weights).

Large files are checked against the LFS sha256 the Hub publishes for that exact revision; small files against their
git blob id. Anything that does not match is deleted and the command fails."""

import hashlib
import json
import urllib.request
from pathlib import Path

API = "https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true"
FILE = "https://huggingface.co/{repo}/resolve/{rev}/{name}"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_blob(p: Path) -> str:
    data = p.read_bytes()
    return hashlib.sha1(b"blob %d\x00" % len(data) + data, usedforsecurity=False).hexdigest()


def fetch(repo: str, revision: str, names: list[str], dest: Path) -> dict:
    if len(revision) != 40:
        raise ValueError("revision must be a full 40-character commit hash")
    with urllib.request.urlopen(API.format(repo=repo, rev=revision), timeout=60) as r:  # noqa: S310 (fixed https host)
        meta = json.load(r)
    if meta.get("sha") != revision:
        raise RuntimeError(f"Hub returned revision {meta.get('sha')}, expected {revision}")
    siblings = {s["rfilename"]: s for s in meta["siblings"]}
    dest.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in names:
        if name.endswith((".bin", ".pt", ".pth", ".pkl", ".py")):
            raise ValueError(f"refusing pickle/code file {name}")
        s = siblings.get(name)
        if s is None:
            raise FileNotFoundError(f"{name} not in {repo}@{revision}")
        out = dest / name
        if not out.exists() or out.stat().st_size != s["size"]:
            tmp = out.with_suffix(out.suffix + ".part")
            urllib.request.urlretrieve(FILE.format(repo=repo, rev=revision, name=name), tmp)  # noqa: S310
            tmp.replace(out)
        lfs = (s.get("lfs") or {}).get("sha256")
        ok = (_sha256(out) == lfs) if lfs else (_git_blob(out) == s["blobId"])
        if not ok:
            out.unlink()
            raise RuntimeError(f"checksum mismatch for {name}; file removed")
        files[name] = {"size_bytes": out.stat().st_size, "sha256": _sha256(out),
                       "verified_against": "hub LFS sha256" if lfs else "hub git blob id"}
    return {"repo": repo, "revision": revision, "licence": (meta.get("cardData") or {}).get("license"),
            "last_modified": meta.get("lastModified"), "files": files}
