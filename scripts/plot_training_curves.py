"""绘制线性基线 vs 余弦调优的训练收敛曲线（loss / eval_loss / lr），输出 PNG。

- 数据源：两轮训练的 trainer_state.json 的 log_history 字段
- 输出：三张对比曲线图，用于文档「6.6 三组消融对比」章节
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")

# 中文字体（Windows）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINEAR = PROJECT_ROOT / "models/finetuned/bge-m3-lora/checkpoint-1250/trainer_state.json"
COSINE = PROJECT_ROOT / "models/finetuned/bge-m3-lora-cosine/checkpoint-1200/trainer_state.json"
OUT_DIR = Path("C:/Users/cx000/WorkBuddy/2026-10-31-19-20-21/images")

# 颜色：线性基线 = 蓝，余弦调优 = 橙红
C_LINEAR = "#2b6cb0"
C_COSINE = "#dd6b20"


def load(path: Path):
    d = json.load(open(path, encoding="utf-8"))
    lh = d["log_history"]
    loss = [(x["step"], x["loss"]) for x in lh if "loss" in x]
    lr = [(x["step"], x["learning_rate"]) for x in lh if "learning_rate" in x]
    eval_loss = [(x["step"], x["eval_loss"]) for x in lh if "eval_loss" in x]
    return loss, lr, eval_loss


def _xy(series):
    xs = [p[0] for p in series]
    ys = [p[1] for p in series]
    return xs, ys


def _style_ax(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="best")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lin_loss, lin_lr, lin_ev = load(LINEAR)
    cos_loss, cos_lr, cos_ev = load(COSINE)

    # ---------- 图 1：训练 loss 收敛曲线 ----------
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(*_xy(lin_loss), color=C_LINEAR, linewidth=1.6, label="线性基线 (linear + wd=0 + 1ep)")
    ax.plot(*_xy(cos_loss), color=C_COSINE, linewidth=1.6, label="余弦调优 (cosine + wd=0.01 + 2ep + 早停)")
    _style_ax(ax, "训练步数 (step)", "训练损失 (train loss)", "训练损失收敛曲线对比")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "loss_curve.png", dpi=150)
    plt.close(fig)

    # ---------- 图 2：验证 eval_loss 曲线 ----------
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(*_xy(lin_ev), color=C_LINEAR, linewidth=1.8, marker="o", markersize=4, label="线性基线 (1ep，完整训完)")
    ax.plot(*_xy(cos_ev), color=C_COSINE, linewidth=1.8, marker="o", markersize=4, label="余弦调优 (0.96ep 早停)")
    # 标注余弦早停终点与最优值
    cos_ev_x, cos_ev_y = _xy(cos_ev)
    best_i = cos_ev_y.index(min(cos_ev_y))
    ax.annotate(
        f"余弦最优 eval_loss={cos_ev_y[best_i]:.4f}\n(step {cos_ev_x[best_i]})",
        xy=(cos_ev_x[best_i], cos_ev_y[best_i]),
        xytext=(cos_ev_x[best_i] * 0.55, cos_ev_y[best_i] + 0.018),
        arrowprops={"arrowstyle": "->", "color": C_COSINE, "lw": 1.2},
        fontsize=9, color=C_COSINE,
        bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": C_COSINE, "alpha": 0.92},
    )
    ax.annotate(
        f"早停终点 step {cos_ev_x[-1]}",
        xy=(cos_ev_x[-1], cos_ev_y[-1]),
        xytext=(cos_ev_x[-1] * 0.82, cos_ev_y[-1] + 0.018),
        arrowprops={"arrowstyle": "->", "color": C_COSINE, "lw": 1.2},
        fontsize=9, color=C_COSINE,
        bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": C_COSINE, "alpha": 0.92},
    )
    _style_ax(ax, "训练步数 (step)", "验证损失 (eval_loss)", "验证集损失曲线对比（余弦过早早停）")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "eval_loss_curve.png", dpi=150)
    plt.close(fig)

    # ---------- 图 3：学习率调度曲线 ----------
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(*_xy(lin_lr), color=C_LINEAR, linewidth=1.8, label="linear 线性衰减 (warmup 125 步)")
    ax.plot(*_xy(cos_lr), color=C_COSINE, linewidth=1.8, label="cosine 余弦退火 (warmup 250 步)")
    _style_ax(ax, "训练步数 (step)", "学习率 (learning rate)", "学习率调度曲线对比")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "lr_curve.png", dpi=150)
    plt.close(fig)

    print("[完成] 三张曲线图已输出到", OUT_DIR)
    for f in ["loss_curve.png", "eval_loss_curve.png", "lr_curve.png"]:
        print("  -", f)


if __name__ == "__main__":
    main()
