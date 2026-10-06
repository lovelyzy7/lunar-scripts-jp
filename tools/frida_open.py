import sys
import time

import frida

JS = open(r'E:\NieRReincarnation\lunar-scripts-jp\tools\frida_open.js', encoding='utf-8').read()
dev = frida.get_usb_device(timeout=15)
pid = int(sys.argv[1])
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 40
sess = dev.attach(pid)
print('[attached] %d' % pid, flush=True)
scr = sess.create_script(JS)


def on_msg(m, d):
    p = m.get('payload', m)
    if isinstance(p, dict) and p.get('t'):
        print('%-22s %s' % (p['t'], p['s']), flush=True)
    else:
        print(p, flush=True)


scr.on('message', on_msg)
scr.load()
time.sleep(dur)
print('=== done ===', flush=True)
