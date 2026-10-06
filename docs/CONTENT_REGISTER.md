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

Health wording is deliberately **not** translated until a qualified reviewer approves both the English text and
its translation; Tamil/Hindi readers see the English text with a notice in their language.
