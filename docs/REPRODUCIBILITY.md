# Reproducibility and verification

## Reproduce software behavior offline

The README quick start installs one exact-version dependency and runs the
synthetic smoke test, roster/manifest planning, and standard-library tests.
No original images, workbook, provider records, or credentials are required.
For local formatting/lint checks, install `requirements-dev.txt`, then run
`python -m ruff check src tests tools` and
`python -m ruff format --check src tests tools`.
Tests generate their own synthetic bytes, PNG, XLSX, and response envelopes.
The test transport never sends a request to a model.

The tests cover fixed manifest membership, digest mismatches, invalid paths,
XLSX reference extraction, strict response parsing, all scientific response
classes, envelope errors, truncation, refusal, metric denominators, duplicate
teeth, explicit negative predictions, interrupted journals, concurrent locks,
changed metadata, stage ceilings, and successful-response preservation.

Installation uses `requirements.txt` (PyYAML 6.0.3). Python 3.11–3.13 is the
supported range; CI declares all three. Hosting aliases, provider routing,
reasoning defaults, image processing at the provider, and network delivery
are not controlled by the local dependency pin.

## Verify actual inputs

Acquire the official ZIP using [data instructions](../data/README.md), then
run `acquire` and `verify`. Verification compares all 20 original JPEG
SHA-256 digests against `data/study_manifest.csv`. It does not certify privacy,
clinical quality, the validity of the labels, or the provenance of an older
undocumented sample-selection run.

Provide an authorized annotation workbook and run `verify --annotations`.
The release reader checks required identifiers and duplicate rows. Initialize
a new run only after the synthetic capability pilots pass. Preserve `run.json`,
`run.sha256`, each response-stage file, and each score snapshot together.

## Verify the recorded study without changing its rules

The recorded study used older directory layouts. Its two final combined
checkpoints select the authoritative response for each of 200 pairs. The
release verifier reads those selections rather than selecting newer responses,
changing classifications, or writing back scores. With authorized local copies:

```bash
python -m src.study verify-checkpoints \
  --checkpoint PRIVATE_PRIMARY_COMBINED_JSON \
  --checkpoint PRIVATE_EXPLORATORY_COMBINED_JSON \
  --record-root PRIVATE_RECORD_ROOT
```

`PRIVATE_RECORD_ROOT` is the directory against which selected relative record
paths resolve. The verifier checks source identity, saved status, predictions,
per-pair counts, and aggregate metrics. It emits source-file digests, coverage,
metrics, and status distributions without emitting clinical rationales or
credentials. Missing source files and mismatched counts fail verification.
The command does not make network requests or overwrite either checkpoint.

The recorded metrics cannot be independently reproduced from a code-only
release: the annotation workbook and selected responses are currently private.
The release therefore distinguishes software reproducibility, verified data
selection, verification of existing scores, and a new hosted-model evaluation.
These are separate levels of evidence. Annotation/output access and rights
must be resolved before claiming fully independent reproduction of the
reported numerical results.

## Export and scan the public source

```bash
python tools/export_release.py --destination output/public-release-candidate
python tools/audit_release.py output/public-release-candidate
```

Export refuses an existing destination. Use a new directory for each revision.
Only files explicitly named in `release-files.txt` are copied; Git metadata,
local research scripts, images, labels, raw responses, workbooks, private
reports, and generated scientific tables are excluded. `RELEASE_SHA256.json`
records the exported file contents. The exporter scans for common credential
formats, personal paths, embedded dialogue markers, symlinks, and disallowed
artifacts. It does not claim to detect every secret or every privacy issue;
a human review is still required.

For the source repository's locally reachable history, a separate read-only
audit is available. Its JSON reports locations and commit IDs, never matching
credential values:

```bash
python tools/audit_release.py . --history > output/history-audit.json
```

A nonzero exit indicates findings. This audit examines all locally available
refs, including non-branch refs, but cannot inspect remote-only refs, forks,
external caches, or confirm credential revocation. `.gitignore` affects future
adds, not already reachable Git objects. Publishing the existing repository
requires a separate reviewed history-cleaning operation or a new repository
containing only the clean export.
