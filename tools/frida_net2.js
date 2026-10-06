// 精确抓取 connect 目标 + getaddrinfo 结果，兼容 Frida 17
function findExport(name) {
  try { var p = Module.findGlobalExportByName(name); if (p) return p; } catch (e) {}
  try { var q = Module.findExportByName(null, name); if (q) return q; } catch (e) {}
  return null;
}
function ts() { return new Date().toISOString().substr(11, 12); }

var gai = findExport('getaddrinfo');
if (gai) {
  Interceptor.attach(gai, {
    onEnter: function (args) {
      try { this.host = args[0].isNull() ? null : args[0].readCString(); } catch (e) { this.host = null; }
      this.res = args[3];
    },
    onLeave: function (ret) {
      var host = this.host || '(null)';
      var code = ret.toInt32();
      var info = '';
      try {
        if (code === 0 && !this.res.isNull()) {
          var p = this.res.readPointer();
          if (!p.isNull()) {
            var fam = p.add(4).readU32();
            var addr = p.add(24).readPointer();
            if (fam === 2) {
              var port = (addr.add(2).readU8() << 8) | addr.add(3).readU8();
              info = [addr.add(4).readU8(), addr.add(5).readU8(), addr.add(6).readU8(), addr.add(7).readU8()].join('.') + ':' + port;
            } else if (fam === 10) {
              var g = [];
              for (var i = 0; i < 16; i += 2) {
                var v = (addr.add(8 + i).readU8() << 8) | addr.add(9 + i).readU8();
                g.push(v.toString(16));
              }
              info = g.join(':') + ':' + ((addr.add(2).readU8() << 8) | addr.add(3).readU8());
            }
          }
        }
      } catch (e) { info = 'parse_err'; }
      send({ t: 'GA', host: host, ret: code, info: info, at: ts() });
    }
  });
}
var conn = findExport('connect');
if (conn) {
  Interceptor.attach(conn, {
    onEnter: function (args) {
      try {
        var sa = args[1];
        var fam = sa.readU16();
        var port = (sa.add(2).readU8() << 8) | sa.add(3).readU8();
        var ip = '?';
        if (fam === 2) {
          ip = [sa.add(4).readU8(), sa.add(5).readU8(), sa.add(6).readU8(), sa.add(7).readU8()].join('.');
        } else if (fam === 10) {
          var g = [];
          for (var i = 0; i < 16; i += 2) {
            var v = (sa.add(8 + i).readU8() << 8) | sa.add(9 + i).readU8();
            g.push(v.toString(16));
          }
          ip = g.join(':');
        }
        send({ t: 'CONN', fam: fam, ip: ip, port: port, at: ts() });
      } catch (e) {
        send({ t: 'CONN_ERR', msg: String(e), at: ts() });
      }
    }
  });
}
send({ t: 'init', gai: !!gai, conn: !!conn });
