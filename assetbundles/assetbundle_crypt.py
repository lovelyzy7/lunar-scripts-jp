"""
Shared helpers for Octo SDK asset bundle encryption / decryption.

The mask is derived from the bundle name via StringToMaskBytes: interleave each
char with its bitwise complement, compute a rotate-right hash (seed 0xBB), then
XOR the whole buffer with that hash.  The version byte at file offset 0 consumes
mask position 0, so content bytes are XOR'd starting at mask position 1.

File format:
  byte 0:  version tag
    0x31  Version1      -- XOR mask applied to the first N header bytes after byte 0
    0x32  Version1Full  -- XOR mask applied to ALL bytes after byte 0
    'U'   (0x55) already a raw UnityFS bundle (no masking)
  byte 1+: masked (or raw) UnityFS bundle data
"""

VERSION1 = 0x31
VERSION1_FULL = 0x32
UNITYFS_MAGIC = b"UnityFS"
DEFAULT_HEADER_LENGTH = 256


def string_to_mask_bytes(name: str) -> bytes:
    """Transform a mask name into the XOR mask byte array.

    Reimplements MaskedHeaderStream.StringToMaskBytes / BytesToHash from the
    Octo SDK (verified against runtime Frida dumps).

    Phase 1 - Interleave: even positions get the raw char byte, odd positions
              (filled from the end) get the bitwise complement.
    Phase 2 - Hash: rotate-right-1 + XOR accumulator seeded with 0xBB.
    Phase 3 - XOR every byte with the hash.
    """
    chars = name.encode("utf-8")
    n = len(chars)
    buf_len = n * 2
    buf = bytearray(buf_len)

    for i in range(n):
        buf[2 * i] = chars[i]
        buf[buf_len - 1 - 2 * i] = (~chars[i]) & 0xFF

    h = 0xBB
    for b in buf:
        h = ((h & 1) << 7 | h >> 1) & 0xFF
        h ^= b

    for i in range(buf_len):
        buf[i] ^= h

    return bytes(buf)


def derive_mask_name(filepath: str) -> str | None:
    """Derive the bundle mask name from its filesystem path.

    Strips everything up to and including the first 'assetbundle/' segment,
    removes the '.assetbundle' suffix, and replaces '/' with ')'.

    Example:
      server/assets/revisions/0/assetbundle/text/en/library/foo/foo_001.assetbundle
      -> text)en)library)foo)foo_001
    """
    norm = filepath.replace("\\", "/")
    marker = "assetbundle/"
    idx = norm.find(marker)
    if idx < 0:
        return None
    rel = norm[idx + len(marker) :]
    if rel.endswith(".assetbundle"):
        rel = rel[: -len(".assetbundle")]
    return rel.replace("/", ")")


def xor_unmask(data: bytearray, mask: bytes, header_length: int, mask_offset: int = 0) -> None:
    """XOR `data` in place using cycling `mask` for the first `header_length` bytes."""
    mask_len = len(mask)
    n = min(header_length, len(data))
    for i in range(n):
        data[i] ^= mask[(i + mask_offset) % mask_len]
