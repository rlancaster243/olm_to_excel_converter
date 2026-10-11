# 06 — Threat Model and Failure Semantics

Status: proposed safeguards; no security test has been performed.

## Assets and trust
Untrusted inputs: archives, member paths, XML, attachment data, filenames, claimed MIME and embedded spreadsheet-like strings.
Protected assets: local filesystem, memory/CPU, private mail/contact content, output integrity, logs and other users' jobs (if hosting is later added).

## Threat scenarios and proposed controls
| Threat | Control | Verification |
|---|---|---|
| ZIP slip/path traversal and symlinks | never extract to attacker-defined paths; normalize member names; reject absolute/../drive paths and links | traversal fixtures |
| ZIP bombs / high expansion ratio | cap total uncompressed bytes, per-member bytes, compression ratio, entry count and nesting depth | adversarial compression corpus |
| XML entities, external resource access, deep nesting | hardened XML parser; prohibit external entities/DTD as feasible; depth and node/size limits | XXE and deep XML fixtures |
| Huge single XML / pathological recursion | incremental parser + bounded buffers; stop on quota | memory profile |
| Formula injection in XLSX | write explicit string-typed cells so formula-like values stay inert without altering text (no prefixing); roundtrip with Excel library. Residual: re-saving the workbook as CSV can make such values live again | malicious-cell tests with exact text equality |
| Filename collisions / archive ordering | deterministic safe names, source-derived run identity, isolated job dirs | concurrent duplicate-name uploads |
| Sensitive content in logs | structured metadata-only logging; explicitly prohibit personal field values | log capture tests |
| Temp file leakage | isolated permissions, lifecycle cleanup, crash recovery janitor | aborted-run test |
| Damaged output mistaken for completed job | verify ZIP/XLSX integrity, counts before atomic publication | disk-full and interrupted-write tests |
| Unexpected host networking | offline default; dependency policy; scan for outbound calls | network-blocked integration tests |
| Malformed encodings and dates | retain original lexemes and mark undecodable data, no silent defaults | encoding corpus |
| Unsupported proprietary payload | mark UNSUPPORTED/PARTIAL and enumerate evidence | unknown-format tests |
| Raw extract row explosion (many tiny nodes) | `raw_extract_max_values` quota, partitioned sheets, stop with RAW_EXTRACT_LIMIT, never silent truncation | node-dense synthetic fixture |
| Raw output read as interpreted data | `raw_` sheet prefix, manifest flag, outcome never SUCCESS when any source value is raw or lost | workbook and UI warning tests |
| Adapter overstates its own coverage | core walker counts source values independently; adapters only report mapped ordinals | under-reporting adapter fixture |
| Record data hidden by declaring it structural | closed declarations in the registry with evidence; validators run by the core; per-declaration consumed and failed counts in `_manifest`; failed checks route to raw or lost | T26-T28: undeclared names never structural; bad values fail |
| Hostile picture payload (oversized, malformed, path-like) | pictures are only base64-decoded and magic-byte sniffed, never parsed with an image library; file names derive from the SHA-256, never from source text; size cap per picture; files written to a temporary directory and moved in only after workbook verification | hostile picture fixtures (T31) |
| Exported image files opened by other software | residual risk, declared: the tool never renders or executes images, but viewers may; files stay opt-in | documented limitation |

## Failure taxonomy
INPUT_INVALID, ARCHIVE_UNSAFE, RESOURCE_LIMIT, FORMAT_UNKNOWN, AMBIGUOUS_ADAPTER, RECORD_PARSE_ERROR, FIELD_LOSS_RISK, EXCEL_LIMIT, RAW_EXTRACT_LIMIT, RAW_EXTRACT_DISABLED, PICTURE_NOT_EXPORTED, STRUCTURAL_MISMATCH (warning), OUTPUT_IO, CANCELLED, INTERNAL_ERROR.
Errors must include stable code, scope (archive/member/record), recoverability, corrective action and safe metadata; no raw personal data.

## Recovery and containment
- Each archive is independently processed; one failure does not roll back verified sibling artifacts.
- A temporary workbook never becomes downloadable until integrity and counter reconciliation checks succeed.
- Cancellation stops at safe checkpoints and removes uncommitted artifacts.
- Retry rereads immutable input and records adapter/tool version; resumed work requires checkpoint semantics explicitly designed and tested.
- On quota exceed stop affected archive; preserve safe manifest; do not bypass limits to “complete” a batch.
- Failed cleanup is an observable exception and must trigger safe quarantine/cleanup routine.

## Residual risks / OPEN
Opaque or encrypted items, incorrect vendor assumptions, irreversible lossy conversions to finite Excel cells and malicious payloads not captured by tests. Declare protection limits rather than claiming comprehensive format support.
