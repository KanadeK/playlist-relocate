# playlist-relocate

Move a local-media M3U playlist between drives or operating systems without
guessing filenames. Preview an explicit mount map, check every destination, then
write a **new** playlist only when the complete plan resolves.

[简体中文](README.zh-CN.md) · Python 3.11+ · MIT · No runtime dependencies

This is useful when an old `M:\Music\Artist\Tone.wav` must become
`library/Artist/Tone.wav` on a new machine. Prefix matching follows path components,
so `M:\MusicOther` is not accidentally rewritten as `M:\Music`.

## Install and try a complete example

```sh
git clone https://github.com/KanadeK/playlist-relocate.git
cd playlist-relocate
python -m venv .venv
```

Activate with `source .venv/bin/activate` (Linux/macOS) or
`.\.venv\Scripts\Activate.ps1` (PowerShell), then:

```sh
python -m pip install .
python examples/make_demo.py
playlist-relocate playlist-demo/old.m3u8 --map playlist-demo/mounts.json --output playlist-demo/moved.m3u8 --json
# Preview: exit 0, status ready; moved.m3u8 does not exist yet.
playlist-relocate playlist-demo/old.m3u8 --map playlist-demo/mounts.json --output playlist-demo/moved.m3u8 --write --json
# Write: exit 0, status written; its relative path opens the generated WAV.
```

The demo creates an explicitly synthetic 0.1-second PCM WAV and a tiny playlist;
no music is downloaded. The old Windows path need not exist on the current host.
Delete the dedicated `playlist-demo` directory to clean up the demo.

## Map a real library

Create a UTF-8 JSON file beside the new library. For example:

```json
{
  "version": 1,
  "source_style": "windows",
  "source_base": "M:\\Music\\Playlists",
  "mappings": [
    {"from": "M:\\Music", "to": "library"},
    {"from": "M:\\Music\\Archive", "to": "old-recordings"}
  ]
}
```

`from` must be an absolute path in the declared source style (`windows` or
`posix`). Windows drive and UNC paths work lexically on every host, without
connecting to the old machine. `source_base` is required only for relative media
entries; `..` is resolved lexically before selecting a map. Windows source-prefix
matching is case insensitive; POSIX matching is case sensitive. The longest
component prefix wins. Repeated equivalent map sources are rejected.

`to` uses the **current host's** filesystem conventions and must already be a
directory. Relative target roots are resolved from the map file's directory,
not the shell's current directory. The remainder of each media path must exist
with the target filesystem's spelling rules; there is no fuzzy, basename-only,
case-insensitive fallback search or percent decoding.

By default, emitted paths are relative to the new playlist's directory and use
forward slashes. Use `--absolute` for absolute native target paths, including
targets on another Windows drive. The output parent must exist. The original
playlist, map and media are never modified or moved.

## Validation and write behavior

- Every media entry must map to an existing regular file inside its resolved
  target root. A symlink that resolves outside that root is rejected.
- Distinct source paths may not collapse onto the same underlying target file
  (device/inode identity, including hard-link aliases).
  Repeated occurrences of the same source track remain in order.
- Blank lines, comments and EXTINF text are preserved. Output is normalized to
  UTF-8 without BOM and LF line endings, with a final newline.
- Remote/file URIs, HLS `#EXT-X-` directives, Windows device paths, drive-relative
  paths and ambiguous path whitespace are rejected. Legacy non-UTF-8 M3U encodings
  are unsupported. Unknown ordinary comment lines are preserved, not interpreted.
- Preview writes nothing. `--write` runs a fresh preflight, stages complete bytes
  beside the output, then uses an atomic no-clobber hard link to publish them.
  Existing output files or symlinks are never replaced, even if created after
  planning. The destination filesystem must support hard links; unsupported
  filesystems fail closed. An interrupted process or cleanup failure may leave
  a `.playlist-relocate-*` staging file in the output directory; remove only the
  staging file you recognize after checking no run is active.

The filesystem is checked at planning time; media content and paths are not locked
or fingerprinted. A concurrently modified library can invalidate that observation.
This is a path relocation check, not a media decoder, audio-content verifier,
playlist repair GUI or operating-system sandbox. [listFix](https://github.com/Borewit/listFix)
is a better fit for interactive searching/repair of a reorganized library. This
tool is for deterministic, headless mount mapping without selecting lookalike files.

## Receipts, limits and exit codes

`--json` emits counts, input/output SHA-256 values and bounded findings with line
numbers and codes. It omits paths and titles. The **new playlist retains the original
comments/titles**, so it is not a privacy sanitizer. There are no runtime HTTP
requests, telemetry, caches or background services; mapped storage is accessed
through the host filesystem.

Default limits: 16 MiB playlist (`--max-bytes`), 100,000 media entries
(`--max-entries`), 50 finding details (`--max-findings`), 1 MiB map and 1,000 rules.
Suppressing details never suppresses detection. JSON duplicate keys and unknown
configuration keys are rejected.

| Exit | Meaning |
| --- | --- |
| 0 | Complete preview ready, or new output successfully written |
| 1 | One or more media entries failed resolution; nothing written |
| 2 | Invalid/unreadable input, limits, output conflict or publication failure |

## Development and uninstall

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests, lint, coverage, builds and an
isolated wheel-install demo. CI checks Linux, Windows and macOS and never commits.
[Report security issues privately](SECURITY.md).

Uninstall with `python -m pip uninstall playlist-relocate`. Deactivate and remove
its dedicated virtual environment to clean up all installed files. No global
configuration or media-library metadata is created.
