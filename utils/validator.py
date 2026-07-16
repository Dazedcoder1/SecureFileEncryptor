"""
validator.py — Input validation for passwords, files, and folders.

Pure functions, no Qt, no side effects: every rule the UI enforces lives
here so dialogs, workers, and tests all share identical validation logic.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from config.constants import (
    MAGIC_HEADER,
    MIN_PASSWORD_LENGTH,
    STRONG_PASSWORD_LENGTH,
)


class ValidationError(Exception):
    """Raised when user input fails validation. Message is user-safe."""


class PasswordStrength(Enum):
    """Buckets driving the UI strength meter (color + label)."""

    VERY_WEAK = 0
    WEAK = 1
    FAIR = 2
    GOOD = 3
    STRONG = 4


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def password_issues(password: str, confirmation: str | None = None) -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    issues: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        issues.append(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if password != password.strip():
        issues.append("Password must not start or end with whitespace.")
    if confirmation is not None and password != confirmation:
        issues.append("Passwords do not match.")
    return issues


def validate_password(password: str, confirmation: str | None = None) -> None:
    """Raise :class:`ValidationError` if the password breaks any rule."""
    issues = password_issues(password, confirmation)
    if issues:
        raise ValidationError(" ".join(issues))


def password_strength(password: str) -> tuple[PasswordStrength, int]:
    """Score a password 0–100 and bucket it for the strength meter.

    Heuristic: length (up to 40 pts), character-class variety
    (10 pts each for lower/upper/digit/symbol), bonus for meeting the
    strong-length threshold and for high character diversity.
    """
    if not password:
        return PasswordStrength.VERY_WEAK, 0

    score = min(len(password) * 4, 40)
    if any(c.islower() for c in password):
        score += 10
    if any(c.isupper() for c in password):
        score += 10
    if any(c.isdigit() for c in password):
        score += 10
    if any(not c.isalnum() for c in password):
        score += 10
    if len(password) >= STRONG_PASSWORD_LENGTH:
        score += 10
    if len(set(password)) >= max(6, len(password) // 2):
        score += 10
    score = min(score, 100)

    if score < 25:
        bucket = PasswordStrength.VERY_WEAK
    elif score < 45:
        bucket = PasswordStrength.WEAK
    elif score < 65:
        bucket = PasswordStrength.FAIR
    elif score < 85:
        bucket = PasswordStrength.GOOD
    else:
        bucket = PasswordStrength.STRONG
    return bucket, score


# --------------------------------------------------------------------------
# Files and folders
# --------------------------------------------------------------------------
def validate_input_file(path: Path) -> None:
    """Ensure ``path`` is an existing, readable, non-empty regular file."""
    if not path.exists():
        raise ValidationError(f"File not found: {path.name}")
    if not path.is_file():
        raise ValidationError(f"Not a file: {path.name}")
    if not os.access(path, os.R_OK):
        raise ValidationError(f"Permission denied reading: {path.name}")
    if path.stat().st_size == 0:
        raise ValidationError(f"File is empty: {path.name}")


def validate_input_folder(path: Path) -> None:
    """Ensure ``path`` is an existing, readable directory."""
    if not path.exists():
        raise ValidationError(f"Folder not found: {path.name}")
    if not path.is_dir():
        raise ValidationError(f"Not a folder: {path.name}")
    if not os.access(path, os.R_OK):
        raise ValidationError(f"Permission denied reading folder: {path.name}")


def validate_output_location(path: Path, overwrite: bool = False) -> None:
    """Ensure a file may be written at ``path``.

    Args:
        path: Intended output file path.
        overwrite: Whether an existing file may be replaced
            (mirrors the 'Overwrite Existing Files' setting).
    """
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise ValidationError(f"Output folder does not exist: {parent}")
    if not os.access(parent, os.W_OK):
        raise ValidationError(f"Permission denied writing to: {parent}")
    if path.exists() and not overwrite:
        raise ValidationError(
            f"Output already exists: {path.name} (enable overwrite in Settings)"
        )


def is_encrypted_file(path: Path) -> bool:
    """True if the file starts with our magic header (i.e. it's ours).

    Used to route drag-and-dropped files to encrypt vs. decrypt and to
    reject files that were not produced by this application.
    """
    try:
        with path.open("rb") as fh:
            return fh.read(len(MAGIC_HEADER)) == MAGIC_HEADER
    except OSError:
        return False
