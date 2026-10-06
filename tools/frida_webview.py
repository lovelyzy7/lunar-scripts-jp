import sys
import time

import frida

PKG = 'com.square_enix.android_googleplay.nierspjp'
JS = open(r'E:\NieRReincarnation\lunar-scripts-jp\tools\frida_webview.js', encoding='utf-8').read()

dev = frida.get_usb_device(timeout=15)
pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 40
if pid is None:
    procs = [p for p in dev.enumerate_processes() if 'spjp' in p.name.lower() or p.name == 'NieR']
    pid = procs[0].pid if procs else None
sess = dev.attach(pid)
print('[attached] pid=%s' % pid, flush=True)
scr = sess.create_script(JS)


def on_msg(m, d):
    print(m.get('payload', m), flush=True)


scr.on('message', on_msg)
scr.load()
time.sleep(dur)
print('=== done ===', flush=True)
