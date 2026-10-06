#!/usr/bin/env python3
"""生成 EN↔JP RVA 对照记录（mod menu 素材）。

用法:
  python3 gen_rva_records.py <EN_dump.cs> <JP_dump.cs> <modmenu_doc.md> <out.md> [JP_libil2cpp.so]

原理:
  1) 解析两份 Il2CppDumper 的 dump.cs，得到 (类路径, 方法名) -> RVA
  2) 从 mod menu 记录文档里提取所有 EN RVA
  3) 用 EN dump 反查每个 EN RVA 对应的 (类, 方法)，再在 JP dump 中查同名方法得到 JP RVA
  4) 输出 markdown 对照表 + 本工具已应用的补丁点（含原始字节）
"""
import re
import sys

re_rva = re.compile(r'// RVA: (0x[0-9A-Fa-f]+) Offset: (0x[0-9A-Fa-f]+)')
re_class = re.compile(r'\b(?:class|struct|enum|interface)\s+([<>`A-Za-z0-9_.@]+)')


def parse(path):
    entries = []  # (class_path, method_name, rva)
    stack = []
    last_rva = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip('\t'))
            m_rva = re_rva.search(line)
            if m_rva:
                last_rva = int(m_rva.group(1), 16)
                continue
            m_cls = re_class.search(line)
            if m_cls and '(' not in line:
                while stack and stack[-1][0] >= indent:
                    stack.pop()
                stack.append((indent, m_cls.group(1)))
                last_rva = None
                continue
            if '(' in line and ('{ }' in line or line.rstrip().endswith(';')):
                head = line.split('(')[0].strip()
                tokens = re.split(r'[\s\*&]+', head)
                name = tokens[-1].split('.')[-1].rstrip('>') if tokens else None
                if name and last_rva is not None:
                    cls = '::'.join(n for _, n in stack)
                    entries.append((cls, name, last_rva))
                last_rva = None
    return entries


def main():
    en_dump, jp_dump, doc, out = sys.argv[1:5]
    print('解析 EN dump ...')
    en = parse(en_dump)
    print('  ', len(en), 'methods')
    print('解析 JP dump ...')
    jp = parse(jp_dump)
    print('  ', len(jp), 'methods')

    en_by_rva = {}
    for cls, name, rva in en:
        en_by_rva.setdefault(rva, (cls, name))
    jp_index = {}
    for cls, name, rva in jp:
        jp_index.setdefault((cls, name), rva)

    doc_text = open(doc, encoding='utf-8', errors='replace').read()
    en_rvas = [int(m, 16) for m in re.findall(r'0x([0-9A-Fa-f]{6,8})', doc_text)]
    seen = set()
    ordered = []
    for r in en_rvas:
        if r not in seen and r in en_by_rva:
            seen.add(r)
            ordered.append(r)

    lines = []
    lines.append('# JP RVA 记录（mod menu 素材，仅记录不制作）\n')
    lines.append('> 由 `tools/gen_rva_records.py` 自动生成：EN dump ↔ JP dump 方法名对照。')
    lines.append('> EN = NieR Re[in]carnation 3.7.1（west），JP = 同版本日服构建。')
    lines.append('> JP dump: `jp/dump-jp-3.7.1/out/dump.cs`（Il2CppDumper）。\n')
    lines.append('> 运行时地址 = `libil2cpp.so` 基址 + RVA（本 dump 中 RVA = Offset = VA = 文件偏移）。\n')
    lines.append('| # | 类 | 方法 | EN RVA | JP RVA | 备注 |')
    lines.append('|---|---|---|---|---|---|')
    miss = 0
    for i, r in enumerate(ordered, 1):
        cls, name = en_by_rva[r]
        j = jp_index.get((cls, name))
        if j is None:
            miss += 1
        lines.append('| %d | %s | %s | 0x%X | %s | |' % (
            i, cls, name, r, ('0x%X' % j) if j else '**(未找到)**'))

    lines.append('\n## 本工具已应用的补丁点（JP）\n')
    lines.append('| 补丁 | JP RVA | EN 对照 RVA | 写入字节 | 说明 |')
    lines.append('|---|---|---|---|---|')
    patches = [
        ('ToNativeCredentials (SSL bypass)', 0x3622514, None, 'mov x0,#0; ret', '同 EN 脚本 0x35C8670'),
        ('HandleNet.Encrypt (passthrough)', 0x274AC64, None, 'mov x0,x1; ret', ''),
        ('HandleNet.Decrypt (passthrough)', 0x274AD64, None, 'mov x0,x1; ret', ''),
        ('OctoManager.Internal.GetListAes', 0x4B55B5C, None, 'mov x0,#0; ret', '明文 list.bin'),
        ('Purchaser.IsExistProduct', 0x2834E9C, 0x282CE78, 'mov w0,#1; ret', '免内购'),
        ('<Initialize>d__16.MoveNext (skip _initialized)', 0x2838858, 0x2830834, 'nop', '免内购'),
        ('<PurchaseRealProductAsync>d__28.MoveNext (IsInitialized cbz)', 0x2839CCC, 0x2831CA8, 'nop', '免内购'),
        ('<PurchaseRealProductAsync>d__28.MoveNext (skip alert)', 0x2839CD0, 0x2831CAC, 'b +0x64', '免内购'),
        ('<BuyProduct>d__24.MoveNext (null storeController)', 0x283C04C, 0x2834028, 'cbz x21', '免内购'),
        ('TitleScreen.InitializeMenuButton', 0x304F32C, 0x2F11900, 'ret', 'EOS 菜单'),
        ('com.adjust.sdk.Adjust.start', 0x3F4A250, None, 'ret', '屏蔽 Adjust'),
        ('com.adjust.sdk.AdjustAndroid.Start', 0x3F4A574, None, 'ret', '屏蔽 Adjust'),
    ]
    for name, jpr, enr, b, note in patches:
        lines.append('| %s | 0x%X | %s | `%s` | %s |' % (
            name, jpr, ('0x%X' % enr) if enr else '-', b, note))

    lines.append('\n## 说明 / 注意事项\n')
    lines.append('- JP 与 EN 的 libil2cpp.so **构建不同**（EN `0f9ffec9…` / JP `262bbfb1…`，体积差约 1.1MB），')
    lines.append('  EN 的 RVA **不能**直接用于 JP；端口覆盖类补丁（`NetworkConfig.get_ServerPort` 等）在 JP 上无效，')
    lines.append('  JP 的 API 端口来自 `assets/bin/Data/deace60a64f3d4398a2db0f3d1a41195`（network_config 资源）。')
    lines.append('- 换游戏版本后必须重新用 Il2CppDumper 生成 dump 并更新本表。')
    lines.append('- EN RVA 来源：`NieR-Re-In-Carnation-Mod_Menu/docs/MOD制作记录.md` 与本工具补丁表。')
    lines.append('\n_本文档只记录数据，不包含任何作弊/菜单实现。_\n')

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('写入', out, '；EN RVA 条目', len(ordered), '；JP 未找到', miss)


if __name__ == '__main__':
    main()
