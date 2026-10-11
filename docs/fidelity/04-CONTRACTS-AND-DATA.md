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
Known unobserved risk: newline and indent text between fields under `xml:space="preserve"` is a text value by the rule above. It is counted and kept raw (outcome PARTIAL) until an export shows it. Treating it as structural would need evidence and an ADR (ADR-009).

## Structural values (ADR-009)
Some source values are format bookkeeping, not record data. An adapter may declare a closed list of structural declarations in its registry entry. Each declaration names an element path pattern and attribute, a validator, and the evidence that justified it. The core, not the adapter, evaluates declarations and counts the values.
- A source value is `structural` only if it matches a declaration and its validator passes. Structural values are checked, not exported: they appear in no family sheet and no raw sheet. The manifest lists each declaration with the number of values it consumed and the number that failed.
- A value that matches a declaration but fails validation is not structural. It is routed as raw or lost, so the outcome is PARTIAL, and a `STRUCTURAL_MISMATCH` warning names the declaration and member (never the value).
- Anything that matches no declaration is never structural. Declaring a value structural when it carries record data (names, addresses, dates, identifiers, free text) needs its own ADR.
- Contacts v1 declarations (evidence E09): (1) `xml:space` on any element, valid values `preserve` and `default`; (2) `elementCount` on the root `contacts` or `categories` element, valid when it is an integer equal to the number of child records parsed in that member, checked when the member ends (if it fails, that one value is routed raw or lost).
- `xml:space="preserve"` still changes which whitespace text counts as a source value (see Source values). Structural status concerns only the attribute value itself.

## Canonical envelope (not Excel sheet grain)
- `source_archive_sha256`, `archive_submission_id`, `archive_member_path`, `source_record_locator`, `source_record_id_if_present`.
- `family` = contact|category|message|event|task|note|group|attachment_metadata|unknown.
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
- PARTIAL and UNSUPPORTED results with a verified workbook are downloadable for assessment (02 decided acceptance choices). The UI shows the outcome state and mapped/structural/raw/lost counts before download, and `_manifest` repeats them as its first rows, so the file never reads as a full conversion.
- Manifest records `raw_extract` on/off, source values mapped/structural/raw/lost per member, partitions and any `RAW_EXTRACT_LIMIT` stop.
- Raw values are as sensitive as canonical values: same cell policy, same logging exclusions.
- Binary payload values that an adapter declares (for example contact pictures) are never written as raw rows, since cells are not a binary store. They are mapped (exported as files) or lost with `PICTURE_NOT_EXPORTED`. Unclaimed members have no adapter to declare payloads, so their text goes raw verbatim.

Limits: the extractor uses the same hardened streaming parser, depth limits and quotas as adapters. A configurable `raw_extract_max_values` per archive caps raw rows. When the cap is reached partway through a member, that member is marked `raw_complete=false` with stop reason `RAW_EXTRACT_LIMIT`; every later unclaimed member still gets an `_raw_index` row with values written 0, `raw_complete=false`, stop reason `RAW_EXTRACT_LIMIT` and source values `uncounted` if it was not walked. No member drops out of the index. A malformed member keeps rows emitted before the parse error, is marked `raw_complete=false` and raises `RECORD_PARSE_ERROR`.

## Contacts v1 sheet contract (provisional, evidence E09)
Derived from one real export, Outlook version unknown. Adapters are selected by content, never by path or file name.
- `contacts-olm-v1` claims an XML member whose root is `contacts`, whose record elements are `contact`, and whose record children are named `OPFContact*`.
- `categories-olm-v1` claims an XML member whose root is `categories` and whose record elements are `category` with attributes `OPFCategoryCopyName` and `OPFCategoryCopyBackgroundColor`.
- Only the first occurrence of each scalar field per contact is mapped (E09 shows exactly one of each). A later occurrence of a scalar field, or a repeated container, is an unknown field. Pictures and picture types are not covered by this rule; see Contact pictures.
- Any element or attribute under a claimed record that is not listed below is an unknown field: it is written as a raw row linked by `record_key`, and the outcome is PARTIAL. Nothing is guessed.

Identity: `record_key = <first 12 hex of archive sha256>/<member ordinal>/<record ordinal>`. `ExchangeID` appears on every contact in E09, but its stability across exports is unproven (U07), so it is a column, not the key.

Sheets:
- `contacts`: one row per `contact`, across all contacts members (E09 had three). Columns: `record_key`, `source_member`, `contact_ordinal`, the 56 scalar columns below, `PrimaryCategory_Name`, `PrimaryCategory_BackgroundColor`, `empty_fields`. A scalar column name is the element name with a leading `OPFContactCopy` removed, else a leading `OPFContact` removed (`OPFContactCopyFirstName` becomes `FirstName`, `OPFContactExchangeID` becomes `ExchangeID`); if two names would collide, the verbatim element names are used. `empty_fields` lists scalar fields that are present but empty, since a blank cell cannot tell empty from absent. Presence is detected from the element itself: an element with no attributes yields an empty source value, and on the real layout, where every element carries `xml:space`, presence comes from that structural attribute (which stays structural and changes no counts). A present field is listed only if it had no content value at all, wherever that content went (cell, pictures or raw), so a field whose content went to raw is never called empty. Listed fields are joined with `; ` in column order. `ContactImage` is a scalar column, but a value that decodes as an image is a picture payload, not cell text (see Contact pictures).
  Scalar columns (closed list): CanDelete, CanEdit, Age, Anniversary, AssistantPhone, Birthday, BusinessCity, BusinessCompany, BusinessCountry, BusinessDepartment, BusinessFax, BusinessHomePage, BusinessOffice, BusinessPhone, BusinessPhone2, BusinessState, BusinessStreetAddress, BusinessTitle, BusinessZip, CellPhone, ContactImage, DisplayName, FirstName, FuriganaFirstName, FuriganaLastName, HomeCity, HomeCountry, HomeFax, HomePhone, HomePhone2, HomeState, HomeStreetAddress, HomeWebPage, HomeZip, LastName, MiddleName, ModDate, NickName, Notes, NotesPlain, OtherCity, OtherCountry, OtherPhone, OtherState, OtherStreetAddress, OtherZip, Pager, RadioPhone, SetNameSuffix, SpousesName, Title, ExchangeID, GetFlagStatus, IsJapaneseContact, MainPhone, Type.
  `PrimaryCategory_Name` and `PrimaryCategory_BackgroundColor` are the element text of the child elements `OPFCategoryCopyName` and `OPFCategoryCopyBackgroundColor` inside the container `OPFContactCopyPrimaryCategory`, which sits directly under `contact` (`/contacts/contact/OPFContactCopyPrimaryCategory[1]/OPFCategoryCopyName[1]`). Only the first container and the first child of each name are mapped; an empty element gives an empty cell. Any other occurrence or shape is an unknown field: a second container or child, an attribute, or text that follows a child element. Unlike `OPFContactCopyCategoryList/category`, where the same names are attributes, here they are elements.
- `contact_emails`: one row per `contactEmailAddress` element in any of six containers: `OPFContactCopyEmailAddressList`, `...List1`, `...List2`, `OPFContactCopyDefaultEmailAddress`, `OPFContactCopyIMAddressList`, `OPFContactCopyDefaultIMAddress`. Columns: `record_key`, `list_source` (container name, verbatim), `list_ordinal`, `Address`, `IsDefault`, `Type` (attribute values, verbatim). No de-duplication: E09 shows equal counts of default and list entries but no evidence that they are copies.
- `contact_categories`: one row per `category` under `OPFContactCopyCategoryList`. Columns: `record_key`, `ordinal`, `Name`, `BackgroundColor`.
- `contact_lists`: one row per `string` under `OPFContactCopyChildren` or `OPFContactCopyFuriganaChildrensNames`. Columns: `record_key`, `list_source`, `ordinal`, `value`.
- `contact_pictures`: see Contact pictures.
- `contact_long_text`: only when some text cell of a contacts-family sheet exceeds 32,000 UTF-16 units (scalar fields, email, category, list and picture-type values alike, so no single value can fail an archive). The main cell holds chunk 1 and this sheet holds chunks 2 to n (`record_key`, `field`, `chunk`, `value`), so main cell plus chunks reproduces the value exactly. `field` is the column name for `contacts` cells and `<sheet>/<list source>/<ordinal>/<column>` for child-sheet cells. The `categories` sheet uses `categories_long_text` (`record_key`, `source_member`, `ordinal`, `field`, `chunk`, `value`) the same way.
- `categories`: one row per `category` in a `categories-olm-v1` member. Columns: `record_key`, `source_member`, `ordinal`, `Name`, `BackgroundColor`. Unknown fields of a category (an extra attribute or child element) are raw rows carrying that category's `record_key`, so they join back to its row here.

Typing (ADR-011): every contact value is written as exact source text. Birthday, Anniversary and ModDate are not converted to Excel dates and have no parsed columns in v1.

Contact pictures (ADR-010): every `OPFContactAddPicture` text value directly under a contact is a picture, whatever its sibling index, and is a binary payload that is never written to cells or raw rows (02 non-goals), so it is never an unknown field. One `contact_pictures` row per picture: `record_key`, `picture_ordinal` (order of appearance within the contact), `type_declared`, `encoding` (`base64` if the value decodes strictly as base64, else `unknown`), `size_chars`, `decoded_bytes`, `detected_format` (from magic bytes only: no image library is used), `hash_basis` (`decoded_bytes`, or `text` when the encoding is unknown), `sha256`, `exported_file`, `source_element` (the verbatim element name: `OPFContactAddPicture`, or `OPFContactCopyContactImage` for a picture found in `ContactImage`).
- `type_declared` is the verbatim text of the contact's `OPFContactAddPictureType` values, collected at any index. It is set, and that type is mapped, only when the contact has exactly one picture and exactly one type. Otherwise `type_declared` is empty for every picture of that contact and every type value is an unknown field (raw, linked by `record_key`).
ContactImage (E12, content still unverified): `OPFContactCopyContactImage` is a plain text cell (`ContactImage`) unless a value is an image on strong evidence: it decodes strictly as base64 (the same rules as above) to at least 64 bytes with a PNG, JPEG, GIF, WebP or HEIC signature, or to a BMP whose header size matches its length. Short tokens whose first bytes merely resemble a magic number stay text. A value too large to decode counts as an image when a short base64 prefix shows one of those signatures. Every text value of the element is checked, at any sibling index or text position. Such a value is treated as a picture payload instead: the `ContactImage` cell stays empty and a `contact_pictures` row is written with `source_element` = `OPFContactCopyContactImage`, handled exactly like an `OPFContactAddPicture` (hash, size, detected format, export or `PICTURE_NOT_EXPORTED`). `picture_ordinal` follows document order across both elements. Its `type_declared` is always empty, and it does not change the pairing rule for `OPFContactAddPicture`. Any other value, such as a flag or an identifier, stays in the cell verbatim.
- Default: metadata only. The picture value is `lost` with reason `PICTURE_NOT_EXPORTED`, so the outcome is PARTIAL.
- Opt-in `export_images`: a picture that decodes is written as a separate file `<workbook stem>-pictures/<sha256 first 16 hex>.<ext>` next to the workbook (`ext` from the detected format, else `bin`; the full hash is used if two different images ever share the first 16 hex), content-addressed so identical images share one file and no source text becomes a path. The value is then `mapped`. A picture that does not decode is not exported and stays `lost`. Files are written to a temporary directory and moved into place only after the workbook verifies.

## XLSX delivery contract
Each XLSX includes `_manifest`, `_members` (one row per archive member: type, adapter, family, counts), `_warnings`, `_unsupported`, populated family/child sheets and, when raw values exist, `_raw_index` plus `raw_NNNN` partitions. Manifest contains input digest, run version, adapter versions, record counts seen/exported/failed/unsupported, source values mapped/structural/raw/lost with lost reason codes, structural declarations with consumed and failed counts, flags, coverage scope, truncation/overflow indexes and outcome.
- Sheet names <=31 chars, unique, deterministic, escaped.
- Excel per-sheet row cap 1,048,576; column cap 16,384; cell text cap 32,767 characters. Partition overflowing families into numbered sheets with manifest linking partitions.
- Preserve Unicode and literal leading whitespace; identifiers/phones/ZIP codes remain text. Protect values starting with = + - @ (and control/whitespace-prefixed variants) from execution by writing them as explicit string-typed cells, not by adding a prefix: the stored text must equal the source value exactly. Confirm behavior with the chosen Excel writer/reader rather than assuming it succeeds.
- No lossy type coercion. Long fields must use chunked sidecar sheets or clearly reported bounded truncation; silent truncation prohibited.
- Chunking rule: chunks are at most 32,000 UTF-16 code units (Excel counts UTF-16 units, not code points), never split a surrogate pair, and are ordered by `chunk`. The headroom below 32,767 is fixed so no later cell policy can push a chunk over the cap.
- Distinguish absent, empty, null-like, parse-failed and unsupported when available in source.
- Dates retain the original lexeme; no unverified timezone conversion. Contacts v1 stores dates as text only (ADR-011); a family that later adds parsed interpretation must keep the lexeme beside it.
- No macro content, formula generation or external hyperlinks generated from untrusted payload by default.

## Completeness contract (count-conserving, not semantic)
`seen = exported + failed + unsupported` at the agreed classification grain; per-family and per-record counters must reconcile, accounting for skipped nonrecords separately. Unknown archive members must be listed even if their semantics cannot be decoded. No blanket “all contents converted” promise when semantics are unknown.
Field-level count-conserving rule, per XML member and per family:
`source_values == mapped + structural + raw + lost`
Counts conserve source values; they do not prove semantic completeness. SUCCESS means every counted value was mapped or checked structural, never that every meaning was understood.
- `mapped`: the value contributes to at least one family or child-sheet cell; each source value counts once.
- `structural`: the value matched a structural declaration and passed its validator (see Structural values).
- `raw`: the value was written as a raw extract row (chunks count once).
- `lost`: neither; each lost value is counted with a reason code (`RAW_EXTRACT_DISABLED`, `RAW_EXTRACT_LIMIT`, `RECORD_PARSE_ERROR`, `EXCEL_LIMIT`, `PICTURE_NOT_EXPORTED`).
Outcome rule:
- SUCCESS requires the record-level equation to reconcile, `raw == 0` and `lost == 0` for every member, and every structural check passed, with no member `uncounted` and no unclaimed non-XML member.
- Otherwise the outcome is PARTIAL if at least one family was converted, UNSUPPORTED if none was (FAILED and CANCELLED keep their 02 meanings).
- `raw` and `lost` are properties of the source, so the outcome is the same with raw extract on or off.
A member whose values could not be counted (not walked after a limit, or parse stopped) is `uncounted` and can never contribute to SUCCESS. Non-XML members claimed by an adapter (for example attachment payloads referenced from records) are accounted at member grain; unclaimed non-XML members are inventoried in `_unsupported`.

## Batch delivery
Aggregate ZIP contains `manifest.json`, one deterministically named per-file workbook for each qualified downloadable result, optional per-file report JSON, opt-in contact picture files (ADR-010), and other extracted attachments only after explicit design approval. Name collision handling is stable and path-safe.

## Compatibility
Schema registry entries define exact fixtures and evidence, not universal claims. Contract changes to sheet names, columns, grain, interpretation or parser selection require versioning plus migration notes.
