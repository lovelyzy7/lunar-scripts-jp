# lunar-scripts-jp

**NieR Re[in]carnation（日服 / JP）私服客户端补丁工具包 —— Android 版（不含 iOS）**

把原版 JP 3.7.1 APK 变成可连接任意私服的客户端（HTTP 明文、免 SSL 校验、免内购、屏蔽官方分析请求）。
与上游 `lunar-scripts`（EN 版）同风格：**地址/端口全部参数化，不包含任何环境专用信息**。

---

## 目录

| 路径 | 说明 |
|---|---|
| `android/patch_apk_jp.py` | 主补丁脚本（解包目录 → 已补丁） |
| `assetbundles/` | asset bundle 解密/加密、`list.bin` 处理（与上游一致） |
| `masterdata/` | 主数据提取 / 打补丁 / 导出（与上游一致） |
| ~~`tools/`~~ | **Frida 诊断脚本已移出仓库** → `jp/tools-jp-frida/`（仅排查用，构建/游玩不需要） |
| `docs/` | 搭建记录、更新方案 |

## 环境要求

- Python 3.9+（`pip install -r requirements.txt`）
- JDK 8+ 与 [Apktool](https://apktool.org/)（`apktool.jar`）
- Android build-tools（`zipalign`、`apksigner`）
- **原版 JP APK**：`NieR Re[in]carnation` 3.7.1（versionCode 152，包名 `com.square_enix.android_googleplay.nierspjp`）

## 使用（四步）

```bash
# 1) 解包
java -jar apktool.jar d -f "NieR Re[in]carnation_3.7.1_JP.apk" -o jp-work

# 2) 打补丁（地址换成你自己的服务器）
python3 android/patch_apk_jp.py jp-work \
    --grpc-addr 203.0.113.10:8003 \
    --http-addr 203.0.113.10:8080 \
    --auth-host 203.0.113.10:3000

# 3) 重建 + 对齐 + 签名（密钥用仓库自带 keys/nier-jp.keystore，三环境通用）
java -jar apktool.jar b jp-work -o patched-unsigned.apk
zipalign -p -f 4 patched-unsigned.apk patched-aligned.apk
apksigner sign --ks keys/nier-jp.keystore --ks-pass pass:lunar-jp --ks-key-alias nier \
    --key-pass pass:lunar-jp --out nier-jp-patched.apk patched-aligned.apk

# 4) 安装
adb install -r nier-jp-patched.apk

# MIUI/部分系统若拦截 adb install，用 root 方式：
adb push nier-jp-patched.apk /data/local/tmp/
adb shell su -c "pm install -r -t /data/local/tmp/nier-jp-patched.apk"
```

## 补丁清单（脚本自动完成）

| # | 位置 | 内容 |
|---|---|---|
| 1 | `global-metadata.dat` | 官方域名 → 你的服务器（api/web/resources-api/dev 备用地址 + 引继桥地址） |
| 2 | `assets/bin/Data/…`（network_config 资源） | **API host + 端口**（唯一有效端口来源；字符串 4 字节对齐，端口错位会读成 31） |
| 3 | `libil2cpp.so` | SSL 校验绕过（`ToNativeCredentials` → NULL） |
| 4 | `libil2cpp.so` | 加解密 passthrough（`HandleNet.Encrypt/Decrypt`） |
| 5 | `libil2cpp.so` | Octo list 明文（`GetListAes` → false） |
| 6 | `libil2cpp.so` | **免内购 / 快速购买**（5 处：`Purchaser.IsExistProduct`、`<BuyProduct>d__24.MoveNext`、`<PurchaseRealProductAsync>d__28.MoveNext` ×2、`<Initialize>d__16.MoveNext`） |
| 7 | `libil2cpp.so` | **屏蔽 Adjust 归因 SDK**（`Adjust.start`、`AdjustAndroid.Start` → `ret`） |
| 8 | `AndroidManifest.xml` | 明文流量许可；移除 Adjust 接收器与 Firebase 自启 provider |
| 9 | `res/xml/network_security_config.xml` | 允许 cleartext |
| 10 | smali（如存在） | Facebook OAuth 重定向到私服 auth（EN 流程；JP 包通常没有 FB SDK，会自动跳过） |

## 参数说明与限制

| 参数 | 说明 | 长度限制 |
|---|---|---|
| `--grpc-addr host:port` | 游戏 API（gRPC）地址与端口 | host ≤ 27 字符 |
| `--http-addr host:port` | 资源/CDN 地址 | — |
| `--auth-host host:port` | 账号/引继服务器地址（可省略） | ≤ 18 字符（引继 URL 替换限制） |

## 签名密钥（三条路径统一，故意入库）

`keys/nier-jp.keystore` 随仓库分发（`.gitignore` 明确 `!keys/*.keystore`，push 不会被忽略），
本地 / Colab / 手动三条签名路径**共用同一密钥**，因此各环境产出的 APK 可互相 `adb install -r` 覆盖安装。

| 参数 | 值 |
|---|---|
| 文件 | `keys/nier-jp.keystore`（JKS，RSA 2048，有效期 10000 天） |
| alias | `nier` |
| store/key 密码 | `lunar-jp` |

| 路径 | 签名方式 | 密钥来源 |
|---|---|---|
| 本地 `run_local.py` / `android/build_apk.py build` | uber-apk-signer（自动传 `--ks`） | `keys/nier-jp.keystore`（默认，可用 `--ks` 覆盖） |
| Colab「Patch APK」单元格 | `apksigner sign --ks /content/scripts-jp/keys/nier-jp.keystore` | 同上（随仓库克隆到 Colab） |
| README 手动四步 | `apksigner sign --ks keys/nier-jp.keystore` | 同上 |

> 私钥入库是**有意为之**：目标是三环境签名一致、覆盖安装不报签名冲突，仅私服/学习用途，
> **勿把此密钥用于其他项目**。若要换成自己的密钥：用同名同密码替换 `keys/nier-jp.keystore` 即可零改动，
> 或同步修改 `android/build_apk.py` 常量、Colab 单元格与本节。

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 20% 弹「维护中」 | 服务端 `/web/static/*/system/maintenance` 返回了 200；应返回 404 |
| 20% 弹「通信失败」+ logcat `Curl error 35` | 客户端仍在连官方地址：确认补丁 1/2 都成功（脚本日志会打印每个补丁点） |
| 连接端口异常（如 31） | network_config 资源端口字段错位；本脚本已按 4 字节对齐写入 |
| 商店购买弹付款/报错 | 补丁 6 未生效；用 `--keep-iap` 之外的默认参数重跑脚本并确认 libil2cpp 补丁点 |
| 覆盖安装报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 旧包不是本密钥签的（比如老的 debug keystore 包）；卸载一次后重装，之后统一密钥即可互相覆盖 |
| 客户端启动即闪退 | 可能是 Firebase provider 移除导致；检查 logcat，必要时回退该项（见 `patch_manifest`） |

## 文本规范（编码 / 换行符，务必遵守）

仓库里出现过 `LF will be replaced by CRLF` 警告和 Windows 控制台乱码，规范如下，提交前自查：

| 项 | 规则 |
|---|---|
| 编码 | 一律 **UTF-8 无 BOM**（禁止 UTF-8 BOM / UTF-16 / GBK 保存） |
| 换行符 | 文本文件一律 **LF**；**仅 `*.bat` 用 CRLF**（符合 `.gitattributes`） |
| 批处理 | `*.bat` **只写 ASCII**，并保留 `chcp 65001`（cmd.exe 用 OEM 代码页，UTF-8 中文会乱码） |
| Shell | `*.sh` 保持 LF 且 `chmod +x`（git 模式 100755） |
| Python | Windows 下打印非 ASCII 的脚本需 UTF-8 stdio（参考 `_enable_utf8_stdio()`） |

```bash
python3 check_text_hygiene.py    # 一键检查：编码 / BOM / 换行符 / 乱码风险
```

通过输出 `OK`；有问题会列出文件与原因并以非 0 退出，适合接 pre-commit / CI。

## 免责声明

仅供学习与私服存档用途，请勿用于商业行为。游戏与素材版权归 SQUARE ENIX / Applibot 所有。

## Python 环境（venv）

```bash
bash setup.sh          # 或 setup.bat（Windows）
bash run_local.sh      # 一键流程（或 run_local.bat）
source .venv/bin/activate
```

依赖全部装进 venv（`requirements.txt`：pycryptodome / protobuf / msgpack / lz4 / UnityPy）；
补丁脚本 `android/patch_apk_jp.py` 仅用 Python 标准库。

## 云端运行（Colab）

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/lovelyzy7/lunar-scripts-jp/blob/main/colab/lunar-scripts-jp.ipynb)

仓库：https://github.com/lovelyzy7/lunar-scripts-jp

## APK 工具（跨平台）

```bash
python android/build_apk.py tools                        # 下载 apktool.jar + uber-apk-signer.jar
python android/build_apk.py unpack <原始.apk> work/jp-final
python android/build_apk.py build  work/jp-final out/JP-modded.apk
```

需要 java（JDK 11+）。产物签名后可直接安装。

## 一键脚本（本地）

```bat
run_local.bat        :: Windows（双击或命令行）
bash run_local.sh    :: Linux / macOS
```

首次运行会自动生成 `local/config.json`，填好 `apk`（可留空 `out`）与服务器地址后再运行：

```bat
run_local.bat
run_local.bat --apk "D:\path\game.apk" --out "D:\path\patched.apk" --grpc 1.2.3.4:8003 --http 1.2.3.4:8080 --auth 1.2.3.4:3000
run_local.bat --from 5          :: 跳过下载/解包，改地址后快速重打补丁
run_local.bat --reinstall-deps  :: 重装 venv 依赖
```

流程：Java 检查 → venv 依赖 → APK 工具 → 解包 → 打补丁 →（可选）主数据 → 重建签名。

- `local/config.json` 中路径建议用正斜杠（`D:/Games/game.apk`），单反斜杠会被自动修正；
- `masterdata` 留空即跳过；有值则输出固定 `20240404193219.bin.e`（与 APK 同目录）；
- `reuse_unpack: true` 时复用 `work/jp-final`，省去重复解包时间。
