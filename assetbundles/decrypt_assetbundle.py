#!/usr/bin/env python3
"""
Decrypt Octo SDK asset bundles by reversing MaskedHeaderStream XOR masking.

Usage:
  python decrypt_assetbundle.py <file.assetbundle>
  python decrypt_assetbundle.py <file.assetbundle> --name "text)en)library)story_character)story_character_0070250"
  python decrypt_assetbundle.py --dir server/assets/revisions/0/assetbundle/ -o /tmp/decrypted/
  python decrypt_assetbundle.py --dir server/assets/revisions/0/assetbundle/ --in-place
"""

import argparse
import sys
from pathlib import Path

from assetbundle_crypt import (
    DEFAULT_HEADER_LENGTH,
    UNITYFS_MAGIC,
    VERSION1,
    VERSION1_FULL,
    derive_mask_name,
    string_to_mask_bytes,
    xor_unmask,
)


def decrypt_bundle(raw: bytes, mask_name: str, default_header_length: int = DEFAULT_HEADER_LENGTH) -> bytes:
    """Decrypt a single asset bundle, returning the raw UnityFS data.

    The on-disk format is [version_byte | encrypted_content...].  The version
    byte occupies mask position 0, so the content (starting at file offset 1)
    is XOR'd with the mask starting at position 1.  We prepend 'U' (0x55) to
    restore the original UnityFS magic.
    """
    if len(raw) == 0:
        raise ValueError("empty file")

    if raw[:7] == UNITYFS_MAGIC:
        return raw

    version = raw[0]
    mask = string_to_mask_bytes(mask_name)

    if version == VERSION1_FULL:
        data = bytearray(raw[1:])
        xor_unmask(data, mask, len(data), mask_offset=1)
        return b"U" + bytes(data)

    if version == VERSION1:
        data = bytearray(raw[1:])
        xor_unmask(data, mask, default_header_length, mask_offset=1)
        return b"U" + bytes(data)

    raise ValueError(f"unknown version byte 0x{version:02x}")


def process_file(
    inpath: str,
    mask_name: str | None,
    outpath: str | None,
    in_place: bool,
    default_header_length: int,
    quiet: bool,
) -> bool:
    """Decrypt one file. Returns True on success."""
    raw = Path(inpath).read_bytes()

    if raw[:7] == UNITYFS_MAGIC:
        if not quiet:
            print(f"  SKIP (already UnityFS): {inpath}")
        return True

    name = mask_name or derive_mask_name(inpath)
    if not name:
        print(f"  ERROR: cannot derive mask name from path: {inpath}", file=sys.stderr)
        return False

    try:
        decrypted = decrypt_bundle(raw, name, default_header_length)
    except ValueError as e:
        print(f"  ERROR: {inpath}: {e}", file=sys.stderr)
        return False

    if decrypted[:7] != UNITYFS_MAGIC:
        hex_head = decrypted[:16].hex()
        print(
            f"  WARN: {inpath}: decrypted header is not UnityFS (got {hex_head}), mask may be wrong",
            file=sys.stderr,
        )

    if in_place:
        dest = inpath
    elif outpath:
        dest = outpath
    else:
        dest = inpath + ".decrypted"

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(decrypted)

    if not quiet:
        tag = "v1full" if raw[0] == VERSION1_FULL else "v1"
        print(f"  OK ({tag}): {inpath} -> {dest}  mask=\"{name}\"")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Decrypt Octo SDK MaskedHeaderStream asset bundles.")

    parser.add_argument("file", nargs="?", help="Single .assetbundle file to decrypt")
    parser.add_argument("--name", help="Override mask name (bundle name with ')' separators)")
    parser.add_argument("--dir", help="Batch: decrypt all .assetbundle files under this directory")
    parser.add_argument("-o", "--output", help="Output file (single mode) or directory (batch mode)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input files in place")
    parser.add_argument("--default-header-length", type=int, default=DEFAULT_HEADER_LENGTH,
                        help=f"Header length for Version1 (0x31) files (default: {DEFAULT_HEADER_LENGTH})")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print errors and warnings")

    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.error("provide either a file argument or --dir for batch mode")

    if args.file and args.dir:
        parser.error("cannot use both positional file and --dir")

    if args.file:
        ok = process_file(args.file, args.name, args.output, args.in_place, args.default_header_length, args.quiet)
        sys.exit(0 if ok else 1)

    root = Path(args.dir)
    if not root.is_dir():
        print(f"ERROR: {args.dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = sorted(root.rglob("*.assetbundle"))
    if not files:
        print(f"No .assetbundle files found under {args.dir}")
        sys.exit(0)

    print(f"Processing {len(files)} files under {args.dir}...")
    ok_count = 0
    fail_count = 0
    skip_count = 0

    for f in files:
        fstr = str(f)
        raw_head = f.read_bytes()[:7]
        if raw_head == UNITYFS_MAGIC:
            skip_count += 1
            if not args.quiet:
                print(f"  SKIP (already UnityFS): {fstr}")
            continue

        out = None
        if args.output:
            rel = f.relative_to(root)
            out = str(Path(args.output) / rel)

        if process_file(fstr, args.name, out, args.in_place, args.default_header_length, args.quiet):
            ok_count += 1
        else:
            fail_count += 1

    print(f"\nDone: {ok_count} decrypted, {skip_count} skipped, {fail_count} failed")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
