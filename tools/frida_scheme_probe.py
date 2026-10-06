#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""frida_scheme_probe.py — 运行引继对话框 scheme/消息探针 (JP 客户端)

用法:
    python tools/frida_scheme_probe.py [包名]
默认包名: com.square_enix.android_googleplay.nierspjp

先确保客户端已启动并停在 标题画面/Menu（探针 attach 后再操作 引继/注册）。
"""
import sys, os, time
import frida

PKG = sys.argv[1] if len(sys.argv) > 1 else "com.square_enix.android_googleplay.nierspjp"
JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frida_scheme_probe.js")

def on_message(msg, data):
    if msg.get("type") == "send":
        print(msg["payload"], flush=True)
    elif msg.get("type") == "error":
        print("[js-error]", msg.get("stack") or msg.get("description"), flush=True)

def main():
    dev = frida.get_usb_device(timeout=10)
    session = dev.attach(PKG)
    with open(JS, "r", encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", on_message)
    script.load()
    print(f"[probe] attached to {PKG}; 现在在客户端里执行 引继/注册 操作，Ctrl+C 退出", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        session.detach()

if __name__ == "__main__":
    main()
