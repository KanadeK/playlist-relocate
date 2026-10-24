# Security

Version 0.1.x is the supported line. Report vulnerabilities privately using
[GitHub private vulnerability reporting](https://github.com/KanadeK/playlist-relocate/security/advisories/new).
Include the affected version, a synthetic reproducer and expected impact.
Do not put secrets or private user data in public issues.

This tool operates locally without telemetry or runtime network requests. Reports
omit content by default, but counts, line positions and hashes are still metadata.
Keep inputs and reports under your own access controls. Hashes of low-entropy
content are not an anonymization guarantee. Use trusted local files; this utility
is not an OS-level sandbox for hostile files or a full format-security validator.
