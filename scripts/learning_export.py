"""Export only portable observation files; excludes model weights and training samples."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.run_dir).resolve()
    output = Path(args.output).resolve()
    allowed = {
        "training_run.json",
        "training_events.jsonl",
        "trainer_state.json",
        "eval_comparison.csv",
        "eval_comparison_3way.csv",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name in allowed:
                if not path.resolve().is_relative_to(root):
                    raise ValueError("Observation file escapes run directory")
                archive.write(path, str(Path(root.name) / path.relative_to(root)))
    print(f"Observation bundle saved: {output}")


if __name__ == "__main__":
    main()
