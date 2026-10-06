// frida_scheme_probe.js — 捕获 JP 客户端引继对话框的 scheme 注册与消息原文
// 用法: python tools/frida_scheme_probe.py
// 目标: libil2cpp.so (JP 3.7.1, md5 262bbfb1e7335fae90e3472c61409be5)
// 关键 RVA:
//   UniWebViewInterface.AddUrlScheme(name, scheme) = 0x3E4F9F0
//   UniWebView.AddUrlScheme(this, scheme)          = 0x36051F4
//   BridgeUtility.OpenAccountTransferDialog        = 0x2DFB018
//   BridgeUtility.OpenAccountRegisterDialog        = 0x2DFAF78
//   WebViewDialogPresenter.WebViewOnMessageReceived= 0x2D66FD0
//   WebViewDialogPresenter.Setup                   = 0x2D662A4

const MOD = 'libil2cpp.so';
const base = Process.getModuleByName(MOD).base;

function readCsString(p) {
  try {
    if (!p || p.isNull()) return null;
    const len = p.add(0x10).readS32();
    if (len <= 0 || len > 4096) return null;
    return p.add(0x14).readUtf16String(len);
  } catch (e) { return null; }
}

function hook(rva, label, nArgs) {
  const addr = base.add(rva);
  Interceptor.attach(addr, {
    onEnter(args) {
      const parts = [];
      for (let i = 0; i < nArgs; i++) {
        const s = readCsString(args[i]);
        if (s !== null) parts.push(`arg${i}="${s}"`);
      }
      console.log(`[${label}] ${parts.join(' ')}`);
    }
  });
  console.log(`[probe] hooked ${label} @ ${addr}`);
}

hook(0x3E4F9F0, 'Interface.AddUrlScheme', 2);
hook(0x36051F4, 'UniWebView.AddUrlScheme', 2);
hook(0x2DFB018, 'OpenAccountTransferDialog', 2);
hook(0x2DFAF78, 'OpenAccountRegisterDialog', 2);
// WebViewOnMessageReceived: 原始参数 + 对象内字符串指针扫描
Interceptor.attach(base.add(0x2D66FD0), {
  onEnter(args) {
    const parts = [];
    for (let i = 0; i < 6; i++) parts.push('x' + i + '=' + args[i]);
    console.log('[WebViewOnMessageReceived] ' + parts.join(' '));
    for (let i = 0; i < 6; i++) {
      const s = readCsString(args[i]);
      if (s !== null) console.log('   arg' + i + ' str: "' + s + '"');
      try {
        for (let off = 0; off < 0x48; off += 8) {
          const p = args[i].add(off).readPointer();
          const t = readCsString(p);
          if (t !== null && t.length > 0) console.log('   arg' + i + '+0x' + off.toString(16) + ' str: "' + t + '"');
        }
      } catch (e) {}
    }
  }
});
hook(0x2D662A4, 'WebViewDialogPresenter.Setup', 3);

// Dictionary<string,string>.get_Item — 只记录 WebViewDialogPresenter 区域(0x2D00000-0x2E00000)的读取
var dictBase = base;
Interceptor.attach(base.add(0x3D247C0), {
  onEnter(args) {
    try {
      var off = this.returnAddress.sub(dictBase).toInt32();
      if (off > 0x2D00000 && off < 0x2E00000) {
        this.k = readCsString(args[1]);
        this.log = true;
        console.log('[Dict.get_Item] caller+0x' + off.toString(16) + ' key="' + this.k + '"');
      }
    } catch (e) {}
  },
  onLeave(retval) {
    if (this.log) console.log('   -> val="' + readCsString(retval) + '"');
  }
});

// 字符串比较探针：仅在 WebViewDialogPresenter 相关区域调用时打印
function inRegion(off) { return (off >= 0x2D00000 && off < 0x2E00000) || (off >= 0x3180000 && off < 0x3190000); }
// 通过 returnAddress 过滤调用方区域
function hookStr(rva, label, isInstance) {
  Interceptor.attach(base.add(rva), {
    onEnter(args) {
      try {
        var off = this.returnAddress.sub(base).toInt32();
        if (!inRegion(off)) return;
        this.on = true;
        var a = readCsString(args[isInstance ? 0 : 0]);
        var b = readCsString(args[1]);
        console.log('[' + label + '] caller+0x' + off.toString(16) + ' "' + a + '" <> "' + b + '"');
      } catch (e) {}
    }
  });
}
hookStr(0x436B4DC, 'String.Contains', true);
hookStr(0x436C400, 'String.StartsWith', true);
hookStr(0x435EABC, 'String.op_Equality', false);


// 【已废弃】强制关窗测试(会导致 access violation)，引继改用服务端结果页方案后不再需要，故移除。

console.log('[probe] ready — 现在在 JP 客户端里执行 引继/注册 操作');
