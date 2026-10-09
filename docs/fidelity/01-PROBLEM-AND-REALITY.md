# 01 — Problem Frame and Reality Audit

## Problem
Users have Outlook for Mac OLM archives and need structured Excel representations of their contents, including multiple files at once. A ZIP-looking archive does not imply a known XML schema, nor does a syntactically valid XLSX demonstrate complete or correct extraction.

## Desired outcomes
- User submits multiple OLM files; receives an XLSX per valid file and a downloadable batch ZIP.
- Every supported record family maps to stable, intelligible tables/sheets.
- Unknown records, unsupported types, field coercions and omissions are visible in a manifest.
- Partial success is distinguishable from full success, preserving recoverable output.
- Personal data is not needlessly uploaded, retained or logged.

## CURRENT — observed from repository artifacts, not runtime
- New standalone GitHub repo with architecture reports, synthetic generator, sample and frozen parent app snapshot.
- `docs/ASSESSMENT.md` documents a parent Streamlit monolith and proposed contact parser; it does not establish that this repo has working conversion code.
- Existing fixture is a ZIP with one guessed `Accounts/.../Address Book/Contacts.xml` and 20,000 synthetic contacts.
- Earlier benchmark (~6 s; ~297 MB RSS) pertains to a throwaway experiment, not a reproduced repo test.
- No real exported OLM schema is demonstrated by the fixture.

## TARGET — proposed
Independent Python core; bounded ingestion; introspection; versioned adapter registry; canonical typed record envelope; normalized family tables; streaming XLSX writer; batch orchestrator; local-first UI/CLI; structured diagnostics; privacy-aware operation.

## MIGRATION — proposed
Document assumptions; source real consented fixtures; classify OLM samples; implement safe archive listing; implement one proven end-to-end contact path; validate correctness; extend families; qualify batch; release.

## UNKNOWN / investigation register
| ID | Unknown | Why it matters | Evidence to resolve |
|---|---|---|---|
| U01 | Actual Outlook-for-Mac OLM container/path/namespaces/version variability | Parser feasibility and coverage | Multiple real exports from different supported Outlook versions |
| U02 | Definition of “full conversion” including mail, calendar, tasks, notes, groups, attachments | Scope and output contracts | Product acceptance decision + representative records |
| U03 | Sizes, ratios, nested archives, XML shape at realistic scale | Memory/resource safety | Sanitized large archives + measured runs |
| U04 | Privacy and retention requirements | Hosted vs local decision | Product/security owner signoff |
| U05 | Excel consumer expectations for multi-valued fields and dates | Sheet modeling | User-reviewed example workbooks |
| U06 | Whether password-protected/encrypted variants occur | Unsupported behavior | Real samples and documented format evidence |
| U07 | OLM identity stability across exports | Dedup and idempotency | Compare repeated exports of same source items |
| U08 | Target performance and maximum input size | Capacity guarantee | Benchmark workload + user SLO decision |

## Competing format hypotheses
H1: contact fields use predictable XML paths; H2: structure differs by version/account; H3: some payloads are opaque or binary; H4: archive contains unrelated files and nested containers. Falsify each against actual data, not guesses from filenames.

## Source authority
User-approved product requirements govern desired scope. Actual archive samples establish observed layout only for those variants. Existing assessment governs historical investigation, not future program invariants. No security assurance or performance SLO is confirmed by documentation alone.

## Next evidence acquisition
Gather permissioned, privacy-sanitized Outlook exports representing at least two application generations, one multi-account archive, one archive with each requested record family, one large archive, and deliberately corrupted/hostile fixtures. Retain fixture manifest (source app version, OS, export settings, rights, hashes, detected features). Use synthetic fixtures only for controlled failure cases.
