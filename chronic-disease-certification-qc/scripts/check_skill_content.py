#!/usr/bin/env python3
"""Scan supported Skill text files for externally supplied forbidden terms.

ASCII identifier-like terms use ``[A-Za-z0-9_-]`` as identifier characters, so
they only match when neither adjacent character is an identifier character.
Other terms use literal, case-insensitive substring matching. Terms are stripped,
empty values are ignored, and case-insensitive duplicates retain the first spelling.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {".md", ".py", ".html", ".yaml", ".yml", ".json", ".txt", ".css", ".js"}
_IGNORED_NAMES = {".git", "__pycache__", ".DS_Store"}
_ASCII_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


class ScanError(ValueError):
    """A controlled scanner input error suitable for command-line reporting."""


def _normalized_terms(forbidden_terms):
    normalized = []
    seen = set()
    for supplied_term in forbidden_terms:
        if not isinstance(supplied_term, str):
            raise ScanError("forbidden terms must be strings")
        term = supplied_term.strip()
        if not term:
            continue
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(term)
    return sorted(normalized, key=lambda term: (term.casefold(), term))


def _patterns(forbidden_terms):
    patterns = []
    for term in _normalized_terms(forbidden_terms):
        escaped = re.escape(term)
        if _ASCII_IDENTIFIER.fullmatch(term):
            escaped = rf"(?<![A-Za-z0-9_-]){escaped}(?![A-Za-z0-9_-])"
        patterns.append((term, re.compile(escaped, re.IGNORECASE)))
    return patterns


def _match_location(text, offset):
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def _validated_root(root):
    candidate = Path(root)
    if candidate.is_symlink():
        raise ScanError("root must not be a symlink")
    if not candidate.exists():
        raise ScanError("root does not exist")
    if not candidate.is_dir():
        raise ScanError("root must be a directory")
    return candidate.resolve()


def _walk_error(error):
    raise ScanError("cannot traverse root") from error


def scan(root: Path, forbidden_terms):
    """Return ordered, actionable matches beneath ``root`` without following links."""
    root_path = _validated_root(root)
    patterns = _patterns(forbidden_terms)
    matches = []

    try:
        for directory, directory_names, file_names in os.walk(
            root_path, followlinks=False, onerror=_walk_error
        ):
            directory_path = Path(directory)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in _IGNORED_NAMES
                and not (directory_path / name).is_symlink()
            )
            for file_name in sorted(file_names):
                if file_name in _IGNORED_NAMES:
                    continue
                path = directory_path / file_name
                if path.is_symlink() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError as error:
                    raise ScanError("cannot read supported file") from error
                relative_path = path.relative_to(root_path).as_posix()
                for term, pattern in patterns:
                    for occurrence in pattern.finditer(text):
                        line, column = _match_location(text, occurrence.start())
                        matches.append(
                            {
                                "path": relative_path,
                                "term": term,
                                "line": line,
                                "column": column,
                            }
                        )
    except OSError as error:
        raise ScanError("cannot traverse root") from error
    matches.sort(
        key=lambda match: (
            match["path"],
            match["line"],
            match["column"],
            match["term"].casefold(),
            match["term"],
        )
    )
    return matches


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--forbid", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.forbid:
        parser.error("at least one --forbid term is required")
    try:
        matches = scan(Path(args.root), args.forbid)
    except (OSError, ScanError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(matches, ensure_ascii=False) + "\n")
    return 1 if matches else 0


if __name__ == "__main__":
    raise SystemExit(main())
