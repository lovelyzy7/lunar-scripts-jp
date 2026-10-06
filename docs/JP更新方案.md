# JP 更新方案（最终版，2026-10-05）

> 本文档只记录方案与决策，不含代码。执行时按 §8 顺序逐项落地。

---

## 1. 决策清单（已全部确认）

| 编号 | 决策 |
|---|---|
| Q1 | `lunar-scripts-jp/` **必须通用**（像原项目一样，任何人用原版 JP 3.7.1 APK + 自己的服务器地址即可生成可用客户端）；不做 iOS |
| Q2 | 条约页：EN 返回**私服自己的英文条款**；JP 返回**由该英文翻译而成的日文**（不找官方原文）；只改网页正文，保留 `###123###` 标记 |
| Q3 | 引继：**EN 怎么做，JP 就怎么做并适配 JP**（把 SE Bridge 流程改到私服 auth-server） |
| Q4 | 外部请求：**客户端补丁**方式根除，写入 lunar-scripts-jp |
| Q5-4 | EN/JP **合用**：同一实例、同一 `db/game.db`、同一主数据（不做独立库/双实例） |
| Q5-5 | 主数据版本：**固定版本，与 EN 相同**（不做版本号管理） |
| Q5-6 | 换机/引继：照抄 EN 方案 + JP 适配 |
| Q5-7 | 备份：**不需要** |
| Q5-8 | 仓库：**先整理、先写文档 → 用户确认 → 再提交** |
| Q5-10 | Individualpop/PVP 空 stub：**与 EN 保持一致**（不额外开发） |
| 额外 | **免内购**：JP 与 EN 行为一致（无付款界面、物品直接到账） |
| 补充 | Firebase/Google 请求**也一起屏蔽** |
| 附加 | **RVA 数据全部记录**（能用于做 mod menu 的素材，有没有用都记），**但不制作 mod menu** |

---

## 2. T1 — `lunar-scripts-jp/`（通用脚本包，无 iOS）

### 目录结构
```
lunar-scripts-jp/
├─ README.md                    # 中文使用说明：参数、完整命令示例、Keystore 生成、安装注意
├─ requirements.txt             # python 依赖
├─ android/
│   └─ patch_apk_jp.py          # 唯一入口：解包→补丁→重建→对齐→签名（或分步）
├─ assetbundles/                # 与上游一致：list.bin 处理、assetbundle 加解密
├─ masterdata/                  # 与上游一致：patch_masterdata.py、dump/extract 等
├─ (frida 诊断工具已移出仓库 → jp/tools-jp-frida/)
│   └─ frida_net2.js/.py        # 网络诊断（域名解析 / connect 目标）
└─ docs/
    ├─ JP私服搭建记录.md
    └─ JP更新方案.md
```

### 通用参数（不写死任何本地地址）
| 参数 | 示例 | 说明 |
|---|---|---|
| `--apk` | `NieR Re[in]carnation_3.7.1_JP.apk` | 原版 JP APK（自动校验版本/关键字节） |
| `--out` | `nier-jp-patched.apk` | 输出 APK |
| `--grpc-addr` | `host:8003` | 游戏 API（gRPC）地址 |
| `--http-addr` | `host:8080` | 资源/CDN 地址 |
| `--auth-host` | `host:3000` | 账号服务器地址（引继用） |
| `--keystore` / `--ks-pass` / `--ks-alias` | 用户的 keystore | 签名（README 含 keytool 生成示例） |
| 可选开关 | `--no-iap` / `--no-analytics-block` | 允许按需裁剪补丁集 |

### 补丁集（写前逐点校验原字节，不匹配即报错退出）
1. **元数据域名替换**：`api/web/resources-api` 的 `.jp`（及兼容 `.com`）→ `--grpc-addr`/`--http-addr`/`--auth-host`
2. **`network_config` 资源补丁**（本次最大发现，必须并入）：`assets/bin/Data/deace60a64f3d4398a2db0f3d1a41195`，host（字符串需 4 字节对齐补零）+ uint32 端口
3. **libil2cpp 基础补丁**（沿用现有）：SSL bypass、HandleNet 加解密 passthrough、Octo 明文 list、EOS 菜单等（JP 3.7.1 专用 RVA）
4. **免内购补丁集**（新增，对照 EN 的 5 处，见 T5）
5. **外部请求屏蔽补丁集**（新增，见 T4）
6. 移除 3 个对 JP 无效的「端口覆盖」补丁，并在文档注明原因（JP/EN libil2cpp 构建不同）

### 通用性要求
- 任何机器上，只要有 Python + 原版 JP 3.7.1 APK + 自己的服务器地址，即可产出可进游戏的客户端
- README 覆盖：环境准备、完整命令、签名、MIUI root 安装方法、常见问题（维护弹窗/通信失败/端口错位）
- 脚本失败时给出可读原因（版本不匹配、字节校验失败、参数缺失）

---

## 3. T2 — 条约页（EN 原文 + 自译日文）

- **内容**：由私服自行撰写英文条款正文（民间保存服务器、与 SQUARE ENIX/Applibot 无关、资产归属、无商业用途、自担风险等），再由该英文**翻译成日文**。
- **实现**：
  - octo-cdn 按请求路径语言返回不同正文（`/web/static/en/terms/...` → 英文；`/web/static/ja/terms/...` → 日文）
  - 正文改为可维护的文件（便于以后自行替换），保留 `###123###` 版本标记
  - 顺带统一处理 `privacy` 页（同一函数）
- **只改网页正文**：客户端弹窗按钮/标题等原生 UI 不动
- **验收**：EN 客户端显示英文正文；JP 客户端显示日文正文；不触发重复同意；客户端无报错

---

## 4. T3 — JP「データ引継ぎ」私服接管（照抄 EN + JP 适配）

### EN 现有实现（照抄对象）
1. 补丁把 Facebook OAuth 重定向到私服 auth-server（smali 层改 `www.facebook.com` → `--auth-host`）
2. auth-server 提供注册/登录页，成功后带 `#access_token=` 返回
3. 客户端拿 token → 调 `TransferUserByFacebook` → 服务端用 auth-server `/me?access_token=` 校验 → **把当前设备的 UUID 改绑到该账号**（进度继承）
4. 账号管理工具（`register-account`、`claim-account`）保持可用

### JP 差异与适配
- JP 包**没有 Facebook SDK**（dex 仅 adjust/google/square_enix/unity3d），引继走 **SQEX BRIDGE**，元数据里两条 URL：
  ```
  https://psg.sqex-bridge.jp/ntv/{gameId}/reg/top?type={deviceType}&token={bridgeBackupToken}
  https://psg.sqex-bridge.jp/ntv/{gameId}/update/top?type={deviceType}&token={bridgeBackupToken}
  ```
- 适配步骤（写入 lunar-scripts-jp + 服务端）：
  1. **客户端补丁**：上面两条 URL 的 host 改为 `--auth-host`（scheme 按需 https→http），路径保持原样
  2. **auth-server 路由**：新增 `/ntv/{gameId}/reg/top`、`/ntv/{gameId}/update/top`，复用现有 login.html 注册/登录逻辑，接收 `type`/`token` 参数
  3. **回跳机制研究（先做）**：用 Frida 观察 JP 客户端 WebView 的 URL 加载/拦截（`shouldOverrideUrlLoading`、`loadUrl`、JS 桥），确定官方桥页面成功后客户端期待什么（自定义 scheme / URL 片段 / JS 回调），据此实现桥接页返回
  4. **服务端确认 RPC**：JP 引继完成后调用的 RPC（大概率 `TransferUser`）→ 确保改绑 UUID 生效
- **验收**：新设备 JP → 数据引继 → 显示**私服页面**（不再是 SE BRIDGE）→ 登录/注册 → 回游戏 → 进度继承；旧设备可再次引继（行为与 EN 一致）

---

## 5. T4 — 外部请求根除（客户端补丁，含 Firebase/Google）

目标：客户端启动后 **无任何外部 443 连接**、logcat 无 `Curl error 35`。

| 目标 | 现象 | 处理方式 |
|---|---|---|
| Adjust 归因 | `185.151.204.x:443`（ADJUST-ANYCAST）、`app.adjust.com/.world/.net.in/.eu.adjust.com` | dump 定位 Unity 侧 `Adjust` 启动调用 → 跳过；smali 侧 `com.adjust.sdk.Adjust` 生命周期方法置空；移除 manifest 的 `AdjustReferrerReceiver` |
| Unity 分析/云配置 | `config.uca.cloud.unity3d.com`、`cdp.cloud.unity3d.com`（34.111.113.40 等） | dump 定位 `UnityServices.InitializeAsync` / 分析初始化 → 跳过 |
| Firebase | Installations/RemoteConfig/Logging/Crashlytics/Messaging、`www.gstatic.com/firebase/ssl/roots.pem` | 移除 `FirebaseInitProvider` 等自启组件与 `FirebaseInstanceIdReceiver`；`FirebaseApp.initializeApp` 置空防 NPE；主 Activity 保留（沿用 UnityPlayerActivity） |
| Google GMS measurement | 随 Firebase 一并消失 | — |

- **风险与回退**：推送通知将失效（私服不需要）；若移除组件导致异常，按"最小可用集"回退（先 Adjust+Unity，再逐项加 Firebase）
- **验收**：启动 60 秒内 `netstat` 无外部连接；游戏可正常登录游玩；EN 端不受影响（EN 单独确认）

---

## 6. T5 — 免内购（JP，对照 EN 5 处补丁）

用 Il2CppDumper（本机已有 `D:\ReverseTools\Il2CppDumper`）对 JP 3.7.1 重新 dump，定位与 EN 对应的下列方法并打补丁（写前校验字节）：

| EN 补丁 | 作用 |
|---|---|
| `PurchaseRealProductAsync.MoveNext`（IsInitialized 检查） | NOP 掉 `_initialized == false → PurchasingUnavailable` 分支 |
| `PurchaseRealProductAsync.MoveNext`（CheckPurchasingAlert） | 跳过弹窗与 awaiter（快速购买） |
| `Purchaser.<BuyProduct>d__24.MoveNext` | null `_storeController` 时改走取消分支（避免 NRE） |
| `Initialize.MoveNext` | 跳过 `_initialized` 检查（免 8 秒 GP 超时） |
| `Purchaser.IsExistProduct` | 恒 true（JP 已有该补丁 → 复验 RVA） |

- **验收**：JP 宝石商店购买 → **无付款界面、无「系统无法找到您要购买的物品」错误**、物品立即到账；与 EN 行为一致

---

## 7. T6–T11 — 其余任务

| 任务 | 内容 |
|---|---|
| T6 合用 | EN/JP 同实例、同 `db/game.db`、同主数据（维持现状；独立库方案仅在文档备查） |
| T7 主数据版本 | **固定版本（与 EN 一致）**。事实依据：服务端会自动把文件 mtime 拼进版本号（`<base>_<mtime毫秒>`，见 `data.go`），替换主数据文件后客户端自动失效缓存 → 无需版本号管理，替换文件 + 重启服务端即生效 |
| T8 备份 | 不做 |
| T9 文档/仓库 | 先整理 `lunar-scripts-jp/` + `jp/server-changes/` + `docs/`，给用户确认后再提交 Gitea |
| T10 空 stub | Individualpop/PVP 保持与 EN 相同（空实现） |
| T11 回归测试 | 每次改动后固定执行（见下） |

### T11 回归测试用例
| 用例 | 判据 |
|---|---|
| EN 登录进游戏 | 日志 Auth→GameStart 全 OK；无报错弹窗 |
| JP 登录进游戏 | 同上 |
| JP 无外部请求 | 启动 60s `netstat` 无外部 :443；logcat 无 `Curl error 35` |
| JP 免内购 | 商店购买无付款界面、无错误、物品到账 |
| JP 引继 | 显示私服页面 → 登录 → 新设备进度继承 |
| 条款语言 | EN 英文 / JP 日文；弹窗正常关闭 |
| EN 回归 | 条款、免内购、登录均与改动前一致 |

### T12 — RVA 数据记录（mod menu 素材，只记录不制作）

在做任何 RVA 相关工作时（尤其 JP 3.7.1 全量 dump），**把能用于制作 mod menu 的数据全部记录下来**（有没有用都记），但**不制作 mod menu**。

记录内容：
1. **原始 dump 产物**：`Il2CppDumper` 输出（`dump.cs`、`DummyDll/`、`stringliteral.json`、`il2cpp.h`）存到工作目录（如 `jp/dump-jp-3.7.1/`）；文件过大不入 git，必要时放 Releases/LFS
2. **人工整理表** `docs/JPRVA记录.md`（表格式，对齐 EN 的 63 条记录风格），每条包含：
   - 类名、方法名（含签名）、参数个数
   - JP 3.7.1 的 RVA（文件偏移）
   - EN 对应方法的 RVA（便于对照）
   - 用途（伤害/HP/Combo/冷却/队伍/目标/网络/UI/IAP/分析…）
   - 是否本次已补丁、是否真机验证、备注（原指令字节、补丁后字节）
3. **覆盖范围（不管有没有用都要记）**：
   - 战斗数值：伤害 setter、CalculateDamageValue、HP setter 等
   - 连击/冷却：Combo get/set、GetCurrentCombo、ResetCombo、MaxCool/CurCool、动画触发（BattleComboView）
   - 队伍/目标：JoinParty(+PartyId)、TeamId、TargetActor、FromActor
   - 网络/配置：ToNativeCredentials、NetworkConfig.get_ServerPort、InitializeApiClient、Octo 相关
   - UI/流程：TitleScreen、Battle 相关
   - 本次新增：IAP 5 处、Adjust/Unity/Firebase 初始化点
   - dump 中扫描到的其它候选（按类分组，宁多勿漏）
4. **边界**：只做记录与核对，不写任何 menu 注入代码、不改客户端用于作弊

**验收**：`docs/JPRVA记录.md` 完成且有原始 dump 归档；后续若要做 mod menu，可直接照表使用。

---

## 8. 执行顺序

1. **T1** 建立 `lunar-scripts-jp/` 骨架 + 现有补丁迁移/通用化 + README
2. **JP 3.7.1 全量 dump**（供 T5/T4 使用 RVA；同时校验现有 9 处基础补丁 RVA）→ **同期完成 T12 记录**
3. **T4** 外部请求屏蔽（Adjust/Unity/Firebase/Google）+ 真机验证
4. **T5** 免内购 5 处补丁 + 真机验证
5. **T2** 条款页（英文正文 + 日文翻译 + octo 按语言返回）
6. **T3** 引继（先 Frida 研究回跳机制 → 客户端补丁 + auth-server 桥接页 → 真机验证）
7. **T9** 文档/目录整理 → 用户确认 → 提交
8. **T11** 全量回归 + 记录

## 9. 交付物

| 交付物 | 说明 |
|---|---|
| `lunar-scripts-jp/` | 通用脚本包（含 README、补丁脚本、工具、文档） |
| 服务端改动 | 条款页按语言返回、auth-server 桥接路由、（已有）server-changes 快照 |
| JP 客户端 APK | 构建产物（不入仓库，脚本可复现） |
| `docs/JPRVA记录.md` + 原始 dump | mod menu 素材记录（只记录不制作，见 T12） |
| docs | 搭建记录、更新方案、使用说明（确认后再提交） |

## 10. 风险与注意

- **T3 回跳机制**是最大不确定点（需 Frida 实测官方桥行为；如官方页面已不可访问，只能从客户端代码推断）
- **Firebase 组件移除**可能引发异常（有分步回退方案）
- **IAP 补丁**地址来自 dump + 字节校验，仍需真机验证
- 所有补丁**绑定 JP 3.7.1 构建**；换版本需重新 dump 更新 RVA
- 通用性红线：脚本不得出现任何本地专用信息（IP、路径、端口），全部参数化
