"""Hand-check sheets for the judge of an eval run (#15): `docs/reference/eval-results.md`.

Interface stub.
"""

from pathlib import Path


def sheet(answers: Path, set_path: Path = Path("eval/questions.yaml"), out_dir: Path = Path("eval")) -> tuple[Path, Path]:
    """Write the sheet and its key; return their paths."""
    return out_dir / "sheet.me.md", out_dir / "key.me.md"


def score(sheet_path: Path) -> dict[str, tuple[int, int]]:
    """Per line kind (`cited`, `supported`, `correct`): (agreeing with the judge, graded)."""
    return {}


def main(argv: list[str] | None = None) -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
