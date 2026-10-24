# Validation for 0.1.0

Executed on Windows / Python 3.13.16, 2026-10-24:

- 35 unittest cases: 33 passed, 2 symbolic-link cases skipped because this local
  OS account cannot create symlinks. The Linux/macOS CI jobs exercise those cases.
  This skip is reported explicitly and does not disable the confinement check.
- Combined statement/branch coverage: 89%; Ruff lint/format checks passed.
- Tests cover component boundaries, longest-prefix maps, Windows/UNC/POSIX source
  semantics, lexical parent traversal, Unicode/literal-percent paths, repeated
  tracks, underlying-file collisions (including actual hard links), malformed
  configuration, size limits and no-clobber behavior when an output appears late.
- A clean wheel install outside the checkout ran the full README demo: generate
  a real synthetic WAV, preview without writing, publish the playlist, open the
  mapped WAV and verify its frame count, then uninstall.
- Source distribution and wheel built successfully. There are no third-party
  runtime dependencies. Manual review checked license/provenance, error privacy,
  output publication, source-path normalization and target-root confinement.

Review exposed two robustness issues which were fixed before publication:
ambiguous target aliases needed filesystem identity checks, and malformed output
paths needed explicit validation rather than relying on platform-specific Path
behavior. Their regression tests remain in the suite.

The first CI run also exposed a test-only platform assumption: macOS resolves
`/var` through `/private/var`, and Windows runners may start with an 8.3 short
temporary-directory path. The absolute-output assertion now requires an absolute
path, actual same-file identity and the expected bytes instead of comparing two
different spellings. The production canonicalization contract is unchanged.

The tool validates paths, not audio identity or decodability. Concurrent library
changes can invalidate a completed preflight. See the README for filesystem
requirements and exact unsupported inputs. Actions contains the authoritative
cross-platform results for this revision.
