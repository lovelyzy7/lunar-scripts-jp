# JP 主数据适配（20240405123139.bin.e）

本文记录 masterdata/ 工具链适配日服最终主数据的差异分析、改动内容与验证结果。
GL 对照样本：`20240404193219.bin.e`；JP 目标样本：`20240405123139.bin.e`（源文件全程只读，
分析副本置于 `_work/`）。

## 结论速览

**GL 与 JP 的主数据 schema 完全一致**：表集合、列数、补丁列位均无差异，工具链无需分叉；
仅需三类适配——文件名/默认输入识别、`m_abiliwy` 拼写别名、小表不压缩的容错。

## GL / JP 差异表

| 维度 | GL `20240404193219` | JP `20240405123139` | 处置 |
|---|---|---|---|
| 表集合 | 607 张 | 607 张，逐名一致（无缺失/新增/改名） | — |
| schema 覆盖 | 606 命中 + 1 错位 | 同左 | 增补别名（见下） |
| 列结构 | 全部行宽 = schema 列数（0 处偏差） | 同左 | 复用同一 schema |
| 补丁列位 | `m_shop:10`、`m_quest_schedule:3`、`m_login_bonus:5/6` … | 抽查全部为有效 int64 时间戳，与 GL 一致 | 复用同一 `PATCH_COLUMNS` |
| 行数 | — | 72 张表与 GL 不同（纯内容差异） | 按行遍历，天然兼容 |
| 存储形态 | 小/空表 3 张为明文 msgpack 数组（无 LZ4 ExtType99 壳） | 4 张（多 `m_costume_collection_bonus`，JP 为空表转明文） | patch 已容错明文数组 |
| 加密 | AES-128-CBC（内建 key/IV） | 同一对 key/IV | — |

### 行数差异代表项（内容差异，非结构差异）

| 表 | GL 行数 | JP 行数 | 说明 |
|---|---|---|---|
| `m_dokan_text` | 3684 | 1300 | 文本类裁剪 |
| `m_consumable_item` | 832 | 794 | JP 少 38 项 |
| `m_collection_bonus_*` / `m_costume_collection_bonus*` | 有数据 | 0 行 | 系列玩法 JP 未实装 |
| `m_complete_mission_group` | 44 | 0 行 | 同上 |
| `m_maintenance` | 87 | 73 | patch 会统一清空 |

### schema 拼写错位（两服相同）

数据 TOC 里的表名是 `m_abiliwy`（官方数据自带拼写），而 `schemas.json` 原条目写作 `m_ability`，
导致该表一直走 fallback 输出 `m_abiliwy.json`（"1 without schema"）。现于 `schemas.json` 增补
`m_abiliwy` 别名条目（复用 `EntityMAbility` 的 2 列：AbilityId / AbilityLevelGroupId，实测两服
均为 2816 行 × 2 列），dump 后输出规范的 `EntityMAbilityTable.json`。条目总数 607 → 608。

## 改动文件

| 文件 | 改动 |
|---|---|
| `masterdata/dump_masterdata.py` | `--input` 默认值改为双候选自动选取（GL→JP）；按文件名识别并打印 `Region: GL/JP`；`m_abiliwy` 走 schema |
| `masterdata/patch_masterdata.py` | 同上的输入识别；**明文（无 LZ4 壳）表容错**——原逻辑跳过这类表（GL 侧 `m_event_quest_guerrilla_free_open` 等 3 张也被跳过，属顺带修复），现直接在明文数组上打补丁 |
| `masterdata/extract_master_data.py` | 支持直接吃 `.bin.e`（自动解密，`--key/--iv/--key-file/--iv-file/--raw`）；argparse 化；打印 Region |
| `masterdata/msgpack_to_json.py` | 识别 ExtType(99) LZ4 表块并透明解压（extract 产物可直接转 JSON）；其他 ExtType 转义保留 |
| `masterdata/schemas.json` | 增补 `m_abiliwy` 别名条目 |
| `README.md` | 新增「主数据工具链（GL 与 JP 双版本）」章节 |
| `docs/JP主数据适配.md` | 本文 |

## 验证记录（全部在 `_work/` 副本上进行）

### 1) dump / extract / msgpack_to_json

```
Region: JP (from filename JP_20240405123139.bin.e)
  608 entity definitions loaded
  607 tables, data blob: 7558759 bytes
  Dumped 607 tables (0 without schema, 0 failed)
extract_master_data.py  -> Extraction complete: 607 tables saved
msgpack_to_json.py      -> Done: 607 converted, 0 failed
```

### 2) patch（EndDatetime 延期等在 JP 上生效）

```
  Patched 8956 values across 29 tables:
    m_shop: 507 values (EndDatetime)          m_quest_schedule: 963 values (EndDatetime)
    m_possession_acquisition_route: 1579      m_consumable_item_term: 732
    m_gimmick_sequence_schedule: 761 (skipped 937 rows by filter)
    m_login_bonus: 208 (EndDatetime, StampReceiveEndDatetime)
    ...（29 表全清单见运行日志）
  Emptied tables: m_maintenance
  Added rows: m_event_quest_unlock_condition (+1 row)
  Gimmick sequence schedules: 1271 duplicate rows expired
  Labyrinth seasons: 39 rows windowed (1 active per chapter)
```

明文表容错修复后，`m_event_quest_guerrilla_free_open` 的 1 处 EndDatetime 也被正确延期
（修复前会打印 WARNING 并跳过）。

### 3) round-trip 一致性

对 `JP_20240405123139_patched.bin.e` 重新 dump，与补丁前 dump 逐表逐格对比：

- 表集合 607 → 607，两份产物均可无损再解析（0 failed）
- 32 张表存在差异，**全部落在预期类别**：补丁列 → 2030 哨兵值、gimmick/迷宫排期改写（0 或开窗值）、
  unlock 表追加 1 行、`m_maintenance` 清空
- **UNEXPECTED = 0**

### 4) lunar-tear 加载（LUNAR_MASTERDATA）

```powershell
$env:LUNAR_MASTERDATA = '<patched JP .bin.e>'
.\lunar-tear.exe --listen 127.0.0.1:8014 --public-addr 127.0.0.1:8014 \
    --octo-url http://127.0.0.1:18080 --db <独立 game.db 副本>
```

```
master data loaded (607 tables)
game config loaded (goldId=1, skipTicketId=2003, rebirthGold=50000)
consumable item catalog loaded: 794 items      <- JP 值（GL 为 832），确认读到 JP 数据
costume catalog loaded: 17308 costumes, ...
```

验证后进程即停止；测试未触碰现网 3000/8080/8003 服务，测试库为 `_work/test_db` 独立副本。

## 使用速查

```bash
# 自动识别文件名（GL/JP 均可），默认输入按 GL->JP 顺序取第一个存在的
python masterdata/dump_masterdata.py --input <任意版本.bin.e> --output <目录>
python masterdata/patch_masterdata.py --input <JP.bin.e> --output <JP_patched.bin.e>
python masterdata/extract_master_data.py <JP.bin.e> <输出目录>   # 直接吃 .bin.e
python masterdata/msgpack_to_json.py <msgpack目录> <json目录>
```
