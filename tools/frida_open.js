// 追踪 openat / AAssetManager_open / fopen，定位引继 URL 的来源文件
function hookFn(name, argIndex, mangler) {
  var p = null;
  try { p = Module.findGlobalExportByName(name); } catch (e) {}
  if (!p) { console.log('[miss] ' + name); return; }
  Interceptor.attach(p, {
    onEnter: function (args) {
      try {
        var s = mangler(args);
        if (s) send({ t: name, s: s });
      } catch (e) {}
    }
  });
}
hookFn('openat', 1, function (a) {
  var p = a[1].readCString();
  return (p && (p.indexOf('/data/') === 0 || p.indexOf('octo') >= 0 || p.indexOf('.dat') >= 0)) ? p : null;
});
hookFn('fopen', 0, function (a) {
  var p = a[0].readCString();
  return p && p.indexOf('/data/') === 0 ? p : null;
});
hookFn('AAssetManager_open', 1, function (a) {
  var p = a[1].readCString();
  return p ? ('ASSET:' + p) : null;
});
console.log('[hooks-ready]');
