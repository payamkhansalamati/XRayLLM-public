# Licensing and third-party notices

## Project code

Project code is distributed under the [MIT License](../LICENSE), with
copyright attributed to XRayLLM contributors. The project license covers
project software and documentation, not third-party datasets, independent
annotations, hosted model weights, or provider-generated clinical records.

## Runtime dependency

The public study pipeline depends on PyYAML 6.0.3, distributed under the MIT
license. Its source and license are available from
[PyYAML](https://github.com/yaml/pyyaml/blob/6.0.3/LICENSE).
The export does not vendor dependency packages. Python and container base
images carry their own licenses; retain their notices when redistributing
those binaries. The archived local image-selection and SDK-based utilities
are not shipped in this candidate and are not covered by the minimal runtime
requirements file. The optional development tool Ruff 0.14.6 is
dual-licensed under MIT or Apache-2.0; see its
[license files](https://github.com/astral-sh/ruff/tree/0.14.6).

## Dataset and separate annotations

DenPAR v3 record [16645076](https://zenodo.org/records/16645076) identifies
CC-BY-4.0 in its [license metadata](https://zenodo.org/api/records/16645076),
checked 2026-11-21. Dataset acquisition, version checksums, attribution, and
the recommended paper citation are documented in [data/README.md](../data/README.md).
Radiographs and archives are deliberately absent from the source export.
The manifest is limited to public dataset filenames, archive members,
identifiers, and derived content digests.

The merged study annotation workbook is a separate artifact with unconfirmed
redistribution terms. It, per-image clinical labels, raw model outputs,
provider logs, and manuscripts are excluded. Do not assume the dataset's
license also grants permission to redistribute these independent artifacts.
The available aggregate table can be checked mathematically, but exact score
reproduction requires authorized access to both the separate annotations
and the selected model responses. No access mechanism for those artifacts
is asserted here.

## Hosted endpoints

The endpoint names are identifiers for the study, not endorsements or
redistributed model weights. API use is subject to OpenRouter and downstream
provider terms. Review those terms and data-processing permissions before
uploading clinical images. The synthetic offline workflow does not contact
these services.
