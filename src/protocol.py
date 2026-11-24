"""Scientific prompt, validation, classification, and metrics for the fixed study.

The extraction and classification rules are retained from the recorded protocol.
They are heuristic rules, not a clinical rationale-validation rubric.
"""

import json
import re


SYSTEM_PROMPT = "You are a professional dental radiologist."

REVISED_INSTRUCTION = (
    "Return exactly one JSON object with `problem_teeth`, `confidence`, and a non-empty "
    "`rationale`. Do not include prose outside the object or wrap it in Markdown. "
    "If you report no findings, use an empty `problem_teeth` list and explain your answer "
    "in `rationale`. If the image cannot be assessed, state that explicitly in `rationale`."
)

HISTORICAL_PROMPT = (
    "You are an experienced dental radiologist. You are given a single periapical X-ray image. "
    "Identify all teeth that show ANY suspicious pathology, including caries, apical lesions, "
    "vertical or horizontal bone loss, root fracture, broken tooth, or other obvious issues. "
    "Use the FDI notation for tooth numbers (e.g. 11, 21, 36, 46).\n\n"
    "Return your answer ONLY as strict JSON with the following keys:\n"
    '  - "problem_teeth": a list of tooth numbers as integers, e.g. [11, 21, 46]. '
    "If you see no problems, use an empty list []. Do NOT use placeholders or empty entries.\n"
    '  - "confidence": a number between 0 and 100 expressing your overall confidence.\n'
    '  - "rationale": 2–3 sentences that clearly mention each suspicious tooth by its FDI '
    "number and describe the suspected problem (e.g. caries, apical lesion, bone loss).\n\n"
    "VERY IMPORTANT:\n"
    "  - Always return VALID JSON.\n"
    "  - Do NOT wrap the JSON in ``` fences.\n"
    '  - Do NOT use template text like "Tooth  shows...". If you are unsure about a tooth, '
    "    simply omit it from problem_teeth.\n"
    "Do NOT include any text outside the JSON."
)

PROMPT = HISTORICAL_PROMPT + "\n\n" + REVISED_INSTRUCTION

FDI_PATTERN = re.compile(r"\b(\d{2})\b")

UNASSESSABLE_PATTERN = re.compile(
    r"\b(cannot|can't|unable|impossible|not possible|not assessable|"
    r"unassessable|cannot reliably|insufficient)\b.{0,80}\b"
    r"(assess|evaluate|interpret|determine|image|radiograph|radiographic|"
    r"visibility|quality|teeth|structures|findings|see|view|visualize)\b|"
    r"\b(no|not enough|lack of)\b.{0,50}\b"
    r"(visible teeth|dental structures|radiographic anatomy)\b",
    re.IGNORECASE,
)

NO_FINDINGS_PATTERN = re.compile(
    r"\b(no|without|none|negative for)\b.{0,50}\b"
    r"(suspicious findings|pathology|abnormalit(?:y|ies)|"
    r"caries|lesions|obvious issues)\b|"
    r"\b(normal|unremarkable|healthy)\b.{0,40}\b"
    r"(radiograph|image|teeth|dentition|findings)\b",
    re.IGNORECASE,
)

ASSESSMENT_PATTERN = re.compile(
    r"\b(assessed|evaluated|examined|reviewed|visible|see|seen|"
    r"observed|identified|detected|noted)\b",
    re.IGNORECASE,
)


def _extract_fdi(text: str) -> set[int]:
    teeth = set()
    for token in FDI_PATTERN.findall(text):
        tooth = int(token)
        quadrant, position = divmod(tooth, 10)
        if 1 <= quadrant <= 4 and 1 <= position <= 8:
            teeth.add(tooth)
    return teeth


def _validate_response(text: str) -> tuple[str, dict | None, str]:
    if not text.strip():
        return "empty_response", None, "Assistant response has no text content."
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        return "parse_failure", None, f"Strict JSON parsing failed: {error}"
    if not isinstance(parsed, dict):
        return (
            "schema_failure",
            None,
            f"Expected one JSON object; received {type(parsed).__name__}.",
        )
    teeth = parsed.get("problem_teeth")
    confidence = parsed.get("confidence")
    rationale = parsed.get("rationale")
    if (
        not isinstance(teeth, list)
        or any(type(tooth) is not int for tooth in teeth)
        or any(not (1 <= tooth // 10 <= 4 and 1 <= tooth % 10 <= 8) for tooth in teeth)
        or type(confidence) is not int
        or not 0 <= confidence <= 100
        or not isinstance(rationale, str)
        or not rationale.strip()
    ):
        return (
            "schema_failure",
            parsed,
            "Require a valid FDI integer list, integer confidence 0–100, and non-empty rationale.",
        )
    return "valid_response", parsed, "Response is one strict JSON object with required fields."


def _classify_response(parsed: dict) -> tuple[str, str]:
    teeth = parsed["problem_teeth"]
    rationale = parsed["rationale"]
    if not teeth:
        if UNASSESSABLE_PATTERN.search(rationale):
            return (
                "IMAGE_UNASSESSABLE",
                "Explicit unassessability; not a negative finding and excluded from accuracy denominators.",
            )
        if NO_FINDINGS_PATTERN.search(rationale) and ASSESSMENT_PATTERN.search(rationale):
            return (
                "EXPLICIT_NO_FINDINGS",
                "Rationale explicitly indicates assessment and no findings; empty tooth set remains a prediction.",
            )
        return (
            "EMPTY_FINDINGS_UNCLEAR",
            "Empty list without explicit assessment and no-findings wording; excluded.",
        )
    if UNASSESSABLE_PATTERN.search(rationale):
        return (
            "SEMANTIC_CONFLICT",
            "Non-empty tooth list conflicts with rationale stating the image cannot be assessed.",
        )
    return (
        "ASSESSABLE_FINDINGS",
        "Valid non-empty tooth findings with no unassessability statement.",
    )


def _response_text(envelope: dict) -> tuple[str, str | None, str | None]:
    if not isinstance(envelope, dict):
        return "", "Response envelope is not a JSON object.", None
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", "Response envelope has no valid choices list.", None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return "", "Response envelope choice has no valid message object.", None
    if message.get("refusal"):
        return "", None, str(message["refusal"])
    content = message.get("content")
    if isinstance(content, str):
        return content, None, None
    if isinstance(content, list):
        return (
            "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ),
            None,
            None,
        )
    return "", None, None


def _metric(tp: int, fp: int, fn: int) -> dict:
    precision_denominator = tp + fp
    recall_denominator = tp + fn
    f1_denominator = 2 * tp + fp + fn
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision_numerator": tp,
        "precision_denominator": precision_denominator,
        "precision": tp / precision_denominator if precision_denominator else None,
        "recall_numerator": tp,
        "recall_denominator": recall_denominator,
        "recall": tp / recall_denominator if recall_denominator else None,
        "f1_numerator": 2 * tp,
        "f1_denominator": f1_denominator,
        "f1": 2 * tp / f1_denominator if f1_denominator else None,
    }


EVALUABLE = frozenset({"ASSESSABLE_FINDINGS", "EXPLICIT_NO_FINDINGS"})
