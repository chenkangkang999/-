"""Observe the colleague's real trainer/evaluator without changing their optimizer logic.

Run explicitly in the GPU environment. This script never installs dependencies.
It emits portable training_run.json/training_events.jsonl consumed by sync_learning.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
METRICS = {
    "loss",
    "eval_loss",
    "learning_rate",
    "grad_norm",
    "epoch",
    "train_loss",
    "train_runtime",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--with-eval", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output = Path(cfg["train"]["output_dir"])
    output = output if output.is_absolute() else ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": args.run_id or str(uuid.uuid4()),
        "label": output.parent.name,
        "status": "running",
        "phase": "training",
        "started_at": datetime.now(UTC).isoformat(),
        "current_step": 0,
        "total_steps": None,
        "config": cfg,
        "provenance": {"kind": "observed_process"},
    }
    state_file = output / "training_run.json"
    events_file = output / "training_events.jsonl"

    def persist():
        temporary = output / "training_run.json.tmp"
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(state_file)

    def event(kind, phase, message="", **values):
        with events_file.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "kind": kind,
                        "phase": phase,
                        "message": message,
                        "timestamp": datetime.now(UTC).isoformat(),
                        **values,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def validate_batch():
        if args.batch_id:
            sys.path.insert(0, str(ROOT))
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
            import django

            django.setup()
            from apps.learning.flywheel import check_batch
            from apps.learning.models import FlywheelBatch

            check_batch(FlywheelBatch.objects.get(pk=args.batch_id))

    def observe_line(line):
        # Console TQDM counters are ambiguous (training and evaluation nest).
        # Accurate progress comes only from the opt-in TrainerState callback.
        start, end = line.find("{"), line.rfind("}")
        if start >= 0 and end > start:
            try:
                value = ast.literal_eval(line[start : end + 1])
            except (ValueError, SyntaxError):
                return
            if isinstance(value, dict):
                metrics = {
                    key: val
                    for key, val in value.items()
                    if key in METRICS and isinstance(val, (int, float))
                }
                if metrics:
                    event("metric", state["phase"], step=state["current_step"], metrics=metrics)

    def execute(script):
        observed_config = {**cfg, "observation": {"enabled": True}}
        runtime_config = output / "observed_training.yaml"
        runtime_config.write_text(
            yaml.safe_dump(observed_config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        command = [sys.executable, str(ROOT / "scripts" / script), "--config", str(runtime_config)]
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
        )
        try:
            line = ""
            while True:
                char = process.stdout.read(1)
                if not char:
                    break
                sys.stdout.write(char)
                if char in "\r\n":
                    observe_line(line)
                    line = ""
                elif len(line) < 20000:
                    line += char
            observe_line(line)
            code = process.wait()
            if code:
                raise RuntimeError(f"{script} exit={code}")
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
            raise

    persist()
    try:
        validate_batch()
        for value in (cfg["data"]["train_file"], cfg["data"]["val_file"]):
            path = Path(value)
            if not (path if path.is_absolute() else ROOT / path).is_file():
                raise FileNotFoundError("Configured training/validation data is unavailable")
        model_dir = Path(cfg["model"]["local_dir"])
        if not (
            (model_dir if model_dir.is_absolute() else ROOT / model_dir) / "config.json"
        ).is_file():
            raise FileNotFoundError("Configured base model is unavailable")
        event("completed", "data", "已核对本次训练输入与授权")
        event("started", "training", "实际训练进程已启动")
        execute("train_lora.py")
        event("completed", "training", "训练进程成功结束")
        if args.with_eval:
            validate_batch()
            state["phase"] = "evaluation"
            persist()
            event("started", "evaluation", "实际检索评测进程已启动")
            execute("eval_retrieval.py")
            adapter = output / "final"
            weight_hash = hashlib.sha256()
            with (adapter / "adapter_model.safetensors").open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    weight_hash.update(chunk)
            adapter_config = json.loads(
                (adapter / "adapter_config.json").read_text(encoding="utf-8")
            )
            fingerprint = hashlib.sha256(
                json.dumps(
                    [adapter_config, weight_hash.hexdigest()], sort_keys=True, ensure_ascii=False
                ).encode()
            ).hexdigest()
            csv_path = Path(cfg["eval"]["output_csv"])
            csv_path = csv_path if csv_path.is_absolute() else ROOT / csv_path
            validation = Path(cfg["data"]["val_file"])
            validation = validation if validation.is_absolute() else ROOT / validation
            with validation.open(encoding="utf-8-sig") as handle:
                count = sum(bool(line.strip()) for line in handle)
            cap = int(cfg["data"].get("max_val_samples", 0))
            manifest = {
                "adapter_sha256": fingerprint,
                "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "queries": min(count, cap) if cap else count,
                "run_id": state["run_id"],
            }
            (csv_path.parent / "evaluation_manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            event("completed", "evaluation", "评测CSV已由评测进程输出")
        state["status"] = "completed"
    except KeyboardInterrupt:
        state["status"] = "interrupted"
        event("interrupted", state["phase"], "操作员中断任务")
    except Exception as exc:
        state["status"] = "failed"
        event(
            "failed",
            state["phase"],
            f"任务失败（{type(exc).__name__}），请在GPU主机核对依赖、资产与控制台",
        )
    finally:
        state["finished_at"] = datetime.now(UTC).isoformat()
        persist()
    return 0 if state["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
