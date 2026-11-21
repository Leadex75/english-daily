from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TOKEN_NAMES = ("paper", "surface", "ink", "muted", "line", "accent", "accent_soft")
PAIRS = (
    ("body text", "ink", "paper", 4.5),
    ("card text", "ink", "surface", 4.5),
    ("secondary text", "muted", "paper", 4.5),
    ("secondary card text", "muted", "surface", 4.5),
    ("accent text", "accent", "paper", 4.5),
    ("accent pill text", "accent", "accent_soft", 4.5),
    ("inverted button text", "paper", "accent", 4.5),
    ("page border", "line", "paper", 3.0),
    ("card border", "line", "surface", 3.0),
)
_ROOT_RE = re.compile(r":root\s*\{(?P<body>.*?)\}", re.DOTALL)
_DARK_RE = re.compile(r':root\[data-theme="dark"\]\s*\{(?P<body>.*?)\}', re.DOTALL)
_PREFERS_RE = re.compile(
    r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root:not\(\[data-theme=\"light\"\]\)\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)


def parse_hex(value: str) -> tuple[float, float, float]:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", str(value).strip())
    if not match:
        raise ValueError(f"Invalid hex colour: {value!r}")
    digits = match.group(1)
    return tuple(int(digits[index:index + 2], 16) / 255 for index in (0, 2, 4))


def relative_luminance(value: str) -> float:
    channels = []
    for channel in parse_hex(value):
        linear = channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        channels.append(linear)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _tokens_from_block(block: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for name in TOKEN_NAMES:
        css_name = name.replace("_", "-")
        match = re.search(rf"--{re.escape(css_name)}\s*:\s*(#[0-9a-fA-F]{{6}})\s*;", block)
        if match:
            tokens[name] = match.group(1).lower()
    return tokens


def parse_theme_tokens(css: str) -> dict[str, dict[str, str]]:
    root = _ROOT_RE.search(css)
    dark = _DARK_RE.search(css)
    prefers = _PREFERS_RE.search(css)
    if not root or not dark or not prefers:
        raise ValueError("CSS must define root, explicit dark and prefers-dark token blocks")
    return {
        "light": _tokens_from_block(root.group("body")),
        "dark": _tokens_from_block(dark.group("body")),
        "dark_prefers": _tokens_from_block(prefers.group("body")),
    }


def audit_tokens(tokens: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for label, foreground, background, minimum in PAIRS:
        ratio = contrast_ratio(tokens[foreground], tokens[background])
        rows.append({
            "pair": label,
            "foreground": foreground,
            "background": background,
            "foreground_colour": tokens[foreground],
            "background_colour": tokens[background],
            "foreground_luminance": round(relative_luminance(tokens[foreground]), 4),
            "background_luminance": round(relative_luminance(tokens[background]), 4),
            "ratio": round(ratio, 2),
            "minimum": minimum,
            "pass": ratio + 1e-9 >= minimum,
        })
    return rows


def audit_css(css: str) -> dict[str, Any]:
    themes = parse_theme_tokens(css)
    rows = []
    for theme in ("light", "dark"):
        for row in audit_tokens(themes[theme]):
            rows.append({"theme": theme, **row})
    dark_matches = themes["dark"] == themes["dark_prefers"]
    return {
        "ok": dark_matches and all(row["pass"] for row in rows),
        "dark_definitions_match": dark_matches,
        "themes": themes,
        "rows": rows,
    }


def _format_table(report: dict[str, Any]) -> str:
    lines = ["theme  pair                     fg/bg                  ratio  min    result"]
    for row in report["rows"]:
        pair = f"{row['pair']:<24}"
        colours = f"{row['foreground_colour']}/{row['background_colour']:<16}"
        result = "PASS" if row["pass"] else "FAIL"
        lines.append(
            f"{row['theme']:<6} {pair} {colours} {row['ratio']:>5.2f}  {row['minimum']:>4.2f}  {result}"
        )
    status = "PASS" if report["ok"] else "FAIL"
    match = "yes" if report["dark_definitions_match"] else "no"
    lines.append("")
    lines.append(f"dark definitions match: {match}")
    lines.append(f"contrast audit: {status}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit WCAG contrast for theme custom properties")
    parser.add_argument("--css", default="static/style.css", help="CSS file to audit")
    parser.add_argument("--json", action="store_true", help="Emit a JSON report")
    args = parser.parse_args(argv)

    css = Path(args.css).read_text(encoding="utf-8")
    report = audit_css(css)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_format_table(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
