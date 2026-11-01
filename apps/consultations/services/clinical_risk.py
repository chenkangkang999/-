from __future__ import annotations

import hashlib
import json
import math
import re

from apps.consultations.services.clinical_evidence import (
    boolean,
    citation,
    normalize,
    patient_facts,
    policy,
    project_path,
    status_text,
)


def numeric(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:岁)?\s*", value)
        if not match:
            return None
        value = match.group(1)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def sex(value, rules):
    return next((key for key, aliases in rules["tokens"]["sex_aliases"].items() if normalize(value) in [normalize(item) for item in aliases]), None)


def framingham(values, rules):
    spec = rules["framingham"]
    path = project_path(spec["artifact"])
    if not path.is_file():
        return {"status": "not_connected", "risk_fraction": None}
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        return {"status": "unverified_model", "risk_fraction": None}
    model = json.loads(raw)
    result = {"model_id": model["id"], "version": model["version"], "endpoint": model["endpoint"], "population": model["population"], "units": model["units"], "limitations": model["limitations"], "source": model["source"], "artifact_sha256": spec["sha256"], "risk_fraction": None}
    if model["kind"] != "framingham2008_lipids_cox":
        return {**result, "status": "unsupported_model"}
    missing = [field for field in model["required"] if values.get(field) is None or values.get(field) == ""]
    if missing:
        return {**result, "status": "insufficient_data", "missing_fields": missing}
    age = numeric(values["age"])
    group = sex(values["sex"], rules)
    flags = {key: boolean(values[key], rules) for key in ("bp_treated", "current_smoker", "diabetes", "prior_cvd")}
    if group not in model["models"] or age is None or any(value is None for value in flags.values()):
        return {**result, "status": "invalid_input"}
    if not model["population"]["minimum_age"] <= age <= model["population"]["maximum_age"] or flags["prior_cvd"]:
        return {**result, "status": "outside_population"}
    if normalize(values["cholesterol_unit"]) != normalize(model["units"]["total_cholesterol"]):
        return {**result, "status": "unit_mismatch"}
    numbers = {key: numeric(values[key]) for key in model["technical_ranges"]}
    if any(value is None or not model["technical_ranges"][key][0] <= value <= model["technical_ranges"][key][1] for key, value in numbers.items()):
        return {**result, "status": "invalid_input"}
    coefficients = model["models"][group]
    if not all(isinstance(value, (float, int)) and math.isfinite(value) for value in coefficients.values()) or not 0 < coefficients["baseline_survival"] < 1:
        return {**result, "status": "invalid_model"}
    linear = coefficients["age"] * math.log(age)
    linear += sum(coefficients[key] * math.log(numbers[key]) for key in ("total_cholesterol", "hdl_cholesterol"))
    linear += coefficients["systolic_treated" if flags["bp_treated"] else "systolic_untreated"] * math.log(numbers["systolic_bp"])
    linear += sum(coefficients[key] * int(flags[key]) for key in ("current_smoker", "diabetes"))
    exponent = linear - coefficients["mean_linear_predictor"]
    try:
        risk = -math.expm1(math.log(coefficients["baseline_survival"]) * math.exp(exponent))
    except OverflowError:
        return {**result, "status": "invalid_input"}
    return {**result, "status": "calculated", "risk_fraction": round(risk, 8), "risk_percent": round(risk * 100, 4), "locally_calibrated": False, "diagnostic_probability": False}


def news2(values, rules):
    spec = rules["news2"]
    result = {"version": spec["version"], "source": spec["source"], "disclaimer": spec["disclaimer"], "level_mapping_note": spec.get("level_mapping_note", ""), "score": None, "components": {}, "risk_level": None}
    age = numeric(values.get("age"))
    pregnancy = boolean(values.get("pregnancy"), rules)
    if (age is not None and age < spec["minimum_age"]) or pregnancy is True or boolean(values.get("hypercapnic_respiratory_failure"), rules) is True:
        return {**result, "status": "outside_population"}
    missing = [field for field in spec["required"] if values.get(field) is None or values.get(field) == ""]
    if age is None:
        missing.append("age")
    if sex(values.get("sex"), rules) != "male" and pregnancy is None:
        missing.append("pregnancy")
    for key, bounds in spec["technical_ranges"].items():
        if values.get(key) is not None:
            value = numeric(values[key])
            if value is None or not bounds[0] <= value <= bounds[1] or (key != "temperature" and not value.is_integer()):
                return {**result, "status": "invalid_input", "invalid_field": key}
            value = round(value, 1) if key == "temperature" else value
            score = next((score for maximum, score in spec["bands"][key] if maximum is None or value <= maximum), None)
            result["components"][key] = score
    oxygen = boolean(values.get("supplemental_oxygen"), rules)
    consciousness = spec["consciousness"].get(values.get("consciousness"))
    if values.get("supplemental_oxygen") is not None and oxygen is None:
        return {**result, "status": "invalid_input", "invalid_field": "supplemental_oxygen"}
    if values.get("consciousness") is not None and consciousness is None:
        return {**result, "status": "invalid_input", "invalid_field": "consciousness"}
    if oxygen is not None:
        result["components"]["supplemental_oxygen"] = spec["oxygen_score"] if oxygen else 0
    if consciousness is not None:
        result["components"]["consciousness"] = consciousness
    if missing:
        observed_warning = spec["single_red_level"] if any(score >= spec["single_red_score"] for score in result["components"].values()) else None
        return {**result, "status": "insufficient_data", "missing_fields": missing, "observed_warning_level": observed_warning}
    total = sum(result["components"].values())
    level = next(item["risk_level"] for item in spec["levels"] if total >= item["minimum"])
    if level == "low" and max(result["components"].values()) >= spec["single_red_score"]:
        level = spec["single_red_level"]
    return {**result, "status": "calculated", "score": total, "risk_level": level, "care_path": spec["care_paths"][level]}


def emergency_flags(context, text, rules):
    for key in ("_screened_red_flags", "red_flags"):
        if key in context.facts:
            return list(context.facts[key])
    if context.facts.get("intake", {}).get("intent") == "education":
        return []
    from apps.consultations.services.intake import policy as intake_policy
    from apps.consultations.services.intake import red_flags
    screen = {**intake_policy(), "red_flag_patterns": rules["emergency"]["patterns"]}
    return red_flags(text, screen)


def assess_risk(context, text):
    rules = policy()
    values = patient_facts(context)
    flags = emergency_flags(context, text, rules)
    acute, chronic = news2(values, rules), framingham(values, rules)
    level = "critical" if flags else (acute.get("risk_level") or acute.get("observed_warning_level") or "low")
    provisional = not flags and acute["status"] != "calculated"
    action = rules["emergency"]["action"] if level == "critical" else (acute.get("care_path") or (rules["news2"]["care_paths"][level] if acute.get("observed_warning_level") else "缺少足够生命体征，不能确认低风险；请结合线下临床评估，症状加重及时就医"))
    citations = [citation(rules["news2"]["source"])]
    if chronic.get("source"):
        citations.append(citation(chronic["source"], chronic["model_id"]))
    if flags:
        citations.append(citation(rules["emergency"]["reference"]))
    from apps.consultations.services.clinical_schema import input_schema
    labels = {item["id"]: item["label"] for item in input_schema()["fields"]}
    missing = "、".join(labels.get(field, "年龄" if field == "age" else field) for field in chronic.get("missing_fields", []))
    content = f"风险审核：{action}\n生命体征评估：{status_text(acute['status'], rules)}，NEWS2总分：{acute['score'] if acute['score'] is not None else '未计算'}。"
    content += (f"\n原始FHS研究公式的10年一般心血管病风险：{chronic['risk_percent']}%；不是诊断概率，未作本地校准。" if chronic["status"] == "calculated" else f"\n慢病风险未计算：{status_text(chronic['status'], rules)}；缺少资料：{missing or '请核对适用范围与输入'}。")
    metadata = {"risk_level": level, "risk_level_is_provisional": provisional, "red_flags": flags, "care_path": action, "news2": acute, "chronic_risk": chronic, "data_status": {"news2": acute["status"], "framingham": chronic["status"]}, "diagnostic_opinions": [], "requires_doctor": True}
    return content, metadata, [item for item in citations if item]
