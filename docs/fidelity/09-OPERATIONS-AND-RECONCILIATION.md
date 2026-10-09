# 09 — Operability, Evidence, and Reconciliation

Status: proposed operational contract for future implementations; no runtime deployment is established.

## Execution observability
Per archive: job ID, SHA-256, byte size, archive member count, adapter signatures/versions, counters per family, current stage, elapsed time, peak memory, outcome, warnings/errors, artifact hash. No contact names, addresses, message bodies, attachment bytes, personal field values or unsafe paths in default logs.

## Operational runbooks
1 Unsupported schema: retain safe inventory and the default-on raw extract, declare unsupported features, request permissioned scrubbed sample, create adapter discovery issue; no fallback guess. Use raw `element_path` distributions, not raw values, as the safe shareable evidence for adapter design.
2 Corrupt/unsafe archive: reject, log safe code and limit hit, do not try alternate unsafe extraction.
3 Partial parse: publish only qualified PARTIAL output + exact manifest, isolate failures; rerun after adapter correction with original read-only file.
4 Output writing failure/disk full: quarantine/delete temp workbook; never publish damaged XLSX; preserve job failure report.
5 Cancelled or interrupted run: terminate at checkpoint, purge temps and report CANCELLED/FAILED accurately; verify cleanup.
6 Privacy event: stop processing, isolate artifacts, apply incident response specified by environment owner; do not retain files to aid debugging without consent.
7 Resource exhaustion: halt offending archive, preserve independent sibling results; adjust limits only after measurements and ADR review. Archive guard defaults are deliberately tight placeholders sized from E09 (largest member 74 MB, stored uncompressed): 1,000,000 entries, 64 GiB total uncompressed, 2 GiB per member, compression ratio 100 per member. Rejecting a legitimate outlier is the cheaper error, and the operator can allow one explicitly (`--max-member-gib`, `--max-ratio`). There is no wall-clock parse limit yet (N03); tracked under W08.

## Support and compatibility matrix
Published matrix by Outlook export version / observed schema fingerprint / families / max tested size / limitations / validated fixture hash / adapter release. Mark untested permutations UNKNOWN, not supported.

## Evidence ledger format
`claim_id | architecture_state | evidence_label | observation | source + revision/time | owner | uncertainty | invalidation trigger | next test`.
Initial entries:
- E01 [OBSERVED] current repo is documentation/synthetic before code.
- E02 [OBSERVED] synthetic OLM contains single guessed contact XML path.
- E03 [OPEN] real vendor OLM structures unvalidated. Partly resolved by E09 for one export; other variants and record families remain unvalidated.
- E04 [PROPOSED] standalone local-first adapter architecture.
- E05 [OPEN] benchmark and security limits unqualified for this implementation.
- E06 [CONTRADICTION in decision context] original parent-module recommendation vs newly requested standalone scope; resolve by explicit ADR-001 approval.
- E07 [OBSERVED] 2026-10-09 throwaway check on `sample.olm` (not committed): a hardcoded-path parser returned 20,000 contacts and 0 emails when `emailAddress` was renamed, and 0 contacts when a root namespace was added, while a schema-agnostic walker counted 241,487 raw values in all three variants. Motivates T17/T18 and ADR-008.
- E08 [PROPOSED] default-on raw extract contract (ADR-008); default-on itself accepted by product owner 2026-10-09.
- E09 [OBSERVED] 2026-10-09 structure report from `olm-excel profile` on the product owner's own export (73,870,643 bytes, sha256 10b7a8ca...1553f4, Outlook build unknown; source `docs/samples/olm-profile.contacts-archive.json`, PR #5). Contacts-only: 4 members stored uncompressed; contacts members with 19,634, 56 and 1 contacts; `Categories.xml` with 202 categories; 1,176,094 source values; 83 distinct element paths. Every element carries `xml:space` except `/categories`; roots carry `elementCount`; `contactEmailAddress` appears in six containers. Contents were never read by the model. Uncertainty: one export, one Outlook version. Invalidation trigger: any export with a different structure. Next test: Q2 real-archive count check.
- E10 [OBSERVED] `OPFContactAddPicture` has 187 values, 12 over the Excel cell cap. [INFERRED] base64 image text; encoding not verified against a real value.
- E11 [CONFIRMED] product owner selections 2026-10-09, relayed verbatim through a second Claude session: structural values "Yes (Recommended)", pictures "Metadata + image files (Recommended)", dates "Keep as text (Recommended)". Recorded as ADR-009 to ADR-011 and 02. Confirmed directly by the product owner in the main session the same day ("Confirmed, and yes add the picture message"), which also approved F17.
- E12 [OPEN] not established by E09: whether `DefaultEmailAddress` entries duplicate list entries; what `OPFContactCopyContactImage` holds; whether `ExchangeID` is stable across exports (U07); how `OPFContactAddPictureType` pairs with pictures; date formats; whether present-but-empty fields matter (an element whose only content is `xml:space` yields no source value, but the contacts adapter detects its presence from that structural attribute and lists it in `empty_fields`); behavior of other Outlook versions (U01).

## Material reconciliation triggers
New fixture contradicts schema hypothesis; parser produces orphan/omitted record; field mapping changes meaning; security boundary changes; coverage count fails; memory/cost materially exceeds requirement; client reports missing record family; owner revises PRD. Record first invalid artifact, impacted dependents and required retest.

## Invalidation propagation
Requirement changed → mark relevant architecture/contract for review → mark affected implementation/verification evidence stale → revise only impacted work packets → rerun impacted real/synthetic tests → reapprove outcome. A passing prior test is not transferable across incompatible parser versions or changed fixtures.

## Qualification statement template
“Version X supports [exact real-export variants] and [record families] under tested limits [L], as established by [fixture hashes and run IDs]. Known unsupported [U]. Results may be PARTIAL with manifest. This statement makes no universal OLM compatibility claim.”

## Owners
Capability owner: product definition/completeness semantics.
Architect: boundaries, quality and ADRs.
Implementation owner: code and packaging.
Verification owner: independent expected outputs and release gates.
Operator: data handling, monitoring and recovery.
Assign actual people before release. One person may fill several roles but disclosed self-review is not independent verification.

## Final fidelity test
Desired outcome → requirements IDs → adapters/contracts → implementation → independent oracle → measured output → user-visible result. If this chain breaks, do not declare complete.
