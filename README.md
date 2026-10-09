# olm_to_excel_converter

## Open questions

1. **Real OLM layout** — The contact XML path, namespaces, and field names have not been validated against an actual Outlook for Mac export (assessment: **Unknown** until a real archive is inspected).
2. **Shipping shape and v1 scope** — The October [assessment](docs/ASSESSMENT.md) favored a parent-repo module (approach B) for a contacts MVP; the [fidelity dossier](docs/fidelity/README.md) (**PROPOSED**) assumes a **standalone** engine in this repo and a broader **target** (multiple record families when validated). Product acceptance is still open—see [docs/README.md](docs/README.md#assessment-vs-fidelity-reconciliation).

---

This repository will hold an **Outlook for Mac (OLM) → Excel** converter (contacts-first in early phases; broader record families described in the proposed [fidelity PRD](docs/fidelity/02-PRD-AND-ACCEPTANCE.md)), split from the [mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter) monolith. Documentation, synthetic samples, and parent source snapshots live under **[docs/](docs/README.md)**.

**Status:** W01 package skeleton. No conversion works yet; the CLI `convert` command exits with code 2.

## Development

Python 3.11+. Runtime dependencies are pinned in `pyproject.toml`: `defusedxml` (hardened XML) and `xlsxwriter` (string-typed cells). `openpyxl` is test-only and is never used to write workbooks.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Two tests are expected to fail until W04 lands. They are the first build targets:

- `tests/integration/test_source_value_count.py`: the core walker must count 241,487 source values in `docs/samples/sample.olm`.
- `tests/unit/test_xlsx_cell_policy.py`: hostile values must round-trip exactly with no formula cells.

Never commit `.olm` files other than the synthetic sample; `.gitignore` blocks them.
