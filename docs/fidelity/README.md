# OLM to Excel — Engineering Fidelity Dossier

Status: **Accepted** target architecture for contacts v1 (Russell 2026-10-11); code in [PR #9](https://github.com/rlancaster243/olm_to_excel_converter/pull/9). Date: 2026-10-08 dossier; decisions 2026-10-11.
Scope: `rlancaster243/olm_to_excel_converter`. Authority: ADRs in [05-DECISIONS-AND-TRADEOFFS.md](05-DECISIONS-AND-TRADEOFFS.md) govern implementation.

## Mission
Convert one or many Outlook for Mac OLM archives into Excel workbooks, preserving supported record values, provenance and diagnostic visibility. Avoid silent loss. Make non-contact records and schema variants discoverable without promising impossible universal semantic interpretation.

## Source baseline
- Root README and `docs/ASSESSMENT.md` currently describe a contacts-only, pre-implementation project.
- `docs/samples/sample.olm` is synthetic, not a real Outlook export.
- Parent `mbox_to_eml_converter` source snapshot is frozen, read-only context, not an importable dependency.
- Synthetic 20k-contact benchmark (~6 s and ~297 MB peak RSS) is historical, unreplicated for this repo.
- Earlier recommendation B (module within parent) was conditional on a narrow contacts MVP. **ADR-001 (accepted):** this repository is the ownership boundary; the parent integrates via installable `olm-excel`.

## Governing sequence
FRAME → UNDERSTAND → DEFINE → ARCHITECT → DESIGN → VERIFY BEFORE BUILD → PLAN → HANDOFF → RECONCILE.
Outer loop: release, observe, operate, recover and revise when deployment becomes relevant. Rigor scales with risk.

## Canonical document registry
| Document | Governs |
|---|---|
| [01-PROBLEM-AND-REALITY.md](01-PROBLEM-AND-REALITY.md) | Problem, evidence, system state, unknowns |
| [02-PRD-AND-ACCEPTANCE.md](02-PRD-AND-ACCEPTANCE.md) | Scope, user outcomes, functional/nonfunctional requirements |
| [03-ARCHITECTURE.md](03-ARCHITECTURE.md) | Target boundaries, flows, authority, failure design |
| [04-CONTRACTS-AND-DATA.md](04-CONTRACTS-AND-DATA.md) | Record taxonomy, parser interfaces, data semantics, workbook contract |
| [05-DECISIONS-AND-TRADEOFFS.md](05-DECISIONS-AND-TRADEOFFS.md) | ADRs, alternatives and revisit triggers |
| [06-THREATS-AND-FAILURES.md](06-THREATS-AND-FAILURES.md) | Threat model, operational failure and recovery |
| [07-VERIFICATION-PLAN.md](07-VERIFICATION-PLAN.md) | Independent test oracles, compatibility corpus, test gates |
| [08-IMPLEMENTATION-AND-HANDOFF.md](08-IMPLEMENTATION-AND-HANDOFF.md) | Work packages, milestones, agent authority, releases |
| [09-OPERATIONS-AND-RECONCILIATION.md](09-OPERATIONS-AND-RECONCILIATION.md) | Observability, runbooks, invalidation and evidence ledger |

## Evidence convention
[CONFIRMED] authoritative requirement or external standard; [OBSERVED] inspected code/artifact/actual output; [INFERRED] grounded, not demonstrated; [PROPOSED] intended design; [OPEN] needs validation; [CONTRADICTION] competing evidence; [STALE] potentially invalidated. Do not confuse normative requirements with empirical behavior.

## State model
CURRENT: documentation and synthetic fixture, no converter app code confirmed.
TARGET: standalone batch-capable conversion engine with adapter-driven schema discovery, record-preserving exports and diagnostics.
MIGRATION: format reconnaissance → first validated contact vertical slice → record family expansion → multiple uploads → qualified release.
UNKNOWN: real OLM variants, practical archive sizes, non-contact semantics, hosting and privacy posture.

## Governing invariants
1. No success claim for a record or field that was silently omitted.
2. Every exported row is traceable to source archive, member, record locator and parser/normalizer version.
3. Ambiguous or unknown semantics never become fabricated canonical fields.
4. Conversion must fail safely on malicious or resource-exhausting archives.
5. Processing one upload must not contaminate another; batch retries are idempotent at result identity level.
6. Inputs remain read-only; temporary plaintext has bounded lifetime.
7. Tests are derived from contracts, not implementation conveniences.
8. Agent implementation may select mechanics, but may not invent requirements, semantic authority or security exemptions.

## Reading and change policy
Begin with the problem and PRD. For code, the implementation plan and verification contract govern scope. Material changes to assumptions require impact analysis of dependent artifacts, not silent edits. Every accepted decision requires evidence and an owner.

## Completion criterion
Documents are a planning deliverable only. “Converter completed” requires real-export compatibility evidence, accepted verification runs and a working downloadable result. 
