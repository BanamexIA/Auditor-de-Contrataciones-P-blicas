from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm.base import ROOT
from telemetry.tracking import export_llm_calls_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Export LLM telemetry records to CSV.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "telemetry" / "results" / "llm_calls_export.csv",
    )
    args = parser.parse_args()
    exported = export_llm_calls_csv(args.output)
    print(json.dumps({"exported_calls": exported, "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
