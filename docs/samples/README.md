# Synthetic OLM sample

**SYNTHETIC — not an Outlook for Mac export.** Do not treat `sample.olm` or its inner layout as ground truth for real OLM archives.

## Files

| File | Description |
|------|-------------|
| [sample.olm](sample.olm) | Synthetic contacts-only archive (ZIP format, `.olm` extension). |
| [make_olm20k.py](make_olm20k.py) | Script that generated `sample.olm`. |

## What is inside `sample.olm`

The archive is a ZIP with a **single** entry:

`Accounts/test@example.com/Address Book/Contacts.xml`

All **20,000** contacts live in that one XML file. The inner folder path is a **guess** aligned with assessment notes, not verified against Outlook.

## Limitations (explicit)

- Field name **`OPFContactCopyBusinessPhone`** (and other `OPFContactCopy*` names) are **unverified** against a real export.
- This sample does **not** exercise walking a real multi-folder OLM (mail, calendar, attachments, multiple accounts, or nested ZIP members beyond this one XML).
- An older **15-contact** generator **`make_olm.py`** existed in prior work and is **superseded** by `make_olm20k.py`; **`make_olm.py` is not shipped** in this repo.

## Synthetic vs real layout (finding #11)

- `make_olm20k.py` now emits `contactEmailAddress` (matching the E09 real layout's six `contactEmailAddress` containers); earlier revisions emitted `emailAddress`, which sent every sample email to raw and meant no mapped email had reached the writer on this fixture.
- The sample stays **DEFLATED** while the E09 real export stores members **uncompressed (STORED)**; compression differs, source-value counts do not (241,487 oracle unchanged).
