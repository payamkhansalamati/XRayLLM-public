# Scientific protocol and implementation boundaries

## Fixed analysis sets

The primary analysis has eight endpoints and 20 fixed images (160 pairs).
Gemini 4 Neon and Claude Fable 5.2 are exploratory additions (40 pairs), not
members of the original primary analysis. The complete release roster and
maximum output-token schedules are in `config/models.yaml`. The matrix is
200 pairs; attempted, completed, and evaluable counts are separate quantities.
No ensemble majority vote or binary-caries task is part of these reported
per-model tooth metrics.

The v3 manifest fixes the recovered image bytes. Older difficulty-selection
history does not record a dataset version or conversion checksum, so the
release cannot establish byte identity with an older undocumented image run.
The current manifest should be used directly rather than regenerated with a
selector. Neither the original selector ranking nor its exact historical
inputs can be independently established from the available records.

## Scientific request

`src/protocol.py` contains the exact retained system prompt, historical user
prompt, and common JSON/no-findings instruction appended to that user prompt.
The combined user prompt is `PROMPT`; no private instructions or operational
notes are part of the scientific request.

| Component | SHA-256 of UTF-8 text |
|---|---|
| Combined user prompt | `82cf176707a47c03d4a679170af8684602decbec44c5db9572f429c7c046ba4f` |
| System prompt | `634ab5fb5f0c6b5bb3a03ff7fec4108c95250bebfd5ebfc293078a097db7f6d2` |

The system prompt is `You are a professional dental radiologist.` Requests
contain text and the original JPEG bytes as a base64 image data URL in the
same user message. Requested temperature is 0.3, timeout 180 seconds, and
initial evaluation cap 1,024 output tokens. No seed, reasoning effort,
provider pin, structured-output schema, or routing preference was set.
Provider defaults and reasoning-token use can therefore affect output length
and behavior. There is no guarantee that an alias resolves to immutable
weights or that requested temperature is honored.

The task asks for all suspicious pathology, including caries, apical lesions,
bone loss, root fracture, broken teeth, and other obvious issues. The requested
JSON fields are `problem_teeth`, `confidence`, and `rationale`. The prompt
allows a numeric confidence, while the retained validator requires an integer
0–100. This discrepancy is retained and documented rather than silently
changing historical eligibility.

## Pilot history and limitations

Original primary pilots used a generated 256-by-256 PNG with a blue triangle
and red circle. They had a visual-description phase and a study-prompt phase,
initially capped at 512 tokens. Hydrogen had two recorded study-prompt retries
at 1,024 tokens. Scout had a study-prompt retry adding the common structured
response instruction. The initial pilot prompt used slightly different
wording (`your JSON` versus `the JSON`) from the final evaluation prompt.
Those capability pilots are not evidence of dental performance.

The two exploratory pilots used 1,024 tokens and the common added instruction.
Their recorded pilot prompt inherits the initial pilot's wording difference.
The release pilot intentionally uses the final evaluation prompt for every
model and is a new, versioned capability check. It checks the four shape/color
words for the visual phase and schema-valid output for the study phase; an
unassessable synthetic image can pass the latter. These checks are limited
format/input tests, not proof that an endpoint reasons correctly about images.

## Actual evaluation and retry history

The original eight-model evaluation used 1,024 tokens. Its resume utility
retried failures at that cap and retained successful responses; it was not a
single-attempt experiment. A separate initial Astra failure retry also exists.
The primary checkpoint then underwent a truncation-only retry at 2,048 tokens
and a further truncation-only stage at 4,096. Each higher-cap stage allowed one
new attempt per eligible pair. Earlier responses and retry records remain
separate. The original main runner and its resume helper have different
selection details; the final combined checkpoint is authoritative for the
reported table.

The exploratory 1,024-token run stopped with four Neon truncations and one
pending Neon attempt; Fable was not attempted there. The 4,096-token continuation
attempted previously unattempted or originally truncated pairs and preserved
other original statuses, including the pending Neon pair. Neon then had nine
8,192-token truncation retries and three 16,384-token truncation retries.
The final selected Neon truncation can still point to a 4,096-token record
even after unsuccessful higher-cap retries: the historical selection rule
preserved the earlier truncation. Selection cap is not the latest attempted cap.

Historical stage totals, pilot caps, request errors, and incomplete attempts
must not be collapsed into a claim of a uniform ten-model experiment. All
aggregate results retain their original selected records and exclusions.

## Response validation and classification

Strict JSON parsing rejects Markdown fences and surrounding prose. The root
must be an object with a list of integer FDI numbers, integer confidence
0–100, and a nonempty rationale. Permanent teeth are restricted to quadrants
1–4 and positions 1–8; booleans are not valid integers. Duplicate tooth entries
are deduplicated for scoring. Additional object fields are permitted. The
historical JSON decoder accepts duplicate keys using Python's last-key rule;
this behavior is retained, not represented as full JSON-schema validation.

| Status | Meaning | Tooth scoring |
|---|---|---|
| `ASSESSABLE_FINDINGS` | Valid nonempty tooth list without detected unassessability wording | Included |
| `EXPLICIT_NO_FINDINGS` | Empty list with detected assessment and no-findings wording | Included as an empty prediction |
| `SEMANTIC_CONFLICT` | Nonempty list with detected unassessability wording | Excluded |
| `IMAGE_UNASSESSABLE` | Empty list with detected unassessability wording | Excluded |
| `EMPTY_FINDINGS_UNCLEAR` | Empty list without the required wording | Excluded |
| `truncated_output` | Provider finish reason reports a length limit | Excluded |
| `parse_failure`, `schema_failure`, `empty_response` | Unusable structured response | Excluded |
| `response_envelope_error`, `refusal` | Invalid envelope or explicit refusal | Excluded |
| `request_error`, `provider_error` | Transport/HTTP failure or provider error | Excluded |
| `in_flight`, `unattempted` | Initiated without a saved result, or no attempt | Excluded |

Classification is based on the regex rules in `src/protocol.py`, not a clinical
review of the rationale. For example, nonempty findings conflicting with a
no-pathology sentence are not detected unless the unassessability pattern
matches. Other semantic errors, contradictory statements, incorrect pathology
labels, and missing rationale references are not comprehensively checked.
A structurally valid response is not necessarily clinically accurate.

The release envelope assessor also recognizes `max_output_tokens` as a
truncation marker, as the saved retry assessors did. Some original initial
and resume paths recognized only `length` and `max_tokens`. Historical
checkpoints are verified against their recorded statuses without reclassifying
them under the newer assessor.

## Reference and metrics

For each image, reference set G is the union of valid permanent-tooth FDI
numbers extracted from all first-worksheet columns whose names end in
`Comment` (case-insensitive). Model prediction P is the structured tooth list.
This extraction is not a pathology-specific reference or a rationale-level
annotation. The separate workbook's existence does not establish clinical
adjudication, licensing, or annotation quality.

Within each evaluable model–image pair:

- TP = |P intersect G|; FP = |P minus G|; FN = |G minus P|.
- Micro precision = sum(TP) / [sum(TP) + sum(FP)].
- Micro recall = sum(TP) / [sum(TP) + sum(FN)].
- Micro F1 = 2 sum(TP) / [2 sum(TP) + sum(FP) + sum(FN)].
- Exact-match image accuracy = number of pairs where P equals G / evaluable pairs.

Undefined denominators yield null. Explicit no-findings responses stay in
scoring and can contribute FN. Other excluded responses do not contribute
FP or FN; they reduce coverage. Consequently models' reference-positive
and evaluable-image denominators differ. True negatives are not defined or
counted. Do not assume 32 teeth are visible and healthy in each cropped
radiograph. Tooth-level accuracy and specificity cannot be recovered from
these positive sets. Rationale-level statement accuracy was not scored.

## New-run execution guarantees

The release runner has engine version `release-1` and creates a new journal;
it is not a byte-for-byte replay of historical orchestration. It retains the
scientific prompt and scientific parsing/classification/metric functions.
It freezes metadata with a SHA-256 sidecar, validates image digests before
calls, writes a durable initiation marker before every possibly billable
request, and never automatically repeats an initiated request. No network
operation occurs without `--execute`. No SDK retry or fallback model is used.

Only a confirmed truncation may advance to the next configured cap; there
is one attempt per pair/cap, and each retry invocation advances one stage.
The first classified response is preserved, including classified but excluded
responses. Invalid, refused, failed, and pending attempts require inspection
and an explicitly separate run rather than automatic replay. These safety
constraints differ from the original primary resume utility's broader
failure retries and must be reported when conducting new experiments.
