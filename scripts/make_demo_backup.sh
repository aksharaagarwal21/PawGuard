#!/usr/bin/env bash
# Create a local, Git-ignored backup that can restore the PawGuard demonstration on this or another machine.
# Contents: Git history (bundle), model files (checksum-verified), database dump of the demo state, storage
# objects, the licence-filtered COCO sample photos, the demo recording (if present), SHA256SUMS and RESTORE.md.
# Credentials (.env, infra/supabase/signing_keys.json) are NOT copied — keep them separately (see RESTORE.md).
#   bash scripts/make_demo_backup.sh            → backups/demo-backup-<date>/
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="backups/demo-backup-$(date +%Y-%m-%d)"
rm -rf "$DEST" && mkdir -p "$DEST"/{repo,models,database,demo-media,video}

echo "1/6 Git history"
git bundle create "$DEST/repo/pawguard.bundle" --all >/dev/null 2>&1
git bundle verify "$DEST/repo/pawguard.bundle" >/dev/null 2>&1 && echo "   bundle verified ($(git rev-list --all | wc -l) commits, HEAD $(git rev-parse --short HEAD))"
if [ -n "$(git status --porcelain)" ]; then echo "   NOTE: uncommitted changes exist and are NOT in the bundle"; fi

echo "2/6 Model files"
cp -r models/. "$DEST/models/"
mkdir -p "$DEST/models/identity-head"
cp data/derived/runs/identity-head-*/head.safetensors "$DEST/models/identity-head/" 2>/dev/null || echo "   (no trained head found under data/derived/runs)"
bad=0
while IFS= read -r -d '' f; do
  rel="${f#models/}"
  [ "$(sha256sum "$f" | cut -d' ' -f1)" = "$(sha256sum "$DEST/models/$rel" | cut -d' ' -f1)" ] || { echo "   MISMATCH $rel"; bad=1; }
done < <(find models -type f -print0)
python - "$DEST" <<'PY' || bad=1
import hashlib, json, pathlib, sys
dest = pathlib.Path(sys.argv[1]) / "models"
ok = True
for m in sorted(pathlib.Path("data/manifests/models").glob("*.json")):
    d = json.loads(m.read_text(encoding="utf-8"))
    checks = [(d["artifact_path"], d["sha256"])] if "artifact_path" in d else         [(f"dinov2-small/{d['revision']}/{name}", f["sha256"]) for name, f in d.get("files", {}).items()]
    for rel, want in checks:
        have = hashlib.sha256((dest / rel).read_bytes()).hexdigest()
        print(("   ok   " if have == want else "   FAIL ") + f"{rel} vs {m.name}")
        ok &= have == want
sys.exit(0 if ok else 1)
PY
[ $bad -eq 0 ] || { echo "model copy verification failed" >&2; exit 1; }

echo "3/6 Database (app + auth schemas; demo data only in this environment)"
docker exec supabase_db_pawguard pg_dump -U postgres -d postgres --schema=app --schema=auth -Fc > "$DEST/database/pawguard-demo.dump"
docker cp supabase_storage_pawguard:/mnt/stub "$DEST/database/storage-objects" >/dev/null
echo "   dump $(du -h "$DEST/database/pawguard-demo.dump" | cut -f1), storage objects $(find "$DEST/database/storage-objects" -type f | wc -l)"

echo "4/6 Demo media"
cp -r data/raw/coco/val2017_sample "$DEST/demo-media/coco-val2017-sample"
cp data/manifests/coco-val2017-dog-sample-v1.json "$DEST/demo-media/"
cp tests/fixtures/*.jpg "$DEST/demo-media/"

echo "5/6 Demo recording"
cp backups/demo-recording/*.webm "$DEST/video/" 2>/dev/null || echo "   (no recording found)"

echo "6/6 Checksums and instructions"
cp docs/BACKUP_RESTORE.md "$DEST/RESTORE.md"
(cd "$DEST" && find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt)
(cd "$DEST" && sha256sum --quiet -c SHA256SUMS.txt) && echo "   SHA256SUMS verified"
echo "Backup ready: $DEST ($(du -sh "$DEST" | cut -f1)). Not for sharing: the database dump contains demo account hashes."
