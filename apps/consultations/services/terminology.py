"""Explicit terminology and calibrated-probability ports, never invented codes."""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path

import yaml
from django.conf import settings
from django.utils.module_loading import import_string


def triage_config():
    path = Path(os.getenv("TRIAGE_CONFIG_PATH", "configs/triage.yaml"))
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    result = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or not 1 <= int(result["top_n"]) <= 20:
        raise ValueError("INVALID_TRIAGE_CONFIGURATION")
    return result


def standardize(symptoms, cfg):
    path = Path(cfg["coding_catalog"])
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    if not path.is_file():
        return {"status": "not_connected", "concepts": [], "unmapped": list(symptoms),
                "note": "未导入授权术语表，未编造ICD-11/SNOMED CT编码；ICD-10不能替代它们。"}
    terms = {item.casefold(): item for item in symptoms}
    concepts = []
    mapped = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"system", "code", "name", "source"}.issubset(reader.fieldnames or []):
            raise ValueError("INVALID_TERMINOLOGY_CATALOG")
        for row in reader:
            if row["system"] not in cfg["coding_systems"]:
                continue
            aliases = {row["name"].strip().casefold(), *(a.strip().casefold() for a in row.get("synonyms", "").split("|"))}
            for value in terms.keys() & aliases:
                if not row["code"].strip() or not row["source"].strip():
                    continue
                concepts.append({"term": terms[value], "system": row["system"], "code": row["code"], "name": row["name"], "source": row["source"], "version": row.get("version", "")})
                mapped.add(value)
    return {"status": "connected", "concepts": concepts, "unmapped": [v for k, v in terms.items() if k not in mapped],
            "note": "仅采用已导入表中的精确名称或别名匹配；不推断未命中编码。"}


def probabilities(context, candidates, cfg):
    provider = cfg.get("probability_provider")
    if not provider:
        return {"status": "not_calibrated", "values": [None] * len(candidates),
                "note": "未接入经过校准的诊断概率模型；排序是待医师核验的鉴别线索，不输出猜测百分比。"}
    result = import_string(provider)().predict(context=context, candidates=candidates)
    values = result.get("probabilities", [])
    required = ("model_id", "calibration_reference", "population", "model_sha256")
    if not all(isinstance(result.get(key), str) and result[key].strip() for key in required):
        raise ValueError("UNCALIBRATED_PROBABILITY_PROVIDER")
    if len(values) != len(candidates) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values) or sum(values) > 1.000001:
        raise ValueError("INVALID_DIAGNOSIS_PROBABILITIES")
    return {"status": "external_calibrated_provider", "values": values, **{key: result[key] for key in required},
            "note": "外部模型的适用人群、校准依据与模型版本必须另行审核；不把大模型主观分数称为概率。"}
