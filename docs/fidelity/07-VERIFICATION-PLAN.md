# 07 — Independent Verification Contract

Status: test design before implementation. No tests have been executed under this plan.

## Oracle design
Golden expected outputs are independently derived from real Outlook sample inspection and user-approved field mapping. A parser's own output is not its own oracle. Preserve source export app version, fixture SHA-256, archive metadata, supported family selection and explicit expected record/value counts.

## Verification ladder
1 Static dependency/interface checks.
2 Parser and normalization unit tests with handcrafted structures.
3 Contract and schema-fingerprint selection tests.
4 Real-sample integration and golden XLSX roundtrip.
5 UI/CLI batch E2E and download verification.
6 Adversarial failure and recovery testing.
7 Capacity/latency memory measurement.
8 Independent review of coverage claims and residual unknowns.

## Acceptance matrix
| ID | Scenario | Required evidence |
|---|---|---|
| T01 | Real exported contacts, alternative layouts/namespaces | full mapped count/field equality; unknowns listed |
| T02 | 3 uploads: valid, corrupt, unsupported | independent results, aggregate manifest and retained success |
| T03 | repeated field values | child rows preserve value cardinality and parent associations |
| T04 | novel unrecognized field | no guessed mapping; audit entry and explicit partiality |
| T05 | multiple accounts and member path variants | correct provenance, correct adapter routing |
| T06 | unknown mail/calendar/task/note/group variant | honest UNSUPPORTED/PARTIAL, not false SUCCESS |
| T07 | Excel hostile value prefixes, Unicode and whitespace | no formula cells in the sheet XML (cell type checked, not just value: a reader returns `=…` text for live formulas too); exact text roundtrip |
| T08 | >1,048,576 family records or >32,767 char values | partitioning/sidecar or explicit loss-free report |
| T09 | malformed XML, entities, nested depth | bounded rejection and safe error |
| T10 | ZIP bomb/traversal/entry count breach | early controlled rejection and no filesystem escape |
| T11 | large single XML | measured bounded memory; progress/timeout correctness |
| T12 | timeout, cancel, disk full | no published invalid output; cleanup and actionable diagnostics |
| T13 | duplicate input names and identical contents | collision-safe naming and deterministic manifest |
| T14 | no-network run, logging | zero outbound content transmission, no PII in logs |
| T15 | no contacts but valid other-family archive | no false “empty success”; family coverage explicit |
| T16 | schema mutation fuzzing | no uncaught unsafe failure; diagnostics preserve coverage state |
| T17 | known family with a renamed child element (e.g. `emailAddress` → `contactEmailAddress`) | whether or not the adapter is selected: mapped + raw + lost == source values; the email attribute values appear as mapped or raw, never silently absent; outcome not SUCCESS |
| T18 | known family with an added root namespace | whether the probe matches namespace-aware (all mapped, SUCCESS allowed) or not (UNSUPPORTED, all raw): mapped + raw + lost == source values; namespace declaration not counted |
| T19 | node-dense member exceeding `raw_extract_max_values`, followed by further unclaimed members | RAW_EXTRACT_LIMIT, `raw_complete=false` on the cut member, every later member indexed with stop reason, no silent truncation, non-SUCCESS outcome |
| T20 | raw extract opt-out on an archive with unclaimed members | no raw rows; unmapped values counted lost with RAW_EXTRACT_DISABLED; outcome identical to the opt-in run |
| T21 | malformed XML in an unclaimed member | rows before the error retained, `raw_complete=false`, RECORD_PARSE_ERROR, member uncounted beyond the error |
| T22 | whitespace-only leaf text, `xml:space="preserve"`, empty element, element with attributes only | counted per 04 Source values; empty vs whitespace vs absent distinguishable in output |
| T23 | value > 32,000 UTF-16 units containing astral characters, with a chunk starting with `=` | chunks ≤ 32,000 UTF-16 units, no split surrogate pair, concatenated chunks equal the source exactly, no executable formula |
| T24 | adapter that under-reports mapped ordinals | core counts unchanged; unreported values routed to raw; outcome not SUCCESS |
| T25 | download of PARTIAL and UNSUPPORTED results | download offered; UI shows outcome and mapped/raw/lost counts before download; `_manifest` first rows state the same; FAILED/CANCELLED offer no workbook |
| T26 | structural values: `xml:space` on every element, root `elementCount` equals the record count | structural counted separately; mapped + structural + raw + lost == source values; no structural value in any sheet |
| T27 | `elementCount` wrong, or `xml:space` with a value other than preserve/default | value not structural; routed raw (or lost with raw off); `STRUCTURAL_MISMATCH` warning; outcome PARTIAL |
| T28 | attribute named like a declaration on the wrong element, or with a different namespace | never structural; routed raw or lost |
| T29 | synthetic archive mirroring the E09 layout (three contacts members, one categories member, no real values) | record counts per member equal `elementCount`; sheet row counts equal the generator's counts; counts reconcile |
| T30 | all six `contactEmailAddress` containers present | one `contact_emails` row per element with correct `list_source`; no de-duplication |
| T31 | pictures: valid base64 image, non-base64 text, oversized value, hostile type text | metadata row per picture; sha256 of decoded bytes; with export, content-addressed files only; without export or on decode failure, `PICTURE_NOT_EXPORTED` and PARTIAL; no picture text in any cell or raw row |
| T32 | date fields (`Birthday`, `Anniversary`, `ModDate`) and every scalar | exact source text; no date-typed cells |
| T33 | unknown element under a contact | raw row with the contact's `record_key`; PARTIAL |
| T34 | contacts member at an unusual path or file name; root renamed | claimed by content when structure matches; not claimed when the root differs |
| T35 | outcome notice (F17) | picture-only PARTIAL names the count and `--export-images`; raw, lost-for-other-reasons, uncounted, non-XML or warnings remove the "only because" wording; export on gives SUCCESS and "Fully converted."; undecodable pictures with export on never advise export; `_manifest` notice equals the CLI line |

Schema-variant fixtures T17/T18 are synthetic mutations of `docs/samples/sample.olm`. Their oracle is the source value count from an independent walker over the unmodified XML: 241,487 for the committed sample (77,592 attribute, 163,895 text, 0 empty; 542 values contain astral characters), counted 2026-10-09 under the 04 Source values definition. Recount when the fixture or the definition changes. The mutations change names, not values, so each variant must also total 241,487.

## Format corpus
Maintain `tests/fixtures/manifest.yaml` with IDs, provenance, anonymization/synthetic tag, license/consent, Outlook build, OS, export scope, hash, sensitive-data handling, family fingerprints, expected counts, compatibility status. Never commit actual user/private OLM exports without explicit authorization and privacy review. Synthetic is never proof of real vendor support.

## Qualification gates
Q0: target scope and requirements approved; real-format fixture acquisition plan exists.
Q1: safe archive reader passes hostile corpus.
Q2: first real contact variant converts with independent 100% in-scope golden field/count checks.
Real-archive Q2 check (private, counts only): the operator runs the converter on their own export and compares against their structure report (E09): records per contacts member equal the report's counts, categories equal the report's, source values equal the report's total, and mapped + structural + raw + lost equals that total. Only counts leave the operator's machine. The file itself is never committed or shared.
Q3: batch orchestration and UI/CLI tests, cancellation, manifest and no cross-file contamination pass.
Q4: each additional family adapter has own real fixture, independent oracle and declared compatibility.
Q5: capacity, security, cleanup, packaging and operating checks pass; residual unknowns published.
No deployment or “universal OLM support” claim is authorized by a passing synthetic-only suite.

## Fitness functions
- `seen == exported + failed + unsupported` per family under recorded classification semantics (record level, as in 04).
- No silent unaccounted known records or mapped fields.
- Per XML member and per family, `source_values == mapped + structural + raw + lost`, counted by the core walker, not the adapter.
- SUCCESS only when raw == 0, lost == 0 and no member is uncounted.
- Outcome is identical with raw extract on and off for the same input.
- Parser ambiguity never falls back to an unverified default.
- Atomic artifact publication only after workbook verification.
- Peak memory and per-file processing measured against separately approved SLOs.
- For any supported fixture, repeat runs preserve logical data and manifest semantics.

## Test evidence record
Store test run ID, commit SHA, fixture hashes, adapter/tool versions, environment, outcome, measured resource use, failing records (safe IDs only), reviewer, limitations, and link to artifact. Passing CI alone is not semantic correctness.
