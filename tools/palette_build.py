from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contrast_check import audit_css

PALETTES: dict[str, dict[str, str]] = {
    "paper": {
        "paper": "#fbfaf7",
        "surface": "#ffffff",
        "ink": "#23221f",
        "muted": "#635f58",
        "line": "#8c887e",
        "accent": "#9b422c",
        "accent_soft": "#f3e8e3",
        "shadow": "0 1px 2px rgba(30, 25, 20, 0.04)",
    },
    "ink": {
        "paper": "#171817",
        "surface": "#1e201e",
        "ink": "#ece9e2",
        "muted": "#b8b4ab",
        "line": "#71756c",
        "accent": "#df9077",
        "accent_soft": "#3a2b25",
        "shadow": "none",
    },
    "sepia": {
        "paper": "#f6f0e4",
        "surface": "#fffaf0",
        "ink": "#2c241b",
        "muted": "#5f5548",
        "line": "#8a7865",
        "accent": "#8a3f24",
        "accent_soft": "#efded0",
        "shadow": "0 1px 2px rgba(57, 42, 25, 0.06)",
    },
    "contrast": {
        "paper": "#ffffff",
        "surface": "#ffffff",
        "ink": "#000000",
        "muted": "#1a1a1a",
        "line": "#000000",
        "accent": "#72001e",
        "accent_soft": "#ffe4e9",
        "shadow": "none",
    },
}

PRESET_ORDER = ("paper", "sepia", "ink", "contrast")
SCHEMES = {"paper": "light", "sepia": "light", "ink": "dark", "contrast": "light"}


def _block(selector: str, palette: dict[str, str], scheme: str) -> str:
    lines = [f"{selector} {{", f"  color-scheme: {scheme};"]
    for name in ("paper", "surface", "ink", "muted", "line", "accent", "accent_soft", "shadow"):
        css_name = name.replace("_", "-")
        lines.append(f"  --{css_name}: {palette[name]};")
    lines.append("}")
    return "\n".join(lines)


def build_css() -> str:
    blocks = [
        _block(f':root[data-theme="{name}"]', PALETTES[name], SCHEMES[name])
        for name in PRESET_ORDER
    ]
    blocks.append(
        "@media (prefers-color-scheme: light) {\n"
        + _block(':root[data-theme="system"]', PALETTES["paper"], "light")
        + "\n}"
    )
    blocks.append(
        "@media (prefers-color-scheme: dark) {\n"
        + _block(':root[data-theme="system"]', PALETTES["ink"], "dark")
        + "\n}"
    )
    return "\n\n".join(blocks) + "\n"


def audit_palettes(css: str | None = None) -> dict[str, Any]:
    return audit_css(css or build_css())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and audit the English Daily theme palettes")
    parser.add_argument("--out", default="static/css/themes.css", help="generated CSS file")
    parser.add_argument("--check", action="store_true", help="check that the committed CSS is current and accessible")
    args = parser.parse_args(argv)

    generated = build_css()
    report = audit_palettes(generated)
    if not report["ok"]:
        failures = [row for row in report["rows"] if not row["pass"]]
        for row in failures:
            print(f"FAIL {row['theme']} {row['pair']}: {row['ratio']:.2f} < {row['minimum']:.2f}")
        return 1

    if args.check:
        target = Path(args.out)
        if not target.is_absolute():
            target = ROOT / target
        if not target.is_file() or target.read_text(encoding="utf-8") != generated:
            print("Theme CSS is missing or out of date; run palette_build.py without --check")
            return 1
        print("theme palette check: PASS")
        return 0

    target = Path(args.out)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated, encoding="utf-8")
    print(f"Wrote {target}")
    print(f"contrast audit: {len(report['rows'])} pairs PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
