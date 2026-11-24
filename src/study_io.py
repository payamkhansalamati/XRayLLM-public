"""Portable configuration, verified inputs, and a single-attempt API transport."""

import base64
import csv
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .protocol import _extract_fdi

API_URL = "https://openrouter.ai/api/v1/chat/completions"
ARCHIVE_SHA256 = "b9edb55020f2cb971ba771b4cf5e4b65c4abb4df957310bd2eccc83d5a08b072"
STUDY_IDS = frozenset(
    "105 199 230 344 386 442 532 620 631 651 654 667 671 690 815 949 1017 1058 1161 1214".split()
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_env(path=Path(".env")):
    """Read simple KEY=value entries without executing or expanding shell text."""
    if not path.is_file():
        return
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"Invalid environment entry at line {number}; use KEY=value.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def load_models(path):
    import yaml

    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    models = value.get("models") if isinstance(value, dict) else None
    if not isinstance(models, list) or len(models) != 10:
        raise ValueError("Study roster must contain exactly 10 models.")
    seen = set()
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Each model must be an object.")
        model_id = model.get("id", "")
        if not re.fullmatch(r"[a-z0-9.-]+/[a-z0-9.-]+", model_id) or model_id in seen:
            raise ValueError("Model identifiers must be unique provider/model endpoints.")
        seen.add(model_id)
        if model.get("analysis_set") not in {"primary", "exploratory"}:
            raise ValueError("Model analysis_set must be primary or exploratory.")
        caps = model.get("token_caps")
        if (
            not isinstance(caps, list)
            or not caps
            or any(type(v) is not int or v <= 0 for v in caps)
            or caps != sorted(set(caps))
            or caps[0] != 1024
        ):
            raise ValueError("Token caps must be increasing positive integers starting at 1024.")
    if sum(m["analysis_set"] == "primary" for m in models) != 8:
        raise ValueError("Study requires eight primary and two exploratory models.")
    return models


def load_manifest(path, images_dir=None):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"filename", "picture_number", "source_member_path", "image_sha256"}
    if len(rows) != 20 or any(not required <= r.keys() for r in rows):
        raise ValueError(
            "Manifest must contain 20 rows with filename, picture_number, source_member_path, image_sha256."
        )
    if {r["picture_number"] for r in rows} != STUDY_IDS:
        raise ValueError("Manifest identifiers differ from the fixed 20-image study.")
    for row in rows:
        filename = row["filename"]
        if (
            filename != row["picture_number"] + ".jpg"
            or row["source_member_path"] != "Dataset/Training/Images/" + filename
        ):
            raise ValueError("Manifest filename or archive member does not match its identifier.")
        if not re.fullmatch(r"[0-9a-f]{64}", row["image_sha256"]):
            raise ValueError(f"Invalid SHA-256 for {filename}.")
        if images_dir is not None:
            path = Path(images_dir) / filename
            if not path.is_file():
                raise ValueError(
                    f"Missing image {filename}; acquire DenPAR v3 and set --images-dir."
                )
            if digest(path) != row["image_sha256"]:
                raise ValueError(f"Image SHA-256 mismatch: {filename}.")
    return rows


def acquire(archive, images_dir, manifest):
    rows = load_manifest(manifest)
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError("Archive SHA-256 mismatch; obtain the documented DenPAR v3 release.")
    images_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for row in rows:
            data = bundle.read(row["source_member_path"])
            if hashlib.sha256(data).hexdigest() != row["image_sha256"]:
                raise ValueError(f"Archive image digest mismatch: {row['filename']}.")
            target = images_dir / row["filename"]
            if target.exists():
                if digest(target) != row["image_sha256"]:
                    raise ValueError("Existing destination image differs; refusing to overwrite.")
            else:
                with target.open("xb") as handle:
                    handle.write(data)
    return load_manifest(manifest, images_dir)


def workbook_rows(path):
    """Read the first XLSX worksheet, including shared and inline strings."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    uri = "{" + ns["m"] + "}"
    with zipfile.ZipFile(path) as bundle:
        strings = []
        if "xl/sharedStrings.xml" in bundle.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(uri + "t"))
                for item in ET.fromstring(bundle.read("xl/sharedStrings.xml"))
            ]
        workbook = ET.fromstring(bundle.read("xl/workbook.xml"))
        sheet = workbook.find(".//m:sheets/m:sheet", ns)
        if sheet is None:
            raise ValueError("Annotation workbook contains no worksheet.")
        rel_id = sheet.attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        rels = ET.fromstring(bundle.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib.get("Id") == rel_id)
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        rows = []
        for row in ET.fromstring(bundle.read(target)).findall(".//m:sheetData/m:row", ns):
            values = {}
            for cell in row.findall("m:c", ns):
                col = re.match("[A-Z]+", cell.attrib["r"]).group()
                value = cell.find("m:v", ns)
                if cell.attrib.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in cell.iter(uri + "t"))
                elif value is not None:
                    text = value.text or ""
                    if cell.attrib.get("t") == "s":
                        text = strings[int(text)]
                else:
                    continue
                values[col] = text
            rows.append(values)
    if not rows:
        raise ValueError("Annotation worksheet is empty.")
    headers = rows[0]
    return [{headers.get(k, k): v for k, v in row.items()} for row in rows[1:]]


def load_reference(path, image_ids=STUDY_IDS):
    rows = workbook_rows(path)
    columns = [k for k in (rows[0] if rows else {}) if k.lower().endswith("comment")]
    if not columns:
        raise ValueError(
            "Annotations require Picture_Number and at least one column ending in Comment."
        )
    result = {}
    for row in rows:
        try:
            picture = str(int(float(row["Picture_Number"])))
        except (KeyError, ValueError, OverflowError):
            continue
        if picture not in image_ids:
            continue
        if picture in result:
            raise ValueError(f"Duplicate annotation identifier: {picture}.")
        result[picture] = sorted(set().union(*(_extract_fdi(str(row.get(c, ""))) for c in columns)))
    if set(result) != set(image_ids):
        raise ValueError("Annotation workbook is missing fixed study identifiers.")
    return result


def redact(text, key=""):
    if key:
        text = text.replace(key, "[redacted credential]")
    text = re.sub(r"sk-or-v1-[A-Za-z0-9_-]{20,}", "[redacted credential]", text)
    return re.sub(r'(?i)Bearer\s+[^\s"\x27]+', "Bearer [redacted credential]", text)


def request(model, image, key, prompt, system, cap, temperature=0.3, timeout=180):
    """Exactly one HTTP request. No SDK retries, fallback models, or implicit calls."""
    mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    url = "data:" + mime + ";base64," + base64.b64encode(image.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": cap,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            },
        ],
    }
    req = urllib.request.Request(
        API_URL,
        json.dumps(payload).encode(),
        {"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return {
                "http_status": response.status,
                "body": redact(response.read().decode("utf-8", errors="replace"), key),
            }
    except urllib.error.HTTPError as error:
        return {
            "http_status": error.code,
            "body": redact(error.read().decode("utf-8", errors="replace"), key),
        }
    except (urllib.error.URLError, TimeoutError, OSError):
        return {
            "http_status": None,
            "transport_error": "Transport failed; delivery and billing may be uncertain.",
        }
