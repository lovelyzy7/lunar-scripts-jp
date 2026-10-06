import sys
import threading
import time

import frida

JS = open(r'E:\NieRReincarnation\lunar-scripts-jp\tools\frida_il2cpp_hook.js', encoding='utf-8').read()
DEV = frida.get_usb_device(timeout=15)
DEV.enable_spawn_gating()
ev = threading.Event()
info = {}


def on_spawn(spawn):
    ident = getattr(spawn, 'identifier', '') or ''
    print('[spawn] pid=%s ident=%s' % (spawn.pid, ident), flush=True)
    if 'nierspjp' in ident:
        info['pid'] = spawn.pid
        ev.set()
    else:
        try:
            DEV.resume(spawn.pid)
        except Exception:
            pass


DEV.on('spawn-added', on_spawn)
print('[gating] waiting for app spawn ...', flush=True)
ev.wait(timeout=90)
if 'pid' not in info:
    print('[!] no spawn captured', flush=True)
    sys.exit(1)
pid = info['pid']
print('[spawn] captured pid=%d' % pid, flush=True)
sess = DEV.attach(pid)
scr = sess.create_script(JS)
scr.on('message', lambda m, d: print(m.get('payload', m), flush=True))
scr.load()
DEV.resume(pid)
print('[resumed]', flush=True)
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 150)
print('=== done ===', flush=True)
