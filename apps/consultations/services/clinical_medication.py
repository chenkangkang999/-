from __future__ import annotations

import itertools
import json
import re

from apps.consultations.services.clinical_evidence import (
    boolean,
    citation,
    evidence_store,
    normalize,
    patient_facts,
    policy,
    resolve_name,
    status_text,
    tokens,
)
from apps.consultations.services.clinical_risk import numeric


def medication_audit(context, text):
    rules, values = policy(), patient_facts(context)
    current = tokens(values.get("current_medications"), rules)
    allergies = tokens(values.get("allergies"), rules)
    allergies = [re.sub(rules["tokens"]["allergy_suffix_pattern"], "", re.sub(rules["tokens"]["allergy_prefix_pattern"], "", item)).strip() for item in allergies if not re.fullmatch(rules["tokens"]["allergy_negative_pattern"], item)]
    requested = tokens(context.facts.get("requested_medications"), rules)
    missing = [key for key in ("allergies", "current_medications") if values.get(key) is None or normalize(values.get(key)) in {normalize(x) for x in rules["tokens"]["unknown_values"]}]
    if len(current) + len(requested) > rules["tokens"].get("max_medications", 30):
        return "待核对药物数量超过配置上限，请由临床药师逐项核对。", {"requires_doctor": True, "data_status": {"screening": "insufficient_data"}, "contraindications": [], "blocked_drugs": [], "diagnostic_opinions": []}, []
    contraindications, interactions, options, citations, unresolved, checks = [], [], [], [], [], []
    blocked_ids = set()
    special = {field: boolean(values.get(field), rules) for field in rules["tokens"]["special_fields"]}
    age = numeric(values.get("age"))
    special["pediatric"] = age < rules["tokens"]["pediatric_age"] if age is not None else None
    with evidence_store(rules) as (connection, statuses):
        status = {key: item["status"] for key, item in statuses.items()}
        canonical = {}
        if connection:
            for name in current + requested:
                drug = resolve_name(connection, name)
                if drug is None:
                    unresolved.append(name)
                else:
                    canonical[drug] = name
            labels = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM labels")]
            patient_text = normalize(text + " " + str(values.get("chronic_conditions", "")) + " " + str(context.facts.get("chief_complaint", "")))
            for entry in labels:
                drug = resolve_name(connection, entry["drug_name"])
                relevant_condition = any(normalize(term) in patient_text for term in entry.get("condition_terms", []) if term)
                if not relevant_condition and drug not in canonical:
                    continue
                source_citation = citation(entry["source"], entry["id"])
                if source_citation:
                    citations.append(source_citation)
                problems = []
                allergy_terms = [entry["drug_name"], *entry.get("aliases", []), *entry.get("allergen_terms", [])]
                for allergy in allergies:
                    # Exact normalized label/group terms; never infer class allergies from an LLM.
                    if normalize(allergy) in {normalize(term) for term in allergy_terms}:
                        problems.append({"drug": entry["drug_name"], "reason": "与已报告过敏原匹配", "field": "allergies", "source_id": entry["id"]})
                for condition in entry.get("contraindications", []):
                    field = condition.get("field")
                    actual = special.get(field) if field in special else values.get(field)
                    expected = condition.get("equals")
                    if actual is not None and (actual == expected or (isinstance(actual, str) and isinstance(expected, str) and normalize(actual) == normalize(expected))):
                        problems.append({"drug": entry["drug_name"], "reason": condition.get("reason", "来源条目列为禁忌"), "field": field, "source_id": entry["id"]})
                population_checks = []
                for population, observed in special.items():
                    if observed is False:
                        continue
                    evidence = entry.get("special_populations", {}).get(population)
                    item = {"drug": entry["drug_name"], "population": population, "patient_status": "present" if observed is True else "unknown", "status": evidence.get("status", "requires_doctor") if evidence else "not_available", "note": evidence.get("note", "未有该特殊人群的已审校资料，不能生成剂量") if evidence else "未有该特殊人群的已审校资料，不能生成剂量", "dose_status": "withheld_requires_clinician"}
                    population_checks.append(item)
                    if observed is True and item["status"] == "contraindicated":
                        problems.append({"drug": entry["drug_name"], "reason": item["note"], "field": population, "source_id": entry["id"]})
                checks.extend(population_checks)
                contraindications.extend(problems)
                if relevant_condition and not problems:
                    education = [value for value in entry.get("education", []) if isinstance(value, str) and not re.search(rules["tokens"]["dose_pattern"], value)]
                    adverse = [value for value in entry.get("adverse_effects", []) if isinstance(value, str) and not re.search(rules["tokens"]["dose_pattern"], value)]
                    options.append({"drug_name": entry["drug_name"], "canonical_drug": drug, "line": entry.get("line", "not_specified"), "condition_terms": entry.get("condition_terms", []), "education": education, "adverse_effects": adverse, "source_id": entry["id"], "requires_doctor": True, "dose_status": "withheld_requires_clinician"})
                    if drug:
                        canonical.setdefault(drug, entry["drug_name"])
            if status.get("ddi") == "connected":
                for first, second in itertools.combinations(sorted(canonical), 2):
                    record = connection.execute("SELECT severity,description,source_id FROM interactions WHERE drug_a=? AND drug_b=?", tuple(sorted((first, second)))).fetchone()
                    if record:
                        description = record["description"]
                        if re.search(rules["tokens"]["dose_pattern"], description):
                            description = "相互作用详情含剂量信息，需由医生或药师核对原始资料"
                        interactions.append({"drugs": [canonical[first], canonical[second]], "severity": record["severity"], "description": description, "source_id": record["source_id"]})
                        source_citation = citation(rules["ddi"]["source"], record["source_id"])
                        if source_citation:
                            citations.append(source_citation)
                        if record["severity"] in rules["ddi"]["blocking_levels"]:
                            blocked_ids.update([first, second])
                            contraindications.append({"drug": " + ".join([canonical[first], canonical[second]]), "reason": "接入的DDInter记录提示需拦截并由临床药师审核的药对", "field": "interaction", "source_id": record["source_id"]})
            if unresolved:
                ddi_result = "unmapped_drug"
            elif status.get("ddi") != "connected":
                ddi_result = status.get("ddi", "not_connected")
            elif len(canonical) < 2:
                ddi_result = "insufficient_data" if missing else "not_applicable"
            else:
                ddi_result = "hit" if interactions else "no_hit"
        else:
            unresolved = current + requested
            ddi_result = status.get("ddi", "not_connected")
    blocked = list(dict.fromkeys(item["drug"] for item in contraindications))
    # Any blocking pair removes its members from source options before explanation.
    blocked_names = {normalize(name) for name in blocked}
    blocked_names.update(normalize(name) for interaction in interactions if interaction["severity"] in rules["ddi"]["blocking_levels"] for name in interaction["drugs"])
    options = [option for option in options if normalize(option["drug_name"]) not in blocked_names and option["canonical_drug"] not in blocked_ids]
    content = "用药审核须由执业医师/药师确认，不自动开具处方或个体剂量。"
    if contraindications:
        content += "\n已发现需拦截或核验的用药线索：" + "；".join(item["drug"] + "：" + item["reason"] for item in contraindications)
    content += f"\n药名资料：{status_text(status.get('drug_names', 'not_connected'), rules)}；药物相互作用资料：{status_text(ddi_result, rules)}；指南/说明书：{status_text(status.get('guidelines', 'not_connected'), rules)}。"
    if ddi_result == "no_hit":
        content += "当前接入表未检索到药对记录，不等于不存在相互作用。"
    if unresolved:
        content += "\n部分药名或中文/英文映射未核验，不能完成相互作用排除。"
    if missing:
        content += "\n尚需补充：" + "、".join(missing)
    if options:
        content += "\n经审校来源列举的治疗选项（需先由医生确认诊断、禁忌和适用条件）：" + "；".join(f"{item['drug_name']}（来源线别：{item['line']}）" for item in options)
        education = [item for option in options for item in option["education"] + option["adverse_effects"]]
        if education:
            content += "\n来源中的用药教育/不良反应提醒：" + "；".join(education)
    else:
        content += "\n当前没有足以支持一线/二线个体化方案的已审校来源，不生成药名或剂量。"
    metadata = {"requires_doctor": True, "allergies": allergies, "current_medications": current, "missing_fields": missing, "contraindications": contraindications, "blocked_drugs": blocked, "interactions": interactions, "interaction_status": ddi_result, "unresolved_drugs": unresolved, "source_options": options, "special_population_checks": checks, "data_status": status, "diagnostic_opinions": [], "dose_status": "withheld_requires_clinician"}
    return content, metadata, [item for index, item in enumerate(citations) if item and item["chunk_id"] not in {previous["chunk_id"] for previous in citations[:index] if previous}]
