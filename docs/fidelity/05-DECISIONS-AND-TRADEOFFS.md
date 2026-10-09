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

## Alternatives matrix
| Choice | Simplicity | Multi-family evolution | Correctness observability | Main risk |
|---|---|---|---|---|
| Parent monolith | high initially | low | low | cross-feature coupling |
| Parent module | medium | medium | medium | shared release/runtime |
| Standalone adapter core | medium initially | high | high if verified | fixture and maintenance overhead |
| Generic XML flattening | deceptively high | superficial | low | fabricated semantics, relationship loss |

## Decision authority
Product owner approves families and UX; architecture owner approves boundaries and ADRs; security/privacy reviewer approves hosting and retention; verification owner approves qualification evidence. A single individual may fill multiple roles, but verification independence must be disclosed.
