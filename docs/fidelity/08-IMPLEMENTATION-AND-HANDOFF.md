# 08 — Execution Plan and Bounded Agent Handoff

Status: PROPOSED, not executed. Implement in reviewable PRs, no direct unreviewed production writes.

## Dependency sequence
W00: Evidence and scope — consented real exports, fixtures metadata, confirm family scope, output example and privacy rules. Exit: U01/U02/U04 reduced and PRD reviewable.
W01: Package and quality skeleton — src layout, pyproject lock strategy, CLI stub, tests/CI, static typing, formatting. Exit: clean reproducible development environment.
W02: Safe archive intake — ZIP guard, member inventory, quotas, malformed archive diagnostics. Exit Q1.
W03: Schema discovery and adapter API — probes, registry, conflict resolution and unknown inventory. Exit: deterministic selection on labeled fixtures.
W04: Canonical envelope and coverage accounting — provenance/identity/time/multivalue records. Exit: independently checked contract tests.
W05: Contacts vertical slice — a **real** format contact adapter, streaming, normalized sheet export and warnings. Exit Q2.
W06: Batch orchestration and surface — multi-upload local UI + CLI, cancel, progress, per-file download, aggregate ZIP. Exit Q3.
W07: Family adapters — messages/calendar/tasks/notes/groups and attachment metadata, each gated by real reference exports; dependencies independent where possible. Exit Q4 per family, no speculative support checkboxes.
W08: Hardening — large XML memory profile, adversarial/fuzz, cleanup, Excel boundary cases, stable packaging and privacy review. Exit Q5.
W09: Qualified release — documented support matrix, user guide, limitations, release artifacts, recovery playbook and monitoring profile. Exit: owner accepts scope-limited release.
W10: Post-release reconciliation — compare user-reported inputs/outputs to certified corpus; add versioned adapter/fixtures/ADRs when new evidence invalidates assumptions.

## Work packet contract
For every Wxx task require: objective, governing docs/revisions, allowed files, exclusions, dependencies, API contract, acceptance tests, negative/failure tests, test evidence, rollback, decision owner and escalation triggers.

## Suggested initial repository structure
```text
src/olm_excel/
  core/{archive_guard,discovery,records,projection,xlsx_writer,coordinator,report}.py
  adapters/
  interfaces/{cli,ui}.py
tests/{unit,integration,golden,security,performance,fixtures}/
docs/fidelity/
pyproject.toml
README.md
```
These paths are proposed and not yet present.

## Agent authority
Mechanical implementation decisions: allowed (local names, factoring within stable contracts).
Implementation-local choice: allowed if exact contract preserved and tested.
Programming design changes (identity, state, retries): escalate.
Architecture changes (streaming boundary, adapter authority, storage/trust): escalate.
Requirements changes (family scope, partial semantics, privacy): escalate.
Forbidden: silently declare any new schema supported, drop unknown records without reporting, bypass limits, commit private fixtures, or modify parent source snapshot.

## Work ordering and verification
One vertical slice before parallel family work. PRs should link requirement IDs, ADR IDs, affected contracts, tests and rollback. Review architecture conformance separately from test green. Required review order: inspection → implementation → tests/negative cases → documentation reconciliation → qualification → merge.

## Release/migration
Do not migrate parent application's behavior automatically; this repository is standalone. Distribution target must be explicitly selected (local CLI executable, pip package, local Streamlit UI or hosted app). Initial release local-first by ADR-005; a hosted service requires separate auth, multi-user isolation and data retention architecture.

## Stop conditions
No real-export fixture for a claimed adapter; uncontrolled memory expansion; unmitigated XXE or ZIP bomb; untraceable silent loss; personally identifiable fixture committed without approval; mismatched workbook count reconciliation; missing recovery on partial batch failure. Return to first invalid assumption and re-plan instead of implementing around it.
