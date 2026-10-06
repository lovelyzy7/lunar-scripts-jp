#!/usr/bin/env python3
"""
patch_apk.py — Static patcher for NieR Re[in]carnation APK.

Patches an apktool-decompiled APK directory so the game connects to a
private server without any runtime (Frida) hooks.

Patches applied:
  1. global-metadata.dat  — rewrite IL2CPP string literals (URLs + hostname)
  2. network_config asset — rewrite API host + port (Unity serialized resource;
                            4-byte aligned string, port field after padding)
  3. libil2cpp.so          — ARM64 binary patches (SSL bypass, encryption passthrough,
                             Octo plain list, IAP bypass/fast purchase, Adjust block)
  4. AndroidManifest.xml  — networkSecurityConfig + remove Adjust/Firebase autostart
  5. res/xml/network_security_config.xml — allow cleartext traffic
  6. smali (DEX)           — redirect Facebook SDK OAuth to custom auth server
                             via Chrome Custom Tabs (--auth-host)
                              - rewrite domain/format strings in com/facebook/**
                              - force CustomTabUtils.getValidRedirectURI() to
                                always return fbconnect://cct.<pkg>, bypassing
                                the FB SDK's "another app is also listening"
                                security check (broken on devices with the FB
                                app or Lite installed)
                              - flip LoginBehavior.NATIVE_WITH_FALLBACK so
                                it permits ONLY the in-app WebView path
                                (Katana, CCT, Facebook Lite, and Instagram
                                SSO are all disabled). Chrome 117+ silently
                                drops app-launched HTTP-to-private-IP
                                navigations to about:blank in both CCT and
                                regular tabs (HTTPS-Upgrade / Private
                                Network Access), but WebView is governed
                                by the app's own network_security_config
                                and is exempt.
                              - add the API-24 shouldOverrideUrlLoading
                                (WebView, WebResourceRequest) override to
                                WebDialog$DialogWebViewClient so Chromium
                                WebView 75+ actually delivers the
                                fbconnect:// cross-scheme navigation to
                                the SDK (forwards to the existing
                                deprecated string-based overload).
"""

import argparse
import os
import re
import struct
import sys

# ---------------------------------------------------------------------------
# global-metadata.dat string literal patching
# ---------------------------------------------------------------------------

METADATA_MAGIC = 0xFAB11BAF

# Header offsets (v24): each section is a (uint32 offset, uint32 size) pair
HDR_STRING_LITERAL_OFF = 8  # stringLiteral table
HDR_STRING_LITERAL_DATA_OFF = 16  # stringLiteralData blob


def patch_metadata_strings(meta_path: str, replacements: list[tuple[str, str]]) -> int:
    with open(meta_path, "rb") as f:
        data = bytearray(f.read())

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != METADATA_MAGIC:
        print(f"  [!] Bad magic 0x{magic:08X}, expected 0x{METADATA_MAGIC:08X}")
        return 0

    version = struct.unpack_from("<i", data, 4)[0]
    print(f"  metadata v{version}, {len(data)} bytes")

    sl_off, sl_size = struct.unpack_from("<II", data, HDR_STRING_LITERAL_OFF)
    sld_off, sld_size = struct.unpack_from("<II", data, HDR_STRING_LITERAL_DATA_OFF)
    n_entries = sl_size // 8
    print(f"  stringLiteral: {n_entries} entries @ 0x{sl_off:X}")
    print(f"  stringLiteralData: {sld_size} bytes @ 0x{sld_off:X}")

    patched = 0
    for old_str, new_str in replacements:
        old_bytes = old_str.encode("utf-8")
        new_bytes = new_str.encode("utf-8")

        if len(new_bytes) > len(old_bytes):
            print(
                f"  [!] SKIP: replacement longer than original "
                f"({len(new_bytes)} > {len(old_bytes)}): {old_str!r}"
            )
            continue

        # 可能有多个字符串以同一前缀开头（如 reg/top 与 update/top 两条桥 URL），
        # 循环处理直到 data blob 中不再出现该前缀。
        while True:
            blob_pos = data.find(old_bytes, sld_off, sld_off + sld_size)
            if blob_pos < 0:
                break
            data_index = blob_pos - sld_off

            entry_found = False
            for i in range(n_entries):
                e_off = sl_off + i * 8
                e_len, e_idx = struct.unpack_from("<II", data, e_off)
                if e_idx != data_index:
                    continue
                if e_len < len(old_bytes):
                    continue

                if e_len == len(old_bytes):
                    # 完整替换：尾部用 NUL 填充
                    struct.pack_into("<I", data, e_off, len(new_bytes))
                    data[blob_pos : blob_pos + len(old_bytes)] = new_bytes + b"\x00" * (
                        len(old_bytes) - len(new_bytes)
                    )
                    print(f"  entry #{i}: length {e_len} -> {len(new_bytes)}")
                else:
                    # 前缀替换（如 URL 只换 scheme+host，保留后面路径）
                    rest = data[blob_pos + len(old_bytes) : blob_pos + e_len]
                    payload = new_bytes + bytes(rest)
                    struct.pack_into("<I", data, e_off, len(payload))
                    data[blob_pos : blob_pos + e_len] = payload + b"\x00" * (
                        e_len - len(payload)
                    )
                    print(f"  entry #{i}: prefix {len(old_bytes)} of {e_len} -> {len(payload)}")

                entry_found = True
                break

            if not entry_found:
                print(
                    f"  [!] No table entry found for {old_str!r} (dataIndex=0x{data_index:X})"
                )
                break

            print(f"  PATCHED: {old_str!r} -> {new_str!r}")
            patched += 1

    with open(meta_path, "wb") as f:
        f.write(data)

    return patched


# ---------------------------------------------------------------------------
# AndroidManifest.xml  — add networkSecurityConfig attribute
# ---------------------------------------------------------------------------


def patch_manifest(manifest_path: str) -> bool:
    with open(manifest_path, "r", encoding="utf-8") as f:
        text = f.read()

    changed = False

    if "networkSecurityConfig" not in text:
        new_attr = 'android:networkSecurityConfig="@xml/network_security_config"'
        text = text.replace("<application ", f"<application {new_attr} ", 1)
        print(f"  added {new_attr}")
        changed = True
    else:
        print("  already has networkSecurityConfig")

    if 'android:extractNativeLibs="false"' in text:
        text = text.replace(
            'android:extractNativeLibs="false"', 'android:extractNativeLibs="true"'
        )
        print("  extractNativeLibs: false -> true")
        changed = True

    # 移除 Adjust 的 INSTALL_REFERRER 接收器（该 SDK 已在 libil2cpp 中禁用）
    m = re.search(
        r"<receiver[^>]*com\.adjust\.sdk\.AdjustReferrerReceiver.*?</receiver>",
        text,
        re.S,
    ) or re.search(
        r"<receiver[^>]*com\.adjust\.sdk\.AdjustReferrerReceiver[^>]*/>", text, re.S
    )
    if m:
        text = text[: m.start()] + text[m.end() :]
        print("  removed com.adjust.sdk.AdjustReferrerReceiver")
        changed = True

    # 移除 Firebase 自启动 provider（阻止 Firebase/Google 后台请求；推送随之失效）
    for fqcn in (
        "com.google.firebase.provider.FirebaseInitProvider",
        "com.google.firebase.perf.provider.FirebasePerfProvider",
    ):
        m = re.search(
            r"<provider[^>]*" + re.escape(fqcn) + r".*?</provider>", text, re.S
        ) or re.search(
            r"<provider[^>]*" + re.escape(fqcn) + r"[^>]*/>", text, re.S
        )
        if m:
            text = text[: m.start()] + text[m.end() :]
            print(f"  removed {fqcn}")
            changed = True

    if changed:
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(text)

    return True


# ---------------------------------------------------------------------------
# res/xml/network_security_config.xml
# ---------------------------------------------------------------------------

NETWORK_SECURITY_CONFIG = """\
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
"""


def create_network_security_config(res_xml_dir: str) -> bool:
    os.makedirs(res_xml_dir, exist_ok=True)
    out = os.path.join(res_xml_dir, "network_security_config.xml")
    with open(out, "w", encoding="utf-8") as f:
        f.write(NETWORK_SECURITY_CONFIG)
    print(f"  wrote {out}")
    return True


# ---------------------------------------------------------------------------
# smali (DEX) Facebook SDK patching — redirect OAuth to custom auth server
# ---------------------------------------------------------------------------

# The Facebook Android SDK constructs URLs from a base domain + format strings:
#   FacebookSdk.facebookDomain = "facebook.com"
#   ServerProtocol.DIALOG_AUTHORITY_FORMAT  = "m.%s"      -> "m.facebook.com"
#   ServerProtocol.GRAPH_URL_FORMAT         = "https://graph.%s"  -> "https://graph.facebook.com"
#   ServerProtocol.GRAPH_VIDEO_URL_FORMAT   = "https://graph-video.%s"
#
# We patch both the base domain and the format strings so the SDK builds
# URLs pointing at our auth server instead.

SMALI_REPLACEMENTS: list[tuple[str, str]] = [
    # Format strings in ServerProtocol.smali — strip subdomain prefixes
    ('"m.%s"', '"%s"'),
    ('"https://graph.%s"', '"http://%s"'),
    ('"https://graph-video.%s"', '"http://%s"'),
    # Utility.URL_SCHEME — buildUri() hardcodes "https"; downgrade to "http"
    ('"https"', '"http"'),
    # Disable native Facebook app SSO — belt-and-suspenders alongside
    # force_webview_only_login_behavior() (which already drops Katana from
    # NATIVE_WITH_FALLBACK at the LoginBehavior layer). Renaming the package
    # IDs prevents Validate.hasFacebookActivity / Validate.hasInternet
    # PackageManager probes from short-circuiting if the user has the FB
    # app installed.
    ('"com.facebook.katana"', '"com.disabled.katana"'),
    ('"com.facebook.orca"', '"com.disabled.orca"'),
    # Hardcoded full domains (belt-and-suspenders)
    ('"www.facebook.com"', None),  # filled at runtime with auth_host
    ('"graph.facebook.com"', None),
]

# Base domain — replaced separately since it appears in FacebookSdk.smali
SMALI_BASE_DOMAIN = ('"facebook.com"', None)  # filled at runtime


def patch_facebook_smali(apk_dir: str, auth_host: str) -> int:
    """Walk smali/com/facebook/ and rewrite Facebook domain strings."""

    replacements = []
    for old, new in SMALI_REPLACEMENTS:
        if new is None:
            new = f'"{auth_host}"'
        replacements.append((old, new))
    replacements.append((SMALI_BASE_DOMAIN[0], f'"{auth_host}"'))

    fb_dirs = []
    for entry in os.listdir(apk_dir):
        if not entry.startswith("smali"):
            continue
        fb_path = os.path.join(apk_dir, entry, "com", "facebook")
        if os.path.isdir(fb_path):
            fb_dirs.append(fb_path)

    if not fb_dirs:
        print("  [!] No smali/com/facebook/ directories found")
        return 0

    files_patched = 0
    for fb_dir in fb_dirs:
        for dirpath, _, filenames in os.walk(fb_dir):
            for fname in filenames:
                if not fname.endswith(".smali"):
                    continue
                fpath = os.path.join(dirpath, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()

                new_content = content
                for old, new in replacements:
                    new_content = new_content.replace(old, new)

                if new_content != content:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    rel = os.path.relpath(fpath, apk_dir)
                    print(f"  PATCHED: {rel}")
                    files_patched += 1

    return files_patched


def _find_smali(apk_dir: str, rel_path: str) -> str | None:
    """Find rel_path under any smali*/ root in apk_dir."""
    for entry in os.listdir(apk_dir):
        if not entry.startswith("smali"):
            continue
        candidate = os.path.join(apk_dir, entry, *rel_path.split("/"))
        if os.path.isfile(candidate):
            return candidate
    return None


def bypass_cct_redirect_check(apk_dir: str) -> bool:
    """Force CustomTabUtils.getValidRedirectURI() to always return
    getDefaultRedirectURI() ("fbconnect://cct.<pkg>"). The FB SDK normally
    queries the device's PackageManager and bails to "" if any *other* app
    is also listening for the fbconnect URI scheme — which is the case on
    most devices that have the official Facebook app or Lite installed.
    Bypassing that gate lets our own com.facebook.CustomTabActivity (declared
    in AndroidManifest.xml for fbconnect://cct.<pkg>) handle the 302."""
    target = _find_smali(apk_dir, "com/facebook/internal/CustomTabUtils.smali")
    if not target:
        print("  [!] CustomTabUtils.smali not found")
        return False
    with open(target, "r", encoding="utf-8") as f:
        text = f.read()
    needle = (
        "    :cond_0\n"
        "    :try_start_0\n"
        '    const-string v1, "developerDefinedRedirectURI"\n'
    )
    replacement = (
        "    :cond_0\n"
        "    invoke-static {}, Lcom/facebook/internal/CustomTabUtils;->"
        "getDefaultRedirectURI()Ljava/lang/String;\n"
        "\n"
        "    move-result-object p0\n"
        "\n"
        "    return-object p0\n"
        "\n"
        "    :try_start_0\n"
        '    const-string v1, "developerDefinedRedirectURI"\n'
    )
    if needle not in text:
        print("  [!] getValidRedirectURI marker not found (already patched?)")
        return False
    new_text = text.replace(needle, replacement, 1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(
        f"  PATCHED: {os.path.relpath(target, apk_dir)} "
        f"(getValidRedirectURI -> always getDefaultRedirectURI)"
    )
    return True


def patch_customtab_use_plain_view_intent(apk_dir: str) -> bool:
    """Replace CustomTab.openCustomTab's body so it launches the OAuth URL with
    a plain Intent.ACTION_VIEW (regular Chrome tab) instead of CustomTabsIntent.
    launchUrl. This mirrors what the iOS patcher does (forces plain Safari
    instead of ASWebAuthenticationSession / SFSafariViewController) and side-
    steps Chrome CCT's HTTPS-Upgrade / Private Network Access policy that
    silently drops http:// navigations to private IPs from third-party apps
    to about:blank. The OAuth 302 to fbconnect://cct.<pkg> still routes back
    to com.facebook.CustomTabActivity via the existing BROWSABLE intent
    filter in AndroidManifest.xml — same return path as CCT, just opened
    with a regular tab."""
    target = _find_smali(apk_dir, "com/facebook/internal/CustomTab.smali")
    if not target:
        print("  [!] CustomTab.smali not found")
        return False
    with open(target, "r", encoding="utf-8") as f:
        text = f.read()

    needle = (
        ".method public final openCustomTab(Landroid/app/Activity;Ljava/lang/String;)Z\n"
        "    .locals 3\n"
        "\n"
        "    invoke-static {p0}, Lcom/facebook/internal/instrument/crashshield/CrashShieldHandler;->isObjectCrashing(Ljava/lang/Object;)Z\n"
        "\n"
        "    move-result v0\n"
        "\n"
        "    const/4 v1, 0x0\n"
        "\n"
        "    if-eqz v0, :cond_0\n"
        "\n"
        "    return v1\n"
        "\n"
        "    :cond_0\n"
        "    :try_start_0\n"
        "    const-string v0, \"activity\"\n"
        "\n"
        "    invoke-static {p1, v0}, Lkotlin/jvm/internal/Intrinsics;->checkNotNullParameter(Ljava/lang/Object;Ljava/lang/String;)V\n"
        "\n"
        "    .line 38\n"
        "    sget-object v0, Lcom/facebook/login/CustomTabPrefetchHelper;->Companion:Lcom/facebook/login/CustomTabPrefetchHelper$Companion;\n"
        "\n"
        "    invoke-virtual {v0}, Lcom/facebook/login/CustomTabPrefetchHelper$Companion;->getPreparedSessionOnce()Landroidx/browser/customtabs/CustomTabsSession;\n"
        "\n"
        "    move-result-object v0\n"
        "\n"
        "    .line 39\n"
        "    new-instance v2, Landroidx/browser/customtabs/CustomTabsIntent$Builder;\n"
        "\n"
        "    invoke-direct {v2, v0}, Landroidx/browser/customtabs/CustomTabsIntent$Builder;-><init>(Landroidx/browser/customtabs/CustomTabsSession;)V\n"
        "\n"
        "    invoke-virtual {v2}, Landroidx/browser/customtabs/CustomTabsIntent$Builder;->build()Landroidx/browser/customtabs/CustomTabsIntent;\n"
        "\n"
        "    move-result-object v0\n"
        "\n"
        "    .line 40\n"
        "    iget-object v2, v0, Landroidx/browser/customtabs/CustomTabsIntent;->intent:Landroid/content/Intent;\n"
        "\n"
        "    invoke-virtual {v2, p2}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;\n"
        "    :try_end_0\n"
        "    .catchall {:try_start_0 .. :try_end_0} :catchall_0\n"
        "\n"
        "    .line 42\n"
        "    :try_start_1\n"
        "    check-cast p1, Landroid/content/Context;\n"
        "\n"
        "    iget-object p2, p0, Lcom/facebook/internal/CustomTab;->uri:Landroid/net/Uri;\n"
        "\n"
        "    invoke-virtual {v0, p1, p2}, Landroidx/browser/customtabs/CustomTabsIntent;->launchUrl(Landroid/content/Context;Landroid/net/Uri;)V\n"
        "    :try_end_1\n"
        "    .catch Landroid/content/ActivityNotFoundException; {:try_start_1 .. :try_end_1} :catch_0\n"
        "    .catchall {:try_start_1 .. :try_end_1} :catchall_0\n"
        "\n"
        "    const/4 p1, 0x1\n"
        "\n"
        "    return p1\n"
        "\n"
        "    :catch_0\n"
        "    return v1\n"
        "\n"
        "    :catchall_0\n"
        "    move-exception p1\n"
        "\n"
        "    .line 46\n"
        "    invoke-static {p1, p0}, Lcom/facebook/internal/instrument/crashshield/CrashShieldHandler;->handleThrowable(Ljava/lang/Throwable;Ljava/lang/Object;)V\n"
        "\n"
        "    return v1\n"
        ".end method\n"
    )
    replacement = (
        ".method public final openCustomTab(Landroid/app/Activity;Ljava/lang/String;)Z\n"
        "    .locals 4\n"
        "\n"
        "    invoke-static {p0}, Lcom/facebook/internal/instrument/crashshield/CrashShieldHandler;->isObjectCrashing(Ljava/lang/Object;)Z\n"
        "\n"
        "    move-result v0\n"
        "\n"
        "    const/4 v1, 0x0\n"
        "\n"
        "    if-eqz v0, :cond_0\n"
        "\n"
        "    return v1\n"
        "\n"
        "    :cond_0\n"
        "    const-string v0, \"activity\"\n"
        "\n"
        "    invoke-static {p1, v0}, Lkotlin/jvm/internal/Intrinsics;->checkNotNullParameter(Ljava/lang/Object;Ljava/lang/String;)V\n"
        "\n"
        "    :try_start_0\n"
        "    new-instance v2, Landroid/content/Intent;\n"
        "\n"
        "    const-string v3, \"android.intent.action.VIEW\"\n"
        "\n"
        "    iget-object v0, p0, Lcom/facebook/internal/CustomTab;->uri:Landroid/net/Uri;\n"
        "\n"
        "    invoke-direct {v2, v3, v0}, Landroid/content/Intent;-><init>(Ljava/lang/String;Landroid/net/Uri;)V\n"
        "\n"
        "    invoke-virtual {v2, p2}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;\n"
        "\n"
        "    invoke-virtual {p1, v2}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V\n"
        "    :try_end_0\n"
        "    .catch Landroid/content/ActivityNotFoundException; {:try_start_0 .. :try_end_0} :catch_0\n"
        "    .catchall {:try_start_0 .. :try_end_0} :catchall_0\n"
        "\n"
        "    const/4 p1, 0x1\n"
        "\n"
        "    return p1\n"
        "\n"
        "    :catch_0\n"
        "    return v1\n"
        "\n"
        "    :catchall_0\n"
        "    move-exception p1\n"
        "\n"
        "    invoke-static {p1, p0}, Lcom/facebook/internal/instrument/crashshield/CrashShieldHandler;->handleThrowable(Ljava/lang/Throwable;Ljava/lang/Object;)V\n"
        "\n"
        "    return v1\n"
        ".end method\n"
    )
    if needle not in text:
        print(
            "  [!] openCustomTab body marker not found "
            "(already patched, or CustomTab.smali shape changed?)"
        )
        return False
    new_text = text.replace(needle, replacement, 1)
    with open(target, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(
        f"  PATCHED: {os.path.relpath(target, apk_dir)} "
        f"(openCustomTab -> plain Intent.ACTION_VIEW startActivity)"
    )
    return True


def force_webview_only_login_behavior(apk_dir: str) -> bool:
    """Flip LoginBehavior.NATIVE_WITH_FALLBACK so it permits ONLY in-app
    WebView. We disable Katana (FB app SSO), Chrome Custom Tabs, Facebook
    Lite SSO, and Instagram SSO. CCT and a regular Intent.ACTION_VIEW
    Chrome tab both silently drop app-launched HTTP-to-private-IP
    navigations to about:blank under Chrome 117+'s HTTPS-Upgrade and
    Private Network Access policies (the user verified disabling
    chrome://flags/#https-upgrades was insufficient). WebView is governed
    by the app's own network_security_config.xml (cleartextTrafficPermitted
    is already true) and is exempt from those Chromium policies, so it
    reliably loads http://<auth-host>/v14.0/dialog/oauth and intercepts
    the fbconnect:// 302 in shouldOverrideUrlLoading.

    Constructor signature is (Ljava/lang/String;IZZZZZZZ)V where the
    booleans (in order) are: allowsGetTokenAuth (p3/v3),
    allowsKatanaAuth (p4/v4), allowsWebViewAuth (p5/v5),
    allowsDeviceAuth (p6/v6), allowsCustomTabAuth (p7/v7),
    allowsFacebookLiteAuth (p8/v8), allowsInstagramAppAuth (p9/v9).
    Fresh-decompile NATIVE_WITH_FALLBACK is (1,1,1,0,1,1,1); we flip
    v4, v7, v8, v9 to 0 and leave v3 and v5 at 1."""
    target = _find_smali(apk_dir, "com/facebook/login/LoginBehavior.smali")
    if not target:
        print("  [!] LoginBehavior.smali not found")
        return False
    with open(target, "r", encoding="utf-8") as f:
        text = f.read()
    needle = '    const-string v1, "NATIVE_WITH_FALLBACK"'
    start = text.find(needle)
    end = text.find("invoke-direct/range", start) if start >= 0 else -1
    if start < 0 or end < 0:
        print("  [!] NATIVE_WITH_FALLBACK enum-constant block not found")
        return False
    block = text[start:end]
    flips = [
        ("const/4 v4, 0x1", "const/4 v4, 0x0"),  # allowsKatanaAuth = false
        ("const/4 v7, 0x1", "const/4 v7, 0x0"),  # allowsCustomTabAuth = false
        ("const/4 v8, 0x1", "const/4 v8, 0x0"),  # allowsFacebookLiteAuth = false
        ("const/4 v9, 0x1", "const/4 v9, 0x0"),  # allowsInstagramAppAuth = false
    ]
    new_block = block
    applied = []
    for old, new in flips:
        if old in new_block:
            new_block = new_block.replace(old, new, 1)
            applied.append(old.split(", ")[0].split()[-1])  # e.g. "v4"
    if new_block == block:
        print(
            "  [!] no flips applied — NATIVE_WITH_FALLBACK already patched "
            "or layout shifted"
        )
        return False
    with open(target, "w", encoding="utf-8") as f:
        f.write(text[:start] + new_block + text[end:])
    print(
        f"  PATCHED: {os.path.relpath(target, apk_dir)} "
        f"(NATIVE_WITH_FALLBACK -> WebView-only; flipped {', '.join(applied)})"
    )
    return True


def patch_webdialog_request_overload(apk_dir: str) -> bool:
    """Add the API-24 shouldOverrideUrlLoading(WebView, WebResourceRequest)
    override to the FB SDK's WebDialog$DialogWebViewClient. The SDK only
    overrides the deprecated string-based overload, but Chromium WebView
    75+ silently drops cross-scheme navigations (e.g. fbconnect://success)
    when the API-24 overload is absent — the deprecated overload is never
    reached, the SDK never extracts access_token from the URL fragment,
    and LoginManager's success callback never fires. The new overload
    extracts the URL via WebResourceRequest.getUrl().toString() and
    forwards to the existing string-based override on the same instance,
    so all of the SDK's existing fbconnect handling logic runs unchanged."""
    target = _find_smali(
        apk_dir, "com/facebook/internal/WebDialog$DialogWebViewClient.smali"
    )
    if not target:
        print("  [!] WebDialog$DialogWebViewClient.smali not found")
        return False
    with open(target, "r", encoding="utf-8") as f:
        text = f.read()
    sig = (
        "shouldOverrideUrlLoading(Landroid/webkit/WebView;"
        "Landroid/webkit/WebResourceRequest;)Z"
    )
    if sig in text:
        print(f"  [!] {os.path.relpath(target, apk_dir)} already has API-24 overload")
        return False
    new_method = (
        "\n"
        ".method public shouldOverrideUrlLoading(Landroid/webkit/WebView;"
        "Landroid/webkit/WebResourceRequest;)Z\n"
        "    .locals 1\n"
        "\n"
        "    invoke-interface {p2}, Landroid/webkit/WebResourceRequest;->"
        "getUrl()Landroid/net/Uri;\n"
        "\n"
        "    move-result-object v0\n"
        "\n"
        "    invoke-virtual {v0}, Landroid/net/Uri;->toString()Ljava/lang/String;\n"
        "\n"
        "    move-result-object v0\n"
        "\n"
        "    invoke-virtual {p0, p1, v0}, "
        "Lcom/facebook/internal/WebDialog$DialogWebViewClient;->"
        "shouldOverrideUrlLoading(Landroid/webkit/WebView;Ljava/lang/String;)Z\n"
        "\n"
        "    move-result v0\n"
        "\n"
        "    return v0\n"
        ".end method\n"
    )
    if not text.endswith("\n"):
        text += "\n"
    new_text = text + new_method
    with open(target, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(
        f"  PATCHED: {os.path.relpath(target, apk_dir)} "
        f"(added API-24 shouldOverrideUrlLoading WebResourceRequest overload)"
    )
    return True


# ---------------------------------------------------------------------------
# libil2cpp.so ARM64 binary patches
# ---------------------------------------------------------------------------

# ARM64 instruction encodings (little-endian)
MOV_X0_0 = struct.pack("<I", 0xD2800000)  # mov x0, #0
MOV_W0_1 = struct.pack("<I", 0x52800020)  # mov w0, #1
MOV_X0_X1 = struct.pack("<I", 0xAA0103E0)  # mov x0, x1
NOP = struct.pack("<I", 0xD503201F)  # nop
RET = struct.pack("<I", 0xD65F03C0)  # ret
B_0x64 = struct.pack("<I", 0x14000019)  # b +0x64（跳过 CheckPurchasingAlert）
CBZ_X21_0x2E8 = struct.pack("<I", 0xB4001675)  # cbz x21, ...（改走取消分支）


def movz_w_imm16(rd: int, imm: int) -> bytes:
    """Encode ARM64 `MOVZ W<rd>, #imm` for a 16-bit immediate."""
    assert 0 <= rd <= 30, f"rd out of range: {rd}"
    assert 0 <= imm <= 0xFFFF, f"imm out of range: {imm}"
    return struct.pack("<I", 0x52800000 | (imm << 5) | rd)


# RVAs from dump.cs (Il2CppDumper output matching client/3.7.1.apk)
IL2CPP_PATCHES = [
    {
        "name": "ToNativeCredentials",
        "desc": "SSL bypass — return NULL to force insecure gRPC channel",
        "rva": 0x3622514,
        "bytes": MOV_X0_0 + RET,
    },
    {
        "name": "HandleNet.Encrypt",
        "desc": "encryption passthrough — return payload as-is",
        "rva": 0x274AC64,
        "bytes": MOV_X0_X1 + RET,
    },
    {
        "name": "HandleNet.Decrypt",
        "desc": "decryption passthrough — return receivedMessage as-is",
        "rva": 0x274AD64,
        "bytes": MOV_X0_X1 + RET,
    },
    {
        "name": "OctoManager.Internal.GetListAes",
        "desc": "Octo list: force plain list (return false = no AES); server serves raw list.bin",
        "rva": 0x4B55B5C,
        "bytes": MOV_X0_0 + RET,
    },
    {
        "name": "Purchaser.IsExistProduct",
        "desc": "IAP bypass — always report product as existing in store",
        "rva": 0x2834E9C,
        "bytes": MOV_W0_1 + RET,
    },
    # --- Google Play 免内购（对照 EN 的 5 处补丁，RVA 来自 JP 3.7.1 dump）---
    {
        "name": "DarkPurchase.<Initialize>d__16.MoveNext (skip _initialized check)",
        "desc": "Fast purchase — NOP the cbz so Initialize returns via builder (skip ~8s GP timeout)",
        "rva": 0x2838858,
        "bytes": NOP,
    },
    {
        "name": "DarkPurchase.<PurchaseRealProductAsync>d__28.MoveNext (inlined IsInitialized check)",
        "desc": "IAP bypass — NOP the cbz that branches to PurchasingUnavailable when _initialized is false",
        "rva": 0x2839CCC,
        "bytes": NOP,
    },
    {
        "name": "DarkPurchase.<PurchaseRealProductAsync>d__28.MoveNext (skip CheckPurchasingAlert)",
        "desc": "Fast purchase — skip CheckPurchasingAlert call, awaiter and dialog (B to post-alert code)",
        "rva": 0x2839CD0,
        "bytes": B_0x64,
    },
    {
        "name": "Purchaser.<BuyProduct>d__24.MoveNext (null _storeController)",
        "desc": "IAP bypass — redirect null _storeController from NRE to cancelled-return path",
        "rva": 0x283C04C,
        "bytes": CBZ_X21_0x2E8,
    },
    {
        "name": "TitleScreen.InitializeMenuButton",
        "desc": "EOS bypass — skip kHideMenuButtonUnixTime check that hides menu button after service end",
        "rva": 0x304F32C,
        "bytes": RET,
    },
    # --- 外部请求根除：Adjust 归因 SDK（185.151.204.x / app.adjust.*）---
    {
        "name": "com.adjust.sdk.Adjust.start",
        "desc": "Analytics block — no-op the Adjust facade entry point",
        "rva": 0x3F4A250,
        "bytes": RET,
    },
    {
        "name": "com.adjust.sdk.AdjustAndroid.Start",
        "desc": "Analytics block — no-op the Adjust Android SDK init",
        "rva": 0x3F4A574,
        "bytes": RET,
    },
]


# ---------------------------------------------------------------------------
# network_config asset（Unity 序列化资源）：API host + port
# ---------------------------------------------------------------------------

NETWORK_CONFIG_ASSET = "assets/bin/Data/deace60a64f3d4398a2db0f3d1a41195"
NETWORK_CONFIG_HOST = b"api.app.nierreincarnation.jp"


def patch_network_config(apk_dir: str, host: str, port: int) -> bool:
    """把 network_config 资源里的 API 域名 + 端口改到私服。

    结构（小端）：[int32 len][host bytes][填充到 4 字节对齐][uint32 port][4B 尾字段]
    Unity 读字符串按 4 字节对齐 —— 端口必须写在「len + 对齐后长度」的位置，
    否则客户端会把端口字段读错（实测 8003 被读成 0x1F=31）。
    """
    host_b = host.encode("utf-8")
    if len(host_b) > 27:
        sys.exit(f"[!] host too long for network_config asset: {host!r} (max 27)")

    candidates = [os.path.join(apk_dir, NETWORK_CONFIG_ASSET)]
    data_dir = os.path.join(apk_dir, "assets", "bin", "Data")
    if os.path.isdir(data_dir):
        for name in os.listdir(data_dir):
            fp = os.path.join(data_dir, name)
            if os.path.isfile(fp) and os.path.getsize(fp) < 65536:
                candidates.append(fp)

    target = None
    found_host = None
    for fp in candidates:
        try:
            with open(fp, "rb") as f:
                blob = f.read()
        except OSError:
            continue
        if NETWORK_CONFIG_HOST in blob:
            target, found_host = fp, NETWORK_CONFIG_HOST
            break
        if host_b in blob:
            target, found_host = fp, host_b
            break

    if target is None:
        sys.exit("[!] network_config asset not found (original host string missing)")

    with open(target, "rb") as f:
        data = bytearray(f.read())

    pos = data.find(found_host)
    len_off = pos - 4
    orig_len = struct.unpack_from("<i", data, len_off)[0]
    if not (8 <= orig_len <= 64):
        sys.exit(f"[!] unexpected host length {orig_len} in {target}")

    cur_port = struct.unpack_from("<I", data, pos + ((orig_len + 3) // 4) * 4)[0]
    if found_host == host_b:
        pad_ok = data[pos + orig_len : pos + orig_len + ((4 - orig_len % 4) % 4)] == b"\x00" * (
            (4 - orig_len % 4) % 4
        )
        if pad_ok and cur_port == port:
            print(f"  {os.path.relpath(target, apk_dir)}: already patched (host={host!r} port={port})")
            return True

    region_end = pos + orig_len + 4 + 4
    new_blob = struct.pack("<i", len(host_b)) + host_b
    new_blob += b"\x00" * ((-len(host_b)) % 4)
    new_blob += struct.pack("<I", port)
    region_size = region_end - len_off
    if len(new_blob) > region_size:
        sys.exit(f"[!] patched network_config too large ({len(new_blob)} > {region_size})")

    data[len_off:region_end] = new_blob + b"\x00" * (region_size - len(new_blob))
    with open(target, "wb") as f:
        f.write(data)
    print(f"  {os.path.relpath(target, apk_dir)}: host={host!r} port={port}")
    return True


# 原始字节（用于版本校验；来自 JP 3.7.1 libil2cpp.so，Il2CppDumper 点位）
PATCH_EXPECT = {
    0x3622514: bytes.fromhex("f44fbea9fd7b01a9"),
    0x274AC64: bytes.fromhex("f50f1df8f44f01a9"),
    0x274AD64: bytes.fromhex("f50f1df8f44f01a9"),
    0x4B55B5C: bytes.fromhex("f70f1cf8f65701a9"),
    0x2834E9C: bytes.fromhex("ff4301d1f51300f9"),
    0x2838858: bytes.fromhex("68000034"),
    0x2839CCC: bytes.fromhex("e8160034"),
    0x2839CD0: bytes.fromhex("610a43a9"),
    0x283C04C: bytes.fromhex("f51a00b4"),
    0x304F32C: bytes.fromhex("f50f1df8"),
    0x3F4A250: bytes.fromhex("f44fbea9"),
    0x3F4A574: bytes.fromhex("ff0302d1"),
}

JP_3_7_1_LIBIL2CPP_MD5 = "262bbfb1e7335fae90e3472c61409be5"


def patch_unity_connect(apk_dir: str) -> bool:
    """关闭 baked 的 Unity Connect/Analytics/Ads（阻止 config.uca/cdp.cloud.unity3d.com 请求）。

    使用 UnityPy 仅重写对象数据后**原地拼接**回文件，
    避免 UnityPy 全量保存损坏 globalgamemanagers（实测 20.5MB -> 219KB）。
    """
    path = os.path.join(apk_dir, "assets", "bin", "Data", "globalgamemanagers")
    if not os.path.isfile(path):
        print("  [!] globalgamemanagers not found, skip Unity Connect patch")
        return False
    try:
        import UnityPy
    except ImportError:
        print(
            "  [!] UnityPy not installed — skipping Unity Connect/Analytics block.\n"
            "      Install it with: pip install UnityPy"
        )
        return False

    env = UnityPy.load(path)
    target = next((o for o in env.objects if o.type.name == "UnityConnectSettings"), None)
    if target is None:
        print("  [!] UnityConnectSettings not found")
        return False

    tree = target.read_typetree()
    if not tree.get("m_Enabled", False):
        print("  = UnityConnectSettings already disabled")
        return True

    raw_orig = target.get_raw_data()
    byte_start = target.byte_start
    tree["m_Enabled"] = False
    tree["UnityAnalyticsSettings"]["m_Enabled"] = False
    tree["UnityAnalyticsSettings"]["m_InitializeOnStartup"] = False
    tree["UnityAdsSettings"]["m_Enabled"] = False
    tree["UnityAdsSettings"]["m_InitializeOnStartup"] = False
    raw_new = target.save_typetree(tree)
    if len(raw_new) != len(raw_orig):
        print("  [!] UnityConnectSettings size changed, aborting (would corrupt file)")
        return False

    with open(path, "rb") as f:
        data = bytearray(f.read())
    data[byte_start : byte_start + len(raw_new)] = raw_new
    with open(path, "wb") as f:
        f.write(data)
    print("  globalgamemanagers: UnityConnect/Analytics/Ads disabled (in-place)")
    return True


def patch_uniwebview_redirect(apk_dir: str, auth_host: str) -> bool:
    """JP 引继：在 UniWebViewDialog 入口重写官方 BRIDGE 地址到私服，并支持完成标记自动关闭。

    1) load(String)：把 psg.sqex-bridge.jp 重写到私服（来源无关）
    2) shouldOverride(String)：若 URL 含 "bridge-done"，
       dismiss() 关闭对话框（→ onStop → onDialogClose → C# WebViewDone → OnShouldClose）
    需要 .locals +2 作为临时寄存器（原体未用到新寄存器）。
    """
    target = None
    for root, _dirs, files in os.walk(apk_dir):
        if os.path.basename(root) == "uniwebview" and "UniWebViewDialog.smali" in files:
            target = os.path.join(root, "UniWebViewDialog.smali")
            break
    if target is None:
        print("  [!] UniWebViewDialog.smali not found, skip bridge redirect patch")
        return False

    with open(target, encoding="utf-8") as f:
        text = f.read()

    new_host = f"http://{auth_host}"
    changed = False

    # ---- 1) load(): 重写桥 URL ----
    if "bridge-redirect-patch" not in text:
        header = ".method load(Ljava/lang/String;)V\n    .locals "
        idx = text.find(header)
        if idx < 0:
            print("  [!] UniWebViewDialog.load(Ljava/lang/String;)V not found")
        else:
            m = re.match(r"\.method load\(Ljava/lang/String;\)V\n    \.locals (\d+)", text[idx:])
            n = int(m.group(1))
            old_header_len = len(".method load(Ljava/lang/String;)V\n    .locals %d\n" % n)
            inject = (
                ".method load(Ljava/lang/String;)V\n"
                f"    .locals {n + 2}\n\n"
                "    # bridge-redirect-patch: 官方 SQUARE ENIX BRIDGE -> 私服\n"
                f'    const-string v{n}, "https://psg.sqex-bridge.jp"\n'
                f'    const-string v{n + 1}, "{new_host}"\n'
                f"    invoke-virtual {{p1, v{n}, v{n + 1}}}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;\n"
                "    move-result-object p1\n\n"
                f'    const-string v{n}, "http://psg.sqex-bridge.jp"\n'
                f'    const-string v{n + 1}, "{new_host}"\n'
                f"    invoke-virtual {{p1, v{n}, v{n + 1}}}, Ljava/lang/String;->replace(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;\n"
                "    move-result-object p1\n"
            )
            text = text[:idx] + inject + text[idx + old_header_len :]
            print(f"  UniWebViewDialog.load: https://psg.sqex-bridge.jp -> {new_host}")
            changed = True
    else:
        print("  = UniWebViewDialog.load already patched")

    # ---- 2) shouldOverride(): bridge-done 自动关闭 ----
    if "bridge-close-patch" not in text:
        header2 = ".method shouldOverride(Ljava/lang/String;Z)Z\n    .locals "
        idx2 = text.find(header2)
        if idx2 < 0:
            print("  [!] UniWebViewDialog.shouldOverride(Ljava/lang/String;Z)Z not found")
        else:
            m2 = re.match(r"\.method shouldOverride\(Ljava/lang/String;Z\)Z\n    \.locals (\d+)", text[idx2:])
            n2 = int(m2.group(1))
            old2_len = len(".method shouldOverride(Ljava/lang/String;Z)Z\n    .locals %d\n" % n2)
            inject2 = (
                ".method shouldOverride(Ljava/lang/String;Z)Z\n"
                f"    .locals {n2 + 2}\n\n"
                "    # bridge-close-patch: 完成页标记 -> 通知 C# + 自动关闭窗口（模仿 EN 的 SDK 拦截行为）\n"
                f'    const-string v{n2}, "bridge-done"\n'
                f"    invoke-virtual {{p1, v{n2}}}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z\n"
                f"    move-result v{n2 + 1}\n"
                f"    if-eqz v{n2 + 1}, :bridge_orig\n"
                f"    iget-object v{n2}, p0, Lcom/onevcat/uniwebview/UniWebViewDialog;->listener:Lcom/onevcat/uniwebview/UniWebViewDialog$DialogListener;\n"
                f"    invoke-interface {{v{n2}, p0, p1}}, Lcom/onevcat/uniwebview/UniWebViewDialog$DialogListener;->onSendMessageReceived(Lcom/onevcat/uniwebview/UniWebViewDialog;Ljava/lang/String;)V\n"
                "    invoke-virtual {p0}, Landroid/app/Dialog;->dismiss()V\n"
                f"    const/4 v{n2 + 1}, 0x1\n"
                f"    return v{n2 + 1}\n"
                "    :bridge_orig\n"
            )
            text = text[:idx2] + inject2 + text[idx2 + old2_len :]
            print("  UniWebViewDialog.shouldOverride: bridge-done -> auto dismiss")
            changed = True
    else:
        print("  = UniWebViewDialog.shouldOverride already patched")

    if changed:
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
    return changed


def patch_libil2cpp(so_path: str) -> int:
    import hashlib

    with open(so_path, "rb") as f:
        digest = hashlib.md5(f.read()).hexdigest()

    with open(so_path, "r+b") as f:
        file_size = f.seek(0, 2)
        patched = 0
        for p in IL2CPP_PATCHES:
            rva = p["rva"]
            if rva + len(p["bytes"]) > file_size:
                print(f"  [!] SKIP {p['name']}: RVA 0x{rva:X} beyond file size")
                continue

            f.seek(rva)
            orig = f.read(len(p["bytes"]))

            if orig == p["bytes"]:
                print(f"  = {p['name']} @ 0x{rva:X}: already patched")
                patched += 1
                continue

            expect = PATCH_EXPECT.get(rva)
            if expect is not None and orig != expect:
                print(
                    f"  [!] SKIP {p['name']} @ 0x{rva:X}: expected original "
                    f"{expect.hex()}, found {orig.hex()} (different build?)"
                )
                continue

            if orig == b"\x00" * len(orig):
                print(f"  [!] SKIP {p['name']} @ 0x{rva:X}: region is zero-filled")
                continue

            f.seek(rva)
            f.write(p["bytes"])
            patched += 1
            print(f"  {p['name']} @ 0x{rva:X}: {orig.hex()} -> {p['bytes'].hex()}")
            print(f"    {p['desc']}")

    if patched < len(IL2CPP_PATCHES) and digest != JP_3_7_1_LIBIL2CPP_MD5:
        print(
            f"  [!] WARNING: {len(IL2CPP_PATCHES) - patched} patch site(s) not applied and\n"
            f"      libil2cpp.so md5={digest} != tested 3.7.1 JP build ({JP_3_7_1_LIBIL2CPP_MD5}).\n"
            f"      Verify with a fresh Il2CppDumper dump of your APK."
        )

    return patched


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(description="Patch decompiled APK for private server")
    p.add_argument("apk_dir", help="Path to apktool-decompiled APK directory")
    p.add_argument(
        "--grpc-addr",
        required=True,
        help="gRPC game server address as host:port (e.g. 10.0.2.2:443)",
    )
    p.add_argument(
        "--http-addr",
        required=True,
        help="HTTP/CDN address as host:port (e.g. 10.0.2.2:8080)",
    )
    p.add_argument(
        "--auth-host",
        help="Auth server host:port for Facebook OAuth redirect (e.g. 10.0.2.2:3000)",
    )
    args = p.parse_args()

    apk = args.apk_dir.rstrip("/")
    auth_host = args.auth_host

    # Parse gRPC address into host + port.
    grpc_host, grpc_port_str = args.grpc_addr.rsplit(":", 1)
    try:
        gp = int(grpc_port_str)
    except ValueError:
        sys.exit(f"[!] Invalid gRPC port in --grpc-addr: {grpc_port_str!r}")
    if not (1 <= gp <= 65535):
        sys.exit(f"[!] gRPC port must be 1..65535, got {gp}")

    web_url = f"http://{args.http_addr}"

    meta = os.path.join(apk, "assets/bin/Data/Managed/Metadata/global-metadata.dat")
    so = os.path.join(apk, "lib/arm64-v8a/libil2cpp.so")
    manifest = os.path.join(apk, "AndroidManifest.xml")
    res_xml = os.path.join(apk, "res/xml")

    for path in (meta, so, manifest):
        if not os.path.isfile(path):
            sys.exit(f"[!] Not found: {path}")

    # 端口不在元数据里：JP 客户端的 API host+port 来自 assets/bin/Data 下的
    # network_config 资源（见 patch_network_config），元数据里的域名只有 host。

    replacements = [
        ("api.app.nierreincarnation.jp", grpc_host),
        (
            "https://web.app.nierreincarnation.jp/assets/release/{0}/database.bin",
            f"{web_url}/assets/release/{{0}}/database.bin",
        ),
        ("https://mama:na23R6uh7P@web.app.nierreincarnation.jp", web_url),
        ("https://resources-api.app.nierreincarnation.jp/", f"{web_url}/"),
        # 备用（dev）数据库地址，JP 包里存在
        ("https://dev-web.dark.abot.sh", web_url),
    ]

    fb_meta_replacement = None
    if auth_host:
        old_fb = "facebook.com"
        if len(auth_host.encode("utf-8")) > len(old_fb.encode("utf-8")):
            print(
                f"  [!] WARN: auth-host {auth_host!r} longer than {old_fb!r} "
                f"({len(auth_host)} > {len(old_fb)}) — skipping metadata patch "
                f"(smali patch still applies)"
            )
        else:
            fb_meta_replacement = (old_fb, auth_host)
            replacements.append(fb_meta_replacement)

        # JP “データ引継ぎ”走 SQUARE ENIX BRIDGE，把桥地址指到私服 auth-server
        # （服务端对应页面实现后，引继流程即由私服接管）
        bridge_old = "https://psg.sqex-bridge.jp"
        bridge_new = f"http://{auth_host}"
        if len(bridge_new.encode("utf-8")) <= len(bridge_old.encode("utf-8")):
            replacements.append((bridge_old, bridge_new))
            print(f"    bridge URL: {bridge_old} -> {bridge_new}")
        else:
            print(
                f"  [!] WARN: auth-host too long for bridge URL replacement "
                f"({len(bridge_new)} > {len(bridge_old)})"
            )

    for old, new in replacements:
        if len(new.encode("utf-8")) > len(old.encode("utf-8")):
            sys.exit(
                f"[!] Replacement too long ({len(new)} > {len(old)}): "
                f"{old!r} -> {new!r}\n"
                f"    Use a shorter server address or omit the port for port 80."
            )

    print(f"\n[*] Patching for gRPC={args.grpc_addr}, HTTP={args.http_addr}")
    print(f"    web URL   = {web_url}")
    print(f"    gRPC host = {grpc_host}:{gp}")
    if auth_host:
        print(f"    auth host = {auth_host} (Facebook OAuth redirect)")
    else:
        print("    auth host = (none, Facebook login patching skipped)")

    print(f"\n[1] Patching global-metadata.dat string literals ...")
    n = patch_metadata_strings(meta, replacements)
    print(f"    {n}/{len(replacements)} strings patched")

    print(f"\n[2] Patching network_config asset (API host + port) ...")
    patch_network_config(apk, grpc_host, gp)

    print(
        f"\n[3] Patching libil2cpp.so (SSL bypass + encryption passthrough + IAP bypass + fast purchase + analytics block) ..."
    )
    n2 = patch_libil2cpp(so)
    print(f"    {n2}/{len(IL2CPP_PATCHES)} methods patched")

    print(f"\n[3b] Disabling Unity Connect / Analytics baked settings ...")
    patch_unity_connect(apk)

    print(f"\n[4] Patching AndroidManifest.xml ...")
    patch_manifest(manifest)

    print(f"\n[5] Creating network_security_config.xml ...")
    create_network_security_config(res_xml)

    if auth_host:
        print("\n[6] Patching Facebook smali (redirect OAuth to auth server, if present) ...")
        n5 = patch_facebook_smali(apk, auth_host)
        print(f"    {n5} smali files patched")

        print("\n[7] Forcing CustomTabUtils.getValidRedirectURI -> default URI ...")
        bypass_cct_redirect_check(apk)

        print("\n[8] Forcing LoginBehavior.NATIVE_WITH_FALLBACK to WebView-only ...")
        force_webview_only_login_behavior(apk)

        print("\n[9] Rewriting CustomTab.openCustomTab -> plain Intent.ACTION_VIEW ...")
        patch_customtab_use_plain_view_intent(apk)

        print(
            "\n[10] Adding shouldOverrideUrlLoading WebResourceRequest overload "
            "to WebDialog$DialogWebViewClient ..."
        )
        patch_webdialog_request_overload(apk)

        print("\n[11] Rewriting SQUARE ENIX BRIDGE URL in UniWebViewDialog (JP transfer) ...")
        patch_uniwebview_redirect(apk, auth_host)

    print(f"\n[+] Done. Rebuild and sign:")
    print(f"    apktool b {apk} -o patched-unsigned.apk")
    print(f"    zipalign -p -f 4 patched-unsigned.apk patched-aligned.apk")
    print(
        f"    apksigner sign --ks <keystore> --ks-pass pass:<pass> "
        f"--out nier-jp-patched.apk patched-aligned.apk"
    )


if __name__ == "__main__":
    main()
