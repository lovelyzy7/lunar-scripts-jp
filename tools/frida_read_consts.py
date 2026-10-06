import sys
import time

import frida

JS = open(r'E:\NieRReincarnation\lunar-scripts-jp\tools\frida_read_consts.js', encoding='utf-8').read()
dev = frida.get_usb_device(timeout=15)
pid = int(sys.argv[1])
sess = dev.attach(pid)
print('[attached] %d' % pid, flush=True)
scr = sess.create_script(JS)
scr.on('message', lambda m, d: print(m.get('payload', m), flush=True))
scr.load()
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 20)
print('=== done ===', flush=True)
