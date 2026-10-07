"""Duplicated-code ratio for a source tree (stdlib only).

Lines are normalized (trimmed, inner whitespace collapsed). Lines that are empty or
consist only of punctuation are ignored. Every window of WINDOW consecutive significant
lines in a file is hashed; a line counts as duplicated when it belongs to a window whose
hash occurs at least twice (in the same file or across files).

    dup_ratio = duplicated significant lines / all significant lines
"""
from __future__ import annotations

import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

WINDOW = 5
EXTENSIONS = (".js", ".mjs", ".cjs", ".ts")
_TRIVIAL = re.compile(r"^[\s{}()\[\];,.]*$")


def significant_lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        norm = " ".join(line.split())
        if norm and not _TRIVIAL.match(norm):
            out.append(norm)
    return out


def dup_ratio(root: Path, extensions=EXTENSIONS, window: int = WINDOW) -> dict:
    files = sorted(p for p in Path(root).rglob("*") if p.suffix in extensions and p.is_file())
    lines_by_file = {p: significant_lines(p.read_text(encoding="utf-8", errors="replace"))
                     for p in files}
    windows = defaultdict(list)
    for path, lines in lines_by_file.items():
        for i in range(len(lines) - window + 1):
            key = hashlib.sha1("\n".join(lines[i:i + window]).encode()).hexdigest()
            windows[key].append((path, i))
    dup = defaultdict(set)
    for hits in windows.values():
        if len(hits) < 2:
            continue
        for path, i in hits:
            dup[path].update(range(i, i + window))
    total = sum(len(v) for v in lines_by_file.values())
    duplicated = sum(len(v) for v in dup.values())
    return {"total_lines": total, "duplicated_lines": duplicated,
            "dup_ratio": duplicated / total if total else 0.0,
            "files": {str(p.relative_to(root)): len(v) for p, v in dup.items()}}


if __name__ == "__main__":
    print(dup_ratio(Path(sys.argv[1])))
