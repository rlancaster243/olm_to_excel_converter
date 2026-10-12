# olm_to_excel_converter

## Open questions

1. **Real OLM layout** — The contact XML path, namespaces, and field names have not been validated against an actual Outlook for Mac export (assessment: **Unknown** until a real archive is inspected).
2. **Parent integration** — This repo is the **standalone** conversion core ([ADR-001](docs/fidelity/05-DECISIONS-AND-TRADEOFFS.md), accepted 2026-10-11). The parent [mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter) should consume `olm-excel` via `pip` and a thin CLI/matrix wire (tracked separately in the parent).

---

This repository will hold an **Outlook for Mac (OLM) → Excel** converter (contacts-first in early phases; broader record families described in the proposed [fidelity PRD](docs/fidelity/02-PRD-AND-ACCEPTANCE.md)), split from the [mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter) monolith. Documentation, synthetic samples, and parent source snapshots live under **[docs/](docs/README.md)**.

**Status:** converts contacts and categories from the one real OLM layout seen so far (evidence E09, one Outlook version). Other record families (mail, calendar, tasks) are not supported: they are listed in the workbook and their values are kept as raw rows, never guessed.

**Scope:** a single run on the owner's own contacts export (ADR-012). That run completed 2026-10-12 with SUCCESS and every source value accounted for (evidence E14). The code is not qualified for other exports or Outlook versions, and no further features are planned.

## Development

Python 3.11+. Runtime dependencies are pinned in `pyproject.toml`: `defusedxml` (hardened XML) and `xlsxwriter` (string-typed cells). `openpyxl` is test-only and is never used to write workbooks.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The full suite takes about a minute; most of that is one test that writes and re-reads all 241,487 sample values. Key oracles:

- `tests/integration/test_source_value_count.py`: the walker counts 241,487 source values in `docs/samples/sample.olm`.
- `tests/unit/test_xlsx_cell_policy.py`: hostile values round-trip exactly with no formula cells.
- `tests/unit/test_walker.py`: the streaming walker matches a whole-document reference on randomized mixed content.

Never commit `.olm` files other than the synthetic sample; `.gitignore` blocks them.

## Converting an archive

```bash
.venv/bin/olm-excel convert "/path/to/Outlook for Mac Archive.olm" -o ~/Desktop/olm-out
```

The archive is opened read-only and never extracted to disk. The output directory gets `<name>.xlsx`. The terminal shows counts and file names only, never contents.

Every source value ends up as exactly one of: **mapped** (in a proper column), **structural** (format bookkeeping such as `xml:space`, checked and counted, not exported), **raw** (kept as a row in the `raw_NNNN` sheets with its path) or **lost** (reported with a reason). The workbook's `_manifest` sheet leads with the outcome and these counts.

| Outcome | Meaning | Exit code |
|---|---|---|
| SUCCESS | every value mapped or structural | 0 |
| PARTIAL | usable output, but some values are raw or lost (for example pictures not exported, unknown fields, non-XML members) | 3 |
| UNSUPPORTED | nothing in the archive has a reader; values are kept as raw rows | 4 |
| FAILED | unsafe or unreadable archive, or the output could not be verified; no workbook is written | 1 |

Options: `--export-images` writes contact pictures as separate files in `<name>-pictures/` (without it the pictures are reported as lost, so the result is PARTIAL); `--no-raw-extract` reports unmapped values as lost instead of writing raw rows (the outcome does not change); `--overwrite` replaces an existing workbook. Existing outputs are never overwritten by default, and an existing pictures directory is never replaced.

Sheets: `_manifest`, `_members`, `_warnings`, `_unsupported`, then `contacts`, `contact_emails`, `contact_categories`, `contact_lists`, `contact_pictures`, `categories`, `contact_long_text` (only if a value exceeds 32,000 UTF-16 units) and the raw sheets when needed. Every value is written as exact text: formulas stay inert, dates are not converted.

## Profiling a real archive without sharing its contents

`olm-excel profile` writes a structure-only JSON report: member counts, sizes and types, and for XML members the element and attribute names with counts. It never writes text or attribute values. Folder names are replaced by hashes using a random per-run salt, file names collapse to `~file.ext`, and only generic Outlook names (e.g. `Address Book`, `Sent Items`) stay readable.

Run it on the machine that holds the archive, then read the report before sharing it:

```bash
.venv/bin/olm-excel profile "/path/to/Outlook for Mac Archive.olm" -o olm-profile.json
```

`--show-names` keeps real folder and file names; leave it off unless you are sure they are not personal.
