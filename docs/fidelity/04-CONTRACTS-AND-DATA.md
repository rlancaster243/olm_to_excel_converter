# 04 — Boundary and Data Contracts

## External intake
`convert_many(inputs: Sequence[InputRef], options: ConvertOptions) -> BatchResult` (conceptual API). InputRef: unique submission ID, opaque stream/path, original display name, optional declared MIME, measured bytes/hash. Avoid loading every file into memory. Jobs isolate temp dirs and artifacts. Original filename is never trusted as identity or filesystem path.
`ConvertOptions.raw_extract: bool = True` (ADR-008). Turning it off is an explicit operator choice recorded in the manifest.

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
Adapters read XML members through the core source-value walker (see Source values) and report which value ordinals each envelope mapped. The core, not the adapter, counts source values and routes unmapped ones to raw or lost. An adapter cannot grade its own coverage.

## Source values
A source value is the unit of field-level completeness, shared by adapters, the raw extractor and the completeness contract. Within an XML member, a source value is one of:
- an attribute value; namespace declarations (`xmlns`, `xmlns:p`) are not values, since the namespace appears in qualified names and paths;
- a text node (element text, or text following a child element) that contains non-whitespace, or that is whitespace-only inside an element with no child elements, or anywhere under `xml:space="preserve"`; whitespace-only text between child elements is formatting and not a value;
- an empty element: no attributes, no children and no text at all (`value_kind=empty`, so absent and empty stay distinguishable).
An element with attributes but no content yields only its attribute values. Each source value has a `node_ordinal` in document order within its member, assigned by the core walker.

## Canonical envelope (not Excel sheet grain)
- `source_archive_sha256`, `archive_submission_id`, `archive_member_path`, `source_record_locator`, `source_record_id_if_present`.
- `family` = contact|message|event|task|note|group|attachment_metadata|unknown.
- `adapter_id/version`, `schema_fingerprint`, `record_ordinal`, `extraction_status`.
- `fields: Map[str, TypedValue|List[TypedValue]]`; `unknown_fields` lists the record's source values the adapter did not map, each with `node_ordinal`, `element_path`, attribute name, `value_kind` and literal value as supplied by the core walker. A bare manifest reference without the literal value is not allowed.
- `time_properties`: original text, source timezone/offset if present, parsed ISO representation only when unambiguous.
- `relationships`: parent/child links with source-local provenance, never inferred global identity.

## Identity and grain
Envelope grain: one source record element/document emitted by one adapter. Sheet grain varies by family:
- Contacts: one row per contact; contact_emails/phones/addresses child sheets, one row per observed value.
- Messages: one row per message; recipients and attachments metadata child sheets. Message body may require an additional sheet/sidecar according to content limits.
- Events: one row per event; attendees/recurrence relations in child sheets; never silently expand recurrence into occurrences.
- Tasks/notes/groups: one row per source item, child membership/relations where applicable.
- Unknown inventory: one row per unparsed source member/record evidence unit.
- Raw extract: one row per raw source value (see Raw extract contract).
All rows carry internal `record_key` = content-scoped archive digest + member locator + ordinal (deterministic within the same archive/adapter). Do not claim stable cross-export business identity absent evidence.

## Raw extract contract (default-on, ADR-008)
Purpose: every readable source value reaches the workbook even when no adapter can interpret it. The raw extract states where a value sat, never what it means.

Scope. The raw extractor runs on:
- every XML member not claimed by a selected adapter (no match, low confidence or ambiguous probe);
- every `unknown_fields` entry inside records an adapter did claim, linked by `record_key`.
Non-XML, binary or undecodable members get an `_unsupported` inventory row only (size, hash, detected signature). Their bytes are never written to cells.

Grain: one row per source value (see Source values) routed to raw. Mixed content keeps each text node as its own row.

Columns (all written as literal text cells):
| Column | Meaning |
|---|---|
| `raw_key` | `member_ordinal:node_ordinal`; node ordinal is document order within the member. Deterministic for identical input and tool version. |
| `archive_submission_id`, `archive_member_path` | provenance, as in the envelope |
| `record_key` | set only for unknown fields of adapter-claimed records; empty for unclaimed members. The raw extractor never infers record boundaries. |
| `element_path` | namespace-qualified positional path in Clark notation of the element that contains the value, e.g. `/{urn:x}contacts[1]/{urn:x}contact[37]/emailAddress[2]`. Text following a child element belongs to the containing parent, not the child. |
| `attribute` | qualified attribute name, empty for text/empty rows |
| `text_position` | for text rows: 0 for text before the first child element, k for text following the k-th child element; empty otherwise |
| `value_kind` | `attribute` / `text` / `empty` |
| `value`, `chunk` | literal value; long values split into ordered chunks sharing one `raw_key` under the chunking rule in the XLSX delivery contract |

Sheets: `raw_0001`, `raw_0002`, ... partitioned at the Excel row cap, plus `_raw_index` with one row per extracted member: member path, first/last `raw_key`, partitions, values observed, values written, `raw_complete` flag, stop reason.

Semantics:
- Raw rows make no semantic claim. They are never promoted into family sheets, typed, or joined to canonical columns by the tool. Promotion happens only by building an adapter (ADR-007).
- The outcome is decided by the field-level completeness rule (Completeness contract), from source values, not from whether raw rows were written. Turning raw extract off changes where unmapped values are reported (lost instead of raw), never the outcome.
- Downloadability of PARTIAL and UNSUPPORTED results follows the OPEN acceptance choice in 02. If partial results are approved as downloadable, an UNSUPPORTED result with a verified raw workbook is downloadable with the same warning treatment as PARTIAL.
- Manifest records `raw_extract` on/off, source values mapped/raw/lost per member, partitions and any `RAW_EXTRACT_LIMIT` stop.
- Raw values are as sensitive as canonical values: same cell policy, same logging exclusions.

Limits: the extractor uses the same hardened streaming parser, depth limits and quotas as adapters. A configurable `raw_extract_max_values` per archive caps raw rows. When the cap is reached partway through a member, that member is marked `raw_complete=false` with stop reason `RAW_EXTRACT_LIMIT`; every later unclaimed member still gets an `_raw_index` row with values written 0, `raw_complete=false`, stop reason `RAW_EXTRACT_LIMIT` and source values `uncounted` if it was not walked. No member drops out of the index. A malformed member keeps rows emitted before the parse error, is marked `raw_complete=false` and raises `RECORD_PARSE_ERROR`.

## XLSX delivery contract
Each XLSX includes `_manifest`, `_warnings`, `_unsupported`, populated family/child sheets and, when raw values exist, `_raw_index` plus `raw_NNNN` partitions. Manifest contains input digest, run version, adapter versions, record counts seen/exported/failed/unsupported, source values mapped/raw/lost with lost reason codes, flags, coverage scope, truncation/overflow indexes and outcome.
- Sheet names <=31 chars, unique, deterministic, escaped.
- Excel per-sheet row cap 1,048,576; column cap 16,384; cell text cap 32,767 characters. Partition overflowing families into numbered sheets with manifest linking partitions.
- Preserve Unicode and literal leading whitespace; identifiers/phones/ZIP codes remain text. Protect values starting with = + - @ (and control/whitespace-prefixed variants) from execution by writing them as explicit string-typed cells, not by adding a prefix: the stored text must equal the source value exactly. Confirm behavior with the chosen Excel writer/reader rather than assuming it succeeds.
- No lossy type coercion. Long fields must use chunked sidecar sheets or clearly reported bounded truncation; silent truncation prohibited.
- Chunking rule: chunks are at most 32,000 UTF-16 code units (Excel counts UTF-16 units, not code points), never split a surrogate pair, and are ordered by `chunk`. The headroom below 32,767 is fixed so no later cell policy can push a chunk over the cap.
- Distinguish absent, empty, null-like, parse-failed and unsupported when available in source.
- Dates retain original lexeme and parsed interpretation; no unverified timezone conversion.
- No macro content, formula generation or external hyperlinks generated from untrusted payload by default.

## Completeness contract
`seen = exported + failed + unsupported` at the agreed classification grain; per-family and per-record counters must reconcile, accounting for skipped nonrecords separately. Unknown archive members must be listed even if their semantics cannot be decoded. No blanket “all contents converted” promise when semantics are unknown.
Field-level completeness rule, per XML member and per family:
`source_values == mapped + raw + lost`
- `mapped`: the value contributes to at least one family or child-sheet cell; each source value counts once.
- `raw`: the value was written as a raw extract row (chunks count once).
- `lost`: neither; each lost value is counted with a reason code (`RAW_EXTRACT_DISABLED`, `RAW_EXTRACT_LIMIT`, `RECORD_PARSE_ERROR`, `EXCEL_LIMIT`).
Outcome rule:
- SUCCESS requires the record-level equation to reconcile and `raw == 0` and `lost == 0` for every member, with no member `uncounted` and no unclaimed non-XML member.
- Otherwise the outcome is PARTIAL if at least one family was converted, UNSUPPORTED if none was (FAILED and CANCELLED keep their 02 meanings).
- `raw` and `lost` are properties of the source, so the outcome is the same with raw extract on or off.
A member whose values could not be counted (not walked after a limit, or parse stopped) is `uncounted` and can never contribute to SUCCESS. Non-XML members claimed by an adapter (for example attachment payloads referenced from records) are accounted at member grain; unclaimed non-XML members are inventoried in `_unsupported`.

## Batch delivery
Aggregate ZIP contains `manifest.json`, one deterministically named per-file workbook for each qualified downloadable result, optional per-file report JSON, and opt-in extracted attachments only after explicit design approval. Name collision handling is stable and path-safe.

## Compatibility
Schema registry entries define exact fixtures and evidence, not universal claims. Contract changes to sheet names, columns, grain, interpretation or parser selection require versioning plus migration notes.
