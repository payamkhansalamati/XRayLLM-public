"""Synthetic tests: no credentials, clinical images, annotations, or model calls."""

import csv
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import evaluation as ev, protocol, study
from src.study_io import load_env, load_manifest, load_models, load_reference, redact, request

ROOT = Path(__file__).resolve().parents[1]


def response(teeth=(11,), rationale="Tooth 11 shows suspicious findings.", finish="stop"):
    return {
        "http_status": 200,
        "body": json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": finish,
                        "message": {
                            "content": json.dumps(
                                {
                                    "problem_teeth": list(teeth),
                                    "confidence": 80,
                                    "rationale": rationale,
                                }
                            )
                        },
                    }
                ]
            }
        ),
    }


def synthetic_inputs(directory):
    images = directory / "images"
    images.mkdir()
    with (ROOT / "data/study_manifest.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        data = b"SYNTHETIC TEST BYTES " + row["filename"].encode()
        (images / row["filename"]).write_bytes(data)
        row["image_sha256"] = hashlib.sha256(data).hexdigest()
    manifest = directory / "manifest.csv"
    with manifest.open("w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    workbook = directory / "synthetic.xlsx"
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    )
    for i, values in enumerate(
        [["Picture_Number", "First_Comment", "Second_Comment"]]
        + [[r["picture_number"], "Tooth 11 and 12", "Tooth 11"] for r in rows],
        1,
    ):
        sheet += (
            "<row>"
            + "".join(
                f'<c r="{col}{i}" t="inlineStr"><is><t>{value}</t></is></c>'
                for col, value in zip("ABC", values)
            )
            + "</row>"
        )
    sheet += "</sheetData></worksheet>"
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Synthetic" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return images, manifest, workbook


class ParsingTests(unittest.TestCase):
    def test_classifications(self):
        for teeth, rationale, expected in [
            ([11], "Tooth 11 has a lesion.", "ASSESSABLE_FINDINGS"),
            (
                [],
                "I reviewed the image and no suspicious findings were identified.",
                "EXPLICIT_NO_FINDINGS",
            ),
            ([], "I cannot assess the image.", "IMAGE_UNASSESSABLE"),
            ([11], "I cannot assess the image.", "SEMANTIC_CONFLICT"),
            ([], "Uncertain.", "EMPTY_FINDINGS_UNCLEAR"),
        ]:
            with self.subTest(expected=expected):
                self.assertEqual(ev.assess(response(teeth, rationale))["status"], expected)

    def test_strict_schema(self):
        good = {"problem_teeth": [11], "confidence": 80, "rationale": "Tooth 11 has a lesion."}
        for field, value in [
            ("problem_teeth", [True]),
            ("problem_teeth", [19]),
            ("problem_teeth", [51]),
            ("confidence", True),
            ("confidence", 80.0),
            ("confidence", 101),
            ("rationale", ""),
        ]:
            with self.subTest(field=field, value=value):
                status, _, _ = protocol._validate_response(json.dumps({**good, field: value}))
                self.assertEqual(status, "schema_failure")
        for text in ["```json\n" + json.dumps(good) + "\n```", "[]", "", "{"]:
            self.assertNotEqual(protocol._validate_response(text)[0], "valid_response")

    def test_envelopes_and_truncation(self):
        for body in ["{", "[]", "{}", json.dumps({"choices": [{"message": {}}]})]:
            self.assertIn(
                ev.assess({"http_status": 200, "body": body})["status"],
                {"response_envelope_error", "empty_response"},
            )
        self.assertEqual(ev.assess(response(finish="length"))["status"], "truncated_output")
        self.assertEqual(
            ev.assess(
                {
                    "http_status": 200,
                    "body": json.dumps({"choices": [{"message": {"refusal": "Declined"}}]}),
                }
            )["status"],
            "refusal",
        )
        self.assertEqual(ev.assess({"http_status": 429})["status"], "request_error")
        self.assertEqual(
            ev.assess({"http_status": 200, "body": '{"error":{"message":"Failed"}}'})["status"],
            "provider_error",
        )

    def test_metrics_exclusions_and_duplicates(self):
        pairs = [
            {
                "status": "ASSESSABLE_FINDINGS",
                "predicted_teeth": [11, 11, 21],
                "reference_teeth": [11, 12],
            },
            {"status": "EXPLICIT_NO_FINDINGS", "predicted_teeth": [], "reference_teeth": [46]},
            {"status": "parse_failure", "predicted_teeth": None, "reference_teeth": [47]},
        ]
        result = ev.metrics_for_pairs(pairs)
        self.assertEqual(
            (result["tp"], result["fp"], result["fn"], result["evaluable"]), (1, 1, 2, 2)
        )
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 1 / 3)
        self.assertEqual(result["f1"], 0.4)
        self.assertIsNone(result["tooth_accuracy"])
        self.assertIsNone(ev.metrics_for_pairs([])["f1"])
        self.assertEqual(
            ev.metrics_for_pairs(
                [
                    {
                        "status": "ASSESSABLE_FINDINGS",
                        "predicted_teeth": [11],
                        "reference_teeth": [11],
                    }
                ]
            )["exact_match_accuracy"],
            1,
        )


class InputTests(unittest.TestCase):
    def test_roster_and_manifest(self):
        models = load_models(ROOT / "config/models.yaml")
        rows = load_manifest(ROOT / "data/study_manifest.csv")
        self.assertEqual(len(models) * len(rows), 200)
        self.assertEqual(sum(m["analysis_set"] == "primary" for m in models), 8)

    def test_verification_and_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            images, manifest, workbook = synthetic_inputs(Path(folder))
            self.assertEqual(len(load_manifest(manifest, images)), 20)
            self.assertTrue(all(v == [11, 12] for v in load_reference(workbook).values()))
            (images / "105.jpg").write_bytes(b"CHANGED")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                load_manifest(manifest, images)

    def test_duplicate_and_traversal_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            images, path, _ = synthetic_inputs(Path(folder))
            original = path.read_text()
            for bad in [
                original.replace("199.jpg,199,", "199.jpg,105,"),
                original.replace("105.jpg,105,", "../105.jpg,105,"),
            ]:
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    load_manifest(path)

    def test_env_no_expansion_and_precedence(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"XRAY_TEST_EXISTING": "shell"}, clear=False),
        ):
            path = Path(folder) / ".env"
            path.write_text("XRAY_TEST_EXISTING=file\nXRAY_TEST_LITERAL=$(unexecuted)\n")
            load_env(path)
            self.assertEqual(os.environ["XRAY_TEST_EXISTING"], "shell")
            self.assertEqual(os.environ["XRAY_TEST_LITERAL"], "$(unexecuted)")

    def test_transport_one_call_and_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "synthetic.png"
            image.write_bytes(b"SYNTHETIC")
            with patch("urllib.request.urlopen", side_effect=TimeoutError) as send:
                result = request(
                    "example/model", image, "synthetic-value", "prompt", "system", 1024
                )
                self.assertEqual(send.call_count, 1)
                self.assertEqual(result["http_status"], None)
            self.assertNotIn("synthetic-value", redact("Bearer synthetic-value", "synthetic-value"))


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.images, self.manifest, self.workbook = synthetic_inputs(self.directory)
        self.run = self.directory / "run"
        ev.initialize(
            self.run, ROOT / "config/models.yaml", self.manifest, self.images, self.workbook
        )

    def test_evaluate_and_resume_no_repeated_calls(self):
        calls = []

        def transport(*args):
            calls.append(args)
            return response()

        self.assertEqual(ev.execute(self.run, self.images, "synthetic", transport=transport), 200)
        before = {p: p.read_bytes() for p in self.run.rglob("*.json")}
        self.assertEqual(ev.execute(self.run, self.images, "synthetic", transport=transport), 0)
        self.assertEqual(
            ev.execute(self.run, self.images, "synthetic", retry=True, transport=transport), 0
        )
        self.assertEqual(len(calls), 200)
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
        score = ev.score_run(self.run)
        self.assertEqual(score["evaluable_pairs"], 200)
        self.assertEqual(score["models"]["openai/gpt-6.2-astra"]["fn"], 20)

    def test_retry_once_per_stage_and_cap_ceiling(self):
        def truncated(*args):
            return response(finish="length")

        self.assertEqual(ev.execute(self.run, self.images, "synthetic", transport=truncated), 200)
        for _ in range(3):
            ev.execute(self.run, self.images, "synthetic", retry=True, transport=truncated)
        self.assertEqual(
            ev.execute(self.run, self.images, "synthetic", retry=True, transport=truncated), 0
        )
        self.assertEqual(len(list(self.run.rglob("*.json"))), 601)
        self.assertEqual(ev.score_run(self.run)["evaluable_pairs"], 0)

    def test_pending_attempt_is_not_repeated(self):
        def crash(*args):
            raise RuntimeError("Synthetic crash")

        with self.assertRaises(RuntimeError):
            ev.execute(self.run, self.images, "synthetic", transport=crash)
        first = next((self.run / "responses").rglob("*.json"))
        self.assertEqual(ev.read_json(first)["status"], "in_flight")
        self.assertEqual(
            ev.execute(self.run, self.images, "synthetic", transport=lambda *args: response()), 199
        )
        self.assertEqual(ev.read_json(first)["status"], "in_flight")
        self.assertEqual(
            ev.execute(
                self.run, self.images, "synthetic", retry=True, transport=lambda *args: response()
            ),
            0,
        )

    def test_error_stops_and_resume_skips_it(self):
        with self.assertRaises(ev.ExecutionStopped) as stopped:
            ev.execute(
                self.run, self.images, "synthetic", transport=lambda *args: {"http_status": 429}
            )
        self.assertEqual(stopped.exception.calls_made, 1)
        self.assertEqual(
            ev.execute(self.run, self.images, "synthetic", transport=lambda *args: response()), 199
        )
        self.assertEqual(ev.score_run(self.run)["evaluable_pairs"], 199)

    def test_cli_returns_failure_for_saved_request_error(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-value"}):
            with patch("src.evaluation.execute", side_effect=ev.ExecutionStopped(1)):
                with redirect_stdout(io.StringIO()) as output:
                    status = study.main(
                        [
                            "evaluate",
                            "--run",
                            str(self.run),
                            "--images-dir",
                            str(self.images),
                            "--execute",
                        ]
                    )
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["calls_made"], 1)

    def test_pilot_stops_after_request_error(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-value"}):
            with self.assertRaises(ev.ExecutionStopped) as stopped:
                study.pilots(
                    self.directory / "pilot-failed",
                    load_models(ROOT / "config/models.yaml"),
                    1024,
                    True,
                    lambda *args: {"http_status": 401},
                )
        self.assertEqual(stopped.exception.calls_made, 1)
        self.assertEqual(len(list((self.directory / "pilot-failed").glob("*.json"))), 1)

    def test_classified_nonevaluable_is_frozen(self):
        self.assertEqual(
            ev.execute(
                self.run,
                self.images,
                "synthetic",
                transport=lambda *args: response([11], "I cannot assess the image."),
            ),
            200,
        )
        self.assertEqual(
            ev.execute(
                self.run, self.images, "synthetic", retry=True, transport=lambda *args: response()
            ),
            0,
        )
        self.assertEqual(ev.score_run(self.run)["evaluable_pairs"], 0)

    def test_changed_images_prevent_calls(self):
        (self.images / "105.jpg").write_bytes(b"CHANGED")
        with self.assertRaises(ValueError):
            ev.execute(
                self.run,
                self.images,
                "synthetic",
                transport=lambda *args: self.fail("Must not send"),
            )

    def test_lock_and_protocol_guards(self):
        (self.run / ".lock").touch()
        with self.assertRaises(ValueError):
            ev.execute(self.run, self.images, "synthetic")
        (self.run / ".lock").unlink()
        manifest = ev.read_json(self.run / "run.json")
        manifest["user_prompt"] = "changed"
        (self.run / "run.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            ev.score_run(self.run)

    def test_selection_preserves_first_classified(self):
        first = {"status": "ASSESSABLE_FINDINGS", "value": 1}
        self.assertIs(
            ev.select_attempt(
                [
                    {"status": "truncated_output"},
                    first,
                    {"status": "ASSESSABLE_FINDINGS", "value": 2},
                ]
            ),
            first,
        )

    def test_offline_commands_never_call_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network")):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(study.main(["smoke"]), 0)
                self.assertEqual(
                    study.main(
                        [
                            "--models",
                            str(ROOT / "config/models.yaml"),
                            "--manifest",
                            str(ROOT / "data/study_manifest.csv"),
                            "plan",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    study.main(
                        ["evaluate", "--run", str(self.run), "--images-dir", str(self.images)]
                    ),
                    0,
                )
                self.assertEqual(
                    study.main(["pilot", "--output", str(self.directory / "pilot")]), 0
                )

    def test_pilot_resume_and_identity(self):
        output = self.directory / "pilot"

        def synthetic(*args):
            if args[3] == study.VISUAL_PROMPT:
                return {
                    "http_status": 200,
                    "body": json.dumps(
                        {"choices": [{"message": {"content": "A blue triangle and a red circle."}}]}
                    ),
                }
            return response([], "I cannot assess the image.")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-value"}):
            study.pilots(output, load_models(ROOT / "config/models.yaml"), 1024, True, synthetic)
            self.assertEqual(
                len(study.validate_pilots(output, load_models(ROOT / "config/models.yaml"))), 20
            )
            result = study.pilots(
                output,
                load_models(ROOT / "config/models.yaml"),
                1024,
                True,
                lambda *args: self.fail("Repeated pilot"),
            )
            self.assertEqual(result["missing_attempts"], 0)
            (output / "synthetic.png").write_bytes(b"CHANGED")
            with self.assertRaises(ValueError):
                study.pilots(output, load_models(ROOT / "config/models.yaml"), 1024, False)

    def test_cli_initializes_frozen_run_with_pilot_provenance(self):
        pilot = self.directory / "pilot-init"

        def synthetic(*args):
            if args[3] == study.VISUAL_PROMPT:
                return {
                    "http_status": 200,
                    "body": json.dumps(
                        {"choices": [{"message": {"content": "A blue triangle and a red circle."}}]}
                    ),
                }
            return response([], "I cannot assess the image.")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-value"}):
            study.pilots(pilot, load_models(ROOT / "config/models.yaml"), 1024, True, synthetic)
        run = self.directory / "cli-run"
        with (
            redirect_stdout(io.StringIO()),
            patch("urllib.request.urlopen", side_effect=AssertionError("No network")),
        ):
            self.assertEqual(
                study.main(
                    [
                        "--models",
                        str(ROOT / "config/models.yaml"),
                        "--manifest",
                        str(self.manifest),
                        "init",
                        "--run",
                        str(run),
                        "--images-dir",
                        str(self.images),
                        "--annotations",
                        str(self.workbook),
                        "--pilot-dir",
                        str(pilot),
                    ]
                ),
                0,
            )
        manifest = ev.read_run(run)
        self.assertEqual(len(manifest["pilot_records_sha256"]), 20)
        self.assertEqual(ev.score_run(run)["planned_pairs"], 200)


if __name__ == "__main__":
    unittest.main()
