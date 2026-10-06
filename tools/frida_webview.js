// 抓取 UniWebView / android.webkit.WebView 加载的 URL（Java 层）
Java.perform(function () {
  function hook(clazz, method, overloads) {
    try {
      var C = Java.use(clazz);
      overloads.forEach(function (sig) {
        try {
          C[method].overload.apply(C[method], sig).implementation = function () {
            var args = Array.prototype.slice.call(arguments);
            console.log("[" + clazz + "." + method + "] " + JSON.stringify(args.map(String).slice(0, 2)));
            return this[method].apply(this, args);
          };
        } catch (e) { console.log("hook " + clazz + "." + method + " " + sig + " err: " + e); }
      });
    } catch (e) { console.log("class " + clazz + " err: " + e); }
  }

  hook("android.webkit.WebView", "loadUrl", [["java.lang.String"], ["java.lang.String", "java.util.Map"]]);
  hook("com.onevcat.uniwebview.UniWebView", "load", [["java.lang.String"], ["java.lang.String", "java.lang.String"]]);
  hook("com.onevcat.uniwebview.UniWebViewDialog", "load", [["java.lang.String"], ["java.lang.String", "java.lang.String"]]);
  console.log("[hook-ready]");
});
