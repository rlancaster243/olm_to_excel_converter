# OLM-to-Excel Architecture Assessment

**Repo:** `rlancaster243/mbox_to_eml_converter`  
**Branch tip SHA (main):** `5abea14dc07238881ea4ab9b770ff9e81784bc0c` (2025-06-05 15:32 CDT — "Added Dev Container Folder")  
**App file last content commit:** `f5afd38808e9dd1ae8a6c0d1dc629cfc3b9e0668` (same day; tip tree still serves that file)  
**Evidence:** GitHub connector + raw fetch of `mbox_to_eml_app.py` / `requirements.txt` / `README.md` at tip SHA into `/workspace/converter-olm-assessment/` (no clone, no repo edits).  
**Labelling:** **Observed** = from the fetched source. **Inferred** = reasoned from patterns / prior work. **Unknown** = not verified.

---

## Headline verdict

**Separate scope** is the right home for OLM-to-Excel if the feature is allowed to grow once a real Outlook-for-Mac export arrives (real nesting, groups, calendar/mail, multi-GB archives, column mapping).

**In-place** (add `olm` → `xlsx` inside the existing monolith) is only justified for a **contacts-only MVP** with hard caps and no UX beyond upload → download.

### Decision criteria / flip triggers

| Stay **in-place** only if all are true | Flip to **separate scope** if any is true |
|---|---|
| Contacts-only forever (no groups/calendar/mail) | Need column-mapping UI, preview, or per-field transforms |
| Archive stays under Streamlit `server.maxUploadSize` (default **200 MB** — Observed from Streamlit docs) | Full-mailbox OLM (mail + contacts) or files that need streaming ZIP |
| Real OLM contact nesting matches the synthetic sample path/fields | Real export layout differs (path, namespaces, nested lists) — Unknown until a real file |
| No independent release / tests / CLI | Want unit tests, CLI, or a second UI without bloating the 350-line monolith |
| One-shot bytes→bytes like every other matrix pair | Need progress, truncation reports, or multi-sheet outputs as first-class UX |

**Middle option (same repo, clean boundary):** `olm_contacts.py` (or package) with `olm_to_xlsx(olm_bytes) -> (xlsx_bytes, report)` plus thin matrix/dispatch wiring. Ships with the converter app but can graduate to its own page/app without a rewrite. **This is the recommended shipping shape** under the separate-scope verdict.

---

## (1) Current architecture (Observed)

**Entry point.** There is no `if __name__` guard. The module *is* the Streamlit script: title at `mbox_to_eml_app.py:236`, then widgets, then the convert button block. README says `streamlit run app.py` (README) but the file is `mbox_to_eml_app.py` (Observed mismatch).

**Conversion registration today** (four touch points for a new pair):

1. **`CONVERSION_MATRIX`** (`:21–40`) — `from_ext → [to_ext, …]`.
2. **`EXTENSION_LABELS`** (`:42–61`) — friendly dropdown labels.
3. **A converter function** (`:65–233`) — typically `*_bytes` in → bytes (or list of `(name, bytes)` for batch) out.
4. **`if/elif` dispatch** (`:261–345`) — one branch per pair; ~22 `elif` arms.
5. **Optional:** add to `accept_multiple` list (`:250–252`) if multi-file upload is needed.

**Dropdown / dispatch.** `st.selectbox` FROM uses `list(CONVERSION_MATRIX.keys())` (`:238–241`); TO uses `CONVERSION_MATRIX[from_ext]` (`:243–248`). Convert runs only when files are present and the button is clicked (`:261`).

**Upload handling.** `st.file_uploader(..., type=[from_ext], accept_multiple_files=accept_multiple)` (`:253–257`). Multi-file only for `mbox`, `eml`, and image extensions (`:250–252`). Most paths use `uploaded_files[0].read()` only.

**Output delivery.** `st.download_button` with raw bytes. Batch ZIP via `zipfile.ZipFile` for multi-image (`:316–322`) and mbox→eml (`:326–332`).

**Shared utilities.** **None Observed** for encoding normalization, formula/CSV injection escape, Excel text-cell forcing, or truncation. Spreadsheet paths use pandas `to_excel` / `read_excel` without dtype=str or escaping (`:104–134`). Temp files via `tempfile.NamedTemporaryFile` + `os.remove` in several converters.

**Import / dependency shape (Observed):**

| Item | Evidence | Risk |
|---|---|---|
| Top-level: streamlit, pandas, PIL, markdown, nbformat, mailbox, zipfile | `:1–10` | Fine |
| Optional PDF stack in `try/except ImportError: pass` | `:12–18` | Silent miss if missing |
| Lazy `bs4` / `markdownify` | `:95`, `:100` | **Not** in `requirements.txt` |
| `requirements.txt` lists `mailbox` | requirements line | PyPI `mailbox` 0.4 = "Python IMAP for Humans" — **not** stdlib `mailbox` (Observed). Stdlib still wins on import; pip may install a useless/conflicting package (Inferred risk). |
| `odfpy` in requirements | requirements | **Unused** in app (Observed) |
| `openpyxl` | **Not** listed in requirements; pandas Excel write/read typically needs it (Inferred — runtime may already pull it transitively; Unknown on clean Cloud install) |
| OCR: `pdf2image.convert_from_bytes` + `pytesseract` | `:181–187` | Needs **Poppler** + **Tesseract** system binaries (Inferred from library docs; README admits Tesseract, claims "no system dependencies" elsewhere — Observed contradiction) |
| Repo tree | tip SHA tree | **No** tests, **no** `.github` CI, **no** `.streamlit/config.toml` (Observed) |

---

## (2) Integration points for OLM → XLSX

### Where it plugs in (in-place pattern)

Mirror any other pair:

- Add `"olm": ["xlsx"]` to `CONVERSION_MATRIX` and a label in `EXTENSION_LABELS`.
- Add `def olm_to_xlsx(olm_bytes): ...` near other converters.
- Add `elif from_ext == "olm" and to_ext == "xlsx":` before the final `else` (`:344`).
- Keep `accept_multiple=False` (single archive).

### Proposed signature / data flow (Inferred design; not implemented)

```
olm_to_xlsx(olm_bytes) -> (xlsx_bytes, report: dict)
  upload bytes
  → zipfile.is_zipfile / ZipFile
  → locate contact XML (synthetic path Observed in sample:
       Accounts/test@example.com/Address Book/Contacts.xml;
       real export path = Unknown)
  → parse OPFContactCopy* children; nested
       OPFContactCopyEmailAddressList / emailAddress attrs
       (field names Inferred from open-source parsers + synthetic sample)
  → row build: union of columns; Email1..n + Type/Name;
       all values as text; formula-escape leading =+-@;
       truncate notes > 32,767 with flag in report
  → pandas/openpyxl write → xlsx_bytes
  → st.download_button + st.info(report summary)
```

**Reuse vs new:**

| Concern | Reuse existing? | Notes |
|---|---|---|
| Bytes in / download out | Yes | Same Streamlit pattern |
| `zipfile` already imported | Yes | `:10`; also used for batch ZIP |
| pandas Excel write | Yes | Same as `csv_to_xlsx` (`:104–109`) |
| XML parsing | **New** | stdlib `xml.etree.ElementTree` (prefer `defusedxml` if untrusted — Inferred) |
| Text-cell safety / formula escape | **New** | Not present anywhere today |
| Streaming / progress for huge OLM | **New** | Current mbox path loads whole mailbox into memory (`:196–206`) |
| Multi-record-type filter | **New** | Outside current matrix model |

Under **separate scope**, the same function lives in `olm_contacts.py`; the Streamlit file only registers the pair and calls it. Column mapping / multi-sheet / CLI can grow in the module without another `elif` jungle.

---

## (3) Risks

| Risk | Class | Notes |
|---|---|---|
| Memory at 20k contacts | Observed (throwaway bench outside repo) | Current sample `/workspace/olm_sample/sample.olm`: 1.59 MB zip / 19.8 MB XML; parse ~0.7 s; total ~6.0 s; peak RSS ~297 MB; xlsx ~2.3 MB. Comfortable vs Community Cloud ~2.7 GB max (Observed Streamlit docs as of Feb 2024; may change). |
| Upload limit | Observed | Default `server.maxUploadSize` = **200 MB**. Contacts-only sample fine. Full mailbox OLM often larger (Inferred). |
| Full-mailbox OLM | Inferred | Size + need to stream ZIP members; monolith pattern loads all bytes first. |
| Missing `bs4` / `markdownify` | Observed | HTML conversions break on clean install. |
| `mailbox` on PyPI | Observed | Wrong package name in requirements. |
| `openpyxl` not pinned | Inferred / Unknown | Needed for xlsx; not in requirements.txt. |
| Poppler + Tesseract | Observed/Inferred | OCR path; README understates Poppler. |
| Monolithic if/elif growth | Observed | 22 elifs already; each new pair adds another. |
| No tests / CI | Observed | Regression risk for every addition. |
| Streamlit reruns | Observed pattern | Script re-executes top-to-bottom; conversion only behind button, but large uploads sit in session — memory pressure under interaction (Inferred). |
| XXE / hostile XML | Inferred | Untrusted user upload → prefer `defusedxml` or hardened ElementTree settings. |
| Real OLM layout | Unknown | Synthetic path/fields may differ from Outlook-produced exports. `OPFContactCopyBusinessPhone` name unverified against real export. |
| README / entrypoint drift | Observed | `app.py` vs `mbox_to_eml_app.py`; "no system deps" vs OCR. |

---

## (4) Ranked approaches (by seamlessness vs growth)

### A — In-place (monolith matrix + elif + function)
- **Seamless with today’s app:** highest for a one-pair MVP.
- **Growth:** poorest — column mapping, multi-type, streaming, tests all fight the single file.
- **Use when:** contacts-only throwaway, hard size cap, structure confirmed.

### B — Same-repo module + thin wire (**recommended**)
- **Seamless:** still one Streamlit app for users; registration is 3–4 lines in the monolith.
- **Growth:** module owns parse/row/xlsx/report/CLI/tests; can later become `pages/olm.py` or a separate app without rewriting converters.
- **Matches** the separate-scope verdict while keeping discoverability in the existing dropdown.

### C — Fully separate app / page from day one
- **Seamless with current converter:** lowest (second URL or multipage nav).
- **Growth:** best isolation; independent deps/limits/UX.
- **Use when:** column mapping UI or large-archive streaming is in the first release, or the monolith’s missing-deps/OCR debt should not block OLM.

**Recommendation:** **B under a separate-scope product decision.** Do not stuff a growing OLM product into the if/elif matrix (A) unless the flip-trigger table’s “in-place” column stays entirely true after a real OLM sample is inspected.
