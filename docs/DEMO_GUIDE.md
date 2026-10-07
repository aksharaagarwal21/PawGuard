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
3. Opening the bare address (e.g. http://localhost:3000) shows the **demo instructions page** first; its
   **Let's start** button opens the sign-in page. Sample photo and certificate are downloadable there.
4. **Keep that PowerShell window open** (minimise it) — closing it can stop the services it started.
5. Open **http://localhost:3000** (instructions) or go straight to **http://localhost:3000/en/sign-in**.

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

## 1b. Temporary public link (for judges' phones)

The app can be reached from any device through a temporary HTTPS address (Cloudflare Quick Tunnel, no account).
It runs **from this laptop**: it stops if the laptop sleeps, loses internet, or the services stop, and the address
changes every time it is started. Anyone with the link can use the fictional demo accounts — stop it after the
event.

```powershell
.\scripts\public_link.ps1          # prints PUBLIC LINK: https://<random>.trycloudflare.com/en/sign-in
.\scripts\public_link.ps1 --stop   # stops the public address (local app keeps running)
```

What it does: downloads the official `cloudflared` into `.tools\` (first time), starts the tunnel, adds the address to
`PAWGUARD_EXTRA_WEB_ORIGINS` and sets `PAWGUARD_STORAGE_SAME_ORIGIN=true` in `.env` (photos are then served through
the web app's signed-link paths only), restarts the API and web, and checks the public page answers. Because it is
HTTPS, phones can also try the offline field kit through it.

Verified on 6 October through a public link: the full §3 journey (sign-in, photo upload, possible match,
confirmation, evidence, verification, refresh) passed, and photos loaded remotely.

## 2. Demo accounts

On the sign-in page, under **Demo accounts (development only)**, click **Sign in as …** — no password needs to be
typed (good for screen sharing). The accounts are fictional and exist only in this local demo; the shared demo
password is documented in `README.md` for development use only.

| Role in the demo | Button | Organisation |
|---|---|---|
| Volunteer | **Sign in as Priya** | Demo — Riverside Animal Welfare Trust |
| Veterinary reviewer | **Sign in as Dr Arun** | Riverside (approved reviewer) |
| Coordinator | **Sign in as Meena** | Riverside coordinator (also a volunteer at Hillview — choose Riverside under **More → Switch organisation** if needed) |
| Pet owner | **Sign in as Neha** | Demo — Lotus Pet Clinic (fictional): Bruno (up to date), Misty (due soon), Coco (overdue) |
| Clinic vet | **Sign in as Dr Kiran** | Lotus (approved veterinary reviewer) |
| Clinic manager | **Sign in as Asha** | Lotus (dashboard and counts; cannot verify) |
| Another clinic | **Sign in as Vikram** | Demo — Banyan Veterinary Centre (fictional): sees none of Lotus's pets |

Tip: open Priya in a normal window and Dr Arun in a private window so you don't have to sign out between steps.

**Files you will upload**
- Query photo (prepared): `C:\PawGuard\data\raw\coco\val2017_sample\000000392818.jpg`
  (a licence-filtered COCO photo; the same picture was enrolled for animal **PG-MGZ2-GBBN** by `demo_prepare.py`)
- Certificate: `C:\PawGuard\tests\fixtures\synthetic-certificate.jpg`

## 3a. Pet vaccination reminders — two-minute walkthrough (the hackathon topic)

Prepare with `bash scripts/demo_up.sh --reset` (seeds the three pets and submits one owner upload for Bruno).
Certificate to upload: `C:\PawGuard\tests\fixtures\synthetic-certificate.jpg` (also on the welcome page).

| # | Do | You should see | Say |
|---|---|---|---|
| 1 | **Sign in as Neha** | *My pets*: Bruno **Up to date**, Misty **Due soon**, Coco **Overdue**; bell shows **2** | "An owner sees one clear status per pet. Every date comes from the vet." |
| 2 | **Reminders** → on Coco open **Notification preview** | Email and SMS text, "Preview only — no message is actually sent." | "Reminders appear 14, 7 and 1 day before and when overdue. In the demo nothing is sent." |
| 3 | Coco → **Add to calendar (.ics)** (optional) → **Mark as done** → certificate → **Mark as done** | "Saved. The clinic's vet will check the certificate." Coco is still **Overdue**, "1 record is waiting…" | "An owner's entry never counts until a vet verifies it." |
| 4 | Sign out → **Sign in as Dr Kiran** → **Clinic** | "2 of 3 registered pets up to date — Based on pets registered in this app — not population coverage."; *Awaiting verification*: Bruno and Coco (**Entered by owner**) | "The clinic sees who is due this week, overdue or waiting." |
| 5 | Coco → **Review** → **Verify** → **Next due date** one year ahead → **Verify** | Record verified | "Only an approved vet verifies; the vet sets the next due date." |
| 6 | **Clinic** → **+7 days** | Misty moves to **Due this week**; then **Back to the real date** | "A demo-only clock shows how reminders progress; stored dates never change." |
| 7 | Sign in as Neha → Coco → **Vaccination card (QR)** → open the link | Coco **Up to date**, verified vaccinations only, "This card shows recorded vaccinations. It is not a health guarantee." | "A groomer or boarding kennel can scan it. The owner can replace or turn off the QR code." |

## 3b. Signed certificates + "This pet bit someone" — two-minute script

Before the demo: open `/en/verify` once on the phone while online (it then works offline), and on the laptop open
`/en/verify/samples` (demo mode only). Sign in on the phone's second tab as Neha once, open Bruno → Vaccination card
(this creates the collar QR), then sign out.

| # | Do | Say |
|---|---|---|
| 1 | Phone: `/en/verify` → **Scan with camera** → scan the **Genuine** sample on the laptop | "Bruno's rabies certificate is signed by the clinic's key. The phone checks the signature itself — green: issued by Lotus Pet Clinic, not changed. It tells us to check the animal matches." |
| 2 | Scan the **Altered** sample | "Same certificate, one date changed by one day — red: changed or not issued by a registered clinic." |
| 3 | Turn on airplane mode; scan Genuine, Altered and **Cancelled** again | "No connection needed — the trust list and cancellations are cached and root-signed. The cancelled one shows amber." Turn airplane mode off. |
| 4 | Scan Bruno's collar QR (or open his card) → red **Did this pet bite someone? Get help now** | "Bite mode. First aid comes first, before anything else — wash 15 minutes, see a doctor today whatever the vaccination status, no home remedies, call 112." Switch the language to Tamil or Hindi. |
| 5 | Scroll: the record shows "Signed certificate checked" | "The doctor sees the rabies record with the signature check — and the doctor decides the treatment." |
| 6 | Fill **Report this bite** (date, person) → **Send report** → copy the private link | "No account, no photo. The reporter gets a private link; the owner never sees the reporter's details." |
| 7 | Laptop: sign in as Neha → banner "Bruno was reported in a bite" → **Bite reports** → tap **Normal** → Save | "The owner was alerted on her channel and records one tap a day for 10 days. Day 2 shows **No update** — we never assume the pet is fine. Misty shows a change: 'Contact your vet now'." |
| 8 | Reporter link → **Make a doctor link** → open it | "A read-only page for the doctor, expiring in 30 days, revocable, every view logged. Urgent changes show a red banner: tell your doctor right away." |

Fixed demo reporter links (fictional data only): `/en/bite/pawguard-demo-reporter-link-bruno-0001` (day 4, one missed
day) and `/en/bite/pawguard-demo-reporter-link-misty-0002` (urgent "unusual behaviour").
Honest limits to say: wording is pending clinical review (Tamil/Hindi are draft translations); the signature proves the
record's origin, not the pet's health or identity; offline verifiers only know cancellations up to their last refresh.

## 3. Three-minute walkthrough (community dog programmes)

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
| 10 (close) | — | — | "Photo matching is research-only: on DogFaceNet pet-dog face photos the right dog was ranked first 94% of the time, but 16% of unknown dogs got a confident match — above our 5% target — and it hasn't been tested on street dogs. Real organisations can't switch it on. Field data and clinical review are next." |

**If matching shows "No confident match — check manually or register a new dog"** (e.g. after a reset without `demo_prepare.py`): say "it found no
similar animal — that doesn't prove the dog is new", click **Search the registry instead**, open any animal, and
continue from step 6. To restore the prepared match: `.venv\Scripts\python.exe scripts\demo_prepare.py`.

**Optional extras if asked (30 s each)**
- *Model evidence:* menu **Model evidence** → the measured DogFaceNet results (pet dog face photos; not validated on
  street dogs), both charts, and why the threshold is not yet reliable.
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
offline page cannot be stored (forms still work). Easiest: use the public HTTPS link (§1b) on the phone; or the
USB port-forwarding steps below.

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
- **Photo matching is research-only.** Evaluated with the model frozen on DogFaceNet (close-up face photos of pet
  dogs), 201 test dogs never used for training: right dog ranked first **0.943** (95% CI 0.914–0.970), in the top 3
  **0.990**; unknown dogs given a confident match **0.160** (0.068–0.252) at the threshold 0.513 chosen on validation
  dogs — the 5% target was **not met**. Street dogs **not tested**. Details: **Model evidence** page. The demo match
  uses the same photo that was enrolled, so it shows the workflow, not accuracy.
- **Offline**: tasks and sightings only; no offline photos or vaccination evidence; not yet tested on real phones.
- **Tamil and Hindi** are partial drafts: many screens fall back to English with a "draft translation" notice.
- **Planning** uses straight-line travel estimates and estimates from single street counts or registry records —
  not population or coverage.
- Health and first-aid wording has **not** been reviewed by clinicians.
- **Pet reminders are in-app only.** Email/SMS texts are previews; nothing is sent. The `.ics` file is real.
  Seeded pets, clinics, products and due dates are fictional; product schedule templates are demo data labelled
  "Demo template — confirm with your vet" — the app only reminds and never decides treatment.
- The clinic count describes **pets registered in this app**, not population coverage.
- The PDF card uses a built-in Latin font: names in Tamil script print as "?" in the PDF (the web card is fine).

## 7. Making the backup video yourself (checklist)

1. `.\scripts\demo_up.ps1 --reset`; close other apps and notifications; browser zoom 100%, window ~1280×800.
2. Use only the **Sign in as …** buttons — never type the password on camera; keep `.env` and terminals off-screen.
3. Windows: **Win + Alt + R** (Xbox Game Bar) records the active window; or OBS "Window capture".
4. Follow §3 steps 1–9, speaking the "Say" column; aim for under 3 minutes.
5. Stop recording; watch it once; save to `backups/demo-recording/` and a USB stick.
