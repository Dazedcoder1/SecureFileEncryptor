"""
file_utils.py — Cross-platform filesystem helpers built on pathlib.

Path derivation for encrypted/decrypted outputs, recursive file
collection for folder encryption, disk-space checks, and collision-free
output naming. No Qt, no crypto — pure filesystem logic.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from config.constants import ENCRYPTED_EXTENSION

# Extra headroom demanded beyond the exact output size (metadata, jitter).
_DISK_SPACE_MARGIN: int = 16 * 1024 * 1024  # 16 MiB


def human_readable_size(num_bytes: float) -> str:
    """Format a byte count for humans: 1536 -> '1.5 KB'."""
    if num_bytes < 0:
        raise ValueError("Size cannot be negative")
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(num_bytes)} {unit}"
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    raise AssertionError("unreachable")


def collect_files(folder: Path) -> list[Path]:
    """Recursively list all regular files under ``folder``, sorted.

    Sorting makes folder encryption order deterministic, which keeps
    progress reporting and tests stable.
    """
    return sorted(p for p in folder.rglob("*") if p.is_file())


def total_size(paths: Iterable[Path]) -> int:
    """Sum of file sizes in bytes (missing files count as zero)."""
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


def encrypted_output_path(source: Path, output_dir: Path | None = None) -> Path:
    """Derive the encrypted output path: report.pdf -> report.pdf.sfep.

    The original extension is kept inside the name so decryption can
    restore it exactly.
    """
    target_dir = output_dir if output_dir is not None else source.parent
    return target_dir / (source.name + ENCRYPTED_EXTENSION)


def decrypted_output_path(source: Path, output_dir: Path | None = None) -> Path:
    """Derive the decrypted output path: report.pdf.sfep -> report.pdf.

    Files lacking our extension get a '.decrypted' suffix instead of
    guessing (never destroy information about the original name).
    """
    target_dir = output_dir if output_dir is not None else source.parent
    if source.name.endswith(ENCRYPTED_EXTENSION):
        original = source.name[: -len(ENCRYPTED_EXTENSION)]
    else:
        original = source.name + ".decrypted"
    return target_dir / original


def ensure_unique_path(path: Path) -> Path:
    """Return ``path`` unchanged if free, else 'name (1).ext', 'name (2).ext'…

    Used when the overwrite setting is off but the user still wants
    output written somewhere.
    """
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for counter in range(1, 10_000):
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a unique name for {path}")


def has_enough_disk_space(target_dir: Path, required_bytes: int) -> bool:
    """True if ``target_dir``'s volume has room for ``required_bytes`` + margin."""
    try:
        free = shutil.disk_usage(target_dir).free
    except OSError:
        return False
    return free >= required_bytes + _DISK_SPACE_MARGIN


def mirror_subpath(src_root: Path, src_file: Path, dst_root: Path) -> Path:
    """Map a file inside ``src_root`` to the same relative spot in ``dst_root``.

    Powers folder encryption's 'maintain directory structure' requirement:
        mirror_subpath(/docs, /docs/a/b.txt, /out) -> /out/a/b.txt
    Parent directories are created.
    """
    relative = src_file.relative_to(src_root)
    destination = dst_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination
