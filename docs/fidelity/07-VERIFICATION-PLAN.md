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
| T07 | Excel hostile value prefixes, Unicode and whitespace | no executable formulas; exact text roundtrip |
| T08 | >1,048,576 family records or >32,767 char values | partitioning/sidecar or explicit loss-free report |
| T09 | malformed XML, entities, nested depth | bounded rejection and safe error |
| T10 | ZIP bomb/traversal/entry count breach | early controlled rejection and no filesystem escape |
| T11 | large single XML | measured bounded memory; progress/timeout correctness |
| T12 | timeout, cancel, disk full | no published invalid output; cleanup and actionable diagnostics |
| T13 | duplicate input names and identical contents | collision-safe naming and deterministic manifest |
| T14 | no-network run, logging | zero outbound content transmission, no PII in logs |
| T15 | no contacts but valid other-family archive | no false “empty success”; family coverage explicit |
| T16 | schema mutation fuzzing | no uncaught unsafe failure; diagnostics preserve coverage state |

## Format corpus
Maintain `tests/fixtures/manifest.yaml` with IDs, provenance, anonymization/synthetic tag, license/consent, Outlook build, OS, export scope, hash, sensitive-data handling, family fingerprints, expected counts, compatibility status. Never commit actual user/private OLM exports without explicit authorization and privacy review. Synthetic is never proof of real vendor support.

## Qualification gates
Q0: target scope and requirements approved; real-format fixture acquisition plan exists.
Q1: safe archive reader passes hostile corpus.
Q2: first real contact variant converts with independent 100% in-scope golden field/count checks.
Q3: batch orchestration and UI/CLI tests, cancellation, manifest and no cross-file contamination pass.
Q4: each additional family adapter has own real fixture, independent oracle and declared compatibility.
Q5: capacity, security, cleanup, packaging and operating checks pass; residual unknowns published.
No deployment or “universal OLM support” claim is authorized by a passing synthetic-only suite.

## Fitness functions
- `classified == exported + failed + unsupported` per family under recorded classification semantics.
- No silent unaccounted known records or mapped fields.
- Parser ambiguity never falls back to an unverified default.
- Atomic artifact publication only after workbook verification.
- Peak memory and per-file processing measured against separately approved SLOs.
- For any supported fixture, repeat runs preserve logical data and manifest semantics.

## Test evidence record
Store test run ID, commit SHA, fixture hashes, adapter/tool versions, environment, outcome, measured resource use, failing records (safe IDs only), reviewer, limitations, and link to artifact. Passing CI alone is not semantic correctness.
