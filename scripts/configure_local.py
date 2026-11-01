"""Local-only configuration dialog. Secrets never leave the machine or enter logs."""

from __future__ import annotations

import tkinter as tk
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def main():
    values = dotenv_values(ENV)
    window = tk.Tk()
    window.title("医协 · 本地模型配置")
    window.geometry("650x540")
    window.minsize(600, 450)
    frame = ttk.Frame(window, padding=26)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="连接你的模型服务", font=("Microsoft YaHei UI", 17, "bold")).pack(
        anchor="w"
    )
    ttk.Label(frame, text="密钥只写入本机 .env；不会上传到聊天或 GitHub。", wraplength=570).pack(
        anchor="w", pady=(8, 20)
    )
    fields = {}
    specs = [
        ("LLM_PROVIDER", "服务商标识", values.get("LLM_PROVIDER") or ""),
        ("LLM_BASE_URL", "接口地址", values.get("LLM_BASE_URL") or ""),
        ("LLM_MODEL", "模型名称", values.get("LLM_MODEL") or ""),
        (
            "DAILY_COST_BUDGET_PER_USER",
            "每日上限（人民币元 / 用户）",
            values.get("DAILY_COST_BUDGET_PER_USER") or "",
        ),
        ("LLM_API_KEY", "API 密钥（仅此项为秘密）", values.get("LLM_API_KEY") or ""),
    ]
    for name, label, value in specs:
        ttk.Label(frame, text=label).pack(anchor="w", pady=(5, 3))
        item = ttk.Entry(frame, show="•" if name == "LLM_API_KEY" else "")
        item.insert(0, value)
        item.pack(fill="x")
        fields[name] = item
    status = ttk.Label(frame, text="填好密钥后保存；不用把密钥发送给任何人。", wraplength=570)
    status.pack(anchor="w", pady=(16, 8))

    def save():
        data = {name: entry.get().strip() for name, entry in fields.items()}
        parsed = urlparse(data["LLM_BASE_URL"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
            messagebox.showerror("地址无效", "请输入有效的模型接口地址。", parent=window)
            return
        try:
            budget = Decimal(data["DAILY_COST_BUDGET_PER_USER"])
            if not budget.is_finite() or budget <= 0:
                raise InvalidOperation()
        except (InvalidOperation, ValueError):
            messagebox.showerror("预算无效", "每日预算必须是正数。", parent=window)
            return
        if (
            not data["LLM_PROVIDER"]
            or not data["LLM_MODEL"]
            or not data["LLM_API_KEY"]
            or any("\n" in value or "\r" in value for value in data.values())
        ):
            messagebox.showerror(
                "配置不完整", "请填写模型名称和密钥，字段中不能包含换行。", parent=window
            )
            return
        for name, value in data.items():
            set_key(str(ENV), name, value)
        local = ROOT / ".local"
        local.mkdir(exist_ok=True)
        (local / "configuration-saved").write_text("saved", encoding="utf-8")
        for entry in fields.values():
            entry.delete(0, tk.END)
        messagebox.showinfo(
            "已保存到本机",
            "配置已保存。请回到聊天回复“已保存”，之后重启后端并进行真实联调。",
            parent=window,
        )
        window.destroy()

    ttk.Button(frame, text="保存到本机", command=save).pack(anchor="e")
    fields["LLM_API_KEY"].focus_set()
    window.mainloop()


if __name__ == "__main__":
    main()
