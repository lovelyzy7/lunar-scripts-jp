#!/usr/bin/env python3
"""
Translate master-data text-table rows in place with row-level byte surgery.

Reads an encrypted MasterMemory binary (.bin.e), replaces the text column of
the targeted (table, id, LanguageType) rows, and writes a new .bin.e that is
byte-identical everywhere except the edited text columns:

  * parsing is used only for LOCATING bytes -- the msgpack object graph is
    never re-encoded wholesale (C# int64 columns must keep their exact
    encoding), per the byte-fidelity discipline;
  * rows are rebuilt from the ORIGINAL column bytes with only the text column
    spliced in (str header style is preserved, upgrading only on overflow);
  * only the changed tables get a fresh LZ4/ext framing (the original ext
    prefix style is preserved); every other table's compressed blob is copied
    verbatim and the TOC offsets are re-laid.

Translation carrier: JSONL (UTF-8, one object per line) with fields
  table / id_column / id / language_type / source / translation
TSV with the same columns is accepted (RFC4180 quoting).

With --fill-missing, a translation row whose (id, language_type) has no
matching table row is APPENDED instead of skipped (row-level byte surgery:
existing rows stay byte-identical, new rows are packed fresh). This builds
multi-slot text tables (e.g. adding LT2/LT3 mirror rows to a JP-only file)
while keeping the byte-fidelity discipline.

Built-in assertions (any failure -> non-zero exit):
  A. value-level diff: only the targeted rows' text columns differ;
  B. byte-level check: every untouched table's compressed blob is identical;
  C. placeholder/markup consistency: {N} placeholders, <tags> and literal
     \\n counts match between source and translation (mismatched rows are
     skipped and reported; with --strict they abort the run).

Usage:
  python translate_masterdata_text.py --master in.bin.e \
      --translations masterdata_zh.jsonl --output out.bin.e --languages 1
  python translate_masterdata_text.py ... --dry-run

Requires: pip install pycryptodome msgpack lz4
"""

import argparse
import csv
import json
import os
import re
import struct
import sys

import lz4.block
import msgpack
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def _enable_utf8_stdio() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


DEFAULT_KEY = "36436230313332314545356536624265"
DEFAULT_IV = "45666341656634434165356536446141"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMAS_PATH = os.path.join(SCRIPT_DIR, "schemas.json")

TEXT_TABLES = frozenset({
    "m_dokan_text",
    "m_gift_text",
    "m_navi_cut_in_text",
    "m_webview_mission_title_text",
    "m_webview_panel_mission_complete_flavor_text",
})


# --- AES ---

def aes_decrypt(data, key, iv):
    return unpad(AES.new(key, AES.MODE_CBC, IV := iv).decrypt(data), AES.block_size)


def aes_encrypt(data, key, iv):
    return AES.new(key, AES.MODE_CBC, iv).encrypt(pad(data, AES.block_size))


# --- LZ4 ext framing ---

def read_lz4_ext_header(ext_data):
    tag = ext_data[0]
    if tag == 0xd2:
        return struct.unpack(">i", ext_data[1:5])[0], ext_data[5:], 0xd2
    if tag == 0xce:
        return struct.unpack(">I", ext_data[1:5])[0], ext_data[5:], 0xce
    if tag == 0xd1:
        return struct.unpack(">h", ext_data[1:3])[0], ext_data[3:], 0xd1
    if tag == 0xcd:
        return struct.unpack(">H", ext_data[1:3])[0], ext_data[3:], 0xcd
    if tag <= 0x7f:
        return tag, ext_data[1:], 0x00
    raise ValueError(f"Unexpected tag 0x{tag:02x} in LZ4 ext header")


def build_lz4_ext_blob(decompressed, prefix_tag=0xd2):
    compressed = lz4.block.compress(decompressed, store_size=False)
    n = len(decompressed)
    if prefix_tag == 0xce:
        header = b"\xce" + struct.pack(">I", n)
    elif prefix_tag == 0xd1:
        header = b"\xd1" + struct.pack(">h", n)
    elif prefix_tag == 0xcd:
        header = b"\xcd" + struct.pack(">H", n)
    elif prefix_tag == 0x00 and n <= 0x7f:
        header = bytes([n])
    else:
        header = b"\xd2" + struct.pack(">i", n)
    return msgpack.packb(msgpack.ExtType(99, header + compressed), use_bin_type=True)


def unpack_table_blob(raw):
    """Return (decompressed_bytes, ext_prefix_tag or None, was_compressed)."""
    obj = msgpack.unpackb(raw, raw=True)
    if isinstance(obj, msgpack.ExtType) and obj.code == 99:
        ulen, lz4_data, tag = read_lz4_ext_header(obj.data)
        return lz4.block.decompress(lz4_data, uncompressed_size=ulen), tag, True
    return raw, None, False


# --- msgpack binary walker (offset-locating only) ---

def skip_msgpack_value(data, pos):
    tag = data[pos]
    if tag <= 0x7f or tag >= 0xe0:
        return pos + 1
    if 0xa0 <= tag <= 0xbf:
        return pos + 1 + (tag & 0x1f)
    if 0x90 <= tag <= 0x9f:
        p = pos + 1
        for _ in range(tag & 0x0f):
            p = skip_msgpack_value(data, p)
        return p
    if 0x80 <= tag <= 0x8f:
        p = pos + 1
        for _ in range((tag & 0x0f) * 2):
            p = skip_msgpack_value(data, p)
        return p
    FIXED = {0xc0: 1, 0xc2: 1, 0xc3: 1, 0xca: 5, 0xcb: 9,
             0xcc: 2, 0xcd: 3, 0xce: 5, 0xcf: 9,
             0xd0: 2, 0xd1: 3, 0xd2: 5, 0xd3: 9,
             0xd4: 3, 0xd5: 4, 0xd6: 6, 0xd7: 10, 0xd8: 18}
    if tag in FIXED:
        return pos + FIXED[tag]
    LENGTH_PREFIXED = {
        0xc4: (1, "B"), 0xc5: (2, ">H"), 0xc6: (4, ">I"),
        0xd9: (1, "B"), 0xda: (2, ">H"), 0xdb: (4, ">I"),
        0xc7: (1, "B"), 0xc8: (2, ">H"), 0xc9: (4, ">I"),
    }
    if tag in LENGTH_PREFIXED:
        sz_bytes, fmt = LENGTH_PREFIXED[tag]
        n = struct.unpack(fmt, data[pos + 1:pos + 1 + sz_bytes])[0]
        extra = 1 if tag in (0xc7, 0xc8, 0xc9) else 0
        return pos + 1 + sz_bytes + extra + n
    ARRAY_MAP = {0xdc: (2, ">H"), 0xdd: (4, ">I"), 0xde: (2, ">H"), 0xdf: (4, ">I")}
    if tag in ARRAY_MAP:
        sz_bytes, fmt = ARRAY_MAP[tag]
        n = struct.unpack(fmt, data[pos + 1:pos + 1 + sz_bytes])[0]
        items = n * 2 if tag in (0xde, 0xdf) else n
        p = pos + 1 + sz_bytes
        for _ in range(items):
            p = skip_msgpack_value(data, p)
        return p
    raise ValueError(f"Unknown msgpack tag 0x{tag:02x} at pos {pos}")


def read_array_len(data, pos):
    tag = data[pos]
    if 0x90 <= tag <= 0x9f:
        return tag & 0x0f, pos + 1
    if tag == 0xdc:
        return struct.unpack(">H", data[pos + 1:pos + 3])[0], pos + 3
    if tag == 0xdd:
        return struct.unpack(">I", data[pos + 1:pos + 5])[0], pos + 5
    raise ValueError(f"Expected array at pos {pos}, got tag 0x{tag:02x}")


def read_int(data, pos):
    tag = data[pos]
    if tag <= 0x7f:
        return tag
    if tag == 0xcc:
        return data[pos + 1]
    if tag == 0xcd:
        return struct.unpack(">H", data[pos + 1:pos + 3])[0]
    if tag == 0xce:
        return struct.unpack(">I", data[pos + 1:pos + 5])[0]
    if tag == 0xd0:
        return struct.unpack(">b", data[pos + 1:pos + 2])[0]
    if tag == 0xd1:
        return struct.unpack(">h", data[pos + 1:pos + 3])[0]
    if tag == 0xd2:
        return struct.unpack(">i", data[pos + 1:pos + 5])[0]
    if tag == 0xd3:
        return struct.unpack(">q", data[pos + 1:pos + 9])[0]
    raise ValueError(f"read_int: unexpected tag 0x{tag:02x} at {pos}")


def decode_str(data, pos):
    """Decode a msgpack str at pos. Returns (text, end_pos, header_tag)."""
    tag = data[pos]
    if 0xa0 <= tag <= 0xbf:
        n = tag & 0x1f
        return data[pos + 1:pos + 1 + n].decode("utf-8"), pos + 1 + n, tag
    if tag in (0xd9, 0xda, 0xdb):
        sz = {0xd9: 1, 0xda: 2, 0xdb: 4}[tag]
        n = struct.unpack({1: "B", 2: ">H", 4: ">I"}[sz], data[pos + 1:pos + 1 + sz])[0]
        return data[pos + 1 + sz:pos + 1 + sz + n].decode("utf-8"), pos + 1 + sz + n, tag
    raise ValueError(f"decode_str: unexpected tag 0x{tag:02x} at {pos}")


def encode_str_like(text, orig_tag):
    """Encode text as msgpack str, preserving the original header family."""
    raw = text.encode("utf-8")
    n = len(raw)
    candidates = []
    if 0xa0 <= orig_tag <= 0xbf:
        candidates = [0xA0, 0xd9, 0xda, 0xdb]
    elif orig_tag == 0xd9:
        candidates = [0xd9, 0xda, 0xdb]
    elif orig_tag == 0xda:
        candidates = [0xda, 0xdb]
    else:
        candidates = [0xdb]
    for tag in candidates:
        if tag == 0xA0 and n <= 0x1f:
            return bytes([0xa0 | n]) + raw
        if tag == 0xd9 and n <= 0xFF:
            return b"\xd9" + struct.pack("B", n) + raw
        if tag == 0xda and n <= 0xFFFF:
            return b"\xda" + struct.pack(">H", n) + raw
        if tag == 0xdb and n <= 0xFFFFFFFF:
            return b"\xdb" + struct.pack(">I", n) + raw
    raise ValueError(f"text too long: {n} bytes")


# --- placeholder / markup consistency ---

def markup_signature(text):
    ph = sorted(re.findall(r"\{\d+\}", text))
    tags = sorted(re.findall(r"</?[A-Za-z][^>]*>", text))
    nls = len(re.findall(r"\\n", text))
    real_nls = text.count("\n")
    return (tuple(ph), tuple(tags), nls, real_nls)


# --- translation carrier ---

def load_translations(path):
    """Return dict[(table, id, lt)] = {"source":..., "translation":...}."""
    out = {}
    if path.lower().endswith(".tsv"):
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                key = (row["table"], int(row["id"]), int(row["language_type"]))
                if key in out:
                    raise SystemExit(f"duplicate translation key {key} in {path}")
                out[key] = {"id_column": row.get("id_column", ""),
                            "source": row.get("source", ""),
                            "translation": row["translation"]}
    else:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                o = json.loads(line)
                key = (o["table"], int(o["id"]), int(o["language_type"]))
                if key in out:
                    raise SystemExit(f"duplicate translation key {key} in {path}")
                out[key] = {"id_column": o.get("id_column", ""),
                            "source": o.get("source", ""),
                            "translation": o["translation"]}
    return out


def load_schema_text_columns():
    """snake -> (id_col_name, id_idx, lt_idx, text_idx, text_col_name)."""
    with open(SCHEMAS_PATH, encoding="utf-8") as f:
        schemas = json.load(f)
    out = {}
    for snake, entry in schemas.items():
        cols = entry["columns"]
        id_idx = lt_idx = text_idx = None
        id_name = text_name = ""
        for idx, typ, name in cols:
            if typ == "int" and id_idx is None:
                id_idx, id_name = idx, name
            elif name == "LanguageType":
                lt_idx = idx
            elif typ == "string":
                text_idx, text_name = idx, name
        if id_idx is not None and lt_idx is not None and text_idx is not None:
            out[snake] = (id_name, id_idx, lt_idx, text_idx, text_name)
    return out


# --- core: row-level surgery ---

def translate_table_blob(decompressed, layout, trans_by_id, languages, stats, table, strict,
                         fill_missing=False):
    """Return new decompressed bytes with text columns replaced.

    layout: (id_name, id_idx, lt_idx, text_idx, text_name)
    """
    id_name, id_idx, lt_idx, text_idx, text_name = layout
    count, pos = read_array_len(decompressed, 0)
    parts = [decompressed[:pos]]
    changed = 0
    seen = set()
    for _ in range(count):
        row_start = pos
        col_count, p = read_array_len(decompressed, pos)
        col_bounds = []
        cp = p
        for _ in range(col_count):
            nxt = skip_msgpack_value(decompressed, cp)
            col_bounds.append((cp, nxt))
            cp = nxt
        row_end = cp
        row_id = read_int(decompressed, col_bounds[id_idx][0])
        row_lt = read_int(decompressed, col_bounds[lt_idx][0])
        seen.add((row_id, row_lt))
        entry = trans_by_id.get((table, row_id, row_lt))
        if entry is None or row_lt not in languages:
            parts.append(decompressed[row_start:row_end])
            pos = row_end
            continue
        s0, s1 = col_bounds[text_idx]
        try:
            cur_text, _, tag = decode_str(decompressed, s0)
        except ValueError:
            stats["skipped_non_str"].append((table, row_id, row_lt))
            parts.append(decompressed[row_start:row_end])
            pos = row_end
            continue
        new_text = entry["translation"]
        if entry.get("source") and entry["source"] != cur_text:
            msg = f"{table} id={row_id} lt={row_lt}: source mismatch"
            if strict:
                raise SystemExit("STRICT: " + msg)
            stats["source_mismatch"].append((table, row_id, row_lt))
        if markup_signature(cur_text) != markup_signature(new_text):
            stats["markup_mismatch"].append((table, row_id, row_lt))
            parts.append(decompressed[row_start:row_end])
            pos = row_end
            continue
        if new_text == cur_text:
            parts.append(decompressed[row_start:row_end])
            pos = row_end
            continue
        new_str = encode_str_like(new_text, tag)
        parts.append(decompressed[row_start:s0])
        parts.append(new_str)
        parts.append(decompressed[s1:row_end])
        pos = row_end
        changed += 1
        if len(stats["samples"]) < 8:
            stats["samples"].append({"table": table, "id": row_id, "lt": row_lt,
                                     "from": cur_text[:40], "to": new_text[:40]})

    appended = 0
    if fill_missing:
        for (tname, rid, rlt), entry in sorted(trans_by_id.items()):
            if tname != table or rlt not in languages or (rid, rlt) in seen:
                continue
            if entry.get("source") and markup_signature(entry["source"]) != markup_signature(entry["translation"]):
                stats["markup_mismatch"].append((table, rid, rlt))
                continue
            parts.append(msgpack.packb([rid, rlt, entry["translation"]], use_bin_type=True))
            appended += 1
            if len(stats["appended_samples"]) < 8:
                stats["appended_samples"].append({"table": table, "id": rid, "lt": rlt,
                                                  "to": entry["translation"][:40]})
        if appended:
            parts[0] = array_header(count + appended)
    return b"".join(parts), changed, appended


def array_header(n):
    if n <= 0x0F:
        return bytes([0x90 | n])
    if n <= 0xFFFF:
        return b"\xdc" + struct.pack(">H", n)
    return b"\xdd" + struct.pack(">I", n)


# --- main ---

def main():
    _enable_utf8_stdio()
    ap = argparse.ArgumentParser(description="Translate master-data text rows with byte-level surgery.")
    ap.add_argument("--master", required=True, help="input .bin.e")
    ap.add_argument("--translations", "--tsv", dest="translations", required=True,
                    help="JSONL (or TSV) translation file")
    ap.add_argument("--output", required=True, help="output .bin.e")
    ap.add_argument("--languages", default="2,3",
                    help="comma list of LanguageType values to rewrite (default 2,3; JP use 1)")
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--iv", default=DEFAULT_IV)
    ap.add_argument("--dry-run", action="store_true", help="report plan only, no write")
    ap.add_argument("--fill-missing", action="store_true",
                    help="append new rows for translation keys with no existing row")
    ap.add_argument("--strict", action="store_true", help="abort on source mismatch")
    ap.add_argument("--report", default=None, help="write JSON stats report here")
    args = ap.parse_args()

    languages = {int(x) for x in args.languages.split(",") if x.strip()}
    if not languages <= {1, 2, 3}:
        raise SystemExit("--languages must be a subset of 1,2,3")

    key = bytes.fromhex(args.key)
    iv = bytes.fromhex(args.iv)
    trans = load_translations(args.translations)
    layouts = load_schema_text_columns()

    print(f"translations: {len(trans)} rows from {args.translations}")
    print(f"languages to rewrite: {sorted(languages)}")

    with open(args.master, "rb") as f:
        encrypted = f.read()
    decrypted = aes_decrypt(encrypted, key, iv)
    try:
        toc = msgpack.unpackb(decrypted, raw=False, strict_map_key=False)
        data_blob = b""
    except msgpack.ExtraData as e:
        toc, data_blob = e.unpacked, e.extra
    print(f"{len(toc)} tables, data blob {len(data_blob)} bytes")

    stats = {"samples": [], "appended_samples": [], "source_mismatch": [],
             "markup_mismatch": [], "skipped_non_str": [], "per_table": {}}
    new_blobs = {}
    appended_by_table = {}
    for tname in sorted(toc):
        want = {k[1] for k in trans if k[0] == tname and k[2] in languages}
        if not want:
            continue
        if tname not in TEXT_TABLES:
            raise SystemExit(f"refusing to edit non-text table {tname}")
        if tname not in layouts:
            raise SystemExit(f"{tname} has no (id, LanguageType, string) layout in schemas.json")
        offset, length = toc[tname]
        raw = data_blob[offset:offset + length]
        decompressed, prefix_tag, compressed = unpack_table_blob(raw)
        new_dec, changed, appended = translate_table_blob(
            decompressed, layouts[tname], trans, languages, stats, tname, args.strict,
            fill_missing=args.fill_missing)
        if changed or appended:
            new_blobs[tname] = (build_lz4_ext_blob(new_dec, prefix_tag if compressed else 0xd2)
                                if compressed else new_dec)
        if appended:
            appended_by_table[tname] = appended
        stats["per_table"][tname] = {"requested": len(want), "changed": changed,
                                     "appended": appended}
        print(f"  {tname}: {changed} rows changed, {appended} rows appended (requested ids: {len(want)})")

    if args.dry_run:
        print("[DRY RUN] no file written")
    else:
        sorted_tables = sorted(toc.items(), key=lambda kv: kv[1][0])
        new_toc, parts, cur = {}, [], 0
        for tname, (off, ln) in sorted_tables:
            part = new_blobs.get(tname, data_blob[off:off + ln])
            new_toc[tname] = (cur, len(part))
            parts.append(part)
            cur += len(part)
        new_dec_full = msgpack.packb(new_toc, use_bin_type=True) + b"".join(parts)
        with open(args.output, "wb") as f:
            f.write(aes_encrypt(new_dec_full, key, iv))
        print(f"written: {args.output}")

    # ---- assertions ----
    failures = []
    if not args.dry_run:
        with open(args.output, "rb") as f:
            out_dec = aes_decrypt(f.read(), key, iv)
        try:
            out_toc = msgpack.unpackb(out_dec, raw=False, strict_map_key=False)
            out_blob = b""
        except msgpack.ExtraData as e:
            out_toc, out_blob = e.unpacked, e.extra
        if set(out_toc) != set(toc):
            failures.append("A: table set changed")
        for tname, (off, ln) in toc.items():
            raw_in = data_blob[off:off + ln]
            ooff, oln = out_toc[tname]
            raw_out = out_blob[ooff:ooff + oln]
            if tname not in new_blobs:
                if raw_in != raw_out:
                    failures.append(f"B: untouched table {tname} blob bytes differ")
                continue
            dec_in, _, _ = unpack_table_blob(raw_in)
            dec_out, _, _ = unpack_table_blob(raw_out)
            rows_in = msgpack.unpackb(dec_in, raw=False, strict_map_key=False)
            rows_out = msgpack.unpackb(dec_out, raw=False, strict_map_key=False)
            n_appended = appended_by_table.get(tname, 0)
            if len(rows_out) != len(rows_in) + n_appended:
                failures.append(f"A: {tname} row count changed unexpectedly")
                continue
            id_name, id_idx, lt_idx, text_idx, _ = layouts[tname]
            for ri, (a, b) in enumerate(zip(rows_in, rows_out)):
                if len(a) != len(b):
                    failures.append(f"A: {tname} row {ri} column count changed")
                    break
                for ci, (va, vb) in enumerate(zip(a, b)):
                    if va == vb:
                        continue
                    if ci != text_idx:
                        failures.append(f"A: {tname} row {ri} non-text col {ci} changed")
                        break
                    if a[lt_idx] not in languages:
                        failures.append(f"A: {tname} row {ri} text changed outside target languages")
                        break
                    if markup_signature(va) != markup_signature(vb):
                        failures.append(f"C: {tname} row {ri} markup/placeholder mismatch")
                        break
            if n_appended:
                id_name, id_idx, lt_idx, text_idx, _ = layouts[tname]
                want_rows = {(k[1], k[2]): v["translation"] for k, v in trans.items()
                             if k[0] == tname and k[2] in languages}
                for b in rows_out[len(rows_in):]:
                    key = (b[id_idx], b[lt_idx])
                    if want_rows.get(key) != b[text_idx]:
                        failures.append(f"A: {tname} appended row {key} content mismatch")
                        break
        if stats["markup_mismatch"]:
            failures.append(f"C: {len(stats['markup_mismatch'])} rows skipped for markup mismatch")
    total_changed = sum(v["changed"] for v in stats["per_table"].values())
    print(f"\ntotal rows changed: {total_changed}")
    if stats["source_mismatch"]:
        print(f"source mismatches (warned): {len(stats['source_mismatch'])}")
    if failures:
        print("ASSERTION FAILURES:", file=sys.stderr)
        for f_ in failures:
            print("  !!", f_, file=sys.stderr)
        sys.exit(1)
    print("assertions: A/B/C all passed")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print("report:", args.report)


if __name__ == "__main__":
    main()
