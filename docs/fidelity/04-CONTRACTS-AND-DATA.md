# 04 — Boundary and Data Contracts

## External intake
`convert_many(inputs: Sequence[InputRef], options: ConvertOptions) -> BatchResult` (conceptual API). InputRef: unique submission ID, opaque stream/path, original display name, optional declared MIME, measured bytes/hash. Avoid loading every file into memory. Jobs isolate temp dirs and artifacts. Original filename is never trusted as identity or filesystem path.

## Adapter contract
```python
class OLMAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    supported_families: frozenset[str]
    def probe(self, inventory: ArchiveInventory) -> ProbeResult: ...
    def iter_records(self, archive: SafeArchive, selected: Selection) -> Iterator[RecordEnvelope]: ...
```
`ProbeResult`: evidence fingerprints, schema variant, family coverage, confidence, reasons, unknown member count. Low confidence or conflicting probes must not auto-select. Iteration reports malformed records with source locator rather than swallowing exceptions.

## Canonical envelope (not Excel sheet grain)
- `source_archive_sha256`, `archive_submission_id`, `archive_member_path`, `source_record_locator`, `source_record_id_if_present`.
- `family` = contact|message|event|task|note|group|attachment_metadata|unknown.
- `adapter_id/version`, `schema_fingerprint`, `record_ordinal`, `extraction_status`.
- `fields: Map[str, TypedValue|List[TypedValue]]`; `unknown_fields` retains namespace/path/type/representation or a manifest reference.
- `time_properties`: original text, source timezone/offset if present, parsed ISO representation only when unambiguous.
- `relationships`: parent/child links with source-local provenance, never inferred global identity.

## Identity and grain
Envelope grain: one source record element/document emitted by one adapter. Sheet grain varies by family:
- Contacts: one row per contact; contact_emails/phones/addresses child sheets, one row per observed value.
- Messages: one row per message; recipients and attachments metadata child sheets. Message body may require an additional sheet/sidecar according to content limits.
- Events: one row per event; attendees/recurrence relations in child sheets; never silently expand recurrence into occurrences.
- Tasks/notes/groups: one row per source item, child membership/relations where applicable.
- Unknown inventory: one row per unparsed source member/record evidence unit.
All rows carry internal `record_key` = content-scoped archive digest + member locator + ordinal (deterministic within the same archive/adapter). Do not claim stable cross-export business identity absent evidence.

## XLSX delivery contract
Each XLSX includes `_manifest`, `_warnings`, `_unsupported`, and populated family/child sheets. Manifest contains input digest, run version, adapter versions, record counts seen/exported/failed/unsupported, flags, coverage scope, truncation/overflow indexes and outcome.
- Sheet names <=31 chars, unique, deterministic, escaped.
- Excel per-sheet row cap 1,048,576; column cap 16,384; cell text cap 32,767 characters. Partition overflowing families into numbered sheets with manifest linking partitions.
- Preserve Unicode and literal leading whitespace; identifiers/phones/ZIP codes remain text. Protect = + - @ (and control/whitespace-prefixed variants) from execution. Confirm behavior with the chosen Excel writer/reader rather than assuming escaping succeeds.
- No lossy type coercion. Long fields must use chunked sidecar sheets or clearly reported bounded truncation; silent truncation prohibited.
- Distinguish absent, empty, null-like, parse-failed and unsupported when available in source.
- Dates retain original lexeme and parsed interpretation; no unverified timezone conversion.
- No macro content, formula generation or external hyperlinks generated from untrusted payload by default.

## Completeness contract
`seen = exported + failed + unsupported` at the agreed classification grain; per-family and per-record counters must reconcile, accounting for skipped nonrecords separately. Unknown archive members must be listed even if their semantics cannot be decoded. No blanket “all contents converted” promise when semantics are unknown.

## Batch delivery
Aggregate ZIP contains `manifest.json`, one deterministically named per-file workbook for each qualified downloadable result, optional per-file report JSON, and opt-in extracted attachments only after explicit design approval. Name collision handling is stable and path-safe.

## Compatibility
Schema registry entries define exact fixtures and evidence, not universal claims. Contract changes to sheet names, columns, grain, interpretation or parser selection require versioning plus migration notes.
