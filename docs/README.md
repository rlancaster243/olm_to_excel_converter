# Documentation index

## Open questions

1. **Real OLM layout** — Contact XML path, namespaces, and field names (e.g. business phone) have **not** been checked against an actual Outlook for Mac export; assessment marks this **Unknown** until a real file is inspected. See [ASSESSMENT.md](ASSESSMENT.md) and [samples/README.md](samples/README.md).
2. **Approach B vs C** — Whether to ship as a same-repo module with thin UI wiring (B) or a separate app/page from day one (C) depends on **Russell’s v1 scope**: column mapping, other record types (groups, calendar, mail), and large-archive handling. See [ASSESSMENT.md](ASSESSMENT.md) and [CONVERTER-OLM-report.md](CONVERTER-OLM-report.md).

---

## Provenance

Architecture assessment and artifacts were produced from the parent repo **[rlancaster243/mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter)**:

- **Main tip SHA:** `5abea14dc07238881ea4ab9b770ff9e81784bc0c`
- **App file last content commit:** `f5afd38808e9dd1ae8a6c0d1dc629cfc3b9e0668`

No clone of the parent was committed here; see [source-snapshot/](source-snapshot/) for a frozen reference copy only.

---

## Assessment and reports

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

That peak suggests **whole-file in-memory parsing** of the contacts XML. The assessment’s “stay under **200 MB** upload” condition for a minimal in-place MVP is **untested** against this workload. A likely direction for large real exports is **streaming inside `Contacts.xml`** (e.g. `iterparse` and clearing each contact element after writing a row), not only entry-by-entry ZIP reading — **unmeasured** here.

---

## Parent-app dependency debt (do not copy)

Issues called out in the assessment apply to **mbox_to_eml_converter**, not this repo:

- **`bs4` / `markdownify`** used in the parent app but **missing** from parent `requirements.txt`
- PyPI package **`mailbox`** listed in parent requirements vs Python **stdlib** `mailbox`
- OCR paths needing **Poppler** and **Tesseract**; README vs runtime mismatch

**Do not** copy [source-snapshot/parent-requirements.txt](source-snapshot/parent-requirements.txt) into a root `requirements.txt` here. This repository has **no** application dependencies until implementation begins.

---

## Source snapshot (read-only)

[source-snapshot/](source-snapshot/) — frozen parent files; **[do not edit or build on them](source-snapshot/README.md)**.
