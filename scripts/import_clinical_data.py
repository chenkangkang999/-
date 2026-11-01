"""Rebuild the configured structured drug evidence index without guessing missing data."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="导入已配置的NMPA/DDInter/人工审校药品证据")
    parser.add_argument("--policy", help="可信管理员提供的配置文件路径")
    args = parser.parse_args()
    if args.policy:
        os.environ["CLINICAL_DATA_POLICY_PATH"] = args.policy
    from apps.consultations.services.clinical_evidence import import_evidence
    print(json.dumps(import_evidence(), ensure_ascii=False))


if __name__ == "__main__":
    main()
