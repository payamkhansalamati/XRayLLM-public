# Recorded study results

This aggregate snapshot was verified offline against the selected saved
responses. Counts are tooth-level micro totals; P, R, F1, and EM are
percentages. EM is complete image-level tooth-set agreement. Evaluable
subsets differ; scores must be interpreted alongside coverage.

| Model | Set | Evaluable | TP | FP | FN | P | R | F1 | EM |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-6.2 Astra | primary | 20/20 | 35 | 6 | 27 | 85.37 | 56.45 | 67.96 | 15.00 |
| GPT-6 Luna | primary | 19/20 | 25 | 15 | 33 | 62.50 | 43.10 | 51.02 | 10.53 |
| Claude Sonnet 5.5 | primary | 18/20 | 30 | 15 | 24 | 66.67 | 55.56 | 60.61 | 11.11 |
| Gemini 4 Carbon | primary | 19/20 | 37 | 10 | 23 | 78.72 | 61.67 | 69.16 | 15.79 |
| Gemini 4 Hydrogen | primary | 16/20 | 28 | 8 | 20 | 77.78 | 58.33 | 66.67 | 18.75 |
| Grok 4.20 | primary | 20/20 | 10 | 30 | 52 | 25.00 | 16.13 | 19.61 | 0.00 |
| Llama 4 Scout | primary | 16/20 | 6 | 10 | 47 | 37.50 | 11.32 | 17.39 | 0.00 |
| Llama 4 Maverick | primary | 20/20 | 19 | 26 | 43 | 42.22 | 30.65 | 35.51 | 5.00 |
| Gemini 4 Neon | exploratory | 17/20 | 30 | 8 | 25 | 78.95 | 54.55 | 64.52 | 17.65 |
| Claude Fable 5.2 | exploratory | 19/20 | 37 | 9 | 22 | 80.43 | 62.71 | 70.48 | 21.05 |

## Coverage from saved records

The matrix contains 200 planned pairs. All 200 have an initiation record;
199 have at least one saved HTTP/transport result. Initiation markers alone
do not establish request delivery. The journals contain 307 non-pilot
attempt records, including two unfinished markers, so 305 have saved results.
One unfinished marker is a Luna retry with an earlier completed truncation;
the other is Neon's only attempt for its pending image. Counts are records,
not an assertion about provider billing or successful model responses.

The final selected statuses contain 167 assessable findings responses and
17 explicit no-findings responses, totaling 184 evaluable pairs (148 primary,
36 exploratory). Exclusions are five truncations, four parse failures, four
semantic conflicts, two unclear empty lists, and one pending pair. There are
no wholly unattempted pairs in this snapshot.

## Snapshot identity

The following source checkpoints were read without modification. These
content digests identify the private input snapshots; the files themselves
and their underlying raw responses are not included in the public export.

| Analysis | Checkpoint timestamp (UTC) | SHA-256 |
|---|---|---|
| Primary | 2026-11-21T19:33:30.110430+00:00 | `f5823a402b38d3035670a0634f350e9d99306f23dbf74d8a573b4f629e7ae2a8` |
| Exploratory | 2026-11-21T20:46:55.549137+00:00 | `a8176dde530a65cbe85462979096cf12cbcffc8b230c1c0979d62817a22b3c9a` |

Tooth-level accuracy and specificity are unavailable because TN is not
defined. Rationale-level statement correctness was not scored. Reference
labels are extracted from a separate private annotation workbook, not
provided by the manifest. See [protocol](PROTOCOL.md) for exact definitions
and [reproducibility](REPRODUCIBILITY.md) for the distinction between
verifying saved scores and running a new hosted-model experiment.
