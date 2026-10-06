#!/usr/bin/env python3
"""跨平台 APK 解包 / 重建 / 签名助手（venv / Colab / 任意环境通用）。

只依赖标准库 + Java（JDK 11+）。

用法:
  python android/build_apk.py tools                      下载 apktool.jar + uber-apk-signer.jar
  python android/build_apk.py unpack <input.apk> <dir>   解包
  python android/build_apk.py build  <dir> <out.apk>     重建 + 对齐 + 签名
"""
import shutil
import subprocess
import sys
import urllib.request
import pathlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "work" / "tools"
APKTOOL_URL = "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar"
SIGNER_URL = ("https://github.com/patrickfav/uber-apk-signer/releases/download/"
              "v1.3.0/uber-apk-signer-1.3.0.jar")
APKTOOL = TOOLS / "apktool.jar"
SIGNER = TOOLS / "uber-apk-signer.jar"


def run(cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def java():
    j = shutil.which("java")
    if not j:
        sys.exit("[!] 未找到 java —— 请安装 JDK 11+")
    return j


def dl(url, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        print("[=] 已存在:", dst)
        return
    print("[dl]", url, flush=True)
    urllib.request.urlretrieve(url, dst)
    print("[ok]", dst)


def tools():
    dl(APKTOOL_URL, APKTOOL)
    dl(SIGNER_URL, SIGNER)


def unpack(apk, out):
    tools()
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    run([java(), "-jar", APKTOOL, "d", "-f", apk, "-o", out])


def build(src, out):
    tools()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".unsigned.apk")
    if tmp.exists():
        tmp.unlink()
    run([java(), "-jar", APKTOOL, "b", src, "-o", tmp])
    run([java(), "-jar", SIGNER, "-a", tmp, "-o", out.parent])
    cand = [q for q in out.parent.glob(tmp.stem + "*.apk")
            if q != tmp and q.name.lower().endswith("signed.apk")]
    if not cand:
        sys.exit("[!] 未找到签名产物，请检查上面的日志")
    signed = max(cand, key=lambda q: q.stat().st_mtime)
    shutil.move(str(signed), out)
    tmp.unlink(missing_ok=True)
    pathlib.Path(str(signed) + ".idsig").unlink(missing_ok=True)
    print("[ok] 完成:", out)


def main():
    a = sys.argv[1:]
    if a and a[0] == "tools":
        tools()
    elif a[0:1] == ["unpack"] and len(a) == 3:
        unpack(a[1], a[2])
    elif a[0:1] == ["build"] and len(a) == 3:
        build(a[1], a[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
