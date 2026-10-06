// 捕获 UniWebView.AddUrlScheme(string) 的入参（C# Il2CppString*）
function readIl2CppString(p) {
  var len = p.add(0x10).readS32();
  if (len < 0 || len > 256) return '<len=' + len + '>';
  var out = '';
  for (var i = 0; i < len; i++) out += String.fromCharCode(p.add(0x14 + i * 2).readU16());
  return out;
}

var base = Process.getModuleByName('libil2cpp.so').base;
console.log('[base] ' + base);

var targets = [
  [0x36051f4, 'UniWebView.AddUrlScheme'],
  [0x3e4f9f0, 'UniWebViewInterface.AddUrlScheme (native)'],
  [0x2d66fd0, 'WebViewDialogPresenter.WebViewOnMessageReceived'],
  [0x2d67164, 'WebViewDialogPresenter.OnWebViewShouldClose'],
  [0x3181610, 'WebViewOnMessageReceived.MoveNext (async)']
];

targets.forEach(function (t) {
  try {
    Interceptor.attach(base.add(t[0]), {
      onEnter: function (args) {
        try {
          var info = { fn: t[1] };
          // 尝试读取第 1、2 个参数（可能是 Il2CppString*）
          for (var i = 0; i < 3; i++) {
            try {
              var p = args[i];
              if (!p.isNull()) {
                var s = readIl2CppString(p);
                if (s && s.length && s.length < 200 && /^[\x20-\x7e\u3000-\u30ff\u4e00-\u9fff]*$/.test(s)) info['a' + i] = s;
              }
            } catch (e) {}
          }
          send(info);
        } catch (e) { send({ fn: t[1], err: String(e) }); }
      }
    });
    console.log('[hooked] ' + t[1]);
  } catch (e) {
    console.log('[hook-err] ' + t[1] + ': ' + e);
  }
});
console.log('[ready]');
