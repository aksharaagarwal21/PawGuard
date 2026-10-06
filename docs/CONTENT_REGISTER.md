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
| C-UI-TA | All interface strings in `apps/web/messages/ta.json` | Interface labels only | — | ta | **Draft translation — needs native-speaker review** | — | Before ta release |
| C-UI-HI | All interface strings in `apps/web/messages/hi.json` | Interface labels only | — | hi | **Draft translation — needs native-speaker review** | — | Before hi release |

Health wording is deliberately **not** translated until a qualified reviewer approves both the English text and
its translation; Tamil/Hindi readers see the English text with a notice in their language.
