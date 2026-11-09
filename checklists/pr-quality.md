# Model Self-Check: PR & Verification Quality

- **Small, self-contained diff (`GIT001`):** Keep each PR focused (`<= 300` non-asset additions, `<= 400` total changes). Split larger features into stacked PRs after aligning on a ~40-line public API skeleton.
- **Parameterized, asset-backed tests:** Place sample YAML/JSON/text fixtures under `tests/assets/` and parameterize cases with `it.each([...])` or `@pytest.mark.parametrize(...)` instead of copy-pasted test blocks.
- **Runnable live verification (`PR004`):** For server, daemon, CLI, or integration changes, run a real end-to-end verification command across live boundaries (not just mocked unit tests) and capture exact stdout proof.
- **Concise PR description (`PR001`–`PR003`):** Keep PR bodies `<= 30` non-empty lines with `## Why`, a short file reading order, and `## Verification` containing the exact command and output.
