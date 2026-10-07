# Content register

Every piece of public health or veterinary wording, its source, locale coverage and review state. "Approved"
can only be set by a named, qualified reviewer for the stated jurisdiction — never by software authors,
machine translation or an AI system.

| ID | Location in product | Content | Sources | Locales | Review state | Reviewer | Next review |
|---|---|---|---|---|---|---|---|
| C-HELP-01 | `/[locale]/help` — wound washing | "Wash the bite or scratch with soap and running water for at least 15 minutes." | S01 | en (ta/hi show English + notice) | **Unreviewed starter** | — | Before any real use |
| C-HELP-02 | `/[locale]/help` — seek care | "Go to a hospital or health centre as soon as you can, even if the wound looks small. A health worker will decide what care you need, which may include vaccination." | S01 (exposure categories) | en | **Unreviewed starter** | — | Before any real use |
| C-HELP-03 | `/[locale]/help` — why it matters | Fatal once symptoms appear (attributed to WHO) | S01 | en | **Unreviewed starter** | — | Before any real use |
| C-HELP-04 | `/[locale]/help` — phone numbers | 112 national emergency; 15400 rabies helpline with five-state coverage caveat | S29, S02 | en | **Unreviewed starter** | — | Re-check coverage quarterly |
| C-HELP-05 | `/[locale]/help` — limits | PawGuard does not diagnose; no need to photograph or approach the animal | Product invariant | en | Product statement (not clinical) | — | — |
| C-LAND-01 | Landing page transparency panel | Not a diagnosis; vaccination record ≠ guarantee; starter-content statement | Product invariants | en | Product statement | — | — |
| C-LAND-02 | Landing page "Why it matters" | Three verbatim quotations from the WHO rabies fact sheet (vaccine-preventable; 99% of human cases from dog bites and scratches; mass dog vaccination most cost-effective), shown in English with the source link and check date | S01 (checked 2026-10-06) | en (all locales show the English quotation) | **Unreviewed starter** (verbatim, attributed) | — | Re-check when WHO updates the fact sheet |
| C-UI-TA-UI2 | Tamil labels added in the UI polish pass (landing headings, status guide, header) | Interface labels and status explanations | — | ta | **Draft translation — pending native-speaker review** | — | Before ta release |
| C-UI-TA | All interface strings in `apps/web/messages/ta.json` | Interface labels only | — | ta | **Draft translation — needs native-speaker review** | — | Before ta release |
| C-UI-HI | All interface strings in `apps/web/messages/hi.json` | Interface labels only | — | hi | **Draft translation — needs native-speaker review** | — | Before hi release |
| C-PET-01 | Pet status and record labels (`pets.status`, `pets.verification`) | "Up to date", "Due soon", "Overdue", "Entered by owner (unverified)", "No verified record" (never shown as "unvaccinated" or "overdue"), "Verified by vet" | Product invariants | en; ta draft | Product statement | — | — |
| C-PET-02 | Public vaccination card and PDF | "This card shows recorded vaccinations. It is not a health guarantee." | Product invariant | en (ta/hi show English) | Product statement — not translated | — | Before any real use |
| C-PET-03 | Next due date from a product template | "Demo template — confirm with your vet" (templates are demo data, not a medical schedule) | Product invariant | en (ta/hi show English) | Product statement — not translated | — | Before any real use |
| C-PET-04 | Reminders and notification preview | "Reminders are shown in the app only…", "Preview only — no message is actually sent.", "PawGuard only reminds you. Your vet decides what your pet needs." | Product invariants | en; ta draft for the preview note | Product statement | — | — |
| C-UI-TA-PETS | Tamil labels for the pet screens (`ta.json`: nav, pets, reminders, clinic, publicCard) | Interface labels only | — | ta | **Draft translation — pending native-speaker review** | — | Before ta release |

| C-BITE-01 | Bite mode, reporter and owner pages — first aid 1 | "Wash the wound with soap and running water for 15 minutes." | S01, S30, S31 | en; ta/hi **draft translations shown with a "draft translation" note** | **Pending clinical review** | — | Before any real use |
| C-BITE-02 | Bite mode — first aid 2 | "See a doctor today, whatever this pet's vaccination status." | S01, S30 ("as soon as possible"), S31 ("consult your doctor immediately") | en; ta/hi draft | **Pending clinical review** | — | Before any real use |
| C-BITE-03 | Bite mode — first aid 3 | "Don't apply turmeric, chilli or other home remedies." The sources name chili powder / chillies, mustard oil, plant juices and irritants; **turmeric is not named in them** (added at the product owner's request as a common local remedy) | S30, S31 | en; ta/hi draft | **Pending clinical review** | — | Before any real use |
| C-BITE-04 | Bite mode / private pages | "Show this screen to your doctor. Your doctor decides your treatment." · "A vaccination record does not replace medical care." · Doctor page: "Information provided to support your clinical decision. Owner reports are not vet-verified unless marked." | Product invariants | en; ta/hi draft (first two) | Product statement | — | — |
| C-BITE-05 | Observation policy | "Observation period: 10 days after the bite (WHO guidance) — pending clinical review." Owner alert: "… keep him/her under observation for 10 days and contact your vet today." | S30 ("Keep the biting animal confined and under observation for 10 days"), S31 p. 90 | en | **Pending clinical review** | — | Before any real use |
| C-BITE-06 | Closing statements | "Observation period completed — the owner reported no changes." / "…ended with days without an update…" / "A change was reported…" plus "This does not change anything your doctor advised." Never "safe", "rabies-free" or "no treatment needed" (automated checks in `test_bites.py` and `bite.spec.ts`) | Product invariants | en | Product statement | — | — |
| C-UI-TA-BITE / C-UI-HI-BITE | Tamil and Hindi bite-mode strings (`bite.*` in ta.json / hi.json) | First aid, record, report form, urgent banner, day statuses | — | ta, hi | **Draft translation — pending clinical and native-speaker review** (written by software, not by a qualified translator) | — | Before ta/hi release |

Health wording is deliberately **not** translated until a qualified reviewer approves both the English text and
its translation; Tamil/Hindi readers see the English text with a notice in their language.

**Exception (7 Oct 2026, product owner's request):** bite mode must be usable in Tamil and Hindi, so its first-aid
lines are shown in draft Tamil/Hindi with a visible "draft translation — pending clinical and language review" note.
This exception is limited to the C-BITE rows above and must be reviewed before any real use.
