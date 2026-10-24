"""Map source path components without accessing the old filesystem."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

from . import __version__

MAX_BYTES = 16 * 1024 * 1024


class PlaylistError(ValueError):
    """Stable diagnostics exclude filenames, titles and playlist contents."""

    def __init__(self, code: str, side: str = "options"):
        self.code = code
        self.side = side
        super().__init__(f"{side}: {code}")


@dataclass(frozen=True)
class Mapping:
    source: PurePath
    target: Path


@dataclass(frozen=True)
class Plan:
    report: dict[str, Any]
    content: bytes | None
    output: Path


def _read(path: Path, limit: int, side: str) -> bytes:
    try:
        if not path.is_file():
            raise PlaylistError("not_regular_file", side)
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except PlaylistError:
        raise
    except (OSError, ValueError):
        raise PlaylistError("cannot_read", side) from None
    if len(data) > limit:
        raise PlaylistError("size_limit", side)
    return data


def _decode(data: bytes, side: str) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise PlaylistError("not_utf8", side) from None
    if any(unicodedata.category(char) == "Cc" and char not in "\r\n\t" for char in text):
        raise PlaylistError("control_character", side)
    return text


def _path(value: str, style: str, base: PurePath | None = None) -> PurePath:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PlaylistError("empty_or_ambiguous_path", "entry")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise PlaylistError("control_character", "entry")
    if style == "windows":
        if value.replace("/", "\\").startswith(("\\\\?\\", "\\\\.\\")):
            raise PlaylistError("device_namespace", "entry")
        cls = PureWindowsPath
    else:
        cls = PurePosixPath
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) and not (
        style == "windows" and re.match(r"^[A-Za-z]:[/\\]", value)
    ):
        raise PlaylistError("unsupported_uri_or_drive_relative", "entry")
    path = cls(value)
    if not path.is_absolute():
        if path.drive or path.root:
            raise PlaylistError("partially_rooted_path", "entry")
        if base is None:
            raise PlaylistError("relative_path_needs_source_base", "entry")
        path = base / path
    parts: list[str] = []
    for part in path.parts[1:]:
        if part == "..":
            if not parts:
                raise PlaylistError("source_root_escape", "entry")
            parts.pop()
        elif part != ".":
            if style == "windows" and (
                re.search(r'[<>:"|?*]', part)
                or part.endswith((".", " "))
                or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
            ):
                raise PlaylistError("invalid_windows_component", "entry")
            parts.append(part)
    return cls(path.anchor, *parts)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlaylistError("duplicate_json_key", "map")
        result[key] = value
    return result


def _config(path: Path) -> tuple[str, PurePath | None, list[Mapping], bytes]:
    raw = _read(path, 1024 * 1024, "map")
    try:
        value = json.loads(_decode(raw, "map"), object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, PlaylistError):
            raise
        raise PlaylistError("invalid_json", "map") from None
    allowed = {"version", "source_style", "source_base", "mappings"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise PlaylistError("invalid_config_keys", "map")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise PlaylistError("unsupported_config_version", "map")
    style = value.get("source_style")
    if not isinstance(style, str) or style not in {"windows", "posix"}:
        raise PlaylistError("invalid_source_style", "map")
    try:
        base = _path(value["source_base"], style) if "source_base" in value else None
    except PlaylistError as exc:
        raise PlaylistError(exc.code, "map") from None
    items = value.get("mappings")
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise PlaylistError("invalid_mappings", "map")
    mappings: list[Mapping] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"from", "to"}:
            raise PlaylistError("invalid_mapping_keys", "map")
        if not isinstance(item["to"], str) or not item["to"].strip():
            raise PlaylistError("invalid_target_root", "map")
        try:
            source = _path(item["from"], style)
            target = Path(item["to"])
            if not target.is_absolute():
                target = path.resolve().parent / target
            target = target.resolve(strict=True)
            if not target.is_dir():
                raise PlaylistError("target_root_not_directory", "map")
        except PlaylistError as exc:
            raise PlaylistError(exc.code, "map") from None
        except (OSError, RuntimeError, ValueError):
            raise PlaylistError("cannot_resolve_target_root", "map") from None
        if any(source == old.source for old in mappings):
            raise PlaylistError("duplicate_mapping_source", "map")
        mappings.append(Mapping(source, target))
    return style, base, mappings, raw


def plan_relocation(
    playlist: str | Path,
    mapping_file: str | Path,
    output: str | Path,
    *,
    absolute: bool = False,
    max_findings: int = 50,
    max_bytes: int = MAX_BYTES,
    max_entries: int = 100_000,
) -> Plan:
    """Preview a complete relocation. No output is created by this function."""
    if any(
        type(n) is not int or n < minimum
        for n, minimum in [(max_findings, 0), (max_bytes, 1), (max_entries, 1)]
    ):
        raise PlaylistError("invalid_limits")
    playlist, mapping_file, output = Path(playlist), Path(mapping_file), Path(output)
    if any(unicodedata.category(char) == "Cc" for char in str(output)):
        raise PlaylistError("invalid_output_path", "output")
    try:
        if output.exists() or output.is_symlink():
            raise PlaylistError("output_exists", "output")
        output = output.resolve()
        if output in {playlist.resolve(), mapping_file.resolve()}:
            raise PlaylistError("output_conflicts_input", "output")
        if output.exists() or output.is_symlink():
            raise PlaylistError("output_exists", "output")
        if not output.parent.is_dir():
            raise PlaylistError("output_parent_missing", "output")
    except PlaylistError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise PlaylistError("cannot_resolve_output", "output") from None
    style, base, mappings, map_bytes = _config(mapping_file)
    data = _read(playlist, max_bytes, "playlist")
    text = _decode(data, "playlist").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rewritten: list[str] = []
    findings: list[dict[str, Any]] = []
    targets: dict[tuple[int, int], PurePath] = {}
    entries = resolved = issue_count = 0
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            if line.upper().startswith("#EXT-X-"):
                raise PlaylistError("hls_not_supported", "playlist")
            rewritten.append(line)
            continue
        entries += 1
        if entries > max_entries:
            raise PlaylistError("entry_limit", "playlist")
        try:
            source = _path(line, style, base)
            choices = [
                (index, rule)
                for index, rule in enumerate(mappings)
                if source.is_relative_to(rule.source)
            ]
            if not choices:
                raise PlaylistError("unmapped_source", "entry")
            _index, rule = max(choices, key=lambda pair: len(pair[1].source.parts))
            suffix = source.relative_to(rule.source)
            if (
                os.name == "nt"
                and style == "posix"
                and any(
                    re.search(r'[\\<>:"|?*]', p) or p.endswith((".", " ")) for p in suffix.parts
                )
            ):
                raise PlaylistError("unsupported_target_component", "entry")
            try:
                target = rule.target.joinpath(*suffix.parts).resolve(strict=True)
            except (OSError, RuntimeError):
                raise PlaylistError("missing_target", "entry") from None
            if not target.is_relative_to(rule.target):
                raise PlaylistError("target_root_escape", "entry")
            if not target.is_file():
                raise PlaylistError("target_not_regular_file", "entry")
            try:
                target_stat = target.stat()
            except OSError:
                raise PlaylistError("cannot_stat_target", "entry") from None
            target_key = (target_stat.st_dev, target_stat.st_ino)
            if not target_stat.st_ino:
                raise PlaylistError("target_file_identity_unavailable", "entry")
            if target_key in targets and targets[target_key] != source:
                raise PlaylistError("target_collision", "entry")
            targets[target_key] = source
            if absolute:
                replacement = target.as_posix()
            else:
                try:
                    replacement = Path(os.path.relpath(target, output.parent)).as_posix()
                except ValueError:
                    raise PlaylistError("different_target_drive_use_absolute", "entry") from None
                if replacement.startswith("#") or re.match(r"^[A-Za-z][\w+.-]*:", replacement):
                    replacement = "./" + replacement
            if replacement != replacement.strip() or any(
                unicodedata.category(char) == "Cc" for char in replacement
            ):
                raise PlaylistError("unrepresentable_target_path", "entry")
            rewritten.append(replacement)
            resolved += 1
        except PlaylistError as exc:
            issue_count += 1
            if len(findings) < max_findings:
                findings.append({"line": number, "code": exc.code})
        except (OSError, ValueError, RuntimeError):
            issue_count += 1
            if len(findings) < max_findings:
                findings.append({"line": number, "code": "cannot_resolve_entry"})
    if not entries:
        raise PlaylistError("empty_playlist", "playlist")
    content = ("\n".join(rewritten) + "\n").encode("utf-8") if issue_count == 0 else None
    return Plan(
        {
            "schema_version": 1,
            "tool_version": __version__,
            "status": "ready" if issue_count == 0 else "blocked",
            "playlist_sha256": hashlib.sha256(data).hexdigest(),
            "map_sha256": hashlib.sha256(map_bytes).hexdigest(),
            "output_sha256": hashlib.sha256(content).hexdigest() if content is not None else None,
            "entries": entries,
            "resolved": resolved,
            "issue_count": issue_count,
            "findings": findings,
            "findings_truncated": issue_count > len(findings),
            "output_mode": "absolute" if absolute else "relative",
        },
        content,
        output,
    )


def write_plan(plan: Plan) -> dict[str, Any]:
    """Publish complete bytes through an atomic, no-clobber same-filesystem link."""
    if plan.content is None or plan.report["status"] != "ready":
        raise PlaylistError("plan_blocked", "output")
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".playlist-relocate-", dir=plan.output.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(plan.content)
            handle.flush()
            os.fsync(handle.fileno())
        # link() fails if output already exists; it never replaces another file.
        os.link(temporary, plan.output)
    except FileExistsError:
        raise PlaylistError("output_exists", "output") from None
    except OSError:
        raise PlaylistError("atomic_publish_failed", "output") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return {**plan.report, "status": "written"}
