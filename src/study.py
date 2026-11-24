"""Command-line entry point. Network requests require an explicit --execute flag."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from . import evaluation as ev
from . import protocol
from .study_io import acquire, digest, load_env, load_manifest, load_models, load_reference, request
from .synthetic import _make_test_png

VISUAL_PROMPT = "Describe the visible shapes and their colors. Be concise; do not infer anything that is not visible."


def pilot_identity(model, phase, cap, image_hash):
    return {
        "model": model,
        "phase": phase,
        "image_sha256": image_hash,
        "system_prompt": protocol.SYSTEM_PROMPT,
        "user_prompt": VISUAL_PROMPT if phase == "visual" else protocol.PROMPT,
        "settings": {"temperature": 0.3, "max_tokens": cap, "timeout_seconds": 180},
    }


def pilot_ok(record):
    result = ev.assess(record.get("http_response", {}))
    if record["phase"] == "study":
        return result.get("validation_status") == "valid_response"
    text = result.get("raw_response_text", "").lower()
    return result["status"] != "truncated_output" and all(
        word in text for word in ("blue", "triangle", "red", "circle")
    )


def pilots(output, models, cap, execute=False, transport=request):
    output.mkdir(parents=True, exist_ok=True)
    image = output / "synthetic.png"
    with tempfile.TemporaryDirectory() as directory:
        generated = Path(directory) / "synthetic.png"
        _make_test_png(generated)
        if image.exists():
            if digest(image) != digest(generated):
                raise ValueError("Pilot synthetic image changed; use a new pilot directory.")
        else:
            with image.open("xb") as handle:
                handle.write(generated.read_bytes())
    key = api_key() if execute else None
    missing = 0
    with ev.run_lock(output):
        for model in models:
            if cap not in model["token_caps"]:
                raise ValueError("Pilot cap must be in each selected model token schedule.")
            for phase in ("visual", "study"):
                path = output / (model["id"].replace("/", "_") + "-" + phase + ".json")
                identity = pilot_identity(model["id"], phase, cap, digest(image))
                if path.exists():
                    record = ev.read_json(path)
                    if any(record.get(k) != v for k, v in identity.items()):
                        raise ValueError("Saved pilot settings differ; use a new pilot directory.")
                    continue
                missing += 1
                if not execute:
                    continue
                record = {**identity, "status": "in_flight"}
                ev.write_new(path, record)
                record["http_response"] = transport(
                    model["id"], image, key, identity["user_prompt"], identity["system_prompt"], cap
                )
                record["status"] = "pass" if pilot_ok(record) else "fail"
                ev.finish_record(path, record)
                if ev.assess(record["http_response"])["status"] in {
                    "request_error",
                    "provider_error",
                }:
                    raise ev.ExecutionStopped(missing)
    return {"planned_calls": 2 * len(models), "missing_attempts": missing, "executed": execute}


def validate_pilots(directory, models):
    image_hash = digest(directory / "synthetic.png")
    results = {}
    for model in models:
        for phase in ("visual", "study"):
            name = model["id"].replace("/", "_") + "-" + phase + ".json"
            path = directory / name
            record = ev.read_json(path)
            # A higher-cap capability pilot is recorded but does not change evaluation caps.
            cap = record.get("settings", {}).get("max_tokens")
            identity = pilot_identity(model["id"], phase, cap, image_hash)
            if (
                cap not in model["token_caps"]
                or any(record.get(k) != v for k, v in identity.items())
                or record.get("status") != "pass"
                or not pilot_ok(record)
            ):
                raise ValueError(
                    "Missing or incompatible passing pilot; inspect pilot responses before evaluation."
                )
            results[name] = digest(path)
    return results


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key or key == "replace-with-your-key":
        raise ValueError("Set OPENROUTER_API_KEY in the environment or .env before --execute.")
    return key


def smoke():
    """A synthetic scoring and resume/retry check with no network or credentials."""
    envelope = {
        "http_status": 200,
        "body": json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "problem_teeth": [11, 21],
                                    "confidence": 80,
                                    "rationale": "Teeth 11 and 21 show suspicious findings.",
                                }
                            )
                        },
                    }
                ]
            }
        ),
    }
    assessed = ev.assess(envelope)
    assert assessed["status"] == "ASSESSABLE_FINDINGS"
    pairs = [
        {"status": assessed["status"], "predicted_teeth": [11, 21], "reference_teeth": [11, 12]},
        {"status": "EXPLICIT_NO_FINDINGS", "predicted_teeth": [], "reference_teeth": [46]},
        {"status": "truncated_output", "predicted_teeth": None, "reference_teeth": [47]},
    ]
    metrics = ev.metrics_for_pairs(pairs)
    assert (metrics["tp"], metrics["fp"], metrics["fn"], metrics["evaluable"]) == (1, 1, 2, 2)
    assert (
        ev.next_cap(
            [{"status": "truncated_output", "settings": {"max_tokens": 1024}}],
            [1024, 2048],
            retry=True,
        )
        == 2048
    )
    assert ev.next_cap([assessed], [1024, 2048], retry=False) is None
    with tempfile.TemporaryDirectory() as directory:
        image = Path(directory) / "synthetic.png"
        _make_test_png(image)
        assert image.read_bytes().startswith(b"\x89PNG")
    return {"offline_smoke": "passed", "synthetic_metrics": metrics}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--models", type=Path, default=Path(os.getenv("XRAY_MODELS_YAML", "config/models.yaml"))
    )
    p.add_argument(
        "--manifest", type=Path, default=Path(os.getenv("XRAY_MANIFEST", "data/study_manifest.csv"))
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("smoke", help="Synthetic offline checks; no credentials or study data.")
    sub.add_parser("plan", help="Validate roster and manifest; no network.")
    data = sub.add_parser(
        "acquire", help="Verify a downloaded ZIP and extract only the study images."
    )
    data.add_argument("--archive", type=Path, required=True)
    data.add_argument(
        "--images-dir",
        type=Path,
        default=Path(os.getenv("XRAY_IMAGES_DIR", "data/private/Dataset/Training/Images")),
    )
    verify = sub.add_parser(
        "verify", help="Verify all image SHA-256 digests and optionally the workbook."
    )
    verify.add_argument(
        "--images-dir",
        type=Path,
        default=Path(os.getenv("XRAY_IMAGES_DIR", "data/private/Dataset/Training/Images")),
    )
    verify.add_argument("--annotations", type=Path, default=None)
    pilot = sub.add_parser(
        "pilot", help="Synthetic capability pilot. --execute incurs API charges."
    )
    pilot.add_argument("--output", type=Path, required=True)
    pilot.add_argument("--cap", type=int, default=1024)
    pilot.add_argument("--execute", action="store_true")
    init = sub.add_parser(
        "init", help="Freeze a new run configuration after passing pilots; no calls."
    )
    init.add_argument("--run", type=Path, required=True)
    init.add_argument(
        "--images-dir",
        type=Path,
        default=Path(os.getenv("XRAY_IMAGES_DIR", "data/private/Dataset/Training/Images")),
    )
    init.add_argument(
        "--annotations",
        type=Path,
        default=Path(os.getenv("XRAY_ANNOTATIONS", "data/private/Dentist_Comments_MERGED.xlsx")),
    )
    init.add_argument("--pilot-dir", type=Path, required=True)
    for command in ("evaluate", "retry"):
        task = sub.add_parser(command, help="Plan requests; --execute incurs API charges.")
        task.add_argument("--run", type=Path, required=True)
        task.add_argument(
            "--images-dir",
            type=Path,
            default=Path(os.getenv("XRAY_IMAGES_DIR", "data/private/Dataset/Training/Images")),
        )
        task.add_argument("--execute", action="store_true")
    score = sub.add_parser("score", help="Offline scoring of a release-format run; prints JSON.")
    score.add_argument("--run", type=Path, required=True)
    checkpoint = sub.add_parser(
        "verify-checkpoints",
        help="Verify saved combined checkpoints without reselecting responses.",
    )
    checkpoint.add_argument("--checkpoint", type=Path, action="append", required=True)
    checkpoint.add_argument("--record-root", type=Path, required=True)
    return p


def main(argv=None):
    try:
        load_env()
        args = parser().parse_args(argv)
        if args.command == "smoke":
            result = smoke()
        elif args.command == "plan":
            models = load_models(args.models)
            images = load_manifest(args.manifest)
            result = {
                "models": models,
                "verified_manifest_entries": len(images),
                "planned_pairs": len(models) * len(images),
                "network_requests": 0,
            }
        elif args.command == "acquire":
            result = {"verified_images": len(acquire(args.archive, args.images_dir, args.manifest))}
        elif args.command == "verify":
            images = load_manifest(args.manifest, args.images_dir)
            if args.annotations:
                load_reference(args.annotations)
            result = {"verified_images": len(images), "annotations_checked": bool(args.annotations)}
        elif args.command == "pilot":
            result = pilots(args.output, load_models(args.models), args.cap, args.execute)
        elif args.command == "init":
            proofs = validate_pilots(args.pilot_dir, load_models(args.models))
            run = ev.initialize(
                args.run, args.models, args.manifest, args.images_dir, args.annotations, proofs
            )
            result = {"planned_pairs": len(run["models"]) * len(run["images"]), "initialized": True}
        elif args.command in ("evaluate", "retry"):
            manifest = ev.read_run(args.run, args.images_dir)
            eligible = sum(
                ev.next_cap(
                    ev.attempts_for(args.run, manifest, m, i),
                    m["token_caps"],
                    args.command == "retry",
                )
                is not None
                for m in manifest["models"]
                for i in manifest["images"]
            )
            result = {"eligible_calls": eligible, "executed": False}
            if args.execute:
                result = {
                    "calls_made": ev.execute(
                        args.run, args.images_dir, api_key(), args.command == "retry"
                    ),
                    "executed": True,
                }
        elif args.command == "score":
            result = ev.score_run(args.run)
        else:
            result = ev.verify_checkpoint(args.checkpoint, args.record_root)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except ev.ExecutionStopped as error:
        print(
            json.dumps(
                {
                    "status": "stopped_after_request_error",
                    "calls_made": error.calls_made,
                    "message": str(error),
                }
            )
        )
        return 1
    except ModuleNotFoundError:
        print(
            "Error: Install the pinned dependencies with python -m pip install -r requirements.txt.",
            file=__import__("sys").stderr,
        )
        return 2
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        # Input and provider content are deliberately excluded from error output.
        message = (
            str(error)
            if isinstance(error, ValueError)
            else "Input missing or malformed; check paths, schemas, and permissions."
        )
        print("Error: " + message, file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
