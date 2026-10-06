// 通过 IL2CPP API 读取 WebViewDialogPresenter 的静态字段值（引导完成回调的 query 参数）
function ex(name) {
  try { return Module.findGlobalExportByName(name); } catch (e) {}
  try { return Module.getExportByName(null, name); } catch (e) {}
  return null;
}

var domainGet = ex('il2cpp_domain_get');
var asmGet = ex('il2cpp_domain_get_assemblies');
var asmImage = ex('il2cpp_assembly_get_image');
var classFromName = ex('il2cpp_class_from_name');
var fieldFromName = ex('il2cpp_class_get_field_from_name');
var fieldStaticGet = ex('il2cpp_field_static_get_value');
console.log('[api] ' + [domainGet, asmGet, asmImage, classFromName, fieldFromName, fieldStaticGet].map(Boolean).join(','));

function readStr(p) {
  try {
    var len = p.add(0x10).readS32();
    if (len < 0 || len > 512) return '<len=' + len + '>';
    var s = '';
    for (var i = 0; i < len; i++) s += String.fromCharCode(p.add(0x14 + i * 2).readU16());
    return s;
  } catch (e) { return '<err>'; }
}

var domain = domainGet();
var sizePtr = Memory.alloc(8);
var asms = asmGet(domain, sizePtr);
var n = sizePtr.readU64().toNumber();
console.log('[assemblies] ' + n);

var found = null;
for (var i = 0; i < n; i++) {
  var asm = asms.add(i * 8).readPointer();
  var img = asmImage(asm);
  var cls = classFromName(img, '', 'WebViewDialogPresenter');
  if (!cls.isNull()) { found = cls; console.log('[class] WebViewDialogPresenter found in image ' + i); break; }
}
if (!found) { console.log('[!] class not found'); } else {
  var fields = [
    'kKeyInquiryMassage', 'kValueInquiryMassage',
    'kKeyOpenMassage', 'kValueOpenMassage',
    'kKeyUrlMassage', 'kSpace', 'kSpaceUrlCode', 'kQuerySeparator',
    'kQueryServerAddress', 'kQueryToken', 'kQueryIsIngame'
  ];
  fields.forEach(function (fn) {
    var f = fieldFromName(found, Memory.allocUtf8String(fn));
    if (f.isNull()) { console.log('  ' + fn + ' = <missing>'); return; }
    var out = Memory.alloc(16);
    fieldStaticGet(f, out);
    var str = readStr(out.readPointer());
    console.log('  ' + fn + ' = ' + JSON.stringify(str));
  });
}
// 同时尝试列出 UniWebView 类里与 scheme 相关的静态字段
var uv = null;
for (var i = 0; i < n; i++) {
  var asm = asms.add(i * 8).readPointer();
  var img = asmImage(asm);
  var cls = classFromName(img, 'com.onevcat.uniwebview', 'UniWebView');
  if (!cls.isNull()) { uv = cls; break; }
}
console.log('[UniWebView class] ' + (uv ? 'found' : 'not found'));
console.log('[done]');
