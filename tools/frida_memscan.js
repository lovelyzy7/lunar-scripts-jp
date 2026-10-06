// 在进程内存中扫描关键字符串，定位 SE 桥域名的来源
function b(s) { return s.split('').map(function (c) { return c.charCodeAt(0).toString(16).padStart(2, '0'); }).join(' '); }

var patterns = [
  ['sqex-bridge', '7365782d627269646765'],
  ['192.168.2.6:3000', '3139322e3136382e322e363a33303030'],
  ['psg.sqex', '7073672e73716578'],
  ['/ntv/', '2f6e74762f']
];

var ranges = Process.enumerateRanges('r--');
var results = {};
patterns.forEach(function (p) { results[p[0]] = []; });

ranges.forEach(function (r) {
  if (r.size > 256 * 1024 * 1024) return;
  patterns.forEach(function (p) {
    try {
      var found = Memory.scanSync(r.base, r.size, p[1]);
      found.forEach(function (m) {
        if (results[p[0]].length < 6) {
          var ctx = '';
          try { ctx = m.address.sub(64).readUtf8String(400) || ''; } catch (e) {}
          results[p[0]].push({ addr: m.address.toString(), base: r.base.toString(), ctx: ctx.slice(0, 220) });
        }
      });
    } catch (e) {}
  });
});

Object.keys(results).forEach(function (k) {
  console.log('===== ' + k + ' : ' + results[k].length + ' hits =====');
  results[k].forEach(function (h) {
    console.log('  @' + h.addr + ' rangeBase=' + h.base);
    console.log('    ctx: ' + JSON.stringify(h.ctx).slice(0, 260));
  });
});
console.log('[scan-done]');
