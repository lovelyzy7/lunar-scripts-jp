#!/usr/bin/env python3
"""check_text_hygiene.py — 仓库文本规范检查（编码 / 换行符 / BOM / 乱码风险）。

用法:
    python3 check_text_hygiene.py

检查项（全部通过才 exit 0）:
  1. 所有文本文件必须是 UTF-8（无 BOM）
  2. 换行符符合 .gitattributes 策略：
       *.bat            -> 全部 CRLF
       其余文本文件      -> 全部 LF（禁止 CRLF，避免 git add 警告与 diff 噪声）
  3. *.bat 只允许 ASCII（cmd.exe 用 OEM 代码页解码批处理，UTF-8 中文会乱码）
  4. *.sh 必须是 LF 且 git 文件模式为 100755（可执行）
  5. 禁止 UTF-8 BOM（Windows 记事本/PowerShell 保存时容易混入）

违反时打印文件与原因，exit 1；用于 pre-commit / CI / 提交前自查。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# .gitattributes 中标记为 binary 的扩展名（不做文本检查）
BINARY_EXTS = {
    ".apk", ".jar", ".keystore", ".jks", ".so", ".bin",
    ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".pyc",
}

CRLF_EXTS = {".bat"}          # 仅批处理保留 CRLF
ASCII_ONLY_EXTS = {".bat"}    # 批处理只允许 ASCII，防止 cmd.exe 乱码
EXEC_CHECK_EXTS = {".sh"}     # 必须带可执行位


def git_tracked() -> list[tuple[str, str]]:
    """返回 [(mode, path)]，mode 形如 '100644' / '100755'。"""
    out = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout
    items = []
    for entry in out.decode("utf-8").split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        items.append((meta.split()[0], path))
    return items


def main() -> int:
    problems: list[str] = []
    checked = 0
    entries = git_tracked()

    for mode, rel in entries:
        path = ROOT / rel
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in BINARY_EXTS:
            continue

        raw = path.read_bytes()
        checked += 1

        # 1) BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{rel}: 含 UTF-8 BOM（请另存为无 BOM 的 UTF-8）")
            continue
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            problems.append(f"{rel}: 含 UTF-16 BOM（必须改为 UTF-8）")
            continue

        # 2) UTF-8 编码
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as e:
            problems.append(f"{rel}: 非 UTF-8 文本（{e}）— 请转成 UTF-8 无 BOM")
            continue

        # 3) 换行符
        crlf = raw.count(b"\r\n")
        lf_only = raw.count(b"\n") - crlf
        if ext in CRLF_EXTS:
            if lf_only:
                problems.append(
                    f"{rel}: 含 {lf_only} 行 LF — *.bat 必须全部 CRLF "
                    f"(git add 会出现 'LF will be replaced by CRLF' 警告)"
                )
            if b"\r\r\n" in raw:
                problems.append(f"{rel}: 含 CRCRLF（换行符被转换了两次）")
        else:
            if crlf:
                problems.append(
                    f"{rel}: 含 {crlf} 行 CRLF — 仓库策略是 LF-only，请转换 (dos2unix)"
                )

        # 4) .bat ASCII-only（防 cmd.exe OEM 代码页乱码）
        if ext in ASCII_ONLY_EXTS:
            bad = [i + 1 for i, line in enumerate(raw.splitlines())
                   if any(b > 127 for b in line)]
            if bad:
                problems.append(
                    f"{rel}: 第 {bad[:5]} 行含非 ASCII 字符 — 批处理必须 ASCII-only，"
                    f"否则 cmd.exe 显示乱码"
                )

        # 5) .sh 必须 LF + 可执行
        if ext in EXEC_CHECK_EXTS:
            if mode != "100755":
                problems.append(f"{rel}: git 文件模式为 {mode}，*.sh 应为 100755 (chmod +x)")

    # 签名密钥必须随仓库分发（本地/Colab/手动三条签名路径共用）：
    # 确认文件存在且未被 .gitignore 忽略（push 时不能丢）
    KEYSTORE = "keys/nier-jp.keystore"
    tracked_paths = {rel for _, rel in entries}
    if not (ROOT / KEYSTORE).is_file():
        problems.append(f"{KEYSTORE}: 文件缺失 — 签名密钥必须随仓库分发")
    elif KEYSTORE not in tracked_paths:
        problems.append(
            f"{KEYSTORE}: 未被 git 跟踪 — 签名密钥必须入库（push 时不能被忽略），检查 .gitignore"
        )

    print(f"checked {checked} tracked text files")
    if problems:
        print(f"\n发现 {len(problems)} 个文本规范问题:\n")
        for p in problems:
            print("  ✗ " + p)
        print("\n修复后重跑: python3 check_text_hygiene.py")
        return 1

    print("OK: UTF-8 无 BOM / 换行符符合 .gitattributes / 无乱码风险 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
