#!/usr/bin/env python3
"""Data integrity audit — enforces the rules in CLAUDE.md "Data Integrity":

  1. No fake / mock / synthetic data in src/
  2. No lookahead bias (centered windows, negative shifts, future-named state)

Run from the project root:

    python scripts/audit_data_integrity.py            # hard checks only
    python scripts/audit_data_integrity.py --strict   # also require backtester
                                                      # functions to document
                                                      # their point-in-time
                                                      # guarantee in a docstring

Exit code is 0 when clean, 1 when any violation is found.

Suppressing a false positive: add a trailing comment on the offending line:

    bad_line  # audit: allow fake-data
    bad_line  # audit: allow lookahead

Suppress everything in a file by putting the marker at module level:

    # audit: allow file

Test fixtures live in tests/ and are not scanned.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

# Per-line regex checks. Each rule is (rule_id, category, compiled_regex, description).
LINE_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "fake-data",
        "fake-data",
        re.compile(r"\b(?:random|np\.random|numpy\.random)\.(?:random|uniform|randint|choice|sample|gauss|normal|rand|randn|standard_normal)\b"),
        "use of a random number generator to produce data",
    ),
    (
        "fake-data",
        "fake-data",
        re.compile(r"\b(?:Mock|MagicMock|AsyncMock)\s*\("),
        "Mock object instantiated in src/",
    ),
    (
        "fake-data",
        "fake-data",
        re.compile(r"^\s*(?:from|import)\s+unittest(?:\.mock)?\b"),
        "unittest/unittest.mock imported in src/",
    ),
    (
        "fake-data",
        "fake-data",
        re.compile(r"\bfrom\s+faker\b|\bimport\s+faker\b|\bFaker\s*\("),
        "Faker library used in src/",
    ),
    (
        "lookahead",
        "lookahead",
        re.compile(r"\.(?:rolling|ewm|expanding)\([^)]*\bcenter\s*=\s*True"),
        "centered window peeks at future bars",
    ),
    (
        "lookahead",
        "lookahead",
        re.compile(r"\.shift\(\s*-\s*\d+"),
        "negative .shift(...) pulls future values into the present",
    ),
]

# Identifier-substring checks (AST-based, so we only flag real names — not strings or comments).
FAKE_DATA_NAME_SUBSTRINGS = ("fake_", "dummy_", "synthetic_", "fabricated_")
LOOKAHEAD_NAME_SUBSTRINGS = ("future_", "lookahead", "look_ahead", "peek_future")

# Backtester docstrings must mention one of these phrases under --strict.
POINT_IN_TIME_PHRASES = ("point-in-time", "point in time", "no lookahead", "no look-ahead")
BACKTESTER_REL_PATH = Path("analysis") / "backtester.py"

ALLOW_LINE_RE = re.compile(r"#\s*audit:\s*allow(?:\s+(\S+))?")
ALLOW_FILE_MARKER = "audit: allow file"


@dataclass(frozen=True)
class Finding:
    rule: str
    category: str  # "fake-data" | "lookahead" | "docstring"
    path: Path
    line: int
    snippet: str
    detail: str


def iter_src_files() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def line_is_allowed(line: str, category: str) -> bool:
    """A line is exempt if it carries `# audit: allow` or `# audit: allow <category>`."""
    m = ALLOW_LINE_RE.search(line)
    if m is None:
        return False
    scope = m.group(1)
    return scope is None or scope == category


def file_is_allowed(text: str) -> bool:
    return ALLOW_FILE_MARKER in text


def scan_lines(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        # Strip out string literals so a regex doesn't fire on log messages /
        # docstrings / column headers that happen to contain "Mock(" etc.
        stripped = re.sub(r"(?:'''.*?'''|\"\"\".*?\"\"\"|'[^']*'|\"[^\"]*\")", "", raw)
        for rule_id, category, pattern, detail in LINE_RULES:
            if pattern.search(stripped) and not line_is_allowed(raw, category):
                findings.append(
                    Finding(
                        rule=rule_id,
                        category=category,
                        path=path,
                        line=lineno,
                        snippet=raw.strip()[:120],
                        detail=detail,
                    )
                )
    return findings


def scan_identifiers(path: Path, tree: ast.AST, source_lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    def report(category: str, detail: str, lineno: int) -> None:
        if lineno < 1 or lineno > len(source_lines):
            return
        raw = source_lines[lineno - 1]
        if line_is_allowed(raw, category):
            return
        findings.append(
            Finding(
                rule=category,
                category=category,
                path=path,
                line=lineno,
                snippet=raw.strip()[:120],
                detail=detail,
            )
        )

    for node in ast.walk(tree):
        names: list[tuple[str, int]] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append((node.name, node.lineno))
        elif isinstance(node, ast.arg):
            names.append((node.arg, node.lineno))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            names.append((node.attr, node.lineno))

        for ident, lineno in names:
            lower = ident.lower()
            for marker in FAKE_DATA_NAME_SUBSTRINGS:
                if marker in lower:
                    report("fake-data", f"identifier '{ident}' suggests fabricated data", lineno)
                    break
            for marker in LOOKAHEAD_NAME_SUBSTRINGS:
                if marker in lower:
                    report("lookahead", f"identifier '{ident}' suggests forward-looking state", lineno)
                    break

    return findings


def scan_backtester_docstrings(path: Path, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        doc = ast.get_docstring(node) or ""
        if not any(phrase in doc.lower() for phrase in POINT_IN_TIME_PHRASES):
            findings.append(
                Finding(
                    rule="docstring",
                    category="docstring",
                    path=path,
                    line=node.lineno,
                    snippet=f"def {node.name}(...)",
                    detail="backtester function missing point-in-time guarantee in docstring",
                )
            )
    return findings


def audit(strict: bool) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_src_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if file_is_allowed(text):
            continue

        findings.extend(scan_lines(path, text))

        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            findings.append(
                Finding(
                    rule="syntax",
                    category="syntax",
                    path=path,
                    line=1,
                    snippet="",
                    detail="file failed to parse — audit could not inspect identifiers",
                )
            )
            continue

        findings.extend(scan_identifiers(path, tree, text.splitlines()))

        if strict and path.relative_to(SRC_ROOT) == BACKTESTER_REL_PATH:
            findings.extend(scan_backtester_docstrings(path, tree))

    return findings


def render(findings: list[Finding]) -> str:
    if not findings:
        return ""
    out: list[str] = []
    for f in findings:
        rel = f.path.relative_to(SRC_ROOT.parent)
        prefix = f"{rel}:{f.line}"
        out.append(f"FAIL {prefix:<48} [{f.category}] {f.detail}")
        if f.snippet:
            out.append(f"     {f.snippet}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also require every public function in src/analysis/backtester.py to document its point-in-time guarantee",
    )
    args = parser.parse_args()

    if not SRC_ROOT.is_dir():
        print(f"audit: src/ not found at {SRC_ROOT}", file=sys.stderr)
        return 2

    findings = audit(strict=args.strict)
    output = render(findings)

    if findings:
        print(output)
        print()
        print(f"{len(findings)} violation(s) — see CLAUDE.md > Data Integrity")
        return 1

    print("OK — no fake-data or lookahead violations found in src/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
