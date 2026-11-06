#!/usr/bin/env python3
"""Convert all msgpack files in a directory to JSON.

Understands the master-data table blobs produced by extract_master_data.py:
each file is a single msgpack value, typically an ExtType(99) wrapping
LZ4-compressed msgpack rows.  Those are decompressed transparently, so the
output is plain JSON (array of positional rows) for both GL and JP builds.
"""

import os
import sys
import json
import struct
import msgpack
import lz4.block
from pathlib import Path


def read_lz4_ext_header(ext_data):
    """Parse the uncompressed-length prefix from an ExtType(99) payload."""
    tag = ext_data[0]
    if tag == 0xd2:  # int32
        return struct.unpack('>i', ext_data[1:5])[0], ext_data[5:]
    if tag == 0xce:  # uint32
        return struct.unpack('>I', ext_data[1:5])[0], ext_data[5:]
    if tag == 0xd1:  # int16
        return struct.unpack('>h', ext_data[1:3])[0], ext_data[3:]
    if tag == 0xcd:  # uint16
        return struct.unpack('>H', ext_data[1:3])[0], ext_data[3:]
    if tag <= 0x7f:  # positive fixint
        return tag, ext_data[1:]
    raise ValueError(f"Unexpected msgpack tag 0x{tag:02x} in LZ4 ext header")


def decode_value(obj):
    """Recursively decode msgpack ExtType wrappers (LZ4 table blobs)."""
    if isinstance(obj, msgpack.ExtType):
        if obj.code == 99:
            ulen, lz4_data = read_lz4_ext_header(obj.data)
            inner = msgpack.unpackb(lz4.block.decompress(lz4_data, uncompressed_size=ulen),
                                    raw=False, strict_map_key=False)
            return decode_value(inner)
        return {"__ext_code__": obj.code, "data_hex": obj.data.hex()}
    if isinstance(obj, list):
        return [decode_value(v) for v in obj]
    if isinstance(obj, dict):
        return {k: decode_value(v) for k, v in obj.items()}
    return obj


def convert_file(input_path, output_path):
    """Convert single msgpack file to JSON."""
    try:
        with open(input_path, 'rb') as f:
            data = msgpack.unpackb(f.read(), raw=False, strict_map_key=False)

        data = decode_value(data)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        return True
    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return False


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_dir> <output_dir>")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    msgpack_files = list(input_dir.glob("*.msgpack"))
    print(f"Found {len(msgpack_files)} msgpack files")

    converted = 0
    failed = 0

    for i, msgpack_file in enumerate(msgpack_files, 1):
        json_file = output_dir / (msgpack_file.stem + ".json")

        if convert_file(msgpack_file, json_file):
            converted += 1
            print(f"[{i}/{len(msgpack_files)}] {msgpack_file.name} -> {json_file.name}")
        else:
            failed += 1

    print(f"\nDone: {converted} converted, {failed} failed")
    print(f"JSON files in: {output_dir}")


if __name__ == '__main__':
    main()
