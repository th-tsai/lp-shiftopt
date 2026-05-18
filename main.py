"""
Producti-Co Ltd Production and Schedule Planning
"""

from pathlib import Path

from src.data import ShiftOptRawData
from src.model import ShiftOpt
from src.utils import print_results


def main() -> None:
    data_dir = Path("data")
    for case_dir in sorted(data_dir.iterdir()):
        toml_path = case_dir / "data.toml"
        if not toml_path.exists():
            continue
        raw = ShiftOptRawData.load_from_toml(toml_path)
        solution = ShiftOpt(raw.structured()).solve()
        result = print_results(solution, label=raw.description or case_dir.name)
        if raw.result is not None:
            raw.result.parent.mkdir(parents=True, exist_ok=True)
            raw.result.write_text(result, encoding="utf-8")



if __name__ == "__main__":
    main()
