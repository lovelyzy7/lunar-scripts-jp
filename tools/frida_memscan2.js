// 全内存区间扫描（含 rw），验证客户端是否加载补丁后的 URL
var patterns = [
  ['our-url', '3139322e3136382e322e363a33303030'],       // 192.168.2.6:3000
  ['se-host', '7073672e737165782d627269646765'],         // psg.sqex-bridge
  ['se-url', '2f6e74762f3235352f757064617465'],          // /ntv/255/update
  ['octo-token', '717a6e384d4c5664665845634e56757145'],  // qzn8MLVdfXEcNVuqE
  ['nier-domain', '6e6965727265696e6361726e6174696f6e']  // nierreincarnation
];

var counts = {};
patterns.forEach(function (p) { counts[p[0]] = 0; });
var samples = {};

Process.enumerateRanges('---').forEach(function (r) {}); // noop
['r--', 'rw-', 'r-x', 'rwx'].forEach(function (prot) {
  Process.enumerateRanges(prot).forEach(function (r) {
    if (r.size > 512 * 1024 * 1024) return;
    patterns.forEach(function (p) {
      try {
        var found = Memory.scanSync(r.base, r.size, p[1]);
        counts[p[0]] += found.length;
        if (found.length && !samples[p[0]]) {
          samples[p[0]] = { prot: prot, base: r.base.toString(), addr: found[0].address.toString() };
        }
      } catch (e) {}
    });
  });
});
console.log(JSON.stringify({ counts: counts, samples: samples }, null, 1));
console.log('[done]');
