# 02 — Product Contract / PRD

Status: PROPOSED, pending scope and product acceptance.

## Users and jobs
Primary: person migrating or analyzing Outlook data with Excel. Secondary: technical operator running repeatable batch conversion. Primary job: select 1..N OLM archives, understand coverage, obtain usable Excel files without manual format debugging.

## Goals
G1 Multi-file drag/drop or selector; individual status/progress, cancel and retry; download one result or all as ZIP.
G2 Archive discovery by inspected signatures and content, not hardcoded directory names alone.
G3 Export supported mail, contacts, events, tasks, notes and groups when their real structures are understood, plus manifest of everything found.
G4 Preserve multi-value fields, source identifiers and raw/unmapped value references in a recoverable manner.
G5 Report exact completeness/partiality and conversion failures per archive, family and record.
G6 Local processing is default until hosting/privacy requirements are explicitly approved.
G7 Archives with unrecognized schemas still deliver their readable values, as a labeled raw extract with provenance and no semantic claim.

## Functional requirements
| ID | Requirement | Acceptance evidence |
|---|---|---|
| F01 | Accept multiple .olm files and distinguish each input | 3 mixed uploads produce 3 independent result states |
| F02 | Reject non-archive, corrupt, encrypted/unsupported and malicious inputs safely | Negative corpus tests, no path traversal or uncontrolled extraction |
| F03 | Enumerate archive members, infer candidate families and select only compatible adapters | Discovery tests with varied paths/namespaces |
| F04 | Extract all proven supported record families | Golden real-format fixtures and expected counts/fields |
| F05 | Represent repeating values (emails, phones, attendees, categories, attachments) without loss | Normalized child sheets or explicit serialized representation |
| F06 | Create XLSX with typed/forced text semantics and guarded formulas | Workbook roundtrip test including = + - @ and Unicode |
| F07 | Keep per-source provenance and stable batch manifest | Every row traceable to archive/member/locator/version |
| F08 | Show unsupported families/fields and conversion warnings | Manifest contains exact counts and reasons |
| F09 | Offer individual XLSX downloads and aggregate ZIP when batch >1 | End-to-end UI/CLI test |
| F10 | Give actionable outcome states: SUCCESS / PARTIAL / FAILED / UNSUPPORTED / CANCELLED | Matrix of all outcomes |
| F11 | Allow cancellation within bounded processing checkpoints | Cancel produces no falsely completed workbook |
| F12 | Make runs reproducible against identical input/config/adapter versions | Deterministic logical outputs and recorded tool versions |
| F13 | By default, write every readable value from unclaimed XML members and unknown fields to raw extract sheets (04 Raw extract contract) | Schema-variant fixtures: mapped + raw + lost equals source values; outcome never SUCCESS when raw > 0; opt-out recorded in manifest |
| F14 | Account for every source value as mapped, raw or lost, per member and family (04 field-level completeness rule) | Manifest counts reconcile on every fixture; any raw or lost value prevents SUCCESS |

## Nonfunctional requirements
N01 Correctness over coverage claims; cannot label a run SUCCESS when any in-scope record is unaccounted for or any source value is raw or lost.
N02 Memory is bounded as a function of configured chunk/buffer sizes, except bounded metadata; no whole-XML tree requirement.
N03 Archive/member/count/ratio/CPU/time concurrency limits configurable and tested.
N04 No external network transfer of uploaded contents in default local mode.
N05 Logs exclude payload and personal fields by default; temp outputs auto-deleted after configured retention.
N06 Parser/adapters independently testable, versioned, and isolated from UI.
N07 Accessible UI with progress and concise corrective error descriptions.
N08 Consistent behavior across clean supported Python environments, with pinned dependency versions.

## Explicit non-goals for first validated release
- Reconstructing a functional Outlook mailbox or perfect preservation of Outlook formatting.
- Guaranteeing every undocumented OLM variant or unrecognized proprietary record type.
- Cloud multi-tenant storage, identity or long-lived retention before approved privacy design.
- Modifying original OLM input.
- Deduplicating distinct sources without stable source identity evidence.
- Flattening binary attachments directly into spreadsheet cells.

## Scope phases
P0 reconnaissance and safety foundation; P1 contacts-only vertical slice against real fixture; P2 multi-upload and diagnostics; P3 independently validated record-family adapters; P4 optional hosted interface only after separate governance decision. Target includes all proven supported families, but P1 is deliberately narrower than the desired full conversion.

## Semantic completion states
SUCCESS: all detected in-scope recognized records exported and every source value mapped: zero raw, zero lost, no uncounted member (04 field-level completeness rule).
PARTIAL: usable output, at least one family converted, but one or more records or source values not mapped (raw or lost); exact exception inventory.
UNSUPPORTED: valid archive with no supported reader for relevant structures.
FAILED: archive safety/integrity or processing fault prevented reliable output.
CANCELLED: operator stopped the work before completion.
A success state must never be inferred merely from “XLSX created.”

## OPEN acceptance choices
- Is “full” intended to include messages, calendar, tasks, notes, groups and attachment metadata? Proposed yes.
- Should attachments themselves be packaged alongside workbook? Proposed opt-in separate files with integrity hash, never embedded by default.
- Confirm output file naming, sharing model, Excel locale/date conventions, batch ceiling, and target operating platform.

## Decided acceptance choices
- 2026-10-09, product owner: PARTIAL and UNSUPPORTED results with a verified workbook are **downloadable**, so their output can be assessed. Before download and inside the workbook, the UI and `_manifest` must state that the result is not fully converted, with the outcome state and the mapped/raw/lost counts. A PARTIAL or UNSUPPORTED download is never presented like a SUCCESS. FAILED and CANCELLED results publish no workbook.
- 2026-10-09, product owner: raw extract for unrecognized schemas is **default-on** (F13, ADR-008). Contract mechanics in 04 remain PROPOSED pending architecture review.
