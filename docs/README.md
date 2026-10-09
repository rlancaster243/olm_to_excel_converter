# Documentation index

## Open questions

1. **Real OLM layout** — Contact XML paths, namespaces and field names are now known for **one** contacts-only export (structure-only profile, evidence E09). Other Outlook versions and record families are still **Unknown**. See [ASSESSMENT.md](ASSESSMENT.md), [fidelity/01-PROBLEM-AND-REALITY.md](fidelity/01-PROBLEM-AND-REALITY.md), and [samples/README.md](samples/README.md).
2. **Shipping shape and v1 scope** — [ASSESSMENT.md](ASSESSMENT.md) and [CONVERTER-OLM-report.md](CONVERTER-OLM-report.md) rank **approach B** (parent-repo `olm_contacts` module + thin Streamlit wire) for a narrow contacts MVP, with **approach C** (separate app) when mapping UI or large archives land in v1. The [Engineering Fidelity Dossier](fidelity/README.md) (**PROPOSED**, 2026-10-08) treats **this repository** as the standalone conversion core (see [ADR-001](fidelity/05-DECISIONS-AND-TRADEOFFS.md)) and scopes **target** output toward multiple record families when validated—not contacts-only forever. Product acceptance still **OPEN** on “full conversion” families and partial-download UX; see [fidelity/02-PRD-AND-ACCEPTANCE.md](fidelity/02-PRD-AND-ACCEPTANCE.md).

---

## Engineering Fidelity Dossier (planning target)

**Status:** PROPOSED planning docs only—not implementation or verified format support. Start at [fidelity/README.md](fidelity/README.md).

| Doc | Governs |
|-----|---------|
| [fidelity/01-PROBLEM-AND-REALITY.md](fidelity/01-PROBLEM-AND-REALITY.md) | Problem, evidence tags, CURRENT vs TARGET vs MIGRATION |
| [fidelity/02-PRD-AND-ACCEPTANCE.md](fidelity/02-PRD-AND-ACCEPTANCE.md) | Functional/nonfunctional requirements, phases P0–P4 |
| [fidelity/03-ARCHITECTURE.md](fidelity/03-ARCHITECTURE.md) | Target boundaries, flows, control vs data plane |
| [fidelity/04-CONTRACTS-AND-DATA.md](fidelity/04-CONTRACTS-AND-DATA.md) | APIs, adapters, canonical record envelope, workbook contract |
| [fidelity/05-DECISIONS-AND-TRADEOFFS.md](fidelity/05-DECISIONS-AND-TRADEOFFS.md) | Proposed ADRs and alternatives matrix |
| [fidelity/06-THREATS-AND-FAILURES.md](fidelity/06-THREATS-AND-FAILURES.md) | Threat model and failure semantics |
| [fidelity/07-VERIFICATION-PLAN.md](fidelity/07-VERIFICATION-PLAN.md) | Test oracles, acceptance matrix, gates |
| [fidelity/08-IMPLEMENTATION-AND-HANDOFF.md](fidelity/08-IMPLEMENTATION-AND-HANDOFF.md) | Work packages W00–W10, proposed `src/` layout |
| [fidelity/09-OPERATIONS-AND-RECONCILIATION.md](fidelity/09-OPERATIONS-AND-RECONCILIATION.md) | Ops, runbooks, evidence ledger |

### Assessment vs fidelity (reconciliation)

Both bodies agree on several **observed** facts: this repo is still **pre-implementation**; [samples/sample.olm](samples/sample.olm) is **synthetic**; real Outlook OLM layout is **unknown**; the parent [source-snapshot/](source-snapshot/) is read-only context; parent dependency debt must **not** be copied here; and formula/cell safety plus memory at scale are real risks (synthetic ~297 MB peak bench is historical, not re-run).

| Topic | [ASSESSMENT.md](ASSESSMENT.md) / Archify (Oct assessment) | [fidelity/](fidelity/README.md) (PROPOSED dossier) |
|-------|--------------------------------------------------------------|-----------------------------------------------------|
| **Repo boundary** | Separate-scope **product** decision; **recommended ship shape B** = module in parent + thin UI wire | **ADR-001:** standalone engine in **this** repo; parent module B recorded as **historical conditional**, not current approved decision |
| **v1 / target scope** | Contacts-first MVP; flip triggers for mail, mapping, streaming, multi-GB | **Target** includes mail, calendar, tasks, notes, groups when structures are understood; **P1** = contacts vertical slice on **real** exports; full family set gated by evidence |
| **Archive discovery** | Inferred path from synthetic sample (`Accounts/…/Contacts.xml`) | **F03 / ADR-002:** discovery by **content signatures**, not filename/path alone |
| **Parsing / memory** | Parent pattern and bench imply whole-buffer / in-memory XML risk; iterparse noted as unmeasured fix | **ADR-004 / N02:** streaming, bounded memory; no requirement to hold whole XML trees |
| **Success semantics** | Risks of silent omission; report dict in inferred `olm_to_xlsx` sketch | **ADR-006–008:** SUCCESS vs PARTIAL vs UNSUPPORTED vs FAILED; no silent canonical mapping of unknown fields; field-level rule `source_values = mapped + raw + lost` decides SUCCESS; default-on raw extract delivers unmapped values as labeled raw rows |
| **Delivery** | Streamlit monolith context; 200 MB upload cap (Streamlit default) discussed | **ADR-005:** local-first default; multi-file batch, per-file XLSX + ZIP; hosting **OPEN** |
| **Verification** | Parent repo: no tests/CI **observed** | **07-VERIFICATION-PLAN:** golden real-export oracles, security corpus—**designed, not executed** |

**How to read them:** Treat **ASSESSMENT** + **CONVERTER-OLM-report** + [architecture/](architecture/) as the October split-from-parent architecture review. Treat **fidelity** as the later **proposed** engineering contract for building in this repo until ADRs are accepted and supersede earlier recommendations.

---

## Provenance

Architecture assessment and artifacts were produced from the parent repo **[rlancaster243/mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter)**:

- **Main tip SHA:** `5abea14dc07238881ea4ab9b770ff9e81784bc0c`
- **App file last content commit:** `f5afd38808e9dd1ae8a6c0d1dc629cfc3b9e0668`

No clone of the parent was committed here; see [source-snapshot/](source-snapshot/) for a frozen reference copy only.

The fidelity dossier is authored for **this** repository (see [fidelity/README.md](fidelity/README.md) scope line).

---

## Assessment and reports (October review)

| Document | Summary |
|----------|---------|
| [ASSESSMENT.md](ASSESSMENT.md) | Principal Architect assessment: separate scope for OLM→Excel, integration points, risks, ranked approaches (A in-place / **B module + thin wire** / C separate app). |
| [CONVERTER-OLM-report.md](CONVERTER-OLM-report.md) | Shorter systems architecture report with the same headline verdict and open decisions. |

---

## Architecture artifacts (Archify)

Under [architecture/](architecture/):

| File | Summary |
|------|---------|
| [converter-olm.architecture.json](architecture/converter-olm.architecture.json) | Machine-readable architecture spec. |
| [converter-olm.html](architecture/converter-olm.html) | Rendered architecture document. |
| [converter-olm.visual-check.html](architecture/converter-olm.visual-check.html) | Visual validation page. |
| [converter-olm.visual-check.json](architecture/converter-olm.visual-check.json) | Visual-check metadata (e.g. showcase 9/9 checks; containment note on overflow). |
| `converter-olm.visual-check.*.png` | Light/dark screenshots at 1440×900 and 2048×1320. |

---

## Synthetic sample and generator

[samples/](samples/) — see [samples/README.md](samples/README.md). **`sample.olm` is synthetic**, not from Outlook.

---

## Benchmark note (synthetic sample only)

From the assessment’s throwaway bench on the **20,000-contact synthetic** archive (zip ~**1.6 MB**, single XML ~19.8 MB): end-to-end ~**6 s**, peak RSS ~**297 MB**, output xlsx ~2.3 MB. These numbers are **synthetic**, measured on **one machine only**, and were **not re-run** for this repo.

That peak suggests **whole-file in-memory parsing** of the contacts XML. The assessment’s “stay under **200 MB** upload” condition for a minimal in-place MVP is **untested** against this workload. A likely direction for large real exports is **streaming inside `Contacts.xml`** (e.g. `iterparse` and clearing each contact element after writing a row), not only entry-by-entry ZIP reading — **unmeasured** in this repo; **proposed** as a requirement in [fidelity/05-DECISIONS-AND-TRADEOFFS.md](fidelity/05-DECISIONS-AND-TRADEOFFS.md) (ADR-004).

---

## Parent-app dependency debt (do not copy)

Issues called out in the assessment apply to **mbox_to_eml_converter**, not this repo:

- **`bs4` / `markdownify`** used in the parent app but **missing** from parent `requirements.txt`
- PyPI package **`mailbox`** listed in parent requirements vs Python **stdlib** `mailbox`
- OCR paths needing **Poppler** and **Tesseract**; README vs runtime mismatch

**Do not** copy [source-snapshot/parent-requirements.txt](source-snapshot/parent-requirements.txt) into a root `requirements.txt` here. This repository has **no** application dependencies until implementation begins (per fidelity W01, dependencies would be introduced via `pyproject.toml`—not present yet).

---

## Source snapshot (read-only)

[source-snapshot/](source-snapshot/) — frozen parent files; **[do not edit or build on them](source-snapshot/README.md)**.
