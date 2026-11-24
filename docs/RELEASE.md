# Release candidate procedure

The candidate is an allowlisted source export, not a publication operation.
Do not copy `.git` from a development or research repository into it. The
export tool does not initialize Git, commit, push, or change hosting visibility.

Before publishing, the maintainer must resolve these gates:

1. Confirm revocation of any credential ever exposed in source or history.
2. Review the included MIT `LICENSE` and attribution, and confirm that all
   files to be published are within the reviewed release scope.
3. Review the exact candidate, rerun offline tests, and inspect its source scan.
4. Confirm the intended GitHub owner and new repository name. Keep any source
   repository containing sensitive history private. Do not mirror all refs.
5. Resolve the separate annotation/output access and redistribution permissions
   before claiming independently reproducible numerical study results. A
   code-only release must retain the documented limits on reproducibility.

Dataset pixels and clinical artifacts are excluded irrespective of the data
license. Keep authorized originals in a separate private research archive.
A clean export cannot revoke credentials, remove copies already obtained by
others, or clean a remote repository's existing history.

## Commit and push a reviewed clean export

These are manual commands for a new repository. Replace `OWNER/REPOSITORY`
with the verified destination; never use a destination containing the old
sensitive history. Run from the clean export, after resolving the gates.

```bash
python -m pip install -r requirements.txt
python -m src.study smoke
python -m unittest discover -s tests -v
# Run from the export's parent or the source tooling to scan the export.
# Inspect RELEASE_SHA256.json and every staged file before committing.
git init -b main
git add --all
git diff --cached --check
git diff --cached --stat
git commit -m "Prepare reproducible XRayLLM research release"
gh repo create OWNER/REPOSITORY --private --source=. --remote=origin
git push --set-upstream origin main
```

Creating the new repository private and pushing the reviewed commit does not
make it public. Review the hosted files and verify identity and visibility:

```bash
gh repo view OWNER/REPOSITORY --json nameWithOwner,isPrivate,url,defaultBranchRef
git remote -v
```

## Visibility is a separate final operation

Only after the verified destination and every release blocker are resolved:

```bash
gh repo edit OWNER/REPOSITORY --visibility public --accept-visibility-change-consequences
```

The command above is documentation only. If the existing repository is to be
reused instead, its affected history, remote refs, and applicable GitHub caches
must first be handled under an explicitly approved cleanup plan. A normal
new commit, a `.gitignore` edit, or a new tip tree does not remove an old secret.
