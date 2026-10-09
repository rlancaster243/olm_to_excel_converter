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
