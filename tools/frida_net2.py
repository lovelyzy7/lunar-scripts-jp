import sys
import time

import frida

PID = int(sys.argv[1])
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 60
JS = open(r'E:\NieRReincarnation\jp\frida_net2.js', encoding='utf-8').read()

dev = frida.get_usb_device(timeout=15)
sess = dev.attach(PID)
print('[attached] pid=%d' % PID, flush=True)
scr = sess.create_script(JS)
n = 0


def on_msg(m, d):
    global n
    if m['type'] != 'send':
        print('[msg]', m, flush=True)
        return
    p = m['payload']
    n += 1
    if n <= 250:
        print(p.get('at', ''), p.get('t'), p.get('host', p.get('ip', '')), p.get('port', ''), p.get('ret', ''), flush=True)


scr.on('message', on_msg)
scr.load()
print('[script loaded]', flush=True)
time.sleep(DUR)
print('=== done (%d msgs) ===' % n, flush=True)
