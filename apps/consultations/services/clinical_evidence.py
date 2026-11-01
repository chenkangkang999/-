"""Read-only structured clinical evidence; imports are explicit, never on Agent reads."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[3]


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def status_text(value, rules):
    return rules.get("status_labels", {}).get(value, "资料待核验")


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def policy():
    path = project_path(os.getenv("CLINICAL_DATA_POLICY_PATH", "configs/clinical_evidence.yaml"))
    result = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("CLINICAL_POLICY_INVALID")
    return result


def data_root(rules):
    return project_path(os.getenv("CLINICAL_DATA_ROOT", rules["data_root"])).resolve()


def index_path(rules):
    return project_path(os.getenv("CLINICAL_DATA_INDEX", rules["index_path"])).resolve()


def source_path(rules, source):
    root = data_root(rules)
    path = (root / source["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("CLINICAL_SOURCE_PATH_NOT_ALLOWED")
    return path


def citation(source, identifier=None, quote=""):
    url = source.get("url", "")
    if urlsplit(url).scheme not in {"http", "https"}:
        return None
    identity = identifier or source.get("id", source.get("title", "source"))
    return {"chunk_id": "clinical:" + str(identity), "title": source.get("title", "临床来源"), "url": url, "authority": source.get("authority", "clinical_reference"), "quote": quote, "source_version": source.get("version", ""), "verified_source": True}


def tokens(value, rules):
    if value is None:
        return []
    values = value if isinstance(value, list) else re.split(rules["tokens"]["split_pattern"], str(value))
    result = []
    for item in values:
        text = str(item).strip()
        if not text or normalize(text) in {normalize(x) for x in rules["tokens"]["empty_values"] + rules["tokens"]["unknown_values"]}:
            continue
        for pattern in rules["tokens"].get("removable_prefixes", []):
            text = re.sub(pattern, "", text).strip()
        if text:
            result.append(text)
    return list(dict.fromkeys(result))


def boolean(value, rules):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    lowered = normalize(value)
    if lowered in rules["tokens"]["positive_values"]:
        return True
    if lowered in rules["tokens"]["negative_values"]:
        return False
    return None


def patient_facts(context):
    values = dict(context.patient)
    for candidate in (context.patient.get("reported_history"), context.facts.get("intake", {}).get("answers"), context.facts.get("clinical_inputs")):
        if isinstance(candidate, dict):
            values.update(candidate)
    vitals = values.get("vitals")
    if isinstance(vitals, dict):
        values.update(vitals)
    return values


def source_record(spec, path):
    return {"status": "connected", "rows": 0, "sha256": file_hash(path), "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns, "path": str(path), "source": spec.get("source", {})}


def checked_csv(rules, spec):
    path = source_path(rules, spec)
    if not path.is_file():
        return None, None
    if path.stat().st_size > rules["max_source_bytes"]:
        raise ValueError("CLINICAL_SOURCE_TOO_LARGE")
    return path, source_record(spec, path)


def aliases(connection, canonical, names):
    for value in names:
        if isinstance(value, str) and value.strip():
            connection.execute("INSERT OR IGNORE INTO aliases(alias,canonical) VALUES(?,?)", (normalize(value), canonical))


def resolve_name(connection, name):
    matches = [row[0] for row in connection.execute("SELECT canonical FROM aliases WHERE alias=?", (normalize(name),))]
    if matches:
        return matches[0] if len(matches) == 1 else None
    text = normalize(name)
    candidates = set()
    for alias, canonical in connection.execute("SELECT alias,canonical FROM aliases WHERE length(alias)>1 AND instr(?,alias)>0 LIMIT 100", (text,)):
        if alias.isascii() and not re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", text):
            continue
        candidates.add(canonical)
    return next(iter(candidates)) if len(candidates) == 1 else None


def import_evidence():
    rules = policy()
    target = index_path(rules)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    statuses = {}
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE aliases(alias TEXT,canonical TEXT,UNIQUE(alias,canonical)); CREATE INDEX alias_lookup ON aliases(alias); CREATE TABLE interactions(drug_a TEXT,drug_b TEXT,severity TEXT,rank INTEGER,description TEXT,source_id TEXT,PRIMARY KEY(drug_a,drug_b)); CREATE TABLE labels(id TEXT PRIMARY KEY,drug TEXT,payload TEXT); CREATE INDEX labels_drug ON labels(drug);")
            for spec in rules["drug_sources"]:
                path, record = checked_csv(rules, spec)
                if path is None:
                    statuses[spec["id"]] = {"status": "not_connected", "rows": 0}
                    continue
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    rows = csv.DictReader(handle)
                    fields = spec["fields"]
                    if fields["name"] not in (rows.fieldnames or []):
                        raise ValueError(f"CLINICAL_CSV_FIELD_MISSING:{spec['id']}:{fields['name']}")
                    for row in rows:
                        name = row.get(fields["name"], "").strip()
                        if not name:
                            continue
                        names = [name, row.get(fields.get("english_name", ""), "")]
                        names.extend(re.split(r"[|;；]", row.get(fields.get("aliases", ""), "")))
                        aliases(connection, normalize(name), names)
                        record["rows"] += 1
                statuses[spec["id"]] = record
            labels_spec = rules["guidelines"]
            path, record = checked_csv(rules, labels_spec)
            if path is None:
                statuses["guidelines"] = {"status": "not_connected", "rows": 0}
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                for entry in payload.get("entries", []):
                    source = entry.get("source", payload.get("source", {}))
                    if source.get("authority") not in labels_spec["allowed_authorities"] or source.get("verified") is not True or not all(source.get(key) for key in labels_spec["required_review_fields"]) or citation(source) is None:
                        raise ValueError("CLINICAL_GUIDELINE_NOT_REVIEWED")
                    if not entry.get("id") or not entry.get("drug_name") or not entry.get("evidence_text"):
                        raise ValueError("CLINICAL_GUIDELINE_FIELDS_MISSING")
                    entry = {**entry, "source": source}
                    canonical = resolve_name(connection, entry["drug_name"]) or normalize(entry["drug_name"])
                    aliases(connection, canonical, [entry["drug_name"], *entry.get("aliases", [])])
                    connection.execute("INSERT INTO labels VALUES(?,?,?)", (entry["id"], canonical, json.dumps(entry, ensure_ascii=False)))
                    record["rows"] += 1
                statuses["guidelines"] = record
            ddi = rules["ddi"]
            path, record = checked_csv(rules, ddi)
            if path is None:
                statuses["ddi"] = {"status": "not_connected", "rows": 0}
            else:
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    rows = csv.DictReader(handle)
                    fields = ddi["fields"]
                    if not {fields["drug_a"], fields["drug_b"], fields["severity"]}.issubset(rows.fieldnames or []):
                        raise ValueError("CLINICAL_CSV_FIELD_MISSING:ddi")
                    for number, row in enumerate(rows, 2):
                        names = [row[fields[key]].strip() for key in ("drug_a", "drug_b")]
                        if not all(names):
                            continue
                        pair = sorted(resolve_name(connection, value) or normalize(value) for value in names)
                        for value, canonical in zip(names, [resolve_name(connection, value) or normalize(value) for value in names], strict=True):
                            aliases(connection, canonical, [value])
                        raw_severity = row[fields["severity"]].strip()
                        severity = ddi["severity_aliases"].get(raw_severity, normalize(raw_severity))
                        if severity not in ddi["severity_ranks"]:
                            raise ValueError("CLINICAL_DDI_SEVERITY_UNKNOWN")
                        rank = ddi["severity_ranks"][severity]
                        description = row.get(fields.get("description", ""), "")
                        connection.execute("INSERT INTO interactions VALUES(?,?,?,?,?,?) ON CONFLICT(drug_a,drug_b) DO UPDATE SET severity=excluded.severity,rank=excluded.rank,description=excluded.description,source_id=excluded.source_id WHERE excluded.rank>interactions.rank", (*pair, severity, rank, description, f"ddi-row-{number}"))
                        record["rows"] += 1
                record["deduplicated_pairs"] = connection.execute("SELECT count(*) FROM interactions").fetchone()[0]
                statuses["ddi"] = record
            for name, record in statuses.items():
                if record["status"] == "connected":
                    stat_now = Path(record["path"]).stat()
                    if (stat_now.st_size, stat_now.st_mtime_ns) != (record["bytes"], record["mtime_ns"]):
                        raise ValueError("CLINICAL_SOURCE_CHANGED_DURING_IMPORT")
                connection.execute("INSERT INTO metadata VALUES(?,?)", (name, json.dumps(record, ensure_ascii=False)))
            connection.execute("INSERT INTO metadata VALUES(?,?)", ("policy_sha256", hashlib.sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()).hexdigest()))
            connection.commit()
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {name: {key: value for key, value in record.items() if key not in {"path"}} for name, record in statuses.items()}


@contextmanager
def evidence_store(rules=None):
    rules = rules or policy()
    path = index_path(rules)
    if not path.is_file():
        yield None, {"ddi": {"status": "not_connected"}, "guidelines": {"status": "not_connected"}, "drug_names": {"status": "not_connected"}}
        return
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        records = dict(connection.execute("SELECT key,value FROM metadata"))
        if records.pop("policy_sha256", "") != hashlib.sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()).hexdigest():
            yield None, {key: {"status": "stale_requires_sync"} for key in ("ddi", "guidelines", "drug_names")}
            return
        statuses = {key: json.loads(value) for key, value in records.items()}
        for record in statuses.values():
            if record["status"] == "connected":
                source = Path(record["path"])
                if not source.is_file() or (source.stat().st_size, source.stat().st_mtime_ns) != (record["bytes"], record["mtime_ns"]):
                    record["status"] = "stale_requires_sync"
        statuses["drug_names"] = {"status": "connected" if any(statuses.get(spec["id"], {}).get("status") == "connected" for spec in rules["drug_sources"]) else "not_connected"}
        if any(record["status"] == "stale_requires_sync" for record in statuses.values()):
            yield None, statuses
        else:
            yield connection, statuses
    finally:
        connection.close()


def clinical_data_status():
    rules = policy()
    with evidence_store(rules) as (_, statuses):
        result = {key: {field: value for field, value in status.items() if field != "path"} for key, status in statuses.items()}
    result["news2"] = {"status": "connected", "version": rules["news2"]["version"], "source": rules["news2"]["source"]}
    model = project_path(rules["framingham"]["artifact"])
    result["framingham"] = {"status": "connected" if model.is_file() and file_hash(model) == rules["framingham"]["sha256"] else "not_connected", "kind": "original_research_formula_not_local_calibration"}
    return result
