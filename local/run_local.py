#!/usr/bin/env python3
"""lunar-scripts-jp - local one-click pipeline (Windows / Linux / macOS).

Steps:
  1 java check   2 venv + deps   3 apk tools   4 unpack
  5 patch apk    6 master data   7 build + sign

Usage:
  python local/run_local.py [--config local/config.json] [--from N] [overrides]

Overrides (also settable in local/config.json):
  --apk PATH         original APK
  --out PATH         patched APK output
  --grpc H:P         gRPC game server
  --http H:P         HTTP / CDN
  --auth H:P         auth server (OAuth redirect)
  --masterdata PATH  master data bin (empty = skip)
  --reuse-unpack     reuse existing work/jp-final
  --reinstall-deps   force pip install
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
UNPACK_DIR = WORK / "jp-final"
VENV = ROOT / ".venv"
MASTERDATA_OUT = "20240404193219.bin.e"

DEFAULTS = {
    "apk": "",
    "out": "",
    "grpc_addr": "127.0.0.1:8003",
    "http_addr": "127.0.0.1:8080",
    "auth_host": "127.0.0.1:3000",
    "masterdata": "",
    "reuse_unpack": True,
    "reinstall_deps": False,
}


def log(step, msg):
    print("[%s] %s" % (step, msg), flush=True)


def die(msg):
    print("[x] %s" % msg, flush=True)
    sys.exit(1)


def run(cmd, step=None):
    if step:
        log(step, "$ " + " ".join(str(c) for c in cmd))
    rc = subprocess.run([str(c) for c in cmd]).returncode
    if rc:
        die("command failed (exit %d): %s" % (rc, " ".join(str(c) for c in cmd)))


def venv_py():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ----------------------------------------------------------------- steps

def step_java():
    log("1/7", "checking java ...")
    if not shutil.which("java"):
        die("java not found - install JDK 11+ (https://adoptium.net) and re-run")
    subprocess.run(["java", "-version"])


def step_venv(args):
    log("2/7", "python venv + requirements ...")
    py = venv_py()
    if not py.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    if args.reinstall_deps or not (VENV / ".deps-ok").exists():
        run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"])
        run([str(py), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])
        (VENV / ".deps-ok").write_text("ok\n", encoding="utf-8")
    else:
        log("2/7", "dependencies already installed (use --reinstall-deps to redo)")
    return py


def step_tools(py):
    log("3/7", "downloading apk tools ...")
    run([str(py), str(ROOT / "android" / "build_apk.py"), "tools"])


def step_unpack(py, args):
    if args.reuse_unpack and UNPACK_DIR.is_dir():
        log("4/7", "reusing existing %s (--reuse-unpack)" % UNPACK_DIR)
        return
    log("4/7", "unpacking apk ...")
    run([str(py), str(ROOT / "android" / "build_apk.py"), "unpack", args.apk, str(UNPACK_DIR)])


def step_patch(py, args):
    log("5/7", "patching for grpc=%s http=%s auth=%s ..."
        % (args.grpc_addr, args.http_addr, args.auth_host))
    cmd = [str(py), str(ROOT / "android" / "patch_apk_jp.py"), str(UNPACK_DIR),
           "--grpc-addr", args.grpc_addr, "--http-addr", args.http_addr]
    if args.auth_host:
        cmd += ["--auth-host", args.auth_host]
    run(cmd)


def step_masterdata(py, args):
    if not args.masterdata:
        log("6/7", "master data: skipped (not set)")
        return
    src = Path(args.masterdata).expanduser()
    if not src.is_file():
        die("master data not found: %s" % src)
    out_dir = Path(args.out).parent if args.out else src.parent
    out = out_dir / MASTERDATA_OUT
    log("6/7", "patching master data -> %s" % out)
    run([str(py), str(ROOT / "masterdata" / "patch_masterdata.py"),
         "--input", str(src), "--output", str(out)])


def step_build(py, args):
    log("7/7", "rebuilding + signing ...")
    run([str(py), str(ROOT / "android" / "build_apk.py"), "build", str(UNPACK_DIR), args.out])
    if not Path(args.out).is_file():
        die("build finished but output not found: %s" % args.out)
    mb = Path(args.out).stat().st_size / 1048576
    print("\n[ok] patched APK: %s (%.1f MB)" % (args.out, mb))
    if args.masterdata:
        print("[ok] master data: %s" % (Path(args.out).parent / MASTERDATA_OUT))


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "local" / "config.json"))
    ap.add_argument("--from", dest="from_step", type=int, default=1,
                    help="start at step N (1-7)")
    ap.add_argument("--apk")
    ap.add_argument("--out")
    ap.add_argument("--grpc", dest="grpc_addr")
    ap.add_argument("--http", dest="http_addr")
    ap.add_argument("--auth", dest="auth_host")
    ap.add_argument("--masterdata")
    ap.add_argument("--reuse-unpack", dest="reuse_unpack", action="store_true", default=None)
    ap.add_argument("--reinstall-deps", dest="reinstall_deps", action="store_true", default=None)
    a = ap.parse_args()

    cfg = dict(DEFAULTS)
    cfg_path = Path(a.config)
    if cfg_path.exists():
        cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
    else:
        example = cfg_path.parent / "config.example.json"
        if example.exists():
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(example, cfg_path)
            print("[!] created %s" % cfg_path)
            print("[!] fill in 'apk' (and server addresses), then run again")
            return
        die("config not found: %s" % cfg_path)

    for key in DEFAULTS:
        v = getattr(a, key, None)
        if v is not None:
            cfg[key] = v
    args = argparse.Namespace(**cfg)

    if not args.apk:
        die("config: 'apk' is empty - set the original JP APK path")
    args.apk = str(Path(args.apk).expanduser())
    if not Path(args.apk).is_file():
        die("APK not found: %s" % args.apk)
    if not args.out:
        args.out = str(Path(args.apk).with_name(Path(args.apk).stem + "-patched.apk"))
    args.out = str(Path(args.out).expanduser())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    print("[config] apk        = %s" % args.apk)
    print("[config] out        = %s" % args.out)
    print("[config] grpc/http/auth = %s | %s | %s"
          % (args.grpc_addr, args.http_addr, args.auth_host))
    print("[config] masterdata = %s" % (args.masterdata or "(skip)"))
    print("[config] reuse_unpack = %s" % bool(args.reuse_unpack))
    print()

    if a.from_step <= 1:
        step_java()

    if a.from_step <= 2:
        py = step_venv(args)
    else:
        py = venv_py() if venv_py().exists() else Path(sys.executable)

    if a.from_step <= 3:
        step_tools(py)
    if a.from_step <= 4:
        step_unpack(py, args)
    if a.from_step <= 5:
        step_patch(py, args)
    if a.from_step <= 6:
        step_masterdata(py, args)
    if a.from_step <= 7:
        step_build(py, args)


if __name__ == "__main__":
    main()
