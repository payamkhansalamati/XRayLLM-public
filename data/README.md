# Data acquisition and rights

The fixed study uses 20 JPEGs from **DenPAR v3**, Zenodo record
[16645076](https://zenodo.org/records/16645076), DOI
[10.5281/zenodo.16645076](https://doi.org/10.5281/zenodo.16645076).
The archive is named `DenPAR Radiographs Dataset.zip`. The official record
lists MD5 `4fcecde6bfa4dc47daec83b1f7856c7f`. The locally verified archive
SHA-256 is `b9edb55020f2cb971ba771b4cf5e4b65c4abb4df957310bd2eccc83d5a08b072`.

The record's [license metadata](https://zenodo.org/api/records/16645076)
identifies CC-BY-4.0 (checked 2026-11-21). The release distributes no images
or archive: researchers acquire the original dataset directly and comply
with its attribution and any applicable use requirements. A code license
would not replace the data license.

1. Download the ZIP from the official record to `data/private/denpar-v3.zip`.
2. Copy `.env.example` to `.env`, adjusting paths if necessary.
3. Run the offline extraction and verification commands:

```bash
python -m src.study acquire --archive data/private/denpar-v3.zip
python -m src.study verify
```

`acquire` checks the complete archive SHA-256 before extracting only the
20 specified members. It writes JPEGs under
`data/private/Dataset/Training/Images` by default, checks individual image
hashes, and refuses to overwrite differing files. The manifest contains
filenames, numeric identifiers, archive-member names, and content digests;
it contains no clinical labels, pixels, patient information, or workbook paths.

The images are original JPEG bytes from `Dataset/Training/Images/`.
The manifest verifies this recovered v3 selection. It does not establish
that an older, undocumented selection run used the same dataset release or
image conversion. Do not rerun a difficulty selector and assume it recreates
the fixed sample.

## Separate study annotations

The study reference requires a separately supplied XLSX workbook, conventionally
`data/private/Dentist_Comments_MERGED.xlsx`. It is not part of the DenPAR ZIP
and is not distributed here. Redistribution permission and an access route
must be resolved by its rights holders before exact independent score
reproduction is possible.

The first worksheet must have a `Picture_Number` column and one or more
columns whose names end in `Comment` (case-insensitive). All 20 fixed image
identifiers must be present exactly once. The reference is the union of valid
permanent-tooth FDI numbers extracted from those free-text comment columns.
This is the recorded extraction rule, not a validated pathology ontology or
an adjudication of individual clinical statements. Duplicate identifiers
and missing required identifiers are rejected by the release reader.

```bash
python -m src.study verify --annotations data/private/Dentist_Comments_MERGED.xlsx
```

Keep workbooks, derived per-image references, clinical response text,
images, and raw model outputs local. Model requests transmit images to
OpenRouter and downstream providers; obtain the necessary permissions
before executing the paid workflow.

## Dataset citation

Rasnayaka, S., Leuke Bandara, D., Jayasundara, A. et al.
DenPAR: Annotated Intra-Oral Periapical Radiographs Dataset for Machine Learning.
*Scientific Data* 12, 1615 (2025).
[doi:10.1038/s41597-025-05906-9](https://doi.org/10.1038/s41597-025-05906-9).
The citation follows the official record; cite the versioned data DOI as well.
