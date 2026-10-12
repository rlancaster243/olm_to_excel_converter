# 05 — Architecture Decisions and Tradeoffs

**Russell decisions (2026-10-11):** ADR-001 (standalone + parent integration contract), ADR-008 mechanics, ADR-009–011 confirmed; compression ratio **100**; canonical cap name **`max_raw_values`**; profile **sha256** retained (strip from committed samples if the repo goes public); empty/structural semantics per doc 04; dual-term **Completeness** vs **count-conserving** glossary in 04; refused members inventoried in `_manifest.refused_members` at member grain; land **PR #9** as the single merge into `main` (stack #1–#7 superseded for integration). Issue [#8](https://github.com/rlancaster243/olm_to_excel_converter/issues/8).

## ADR-001 — Standalone repository and engine
Status: **ACCEPTED** 2026-10-11, architecture owner Russell.
Decision: use this repository as the independent conversion core with thin UI and CLI.
Benefit: isolated dependencies, testability, release ownership, scalable record-family support.
Cost: separate user entrypoint from parent universal converter.
Assumption: multi-upload and multiple record families justify isolation.
Revisit: scope is permanently contacts-only and parent integration becomes a stronger user requirement.
Historical conflict: prior `docs/ASSESSMENT.md` recommends parent module B for narrow MVP. Preserve as historical conditional recommendation, not current approved decision.

**Parent integration contract (accepted with ADR-001):**
- Ship **`olm-excel`** as an installable Python package (`pip install -e .` / future PyPI) with a stable **`olm-excel convert`** CLI.
- Programmatic entry: `olm_excel.core.convert.convert` (and documented `ConvertOptions`) is the supported library surface for the parent `mbox_to_eml_converter` or other hosts.
- Parent wiring is a **separate tracked task** in the parent repo (thin Streamlit/matrix dispatch); this repo does not block on it.
- Versioning: adapter and tool versions appear in every workbook `_manifest`; breaking contract changes require doc 04 versioning notes.

## ADR-002 — Signature-based adapter registry
Status: **ACCEPTED** (implementation in stack).
Decision: discover archive contents and select versioned adapters using content signatures, namespaces and tested fingerprints.
Benefit: supports evolving layouts without pretending arbitrary unknown formats are interpretable.
Cost: fixture curation, probe ambiguity and registry maintenance.
Assumption: several structural variants can be classified by observable signatures.
Revisit: evidence shows only one stable schema or wholly opaque/proprietary content prevents reliable parsing.

## ADR-003 — Canonical envelope and normalized sheets
Status: **ACCEPTED** (contacts v1 uses adapter-local row assembly; full envelope deferred per 08).
Decision: adapters emit record envelopes; projection produces family sheets and child-value sheets.
Benefit: avoids field loss and flattening explosions; cross-family consistency.
Cost: more worksheets and join keys for Excel consumers.
Assumption: consumer accepts relational workbook design.
Revisit: user testing demands one-table presentation; add a convenience view only if underlying normalized contract remains authoritative.

## ADR-004 — Streaming with bounded resources
Status: **ACCEPTED** (implementation in stack).
Decision: do not retain whole XML/member trees or all workbooks in memory; process streams and spool securely if necessary.
Benefit: bounded memory and safer large input behavior.
Cost: more complex error accounting, progress and writer design.
Assumption: tested parsers can incrementally handle real observed encodings.
Revisit: physical format mandates random-access or nonstreamable processing; document safe bounded fallback.

## ADR-005 — Local-first delivery
Status: **ACCEPTED** (default mode).
Decision: initial CLI/local UI has no content transfer to third parties.
Benefit: lower privacy exposure, simpler trust boundary.
Cost: less frictionless browser hosting/sharing.
Assumption: user can run local environment.
Revisit: explicit hosted product requirement with threat/privacy review.

## ADR-006 — Partial output with mandatory diagnostics
Status: **ACCEPTED** (02 download decision).
Decision: permit PARTIAL workbooks only with machine-readable manifest and prominent warning.
Benefit: recovery and transparency for mixed-format archives.
Cost: consumers must interpret completeness state.
Assumption: users value recoverable supported data over total abort.
Revisit: downstream compliance requirement mandates all-or-nothing.

## ADR-007 — No semantic guessing
Status: **ACCEPTED** (implementation in stack).
Decision: unknown fields/record types remain raw/provenance-labeled and cannot be silently mapped to canonical columns.
Benefit: protects truth and enables future adapter work.
Cost: less instantly polished output on novel schemas.
Assumption: correctness and accountability outweigh superficial coverage.
Revisit: verified format mapping and tests justify promotion.

## ADR-008 — Default-on raw extract for unrecognized structures
Status: **ACCEPTED** 2026-10-11, architecture owner Russell (default-on product decision 2026-10-09; mechanics confirmed 2026-10-11).
Decision: when no adapter claims an XML member, or a claimed record carries unknown fields, write every readable value as one raw row (positional path, provenance, literal text) instead of only inventorying it. On by default; operators may opt out.
**Mechanics (accepted):** `ConvertOptions.raw_extract=True` by default; **`max_raw_values` = 5,000,000** per archive; unclaimed values partition into **`raw_NNNN`** sheets with `_raw_index`; manifest records `raw_extract` on/off and per-member counts.
Benefit: no readable value is withheld from the user; schema changes stay visible instead of silently vanishing; the raw sheets are the evidence base for the next adapter.
Cost: one-row-per-value sheets are awkward to read and can hit row caps quickly on large mailboxes; more output volume and processing time; users may mistake raw output for supported conversion.
Assumption: users prefer awkward-but-complete data over an inventory-only result; sheet naming, manifest flags and the non-SUCCESS outcome prevent raw output being read as interpreted data.
Completeness: the outcome comes from the field-level rule in 04 (`source_values == mapped + structural + raw + lost`), counted by the core walker. The raw extract flag decides only whether unmapped values are delivered as raw or reported as lost, never the outcome.
Relation to ADR-007: compatible. Raw rows claim location, not meaning, and are never promoted to canonical columns without an adapter. This is distinct from the rejected generic XML flattening, which guesses columns from tag names.
Revisit: raw volume regularly exceeds limits, users report misreading raw output as converted data, or privacy review requires minimizing output to interpreted fields.

## ADR-009 - Structural values
Status: **ACCEPTED** 2026-10-11, Russell (relay confirmed; was pending confirm in finding #6).
Decision: an adapter may declare a closed list of source values as structural (`xml:space`, root `elementCount` for contacts v1). The core checks them with validators and counts them separately; they are not exported.
Benefit: a real export carries `xml:space` on 577,741 of 1,176,094 source values across its four members (E09; the largest member alone carries it on 575,912 of 1,172,223). Exporting them is noise and treating them as lost would make every conversion PARTIAL, which hides real loss behind a permanent warning.
Cost: a new place for loss to hide. Controls: closed declarations with evidence, validators run by the core, per-declaration counts in the manifest, a failed check routes the value to raw or lost.
Assumption: these attributes carry no record data in contacts exports.
Revisit: any declaration that matches a value carrying record data, or a variant where `elementCount` disagrees with the record count in an otherwise valid export.

## ADR-010 - Binary payloads as files, metadata in cells
Status: **ACCEPTED** 2026-10-11, Russell (relay confirmed).
Decision: contact pictures are never written to cells or raw rows. A metadata sheet always lists them; the images are written as separate content-addressed files only when the operator opts in. Without the opt-in the pictures are `lost` (`PICTURE_NOT_EXPORTED`) and the outcome is PARTIAL.
Benefit: no binary in cells (02 non-goals), no loss hidden, exact integrity via SHA-256, identical images stored once.
Cost: a default conversion of an archive with pictures is PARTIAL; an extra output directory with its own lifecycle.
Assumption: picture values are base64 text (E10, [INFERRED]; encoding unverified against a real value).
Revisit: pictures prove not to be base64, or users want embedded images in the workbook.
Messaging (F17): a PARTIAL caused only by unexported pictures names the count and the opt-in (`--export-images`), so a default run does not read as a failure.

## ADR-011 - Contact dates stay text
Status: **ACCEPTED** 2026-10-11, Russell (relay confirmed).
Decision: contacts v1 writes dates exactly as exported, with no Excel date cells and no parsed columns.
Benefit: no timezone or locale guessing (E09 does not show the date format); exact round trip.
Cost: users sort and filter dates as text until a parsed column exists.
Revisit: the real date lexemes are confirmed unambiguous and users ask for date cells.

## ADR-012 - Scope is a single run on one export
Status: **ACCEPTED** 2026-10-12, product owner Russell ("the scope of this system is a one time run").
Decision: the system exists to convert the product owner's own contacts export (E09) once. That run took place 2026-10-12 and returned SUCCESS (E14). W06 to W10 and phases P2 to P4 are out of scope and will not be built.
Benefit: no investment in batch, UI, further families, hardening or release work that nobody will use.
Cost: the code is qualified for one export only (E09, E14). Known limits stay unfixed: the provenance log grows with archive size (about 316 bytes per value, measured 2026-10-12), there is no wall-clock parse limit (N03), and the `_provenance` and `_columns` sheets are not defined in 04. None of these affected the single run.
Revisit: any second export, another Outlook version, or another record family. Each reopens W06 to W08 and needs its own Q2-style count check, because E14 does not transfer to them.

## Alternatives matrix
| Choice | Simplicity | Multi-family evolution | Correctness observability | Main risk |
|---|---|---|---|---|
| Parent monolith | high initially | low | low | cross-feature coupling |
| Parent module | medium | medium | medium | shared release/runtime |
| Standalone adapter core | medium initially | high | high if verified | fixture and maintenance overhead |
| Generic XML flattening | deceptively high | superficial | low | fabricated semantics, relationship loss |
| Raw extract (one row per value, ADR-008) | medium | supports adapter discovery | high: count-conserving and countable | consumer usability, output volume |

## Decision authority
Product owner approves families and UX; architecture owner approves boundaries and ADRs; security/privacy reviewer approves hosting and retention; verification owner approves qualification evidence. A single individual may fill multiple roles, but verification independence must be disclosed.
