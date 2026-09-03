"""
check_table_counts.py — Drift detector for the 45-table → 49-table reconciliation.

Scans the four canonical doc files for stale tokens that mention the old count
or class breakdown, and exits non-zero if any are found. The intent is to make
the 45 → 49 reconciliation permanent — if any of these docs ever drift back to
45 (or any of 24 / 9 / 12, which were the wrong class breakdowns for the legacy
ER), this script fails.

Canonical counts after reconciliation:
  - Total tables: 49
  - [V] versioned: 26
  - [L-E] events: 3
  - [L-W] workflows: 6
  - [L-S] sessions: 2
  - [A] append-only: 12

The old (pre-reconciliation) counts the script flags as stale:
  - "45 tables" / "AUDIT-FIRST (45" / "24 [V]" / "9 [L]" / "12 [A]"
  - "24 versioned" / "4 L-W" / "12 [A]" / "9 [L]" / "3 [L-E]" / "2 [L-S]" (legacy breakdown)

Usage:
  python openspec/scripts/check_table_counts.py [DOC_ROOT]

  DOC_ROOT defaults to ./openspec. Exit codes:
    0 = no drift detected
    1 = at least one stale token found
    2 = a target doc file is missing
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Canonical counts (post-reconciliation, ratified 2026-09-03).
CANONICAL = {
    "total": 49,
    "[V]": 26,
    "[L-E]": 3,
    "[L-W]": 6,
    "[L-S]": 2,
    "[A]": 12,
}

# Stale-token patterns (regex -> human description).
# We flag any mention of the old counts in the four reconciled docs. We do
# NOT flag mentions in code/comments outside those docs.
STALE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Total counts
    (re.compile(r"\b45\s*tables\b"), "stale '45 tables' (canonical: 49)"),
    (re.compile(r"\(45\s*tables?"), "stale '(45 tables' header (canonical: 49 tables)"),
    (re.compile(r"AUDIT-FIRST\s*\(45\b"), "stale 'AUDIT-FIRST (45' (canonical: 49)"),
    # Legacy [V] count
    (re.compile(r"\b24\s*\[V\]"), "stale '24 [V]' (canonical: 26)"),
    (re.compile(r"\b24\s+versioned\b"), "stale '24 versioned' (canonical: 26)"),
    # Legacy [L] total
    (re.compile(r"\b9\s*\[L\]"), "stale '9 [L]' (canonical: 11)"),
    # Legacy [L-W] count
    (re.compile(r"\b4\s*L-W\b"), "stale '4 L-W' (canonical: 6)"),
    (re.compile(r"\b4\s+workflow\b"), "stale '4 workflow' (canonical: 6)"),
    (re.compile(r"\(4\s*tables\)\s*\bworkflow\b"), "stale '(4 tables) workflow'"),
    # Legacy [A] count — also the canonical 12 happens to match; we don't flag 12 alone.
    # The pattern below catches only the combined "(12 [A])" with wrong siblings.
    (re.compile(r"\b12\s*\[A\].*\b24\b|\b24\b.*\b12\s*\[A\]"), "stale combined (24 [V] / 12 [A]) breakdown"),
]

# Doc files the script scans. Each path is relative to DOC_ROOT.
TARGET_DOCS = [
    "PROJECT_CONTEXT.md",
    "_meta/roadmap.md",
    "_meta/iteration-plan.md",
    "config.yaml",
]


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return a list of (line_number, line_text, pattern_description) for each
    stale token found in `path`. line_text is stripped and truncated."""
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, description in STALE_PATTERNS:
            if pattern.search(line):
                findings.append((lineno, line.strip()[:160], description))
    return findings


def main(argv: list[str]) -> int:
    doc_root = Path(argv[1]) if len(argv) > 1 else Path("./openspec")
    if not doc_root.is_dir():
        print(f"ERROR: doc root not found: {doc_root}", file=sys.stderr)
        return 2

    print(f"Scanning {doc_root} for stale 45-table tokens...")
    print(f"Canonical: total={CANONICAL['total']}, [V]={CANONICAL['[V]']}, "
          f"[L-E]={CANONICAL['[L-E]']}, [L-W]={CANONICAL['[L-W]']}, "
          f"[L-S]={CANONICAL['[L-S]']}, [A]={CANONICAL['[A]']}")
    print()

    total_findings = 0
    missing_files: list[str] = []
    for rel in TARGET_DOCS:
        path = doc_root / rel
        if not path.is_file():
            missing_files.append(rel)
            continue
        findings = scan_file(path)
        if findings:
            print(f"STALE: {rel}")
            for lineno, text, desc in findings:
                print(f"  line {lineno}: {desc}")
                print(f"    > {text}")
            total_findings += len(findings)

    if missing_files:
        print()
        print(f"ERROR: missing target files: {missing_files}", file=sys.stderr)
        return 2

    print()
    if total_findings == 0:
        print("OK: no drift detected. Docs reflect canonical 49 / 26 [V] / 3 [L-E] / 6 [L-W] / 2 [L-S] / 12 [A].")
        return 0

    print(f"FAIL: {total_findings} stale token(s) found across {len(TARGET_DOCS)} docs.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
