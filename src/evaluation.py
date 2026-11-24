"""Offline scoring and immutable per-stage execution journals for new runs."""

import json
import os
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import protocol
from .study_io import digest, load_manifest, load_models, load_reference, request

ENGINE_VERSION = "release-1"
CLASSIFIED = protocol.EVALUABLE | {
    "SEMANTIC_CONFLICT",
    "IMAGE_UNASSESSABLE",
    "EMPTY_FINDINGS_UNCLEAR",
}


class ExecutionStopped(RuntimeError):
    """A failed request was saved and execution stopped without automatic retry."""

    def __init__(self, calls_made):
        super().__init__(
            "Request/provider failure saved; inspect the private record before resuming."
        )
        self.calls_made = calls_made


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def finish_record(path, value):
    temp = path.with_suffix(".tmp")
    write_new(temp, value)
    temp.replace(path)


@contextmanager
def run_lock(run):
    """Fail closed after interruption; a stale lock requires operator inspection."""
    path = run / ".lock"
    try:
        handle = path.open("x")
    except FileExistsError as error:
        raise ValueError(
            "Run is locked. Inspect active processes and pending records before removing .lock."
        ) from error
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        path.unlink()


def assess(response):
    if response.get("http_status") != 200:
        return {"status": "request_error"}
    try:
        envelope = json.loads(response.get("body", ""))
    except (ValueError, TypeError):
        return {"status": "response_envelope_error"}
    if not isinstance(envelope, dict):
        return {"status": "response_envelope_error"}
    if envelope.get("error"):
        return {"status": "provider_error"}
    text, envelope_error, refusal = protocol._response_text(envelope)
    if envelope_error:
        return {"status": "response_envelope_error"}
    if refusal:
        return {"status": "refusal"}
    choice = envelope["choices"][0]
    details = {
        "raw_response_text": text,
        "finish_reason": choice.get("finish_reason"),
        "native_finish_reason": choice.get("native_finish_reason"),
        "provider": envelope.get("provider"),
        "usage": envelope.get("usage"),
    }
    if any(
        str(choice.get(k) or "").lower() in {"length", "max_tokens", "max_output_tokens"}
        for k in ("finish_reason", "native_finish_reason")
    ):
        return {"status": "truncated_output", **details}
    validation, parsed, reason = protocol._validate_response(text)
    if validation != "valid_response":
        return {"status": validation, "reason": reason, **details}
    status, reason = protocol._classify_response(parsed)
    return {
        "status": status,
        "reason": reason,
        "parsed_response": parsed,
        "validation_status": validation,
        **details,
    }


def metrics_for_pairs(pairs):
    """Count each tooth once per image; exclude nonevaluable pairs explicitly."""
    tp = fp = fn = exact = n = 0
    for row in pairs:
        if row["status"] not in protocol.EVALUABLE:
            continue
        predicted, reference = set(row["predicted_teeth"]), set(row["reference_teeth"])
        tp += len(predicted & reference)
        fp += len(predicted - reference)
        fn += len(reference - predicted)
        exact += predicted == reference
        n += 1
    return {
        **protocol._metric(tp, fp, fn),
        "evaluable": n,
        "exact_match_images": exact,
        "exact_match_accuracy": exact / n if n else None,
        "tooth_accuracy": None,
        "true_negatives": None,
    }


def initialize(run, models_path, manifest_path, images_dir, annotations, pilot_proofs=None):
    models = load_models(models_path)
    images = load_manifest(manifest_path, images_dir)
    reference = load_reference(annotations)
    manifest = {
        "engine_version": ENGINE_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "models": models,
        "images": images,
        "reference": reference,
        "annotation_sha256": digest(annotations),
        "system_prompt": protocol.SYSTEM_PROMPT,
        "user_prompt": protocol.PROMPT,
        "temperature": 0.3,
        "timeout_seconds": 180,
        "retry_rule": "one attempt at each higher cap; only truncated responses eligible",
        "selection_rule": "first classified response; otherwise retain prior truncation",
        "reference_rule": "union of valid permanent FDI numbers in comment columns",
        "pilot_records_sha256": pilot_proofs or {},
    }
    run.mkdir(parents=True, exist_ok=False)
    write_new(run / "run.json", manifest)
    (run / "run.sha256").write_text(digest(run / "run.json") + "\n")
    return manifest


def read_run(run, images_dir=None):
    if (run / "run.sha256").read_text().strip() != digest(run / "run.json"):
        raise ValueError(
            "Frozen run manifest changed; restore its original content or initialize a separate run."
        )
    manifest = read_json(run / "run.json")
    if (
        manifest.get("engine_version") != ENGINE_VERSION
        or manifest.get("user_prompt") != protocol.PROMPT
        or manifest.get("system_prompt") != protocol.SYSTEM_PROMPT
    ):
        raise ValueError("Run engine or scientific prompt differs; use its original version.")
    if images_dir is not None:
        for image in manifest["images"]:
            path = images_dir / image["filename"]
            if not path.is_file() or digest(path) != image["image_sha256"]:
                raise ValueError("Image missing or changed; no requests sent.")
    return manifest


def record_path(run, model, filename, cap):
    return run / "responses" / model.replace("/", "_") / filename / f"{cap}.json"


def select_attempt(attempts):
    """Freeze the first classified response; never replace it with a retry."""
    selected = None
    for attempt in attempts:
        if selected is not None and selected["status"] in CLASSIFIED:
            break
        if selected is None or attempt["status"] in CLASSIFIED:
            selected = attempt
    return selected


def attempts_for(run, manifest, model, image):
    attempts = []
    for cap in model["token_caps"]:
        path = record_path(run, model["id"], image["filename"], cap)
        if not path.is_file():
            continue
        record = read_json(path)
        if (
            record.get("model") != model["id"]
            or record.get("image_filename") != image["filename"]
            or record.get("image_sha256") != image["image_sha256"]
            or record.get("settings")
            != {
                "temperature": manifest["temperature"],
                "max_tokens": cap,
                "timeout_seconds": manifest["timeout_seconds"],
            }
            or record.get("user_prompt") != manifest["user_prompt"]
            or record.get("system_prompt") != manifest["system_prompt"]
        ):
            raise ValueError("Saved attempt identity or settings differ from run manifest.")
        attempts.append(record)
    return attempts


def next_cap(attempts, caps, retry=False):
    if not attempts:
        return None if retry else caps[0]
    if not retry:
        return None  # Resume never repeats an initiated request, including pending attempts.
    selected = select_attempt(attempts)
    if selected["status"] != "truncated_output" or attempts[-1]["status"] != "truncated_output":
        return None
    last = attempts[-1]["settings"]["max_tokens"]
    return next((cap for cap in caps if cap > last), None)


def execute(run, images_dir, key, retry=False, transport=request):
    with run_lock(run):
        manifest = read_run(run, images_dir)
        count = 0
        for model in manifest["models"]:
            for image in manifest["images"]:
                attempts = attempts_for(run, manifest, model, image)
                cap = next_cap(attempts, model["token_caps"], retry)
                if cap is None:
                    continue
                path = record_path(run, model["id"], image["filename"], cap)
                record = {
                    "model": model["id"],
                    "image_filename": image["filename"],
                    "image_sha256": image["image_sha256"],
                    "started_at_utc": datetime.now(timezone.utc).isoformat(),
                    "system_prompt": manifest["system_prompt"],
                    "user_prompt": manifest["user_prompt"],
                    "settings": {
                        "temperature": manifest["temperature"],
                        "max_tokens": cap,
                        "timeout_seconds": manifest["timeout_seconds"],
                    },
                    "status": "in_flight",
                }
                write_new(path, record)  # Durable marker before the possibly billable operation.
                response = transport(
                    model["id"],
                    images_dir / image["filename"],
                    key,
                    manifest["user_prompt"],
                    manifest["system_prompt"],
                    cap,
                    manifest["temperature"],
                    manifest["timeout_seconds"],
                )
                record.update(
                    http_response=response,
                    **assess(response),
                    completed_at_utc=datetime.now(timezone.utc).isoformat(),
                )
                finish_record(path, record)
                count += 1
                if record["status"] in {"request_error", "provider_error"}:
                    raise ExecutionStopped(count)
        return count


def score_run(run):
    manifest = read_run(run)
    pairs = []
    initiated = completed = 0
    for model in manifest["models"]:
        for image in manifest["images"]:
            attempts = attempts_for(run, manifest, model, image)
            initiated += bool(attempts)
            completed += any("http_response" in a for a in attempts)
            selected = select_attempt(attempts)
            row = {
                "model": model["id"],
                "image_filename": image["filename"],
                "status": selected["status"] if selected else "unattempted",
                "predicted_teeth": None,
                "reference_teeth": manifest["reference"][image["picture_number"]],
            }
            if selected and selected["status"] in protocol.EVALUABLE:
                row["predicted_teeth"] = selected["parsed_response"]["problem_teeth"]
            pairs.append(row)
    return {
        "planned_pairs": len(pairs),
        "initiated_pairs": initiated,
        "completed_pairs": completed,
        "evaluable_pairs": sum(r["status"] in protocol.EVALUABLE for r in pairs),
        "models": {
            m["id"]: {
                "name": m["name"],
                "analysis_set": m["analysis_set"],
                "statuses": dict(Counter(r["status"] for r in pairs if r["model"] == m["id"])),
                **metrics_for_pairs([r for r in pairs if r["model"] == m["id"]]),
            }
            for m in manifest["models"]
        },
        "pairs": pairs,
    }


def verify_checkpoint(paths, record_root):
    """Verify published selection rules without reselecting or rewriting old records."""
    pairs, provenance = [], []
    seen = set()
    for path in paths:
        checkpoint = read_json(path)
        provenance.append(
            {
                "filename": path.name,
                "sha256": digest(path),
                "updated_at_utc": checkpoint.get("updated_at_utc"),
            }
        )
        rows = checkpoint.get("rows", checkpoint.get("pairs"))
        if not isinstance(rows, list):
            raise ValueError("Checkpoint requires rows or pairs.")
        for row in rows:
            raw = None
            identity = (row["model"], row["image_filename"])
            if identity in seen:
                raise ValueError("Duplicate model-image pair in checkpoints.")
            seen.add(identity)
            status = row.get("selected_status", row.get("status"))
            if row["evaluable"] != (status in protocol.EVALUABLE):
                raise ValueError("Checkpoint evaluability conflicts with recorded classification.")
            relative = row.get("selected_record_path", row.get("selected_record"))
            if relative:
                source = (record_root / relative).resolve()
                if not source.is_relative_to(record_root.resolve()):
                    raise ValueError("Record path escapes the configured record root.")
                raw = read_json(source)
                if (
                    raw.get("model") != row["model"]
                    or raw.get("image_filename") != row["image_filename"]
                    or raw.get("status") != status
                ):
                    raise ValueError("Selected record does not match checkpoint identity/status.")
            elif row["evaluable"]:
                raise ValueError("Evaluable checkpoint row lacks a selected source record.")
            if row["evaluable"]:
                predicted = sorted(set(raw["parsed_response"]["problem_teeth"]))
                reference = sorted(set(row["reference_teeth"]))
                if predicted != sorted(row["predicted_teeth"]):
                    raise ValueError("Selected prediction differs from checkpoint.")
                counts = (
                    len(set(predicted) & set(reference)),
                    len(set(predicted) - set(reference)),
                    len(set(reference) - set(predicted)),
                )
                if counts != (row["tp"], row["fp"], row["fn"]):
                    raise ValueError("Saved tooth counts differ from selected source sets.")
            pairs.append(
                {
                    "model": row["model"],
                    "image_filename": row["image_filename"],
                    "status": status,
                    "predicted_teeth": row["predicted_teeth"],
                    "reference_teeth": row["reference_teeth"],
                    "initiated": bool(relative),
                    "selected_response_saved": bool(raw and "http_response" in raw),
                }
            )
        for model, saved in checkpoint["models"].items():
            calculated = metrics_for_pairs([r for r in pairs if r["model"] == model])
            for key in ("tp", "fp", "fn", "precision", "recall", "f1"):
                if calculated[key] != saved["tooth_metrics_micro"][key]:
                    raise ValueError(f"Checkpoint metric mismatch for {model}: {key}.")
    return {
        "source_checkpoints": provenance,
        "planned_pairs": len(pairs),
        "initiated_pairs": sum(r["initiated"] for r in pairs),
        "selected_response_pairs": sum(r["selected_response_saved"] for r in pairs),
        "evaluable_pairs": sum(r["status"] in protocol.EVALUABLE for r in pairs),
        "models": {
            m: {
                "statuses": dict(Counter(r["status"] for r in pairs if r["model"] == m)),
                **metrics_for_pairs([r for r in pairs if r["model"] == m]),
            }
            for m in dict.fromkeys(r["model"] for r in pairs)
        },
    }
