# XRayLLM

XRayLLM evaluates vision-language models on a fixed set of 20 DenPAR v3
intraoral periapical radiographs. The study contains eight primary models
and two exploratory additions: **200 planned model–image pairs**. The task
is to identify problematic teeth using permanent-tooth FDI numbers.

The release pipeline provides verified image manifests, the scientific
prompt, explicit response classifications, resumable request journals,
and offline tooth-level scoring. It does not measure clinical diagnostic
accuracy or the correctness of individual rationale statements.

## Quick start without credentials or clinical data

Use Python 3.11–3.13. Run commands from the repository root.

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
python -m src.study smoke
python -m src.study plan
python -m unittest discover -s tests -v
```

`smoke` uses synthetic responses and a generated shapes image, makes no
network requests, and requires no credentials. `plan` validates the model
roster and metadata-only manifest and reports 200 planned pairs; it does
not verify the image bytes until the images have been acquired.

## Models and recorded coverage

| Model | Endpoint ID | Analysis set | Evaluable images |
|---|---|---|---:|
| GPT-6.2 Astra | `openai/gpt-6.2-astra` | Primary | 20/20 |
| GPT-6 Luna | `openai/gpt-6-luna` | Primary | 19/20 |
| Claude Sonnet 5.5 | `anthropic/claude-sonnet-5.5` | Primary | 18/20 |
| Gemini 4 Carbon | `google/gemini-4-carbon` | Primary | 19/20 |
| Gemini 4 Hydrogen | `google/gemini-4-hydrogen` | Primary | 16/20 |
| Grok 4.20 | `x-ai/grok-4.20` | Primary | 20/20 |
| Llama 4 Scout | `meta-llama/llama-4-scout` | Primary | 16/20 |
| Llama 4 Maverick | `meta-llama/llama-4-maverick` | Primary | 20/20 |
| Gemini 4 Neon | `google/gemini-4-neon` | Exploratory | 17/20 |
| Claude Fable 5.2 | `anthropic/claude-fable-5.2` | Exploratory | 19/20 |

The recorded snapshot has 200 pairs with an initiation record, 199 pairs
with a saved HTTP/transport result, and **184 evaluable pairs** (148 primary,
36 exploratory). An initiation marker alone does not prove delivery or
billing. Coverage and scores come from saved records, not from treating
all planned requests as successful. See [recorded results](docs/STUDY_RESULTS.md).

## Data and configuration

Radiographs, annotation workbooks, raw responses, and manuscript files are
not included. Obtain DenPAR v3 from its [official Zenodo record](https://zenodo.org/records/16645076),
and follow [data acquisition and rights](data/README.md). The metadata-only
`data/study_manifest.csv` specifies the 20 archive members and their SHA-256
digests. The separate study annotation workbook is required for an actual
evaluation; the DenPAR download does not supply that workbook.

```bash
cp .env.example .env
# Set local paths and, only for paid calls, OPENROUTER_API_KEY in .env.
python -m src.study acquire --archive data/private/denpar-v3.zip
python -m src.study verify --annotations data/private/Dentist_Comments_MERGED.xlsx
```

Environment variables are documented in `.env.example`. Explicit CLI paths
override defaults; shell variables take precedence over `.env`. The loader
supports simple `KEY=value` entries and does not execute shell expressions.
Top-level options `--models` and `--manifest` must precede the subcommand.

## Pilot, evaluate, resume, retry, and score

The release runner creates new, separately versioned runs. It does not
resume or alter the original study's private journals. Its safety behavior
and the recorded historical deviations are described in the [protocol](docs/PROTOCOL.md).

```bash
# Offline pilot plan: generates a synthetic image and reports missing calls.
python -m src.study pilot --output output/pilot-new

# PAID: up to 20 initial synthetic pilot requests. Inspect the saved responses.
python -m src.study pilot --output output/pilot-new --execute

# Offline initialization: verifies images, annotations, and passing pilots.
# Refuses to overwrite an existing run directory.
python -m src.study init --run output/study-new --pilot-dir output/pilot-new

# Offline plan; no API calls.
python -m src.study evaluate --run output/study-new

# PAID: one initial request per previously unattempted pair.
python -m src.study evaluate --run output/study-new --execute

# PAID: resume the same command; existing attempts are preserved and skipped.
python -m src.study evaluate --run output/study-new --execute

# Offline retry plan.
python -m src.study retry --run output/study-new

# PAID: one next-cap attempt for each eligible truncated pair.
python -m src.study retry --run output/study-new --execute

# Offline scoring. Use a NEW filename to preserve prior score snapshots.
python -m src.study score --run output/study-new > output/study-new/metrics.json
```

A pilot directory is immutable per model/phase: failed or interrupted pilots
are not automatically repeated. To test a documented higher cap, use a new
pilot directory and `--cap 4096`; record the resulting pilot provenance.
Each retry invocation advances at most one permitted cap per eligible pair.
The primary cap sequence is 1,024 → 2,048 → 4,096. Neon uses 1,024 → 4,096 →
8,192 → 16,384; Fable uses 1,024 → 4,096. The schedules specify maximum stages,
not evidence that all stages occurred in the saved study.

Run metadata freezes the roster, prompts, settings, annotation digest,
reference sets, and image hashes. Resume checks the frozen metadata and
image bytes. Completed successes, invalid responses, and interrupted
`in_flight` markers are never automatically re-requested. Only confirmed
truncations are eligible for a higher-cap retry. Provider/request errors
stop that execution and return exit status 1; input errors return status 2. Inspect uncertain delivery before planning a separate
run; do not delete records to force retries.

A `.lock` prevents concurrent writers. After an unclean process termination,
confirm no process is running and inspect pending records before removing
only the stale `.lock`. Pending attempt records must remain intact.

## Outputs and interpretation

`output/study-new/run.json` and `run.sha256` contain the frozen protocol and
reference; `responses/<model>/<image>/<cap>.json` contains each request stage,
its response, classification, settings, and usage when available. Outputs
are private by default. `score` prints JSON with coverage, per-model micro
TP/FP/FN, precision, recall, F1, and exact-match image accuracy. Undefined
metrics are `null`, not zero.

The scoring unit is a tooth within an evaluable model–image pair. Explicit
no-findings responses contribute missed reference teeth as FN. Missing,
truncated, invalid, conflicting, unclear, and unassessable responses are
excluded from tooth scoring and reported in coverage. No true-negative
universe is defined, so tooth-level accuracy and specificity are unavailable.
Exact-match image accuracy is a different measure. Models have differing
evaluable subsets; the table is not a controlled common-subset ranking.

The sample is small and selected, reference labels are extracted from free
text, classification uses wording heuristics, output caps vary, and endpoint
routing/default reasoning may change. Requested temperature is not proof of
effective sampling temperature. See [protocol and limitations](docs/PROTOCOL.md).

## Repository layout

```text
config/models.yaml       Ten saved endpoint IDs, analysis sets, token schedules
src/protocol.py          Exact scientific prompt and retained scoring rules
src/study_io.py          Portable configuration, XLSX reader, input verification
src/evaluation.py        Response assessment, journals, retry policy, metrics
src/study.py             CLI for offline checks and explicitly enabled API calls
src/synthetic.py         Synthetic capability-pilot image generator
data/study_manifest.csv Metadata only; no radiograph pixels or clinical labels
tests/                   Synthetic offline tests
docs/                    Protocol, results, rights, and release documentation
tools/                   Safe source export and public-material audits
output/                  Local private runs; excluded from the public export
```

The public source export is defined by `release-files.txt`. Older local
selection, binary-caries, and spreadsheet-ensemble utilities are outside this
release workflow and are not needed to reproduce its scoring implementation.

## Container and verification

```bash
docker build -t xrayllm .
docker run --rm xrayllm smoke
```

The container defaults to an offline check and copies only public code,
configuration, and the metadata manifest. It never copies local data
or `.env`. Live Docker execution requires explicit mounted data/output
paths, a runtime environment file, and `--execute`.

Offline CI covers Python 3.11–3.13. See [reproducibility checks](docs/REPRODUCIBILITY.md)
and [release procedure](docs/RELEASE.md). Project code is licensed under
the [MIT License](LICENSE). Dataset and annotation rights are separate; see
[third-party notices](docs/THIRD_PARTY.md). Publishing still requires the
security and reproducibility gates described in the release procedure.
