# 05 — Architecture Decisions and Tradeoffs

All decisions here are PROPOSED pending review. Each should become an ADR with named approver and acceptance date before it governs implementation.

## ADR-001 — Standalone repository and engine
Decision: use this repository as independent conversion core with thin UI and CLI.
Benefit: isolated dependencies, testability, release ownership, scalable record-family support.
Cost: separate user entrypoint from parent universal converter.
Assumption: multi-upload and multiple record families justify isolation.
Revisit: scope is permanently contacts-only and parent integration becomes a stronger user requirement.
Historical conflict: prior `docs/ASSESSMENT.md` recommends parent module B for narrow MVP. Preserve as historical conditional recommendation, not current approved decision.

## ADR-002 — Signature-based adapter registry
Decision: discover archive contents and select versioned adapters using content signatures, namespaces and tested fingerprints.
Benefit: supports evolving layouts without pretending arbitrary unknown formats are interpretable.
Cost: fixture curation, probe ambiguity and registry maintenance.
Assumption: several structural variants can be classified by observable signatures.
Revisit: evidence shows only one stable schema or wholly opaque/proprietary content prevents reliable parsing.

## ADR-003 — Canonical envelope and normalized sheets
Decision: adapters emit record envelopes; projection produces family sheets and child-value sheets.
Benefit: avoids field loss and flattening explosions; cross-family consistency.
Cost: more worksheets and join keys for Excel consumers.
Assumption: consumer accepts relational workbook design.
Revisit: user testing demands one-table presentation; add a convenience view only if underlying normalized contract remains authoritative.

## ADR-004 — Streaming with bounded resources
Decision: do not retain whole XML/member trees or all workbooks in memory; process streams and spool securely if necessary.
Benefit: bounded memory and safer large input behavior.
Cost: more complex error accounting, progress and writer design.
Assumption: tested parsers can incrementally handle real observed encodings.
Revisit: physical format mandates random-access or nonstreamable processing; document safe bounded fallback.

## ADR-005 — Local-first delivery
Decision: initial CLI/local UI has no content transfer to third parties.
Benefit: lower privacy exposure, simpler trust boundary.
Cost: less frictionless browser hosting/sharing.
Assumption: user can run local environment.
Revisit: explicit hosted product requirement with threat/privacy review.

## ADR-006 — Partial output with mandatory diagnostics
Decision: permit PARTIAL workbooks only with machine-readable manifest and prominent warning.
Benefit: recovery and transparency for mixed-format archives.
Cost: consumers must interpret completeness state.
Assumption: users value recoverable supported data over total abort.
Revisit: downstream compliance requirement mandates all-or-nothing.

## ADR-007 — No semantic guessing
Decision: unknown fields/record types remain raw/provenance-labeled and cannot be silently mapped to canonical columns.
Benefit: protects truth and enables future adapter work.
Cost: less instantly polished output on novel schemas.
Assumption: correctness and accountability outweigh superficial coverage.
Revisit: verified format mapping and tests justify promotion.

## ADR-008 — Default-on raw extract for unrecognized structures
Status: default-on accepted by product owner 2026-10-09; contract mechanics (04) PROPOSED pending architecture review.
Decision: when no adapter claims an XML member, or a claimed record carries unknown fields, write every readable value as one raw row (positional path, provenance, literal text) instead of only inventorying it. On by default; operators may opt out.
Benefit: no readable value is withheld from the user; schema changes stay visible instead of silently vanishing; the raw sheets are the evidence base for the next adapter.
Cost: one-row-per-value sheets are awkward to read and can hit row caps quickly on large mailboxes; more output volume and processing time; users may mistake raw output for supported conversion.
Assumption: users prefer awkward-but-complete data over an inventory-only result; sheet naming, manifest flags and the non-SUCCESS outcome prevent raw output being read as interpreted data.
Completeness: the outcome comes from the field-level rule in 04 (`source_values == mapped + raw + lost`), counted by the core walker. The raw extract flag decides only whether unmapped values are delivered as raw or reported as lost, never the outcome.
Relation to ADR-007: compatible. Raw rows claim location, not meaning, and are never promoted to canonical columns without an adapter. This is distinct from the rejected generic XML flattening, which guesses columns from tag names.
Revisit: raw volume regularly exceeds limits, users report misreading raw output as converted data, or privacy review requires minimizing output to interpreted fields.

## ADR-009 - Structural values
Status: product owner selected "Yes (Recommended)" 2026-10-09; mechanics PROPOSED.
Decision: an adapter may declare a closed list of source values as structural (`xml:space`, root `elementCount` for contacts v1). The core checks them with validators and counts them separately; they are not exported.
Benefit: a real export carries `xml:space` on 575,912 of 1,172,223 values (E09). Exporting them is noise and treating them as lost would make every conversion PARTIAL, which hides real loss behind a permanent warning.
Cost: a new place for loss to hide. Controls: closed declarations with evidence, validators run by the core, per-declaration counts in the manifest, a failed check routes the value to raw or lost.
Assumption: these attributes carry no record data in contacts exports.
Revisit: any declaration that matches a value carrying record data, or a variant where `elementCount` disagrees with the record count in an otherwise valid export.

## ADR-010 - Binary payloads as files, metadata in cells
Status: product owner selected "Metadata + image files (Recommended)" 2026-10-09; mechanics PROPOSED.
Decision: contact pictures are never written to cells or raw rows. A metadata sheet always lists them; the images are written as separate content-addressed files only when the operator opts in. Without the opt-in the pictures are `lost` (`PICTURE_NOT_EXPORTED`) and the outcome is PARTIAL.
Benefit: no binary in cells (02 non-goals), no loss hidden, exact integrity via SHA-256, identical images stored once.
Cost: a default conversion of an archive with pictures is PARTIAL; an extra output directory with its own lifecycle.
Assumption: picture values are base64 text (E10, [INFERRED]; encoding unverified against a real value).
Revisit: pictures prove not to be base64, or users want embedded images in the workbook.

## ADR-011 - Contact dates stay text
Status: product owner selected "Keep as text (Recommended)" 2026-10-09.
Decision: contacts v1 writes dates exactly as exported, with no Excel date cells and no parsed columns.
Benefit: no timezone or locale guessing (E09 does not show the date format); exact round trip.
Cost: users sort and filter dates as text until a parsed column exists.
Revisit: the real date lexemes are confirmed unambiguous and users ask for date cells.

## Alternatives matrix
| Choice | Simplicity | Multi-family evolution | Correctness observability | Main risk |
|---|---|---|---|---|
| Parent monolith | high initially | low | low | cross-feature coupling |
| Parent module | medium | medium | medium | shared release/runtime |
| Standalone adapter core | medium initially | high | high if verified | fixture and maintenance overhead |
| Generic XML flattening | deceptively high | superficial | low | fabricated semantics, relationship loss |
| Raw extract (one row per value, ADR-008) | medium | supports adapter discovery | high: lossless and countable | consumer usability, output volume |

## Decision authority
Product owner approves families and UX; architecture owner approves boundaries and ADRs; security/privacy reviewer approves hosting and retention; verification owner approves qualification evidence. A single individual may fill multiple roles, but verification independence must be disclosed.
