#!/usr/bin/env python3
"""
Refresh list.bin entries from on-disk asset bundles / resources.

list.bin is the protobuf catalog the Octo SDK uses to find downloadable assets;
each entry carries the file's size, md5, and crc.  When you swap an
.assetbundle file (e.g. a translated bundle), the entry must be regenerated or
the CDN's md5 check rejects the file before the client even sees it.

The Data.crc field is decorative as far as the client is concerned: the public
AssetBundle.LoadFromFileAsync(path) wrapper passes crc=0 to Unity, skipping
verification.  Octo's own integrity check on downloaded bundles is size+md5;
the crc is never compared.  We also can't reproduce Unity's build-time CRC
from a built bundle (it's computed on the uncompressed serialized bundle,
before LZMA/LZ4 and before Octo's XOR mask), so:
  - Entries whose size+md5 still match disk are left UNTOUCHED.
  - Entries whose size or md5 changed get crc=0 (matches what the client
    passes to Unity, and avoids advertising a stale or fabricated value).
This keeps unmodified runs as no-ops and only mutates real swaps.

Usage:
  # Patch one list.bin in place (with .bak backup on first run)
  python3 patch_listbin.py path/to/list.bin

  # Patch every list.bin under a revision tree
  python3 patch_listbin.py --all server/assets/revisions/0

  # Report what would change without writing anything
  python3 patch_listbin.py path/to/list.bin --dry-run

  # Show per-entry diffs
  python3 patch_listbin.py path/to/list.bin --verbose

Path resolution mirrors server/internal/service/listbin.go: each entry's
`name` field is treated as a path with `)` separators, mapped to either
<list.bin parent>/assetbundle/<name>.assetbundle or
<list.bin parent>/resources/<name>.  Files missing on disk are left untouched
(no fields edited, no entry removed) so the CDN keeps serving whatever the
operator has and missing files surface as 404s instead of silent drops.
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import octo_pb2


def load_database(list_bin_path: Path) -> octo_pb2.Database:
    db = octo_pb2.Database()
    db.ParseFromString(list_bin_path.read_bytes())
    return db


def asset_root_for(list_bin_path: Path) -> Path:
    """Return the directory that contains assetbundle/ and resources/ trees for a given list.bin."""
    return list_bin_path.parent


def candidate_filesystem_path(asset_root: Path, asset_type: str, name: str) -> Path:
    """Mirror listbin.go's pathStrToFullPaths for the primary (non-fallback) candidate."""
    rel = name.replace(")", "/")
    if asset_type == "assetbundle":
        return asset_root / "assetbundle" / (rel + ".assetbundle")
    return asset_root / "resources" / rel


def md5_and_size(path: Path) -> tuple[int, str]:
    """Return (size, md5_hex) for the file at `path`."""
    data = path.read_bytes()
    return len(data), hashlib.md5(data).hexdigest()


def iter_entries(db: octo_pb2.Database):
    for entry in db.assetBundleList:
        yield "assetbundle", entry
    for entry in db.resourceList:
        yield "resources", entry


def patch_database(
    db: octo_pb2.Database,
    asset_root: Path,
    *,
    verbose: bool = False,
) -> tuple[int, int, int]:
    """Recompute size/md5 for every entry whose file exists and whose size or
    md5 differs from disk, and zero the crc on those entries.  Entries with
    matching size+md5 are untouched (crc preserved as-is).

    Returns (changed_count, missing_count, scanned_count).
    """
    changed = 0
    missing = 0
    scanned = 0
    for asset_type, entry in iter_entries(db):
        scanned += 1
        path = candidate_filesystem_path(asset_root, asset_type, entry.name)
        if not path.is_file():
            missing += 1
            continue
        size, md5 = md5_and_size(path)
        if size == entry.size and md5 == entry.md5:
            continue
        if verbose:
            diffs = []
            if size != entry.size:
                diffs.append(f"size {entry.size}->{size}")
            if md5 != entry.md5:
                diffs.append(f"md5 {entry.md5}->{md5}")
            if entry.crc != 0:
                diffs.append(f"crc {entry.crc}->0")
            print(f"  [{asset_type}] {entry.name}: {', '.join(diffs)}")
        entry.size = size
        entry.md5 = md5
        entry.crc = 0
        changed += 1
    return changed, missing, scanned


def write_atomic(path: Path, data: bytes, *, backup: bool) -> None:
    if backup:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(path.read_bytes())
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def process_one(list_bin_path: Path, *, dry_run: bool, verbose: bool) -> bool:
    if not list_bin_path.is_file():
        print(f"ERROR: not a file: {list_bin_path}", file=sys.stderr)
        return False
    db = load_database(list_bin_path)
    asset_root = asset_root_for(list_bin_path)
    changed, missing, scanned = patch_database(db, asset_root, verbose=verbose)
    label = f"{list_bin_path}"
    summary = f"{label}: {changed} changed, {missing} missing-file, {scanned} scanned"
    if changed == 0:
        print(summary + " (no write)")
        return True
    if dry_run:
        print(summary + " (dry-run, no write)")
        return True
    write_atomic(list_bin_path, db.SerializeToString(), backup=True)
    print(summary + " (written, .bak preserved)")
    return True


def find_list_bins(root: Path) -> list[Path]:
    """Find every list.bin under a revisions tree."""
    return sorted(root.rglob("list.bin"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh size/md5/crc in Octo list.bin entries from disk."
    )
    parser.add_argument(
        "target",
        help="Path to list.bin (single mode) or directory to scan recursively (with --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Treat target as a directory and process every list.bin under it",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute changes but do not write"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print per-entry diffs"
    )
    args = parser.parse_args()

    target = Path(args.target)
    if args.all:
        if not target.is_dir():
            parser.error(f"--all requires a directory, got: {target}")
        list_bins = find_list_bins(target)
        if not list_bins:
            print(f"No list.bin files under {target}")
            sys.exit(0)
        ok_all = True
        for lb in list_bins:
            ok = process_one(lb, dry_run=args.dry_run, verbose=args.verbose)
            ok_all = ok_all and ok
        sys.exit(0 if ok_all else 1)

    ok = process_one(target, dry_run=args.dry_run, verbose=args.verbose)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
