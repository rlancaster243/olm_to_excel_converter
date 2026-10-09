# olm_to_excel_converter

## Open questions

1. **Real OLM layout** — The contact XML path, namespaces, and field names have not been validated against an actual Outlook for Mac export (assessment: **Unknown** until a real archive is inspected).
2. **Shipping shape and v1 scope** — The October [assessment](docs/ASSESSMENT.md) favored a parent-repo module (approach B) for a contacts MVP; the [fidelity dossier](docs/fidelity/README.md) (**PROPOSED**) assumes a **standalone** engine in this repo and a broader **target** (multiple record families when validated). Product acceptance is still open—see [docs/README.md](docs/README.md#assessment-vs-fidelity-reconciliation).

---

This repository will hold an **Outlook for Mac (OLM) → Excel** converter (contacts-first in early phases; broader record families described in the proposed [fidelity PRD](docs/fidelity/02-PRD-AND-ACCEPTANCE.md)), split from the [mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter) monolith. Documentation, synthetic samples, and parent source snapshots live under **[docs/](docs/README.md)**.

**Status:** pre-implementation, docs only.
