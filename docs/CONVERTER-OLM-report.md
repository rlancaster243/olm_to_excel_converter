# Systems Architecture Report: OLM → Excel vs Universal File Converter

**Seat:** Principal Architect (read-only)  
**Repo:** https://github.com/rlancaster243/mbox_to_eml_converter  
**Tip SHA (main):** `5abea14dc07238881ea4ab9b770ff9e81784bc0c` (2025-06-05)  
**App content SHA:** `f5afd38808e9dd1ae8a6c0d1dc629cfc3b9e0668`  
**Artifacts:** `/workspace/converter-olm-assessment/`  
**No clone, no PRs, no code written into the repo.**

---

## Headline verdict

**Separate scope** — OLM-to-Excel does **not** fit neatly into the current converter *as a growing product*. The existing app is a single-file Streamlit matrix (`CONVERSION_MATRIX` + labels + 22-arm `if/elif` + per-pair functions). That pattern fits a contacts-only MVP; it fights column mapping, multi-record-type exports, streaming multi-GB archives, and iterative discovery against a real OLM.

**Recommended shipping shape:** same-repo module (`olm_contacts.py`) with thin UI wiring (Approach B) — separate product scope, shared entry dropdown until it graduates.

### Flip triggers

| Keep a thin in-place MVP only if… | Move/keep separate scope if… |
|---|---|
| Contacts-only, forever | Groups, calendar, mail, or multi-sheet |
| No column-mapping UI | Preview / field mapping / transforms |
| Archives ≪ 200 MB upload cap | Full-mailbox or streaming ZIP needed |
| Real OLM matches synthetic sample | Nesting/path/namespaces differ (Unknown today) |

---

## Current architecture (Observed)

- **Entry:** `mbox_to_eml_app.py` is the Streamlit script (`st.title` L236). README wrongly says `app.py`.
- **Registry:** `CONVERSION_MATRIX` L21–40; `EXTENSION_LABELS` L42–61.
- **Dispatch:** button + `if/elif` L261–345 (~22 elifs).
- **Upload:** `st.file_uploader`; multi-file only for mbox/eml/images L250–257.
- **Output:** `st.download_button`; ZIP for batch images and mbox→eml L316–332.
- **Shared safety helpers:** none (no formula escape, no forced text cells).
- **Debt:** `bs4`/`markdownify` used L95/L100 but absent from requirements; PyPI `mailbox` ≠ stdlib; `odfpy` unused; OCR needs Poppler+Tesseract; no tests/CI/`.streamlit` config.

---

## Integration plan (Inferred design)

`olm_to_xlsx(olm_bytes) -> (xlsx_bytes, report)`  
upload → ZIP open → find contacts XML → parse `OPFContactCopy*` + nested emails → union columns, Email1..n, all-text, formula-escape, 32 767 truncate+flag → openpyxl/pandas → download.

**Reuse:** `zipfile`, pandas Excel path, download button.  
**New:** XML parse, safety, report, contact-only filter. Prefer `defusedxml` for untrusted XML (Inferred).  
Real in-archive path = **Unknown** (synthetic sample uses `Accounts/…/Contacts.xml`).

**Bench (Observed, throwaway, outside repo):** 20 000-contact sample — zip 1.6 MB / XML 19.8 MB; ~6 s end-to-end; peak RSS ~297 MB; xlsx ~2.3 MB. Fine vs ~2.7 GB Community Cloud RAM (docs) and 200 MB default upload.

---

## Risks (summary)

| Risk | Severity | Evidence |
|---|---|---|
| Growing OLM UX vs monolith elif | High | Observed structure |
| Full-mailbox size / upload 200 MB | High | Streamlit default Observed; mailbox size Inferred |
| Missing bs4/markdownify; bad `mailbox` req | Medium | Observed |
| OCR system deps / README drift | Medium | Observed |
| XXE on user XML | Medium | Inferred |
| Real OLM layout unknown | High (blocker for certainty) | Unknown |
| No tests/CI | Medium | Observed tree |
| Memory at 20k contacts | Low | Bench Observed |

---

## Ranked approaches

1. **B — Separate scope, same-repo module + thin wire (recommend)**  
   Product boundary clear; users still pick olm→xlsx in the app; module can grow tests/CLI/pages.

2. **C — Fully separate app/page day one**  
   Best if column mapping or large-archive streaming is in v1; worse discoverability.

3. **A — In-place matrix/elif only**  
   Fastest MVP; reject for anything beyond capped contacts-only once a real OLM arrives.

---

## Unknowns / open decisions

1. Confirm real Outlook-for-Mac OLM contact XML path, namespaces, and `BusinessPhone` field name.  
2. Product intent: contacts MVP only vs multi-type + mapping UI.  
3. Pin `openpyxl`; remove/replace PyPI `mailbox`; add `bs4`/`markdownify` or drop HTML paths.  
4. Hosting: Community Cloud upload/RAM vs local-only for large archives.  
5. Whether multipage Streamlit (`pages/`) is acceptable as the graduation path from B→C.

---

## Archify

- Spec: `converter-olm.architecture.json`  
- HTML: `converter-olm.html`  
- Validate: showcase **9/9 checks, 0 errors, 0 warnings**  
- Visual-check: readability pass; **containment fail** (vertical overflow from cards — truthful; artifact not re-edited after freeze)
