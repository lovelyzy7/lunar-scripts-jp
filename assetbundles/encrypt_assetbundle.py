#!/usr/bin/env python3
"""
Encrypt raw UnityFS asset bundles into the Octo SDK MaskedHeaderStream format.

Reverse of decrypt_assetbundle.py: takes a raw UnityFS file and applies the XOR
mask, prepending the version byte.

Usage:
  python encrypt_assetbundle.py <file.assetbundle>
  python encrypt_assetbundle.py <file.assetbundle> --name "text)en)library)story_character)story_character_0070250"
  python encrypt_assetbundle.py --dir /tmp/decrypted/ -o server/assets/revisions/0/assetbundle/
  python encrypt_assetbundle.py --dir /tmp/decrypted/ --in-place
  python encrypt_assetbundle.py <file.assetbundle> --version v1 --header-length 512
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


def encrypt_bundle(
    raw: bytes,
    mask_name: str,
    version: int = VERSION1_FULL,
    header_length: int = DEFAULT_HEADER_LENGTH,
) -> bytes:
    """Encrypt a raw UnityFS bundle into the masked on-disk format.

    The first byte ('U') is replaced by the version tag.  The remaining content
    is XOR'd with the mask starting at offset 1 (since the version byte
    occupies mask position 0).
    """
    if len(raw) == 0:
        raise ValueError("empty file")

    if raw[:7] != UNITYFS_MAGIC:
        raise ValueError(f"not a UnityFS file (starts with {raw[:7].hex()})")

    mask = string_to_mask_bytes(mask_name)
    data = bytearray(raw[1:])

    if version == VERSION1_FULL:
        xor_unmask(data, mask, len(data), mask_offset=1)
    elif version == VERSION1:
        xor_unmask(data, mask, header_length, mask_offset=1)
    else:
        raise ValueError(f"unsupported version 0x{version:02x}")

    return bytes([version]) + bytes(data)


def process_file(
    inpath: str,
    mask_name: str | None,
    outpath: str | None,
    in_place: bool,
    version: int,
    header_length: int,
    quiet: bool,
) -> bool:
    """Encrypt one file. Returns True on success."""
    raw = Path(inpath).read_bytes()

    if raw[:7] != UNITYFS_MAGIC:
        if raw[0] in (VERSION1, VERSION1_FULL):
            if not quiet:
                print(f"  SKIP (already encrypted): {inpath}")
            return True
        print(f"  ERROR: {inpath}: not a UnityFS file and not already encrypted", file=sys.stderr)
        return False

    name = mask_name or derive_mask_name(inpath)
    if not name:
        print(f"  ERROR: cannot derive mask name from path: {inpath}", file=sys.stderr)
        return False

    try:
        encrypted = encrypt_bundle(raw, name, version, header_length)
    except ValueError as e:
        print(f"  ERROR: {inpath}: {e}", file=sys.stderr)
        return False

    if in_place:
        dest = inpath
    elif outpath:
        dest = outpath
    else:
        dest = inpath + ".encrypted"

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(encrypted)

    if not quiet:
        tag = "v1full" if version == VERSION1_FULL else "v1"
        print(f"  OK ({tag}): {inpath} -> {dest}  mask=\"{name}\"")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt raw UnityFS bundles into Octo SDK masked format.")

    parser.add_argument("file", nargs="?", help="Single .assetbundle file to encrypt")
    parser.add_argument("--name", help="Override mask name (bundle name with ')' separators)")
    parser.add_argument("--dir", help="Batch: encrypt all .assetbundle files under this directory")
    parser.add_argument("-o", "--output", help="Output file (single mode) or directory (batch mode)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input files in place")
    parser.add_argument("--version", choices=["v1", "v1full"], default="v1full",
                        help="Encryption version (default: v1full)")
    parser.add_argument("--header-length", type=int, default=DEFAULT_HEADER_LENGTH,
                        help=f"Header length for v1 mode (default: {DEFAULT_HEADER_LENGTH})")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print errors and warnings")

    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.error("provide either a file argument or --dir for batch mode")

    if args.file and args.dir:
        parser.error("cannot use both positional file and --dir")

    ver = VERSION1_FULL if args.version == "v1full" else VERSION1

    if args.file:
        ok = process_file(args.file, args.name, args.output, args.in_place, ver, args.header_length, args.quiet)
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
        if raw_head != UNITYFS_MAGIC:
            first_byte = f.read_bytes()[0]
            if first_byte in (VERSION1, VERSION1_FULL):
                skip_count += 1
                if not args.quiet:
                    print(f"  SKIP (already encrypted): {fstr}")
                continue

        out = None
        if args.output:
            rel = f.relative_to(root)
            out = str(Path(args.output) / rel)

        if process_file(fstr, args.name, out, args.in_place, ver, args.header_length, args.quiet):
            ok_count += 1
        else:
            fail_count += 1

    print(f"\nDone: {ok_count} encrypted, {skip_count} skipped, {fail_count} failed")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
