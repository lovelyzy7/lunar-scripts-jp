# JP 私服搭建记录（2026-10-05）

> 结论：**JP 客户端 3.7.1 已成功连接私服并进入游戏；EN 客户端同时正常，两者共用同一服务端实例。**

---

## 1. 环境

| 项目 | 值 |
|---|---|
| 服务端源码 | `E:\NieRReincarnation\lunar-tear\server`（Go 1.26.3） |
| 端口 | auth-server `3000` / lunar-tear `8003` / octo-cdn `8080` |
| PC IP | 192.168.2.6 |
| 手机 | 小米 2308CPXD0C，Android 16，KernelSU 已 root，IP 192.168.2.94 |
| JP 客户端 | `com.square_enix.android_googleplay.nierspjp`，versionCode 152 / versionName 3.7.1 |
| EN 客户端 | `com.square_enix.android_googleplay.nierspww`，3.7.1（同版本） |
| 签名 | `keys/nier.keystore`，alias `nier`，pass `nier123456` |

启动命令（`jp/logs/` 下日志，**Go 日志在 stderr**）：

```
bin\auth-server.exe --listen 0.0.0.0:3000 --db db/auth.db
bin\octo-cdn.exe    --listen 0.0.0.0:8080 --public-addr 192.168.2.6:8080
bin\lunar-tear.exe  --listen 0.0.0.0:8003 --public-addr 192.168.2.6:8003 --db db/game.db ^
                    --octo-url http://192.168.2.6:8080 --auth-url http://0.0.0.0:3000
```

---

## 2. 服务端修改（已构建部署）

| 文件 | 改动 |
|---|---|
| `cmd/lunar-tear/main.go` | 新增环境变量 `LUNAR_MASTERDATA` / `LUNAR_MASTERDATA_VERSION`（可切换主数据文件与版本号） |
| `internal/service/data.go` | 主数据路径/版本号读取上述环境变量，默认值不变（向后兼容） |
| `internal/service/octo.go` | ① `/master-data/` 改为返回真实 database.bin（原来是空 200）；② maintenance 探测页返回 **404**（原来永远 200 → 客户端误判维护中） |
| `internal/service/individualpop.go`（新增） | `GetUnreadPop` 返回空列表 |
| `internal/service/pvp.go`（新增） | 9 个 PVP RPC 空 stub |
| `cmd/lunar-tear/grpc.go` | 注册 `IndividualpopService` + `PvpService` |
| `proto/individualpop.proto` + `gen/proto/individualpop*.go`（新增） | 新协议 |
| `Makefile` | `PROTO_USED` 加入 individualpop |

构建流程脚本：`jp/gen_proto.bat` → `jp/build_server.bat` → `jp/rebuild_cdn.bat` → `jp/deploy_and_restart.bat`
（旧二进制已备份为 `bin\*.exe.bak`；本次改动源码快照在 `jp/server-changes/`）

主数据版本号示例：
```
set LUNAR_MASTERDATA=assets\release\20240404193219.bin.e
set LUNAR_MASTERDATA_VERSION=20240404193219
```

---

## 3. 客户端补丁（两个大坑）

标准流程：`lunar-scripts/android/patch_apk_jp.py`（元数据域名 4 处、libil2cpp 9 处、manifest、network security config）→ apktool b → zipalign → apksigner → root 安装。

### 坑 1：`network_config` 资源文件（关键！）

- 文件：`assets/bin/Data/deace60a64f3d4398a2db0f3d1a41195`（4 KB，Unity 序列化资源）
- 内容结构（小端）：

```
[int32 len][ "api.app.nierreincarnation.jp\0" ][uint32 port=443][4B 尾字段]
```

- **元数据补丁改不到它** → 客户端启动时依旧用官方域名 443 端口 → TLS 校验失败（logcat: `Curl error 35: Handshake did not perform verification`），20% 处报「通信に失敗しました」。
- 修补方法（原地，保持文件大小）：

```
[int32 len=11][ "192.168.2.6" ][1B 对齐补零][uint32 port=8003][其余清零]
```

- **坑中坑：Unity 读字符串按 4 字节对齐**。字符串 11 字节 → 实际占 12 字节。第一次直接把端口写在字符串后（offset 11）时，客户端在 offset 12 读到 `0x001F = 31`，于是疯狂连 `192.168.2.6:31`。补 1 个零字节后端口正确读出 8003。
- EN 客户端的同名文件该区域全为 0（EN 走元数据），所以 EN 不需要这步。

### 坑 2：JP 脚本里 3 个端口覆盖补丁的 RVA 与 EN 相同

`NetworkConfig.get_ServerPort`(0x361D548)、`InitializeApiClient.OnStateBegin`(0x2DEAF68)、`CalculatorNetworking.InitializeApiClient`(0x2E1B278) —— EN/JP 的 libil2cpp.so 构建不同（EN `0f9ffec9…` / JP `262bbfb1…`，体积差 1.1MB），这些 RVA 对 JP 无效。
**影响：JP 客户端的端口只能由上面的资源文件提供**（已解决）。以后若要再改端口，改资源文件即可。

### 验证补丁是否生效的办法

`frida_net2.js`（Frida 17 需用 `Module.findGlobalExportByName`）hook `getaddrinfo` / `connect`，可直接看到客户端解析的域名与连接目标（IP:端口）。

---

## 4. 验证结果

- **JP**：`Auth → GetLatestMasterDataVersion → GetUserData → GameStart → CheckBeforeGamePlay → GetHeaderNotification → InitSequenceSchedule → UpdateMainQuestSceneProgress` 全部 OK；标题画面 → 序章 3D 场景可正常游玩。
- **EN**：同一实例同时正常（`UpdateMainFlowSceneProgress` / `GetRewardGacha`），已进游戏（角色 14 级存档正常）。
- **Octo CDN**：JP `gameId 300558242`、EN `gameId 300116832` 的 `/v1/list/<gameId>/<rev>` 均由同一 octo-cdn 提供。
- 非致命现象：启动时客户端仍会连 `185.151.204.x:443`（SE 官方/CDN/分析服务）并报 `Curl error 35`，**不影响进入游戏**（重试后自动走私服）。

---

## 5. 排查经验

| 现象 | 原因 | 处理 |
|---|---|---|
| 20% 弹「维护中」 | maintenance 探测页返回 200 | octo-cdn 改 404 |
| 20% 弹「通信失败」+ `Curl error 35` | API 域名/端口来源未全补 | 依次查：`global-metadata.dat` 字符串 → `assets/bin/Data` 资源 → libil2cpp 字面量 |
| 连错端口（如 31） | Unity 字符串 4 字节对齐 | 字符串后补零对齐 |
| 改手机 hosts 无效 | Android 应用从 zygote fork，运行时 bind-mount `/system/etc/hosts` 对其不可见 | 不要用 hosts 方案；直接改 APK 内资源，或 KernelSU 系统级模块+重启 |

---

## 6. 回滚

- 服务端：恢复 `bin/*.exe.bak`（或重新构建），并去掉环境变量。
- 客户端：安装原始 `NieR Re[in]carnation_3.7.1_JP.apk`。
- 手机：本记录的临时文件已清理，`/system/etc/hosts` 已恢复原状。

---

## 7. 文件清单

| 路径 | 说明 |
|---|---|
| `jp/nier-jp-private-server-3.7.1.apk` | **最终可用 JP 客户端**（254.8MB，已签名） |
| `jp/patched_work/` | apktool 解包目录（可重复构建） |
| `jp/server-changes/` | 服务端改动源码快照（8 个文件） |
| `jp/frida_net2.js` / `.py` | 网络诊断脚本（域名/连接目标） |
| `jp/build_server.bat` 等 4 个 .bat | 构建/部署/重启脚本 |
| `jp/logs/` | 服务端运行日志（`lunar.err.log` / `octo2.err.log` 有效） |
| `jp/*.png` | 验证截图（jp6=标题, jp7/jp8=JP 游戏内, en1=EN 游戏内） |
