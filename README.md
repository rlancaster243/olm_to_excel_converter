# olm_to_excel_converter

## Open questions

1. **Real OLM layout** — The contact XML path, namespaces, and field names have not been validated against an actual Outlook for Mac export (assessment: **Unknown** until a real archive is inspected).
2. **Approach B vs C** — Module-in-parent-repo with thin UI wiring vs a separate app/page depends on v1 scope: column mapping, non-contact record types, and large-archive behavior. Product owner input needed before implementation.

---

This repository will hold an **Outlook for Mac (OLM) contacts → Excel** converter, split from the [mbox_to_eml_converter](https://github.com/rlancaster243/mbox_to_eml_converter) monolith following a separate-scope architecture decision. Documentation, synthetic samples, and parent source snapshots live under **[docs/](docs/README.md)**.

**Status:** pre-implementation, docs only.
