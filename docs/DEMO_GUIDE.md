# PawGuard 360 — Demo guide (hackathon, 7 October 2026)

Everything in the demo is **fictional data** in two demo organisations on this laptop. The journey below was run
end to end through the real interface on 6 October (Playwright recording:
`backups/demo-recording/demo-journey-2026-10-06.webm`). Longer background: `docs/RELEASE_REPORT_PREVENTION.md`.

## 1. Start, check, stop

Commands for **PowerShell** in `C:\PawGuard` (your usual terminal). Note: in PowerShell, `bash` is WSL's Linux
bash and cannot run these scripts — always use the `.ps1` launcher (it runs Git Bash for you).

1. Start **Docker Desktop** and wait for "Engine running".
2. Start everything with a clean, prepared demo (≈ 3–5 min):
   ```powershell
   cd C:\PawGuard
   .\scripts\demo_up.ps1 --reset
   ```
   It ends with a line containing `"status":"ready"`. Without `--reset` it only (re)starts the services and keeps
   the current demo data. If PowerShell refuses to run scripts:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` and retry.
3. **Keep that PowerShell window open** (minimise it) — closing it can stop the services it started.
4. Open **http://localhost:3000/en/sign-in**.

Quick commands (PowerShell, in `C:\PawGuard`):

| Purpose | Command |
|---|---|
| Health check | `curl.exe -s http://127.0.0.1:8000/health/ready` → `"status":"ready"`, migration 0011 |
| Quick reset after a rehearsal (≈ 30 s) | `.venv\Scripts\pawguard-admin.exe demo-reset --yes; .venv\Scripts\python.exe scripts\demo_prepare.py` |
| Restart services, keep data | `.\scripts\demo_up.ps1` |
| Make a backup | `& "$env:ProgramFiles\Git\bin\bash.exe" scripts/make_demo_backup.sh` |

(Git Bash users: the same scripts run as `bash scripts/demo_up.sh --reset`, etc.)

Stop after the demo (data is kept):
```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('uvicorn.exe','pawguard-worker.exe') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
npx --yes supabase@2.119.0 stop --workdir infra    # optional: stops the database containers
```

## 2. Demo accounts

On the sign-in page, under **Demo accounts (development only)**, click **Sign in as …** — no password needs to be
typed (good for screen sharing). The accounts are fictional and exist only in this local demo; the shared demo
password is documented in `README.md` for development use only.

| Role in the demo | Button | Organisation |
|---|---|---|
| Volunteer | **Sign in as Priya** | Demo — Riverside Animal Welfare Trust |
| Veterinary reviewer | **Sign in as Dr Arun** | Riverside (approved reviewer) |
| Coordinator | **Sign in as Meena** | Riverside coordinator (also a volunteer at Hillview — choose Riverside under **More → Switch organisation** if needed) |

Tip: open Priya in a normal window and Dr Arun in a private window so you don't have to sign out between steps.

**Files you will upload**
- Query photo (prepared): `C:\PawGuard\data\raw\coco\val2017_sample\000000392818.jpg`
  (a licence-filtered COCO photo; the same picture was enrolled for animal **PG-MGZ2-GBBN** by `demo_prepare.py`)
- Certificate: `C:\PawGuard\tests\fixtures\synthetic-certificate.jpg`

## 3. Three-minute walkthrough

| # | Do (exact clicks and inputs) | You should see | Say |
|---|---|---|---|
| 1 | Sign-in page → **Sign in as Priya** | *Today* page, "Demo environment" banner | "PawGuard helps community rabies programmes keep trustworthy vaccination records. Everything here is fictional demo data." |
| 2 | Left menu **Add photo** | **Find an animal from a photo** and the orange notice **Research preview — not validated** | "A volunteer meets a dog and wants to know if it's already registered." |
| 3 | **Choose photo** → select `000000392818.jpg` | Status **Checking the file…** → **Ready**, then the photo with a numbered box and **Which dog do you want to look up?** | "The photo is checked and stripped of location metadata; the detector only marks where a dog may be." |
| 4 | Click **Dog 1**. If **Why use this photo anyway?** appears, type `Clearest photo taken today`. Click **Look for possible matches** | "Looking through this organisation's photos…", then **Possible matches** → **Possible match 1 · PG-MGZ2-GBBN** with **Your photo** beside **On record** photos, no percentages | "These are suggestions, not identifications. There's no confidence percentage on purpose — the person compares the photos." |
| 5 | On the card: **This is the same animal** → dialog **Record this photo as a sighting of PG-MGZ2-GBBN?** → **Yes, same animal** | The animal's profile, *Sightings* tab, with today's sighting | "Nothing is linked until a person confirms." |
| 6 | Click **Record vaccination evidence**. **Date**: yesterday · **Vaccine product**: *DEMO Rabies Vaccine A (fictional)* · **Lot / batch number**: *DEMO-A-001* · **Given by (name)**: `Dr Fictional (demo)` · evidence **Choose file** → `synthetic-certificate.jpg` (wait for **Ready**) → **Submit for review** | Record page **Submitted for review** | "Volunteers submit evidence; they can't verify it — the server refuses even a hand-made request." |
| 7 | Switch to Dr Arun's window (or **Sign out** → **Sign in as Dr Arun**) → menu **Review** → click **PG-MGZ2-GBBN** in *Waiting for review* | **Verification workbench** with the record and the certificate | "Only an approved veterinary reviewer, who didn't submit it, can verify." |
| 8 | **Verify** → read the dialog → **Verify** | Dialog text: verifying "does not certify that the animal cannot carry or transmit disease"; then **Record verified.** | "We are careful about what a record means." |
| 9 | Priya's window → open PG-MGZ2-GBBN (Animals → search `PG-MGZ2-GBBN`) → press **F5** | **Last verified vaccination record: <date>** and "It does not mean the animal cannot carry or transmit disease." — still there after refresh | "It's stored server-side with a full audit trail, and another organisation can't see any of it." |
| 10 (close) | — | — | "Photo matching is research-only: on a pet-dog face benchmark the right dog was among 3 suggestions 89% of the time, but it suggested a dog for 11% of unknown animals — above our 10% limit — and it hasn't been tested on street dogs. Real organisations can't switch it on. Field data and clinical review are next." |

**If matching shows "No similar animals found"** (e.g. after a reset without `demo_prepare.py`): say "it found no
similar animal — that doesn't prove the dog is new", click **Search the registry instead**, open any animal, and
continue from step 6. To restore the prepared match: `.venv\Scripts\python.exe scripts\demo_prepare.py`.

**Optional extras if asked (30 s each)**
- *Offline:* as Priya open **Offline field kit** → **Use this device for field work** (once) → browser DevTools →
  Network → **Offline** → reload → **Start** a task → "Not sent yet" → set back to **No throttling** → "Sent: 1 applied…".
- *Planning:* as Meena → **Campaign planning** → **Demo October vaccination round** → **Make plan** → point at
  "Travel times are straight-line distance × 1.3 at 15 km/h — an estimate" and **Not planned, and why**.

## 4. Recovery during the demo

| What happens | Do this |
|---|---|
| Photo stays on **Checking the file…** / "Saved. It will be checked shortly" for > 20 s | Worker or dispatcher stopped: run `.\scripts\demo_up.ps1` (≈ 2 min), then **Remove** the photo and choose it again |
| "This file was not accepted: …" or "Upload failed. Check your connection and try again." | Use **Choose another file** with the same prepared photo; check the API with the health command |
| "Automatic detection isn't available right now. You can still use this photo." | Choose **None of these / not sure** and continue — lookup then compares the whole photo; or use **Search the registry instead** |
| "Photo comparison isn't available" (no lookup page) | Research preview is off: `.venv\Scripts\pawguard-admin.exe models research-preview dinov2_small_arcface_head ed25f3a3-resize224-head-v1 --reason "demo"`; meanwhile use **Find the animal in the registry** |
| "Photo comparison didn't work this time" / "Results may be incomplete" | Click **Search again**; if it persists, `.\scripts\demo_up.ps1` and use the registry search |
| "Your session has ended. Please sign in again." | Click **Sign in as …** again; work already submitted is saved |
| Page error or blank | `.\scripts\demo_up.ps1` (restarts API, worker and web; keeps data) |
| Demo data messy | `.venv\Scripts\pawguard-admin.exe demo-reset --yes; .venv\Scripts\python.exe scripts\demo_prepare.py` (demo organisations only) |
| "uv: command not found" | You ran `bash …` from PowerShell (that is WSL). Use `.\scripts\demo_up.ps1` |
| Nothing works | Play `backups/demo-recording/demo-journey-2026-10-06.webm` and show `docs/screenshots/phase9/` |

Backups and full restoration: `docs/BACKUP_RESTORE.md`.

## 5. Real-phone check (Android Chrome recommended)

Offline mode needs a **secure context**: `https://…` or `http://localhost`. On plain `http://<laptop-ip>:3000` the
offline page cannot be stored (forms still work).

1. Phone: Settings → Developer options → **USB debugging** on; connect by USB.
2. Laptop Chrome: `chrome://inspect` → **Port forwarding…** → add `3000` → `localhost:3000`, tick *Enable*.
3. Phone Chrome: open `http://localhost:3000/en/sign-in` → **Sign in as Priya**.
4. **More** → **Offline field kit** → **Use this device for field work** → expect "Ready. N tasks are saved…".
5. Airplane mode **on** → reload the kit → expect **Offline** and the task list.
6. **Start** a task; on a task with an animal **Record a sighting** → expect "Not sent yet" and "2 changes are saved…".
7. Close the tab, reopen the kit (still offline) → changes still listed.
8. Airplane mode **off** → expect "Sent: 2 applied…" (or tap **Send changes now**).
9. Conflict: on the laptop as Meena cancel one of Priya's tasks; on the phone go offline, **Complete** it, go online →
   expect **Changes that need your decision** … "It is now: cancelled. Nothing was overwritten."
10. **Sign out** with a change unsent → expect the warning → **Sign out and delete them**.
11. Note phone model, browser version and anything that failed. iPhone: needs HTTPS (USB forwarding is Android-only).

Not available offline (by design): photos, vaccination evidence, registering animals, photo lookup, the map.

## 6. Limitations to state honestly

- **Fictional data only**; no real programme, clinician or field team has used it.
- **Photo matching is research-only.** Evaluated once on a test split of the DogFaceNet face benchmark (pet dogs,
  aligned face crops, unreviewed labels): 147 enrolled + 63 unknown identities, 479 known + 336 unknown queries;
  right animal among shown candidates **0.887** (95% CI 0.852–0.920); a suggestion for an unknown animal **0.107**
  (0.056–0.169) at the threshold 0.538 chosen on validation. Release gate (field photos of community dogs, unknown
  false suggestions ≤ 0.10) **not met**. Street dogs **not tested**. The demo match uses the same photo that was
  enrolled, so it shows the workflow, not accuracy.
- **Offline**: tasks and sightings only; no offline photos or vaccination evidence; not yet tested on real phones.
- **Tamil and Hindi** are partial drafts: many screens fall back to English with a "draft translation" notice.
- **Planning** uses straight-line travel estimates and estimates from single street counts or registry records —
  not population or coverage.
- Health and first-aid wording has **not** been reviewed by clinicians.

## 7. Making the backup video yourself (checklist)

1. `.\scripts\demo_up.ps1 --reset`; close other apps and notifications; browser zoom 100%, window ~1280×800.
2. Use only the **Sign in as …** buttons — never type the password on camera; keep `.env` and terminals off-screen.
3. Windows: **Win + Alt + R** (Xbox Game Bar) records the active window; or OBS "Window capture".
4. Follow §3 steps 1–9, speaking the "Say" column; aim for under 3 minutes.
5. Stop recording; watch it once; save to `backups/demo-recording/` and a USB stick.
