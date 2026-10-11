#!/usr/bin/env python3
"""跨平台 APK 解包 / 重建 / 签名助手（venv / Colab / 任意环境通用）。

只依赖标准库 + Java（JDK 11+）。

用法:
  python android/build_apk.py tools                      下载 apktool.jar + uber-apk-signer.jar
  python android/build_apk.py unpack <input.apk> <dir>   解包
  python android/build_apk.py build  <dir> <out.apk>     重建 + 对齐 + 签名
  可选签名参数（默认用仓库自带密钥，与 Colab / README 手动流程一致）:
  --ks PATH --ks-pass PASS --ks-alias ALIAS --key-pass PASS
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

# ---------------------------------------------------------------- 签名密钥
# 三条签名路径（本地 run_local.py / Colab / README 手动流程）共用仓库内
# 同一密钥，保证各环境产出的 APK 可互相覆盖安装（adb install -r）。
# 密钥随仓库分发，仅私服/学习用途，勿用于其他项目。
KEYSTORE = ROOT / "keys" / "nier-jp.keystore"
KEYSTORE_PASS = "lunar-jp"
KEY_ALIAS = "nier"
KEY_PASS = "lunar-jp"


def _enable_utf8_stdio():
    """Force UTF-8 stdout/stderr on Windows to avoid console/log mojibake."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


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


def build(src, out, ks=None, ks_pass=None, ks_alias=None, key_pass=None):
    tools()
    ks = Path(ks) if ks else KEYSTORE
    ks_pass = ks_pass or KEYSTORE_PASS
    ks_alias = ks_alias or KEY_ALIAS
    key_pass = key_pass or KEY_PASS
    if not ks.is_file():
        sys.exit("[!] 签名密钥不存在: %s（应随仓库提供，见 keys/）" % ks)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".unsigned.apk")
    if tmp.exists():
        tmp.unlink()
    run([java(), "-jar", APKTOOL, "b", src, "-o", tmp])
    run([java(), "-jar", SIGNER, "-a", tmp, "-o", out.parent,
         "--ks", str(ks), "--ksPass", ks_pass,
         "--ksAlias", ks_alias, "--keyPass", key_pass])
    cand = [q for q in out.parent.glob(tmp.stem + "*.apk")
            if q != tmp and q.name.lower().endswith("signed.apk")]
    if not cand:
        sys.exit("[!] 未找到签名产物，请检查上面的日志")
    signed = max(cand, key=lambda q: q.stat().st_mtime)
    shutil.move(str(signed), out)
    tmp.unlink(missing_ok=True)
    pathlib.Path(str(signed) + ".idsig").unlink(missing_ok=True)
    print("[ok] 完成:", out)


def _sign_opts(argv):
    """解析可选签名参数 -> dict。"""
    mapping = {"--ks": "ks", "--ks-pass": "ks_pass",
               "--ks-alias": "ks_alias", "--key-pass": "key_pass"}
    opts = {}
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag not in mapping or i + 1 >= len(argv):
            sys.exit(__doc__)
        opts[mapping[flag]] = argv[i + 1]
        i += 2
    return opts


def main():
    _enable_utf8_stdio()
    a = sys.argv[1:]
    if a and a[0] == "tools":
        tools()
    elif a[0:1] == ["unpack"] and len(a) >= 3:
        unpack(a[1], a[2])
    elif a[0:1] == ["build"] and len(a) >= 3:
        build(a[1], a[2], **_sign_opts(a[3:]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
