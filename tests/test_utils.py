"""Unit tests for the utils layer (logger, validator, file_utils, helpers).

Run from the project root:
    python -m pytest tests/test_utils.py -v
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from config.constants import ENCRYPTED_EXTENSION, MAGIC_HEADER, MIN_PASSWORD_LENGTH
from utils import file_utils, helpers
from utils.logger import setup_logging
from utils.validator import (
    PasswordStrength,
    ValidationError,
    is_encrypted_file,
    password_issues,
    password_strength,
    validate_input_file,
    validate_input_folder,
    validate_output_location,
    validate_password,
)


# --------------------------------------------------------------------------
# validator: passwords
# --------------------------------------------------------------------------
class TestPasswordValidation:
    def test_short_password_rejected(self) -> None:
        issues = password_issues("a" * (MIN_PASSWORD_LENGTH - 1))
        assert any("at least" in i for i in issues)

    def test_mismatched_confirmation_rejected(self) -> None:
        issues = password_issues("ValidPass123!", "DifferentPass123!")
        assert any("do not match" in i for i in issues)

    def test_surrounding_whitespace_rejected(self) -> None:
        assert password_issues(" ValidPass123! ")

    def test_valid_password_passes(self) -> None:
        assert password_issues("ValidPass123!", "ValidPass123!") == []
        validate_password("ValidPass123!", "ValidPass123!")  # no raise

    def test_validate_password_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_password("short")


class TestPasswordStrength:
    def test_empty_password_is_very_weak(self) -> None:
        bucket, score = password_strength("")
        assert bucket is PasswordStrength.VERY_WEAK
        assert score == 0

    def test_trivial_password_is_weak(self) -> None:
        bucket, _ = password_strength("abc")
        assert bucket in (PasswordStrength.VERY_WEAK, PasswordStrength.WEAK)

    def test_complex_password_is_strong(self) -> None:
        bucket, score = password_strength("Correct-Horse7-Battery!")
        assert bucket is PasswordStrength.STRONG
        assert score >= 85

    def test_score_never_exceeds_100(self) -> None:
        _, score = password_strength("Xy9!" * 40)
        assert score <= 100

    def test_more_complexity_never_lowers_score(self) -> None:
        _, weak = password_strength("aaaaaaaa")
        _, strong = password_strength("Aa1!aaaaaaaa")
        assert strong > weak


# --------------------------------------------------------------------------
# validator: files and folders
# --------------------------------------------------------------------------
class TestFileValidation:
    def test_missing_file_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            validate_input_file(tmp_path / "ghost.txt")

    def test_directory_rejected_as_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="Not a file"):
            validate_input_file(tmp_path)

    def test_empty_file_rejected(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.bin"
        empty.touch()
        with pytest.raises(ValidationError, match="empty"):
            validate_input_file(empty)

    def test_valid_file_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"payload")
        validate_input_file(f)  # no raise

    def test_missing_folder_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            validate_input_folder(tmp_path / "ghost_dir")

    def test_file_rejected_as_folder(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        with pytest.raises(ValidationError, match="Not a folder"):
            validate_input_folder(f)

    def test_existing_output_without_overwrite_rejected(
        self, tmp_path: Path
    ) -> None:
        existing = tmp_path / "out.sfep"
        existing.write_bytes(b"x")
        with pytest.raises(ValidationError, match="already exists"):
            validate_output_location(existing, overwrite=False)
        validate_output_location(existing, overwrite=True)  # no raise

    def test_missing_parent_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="does not exist"):
            validate_output_location(tmp_path / "nowhere" / "out.sfep")

    def test_is_encrypted_file_detects_magic(self, tmp_path: Path) -> None:
        ours = tmp_path / "a.sfep"
        ours.write_bytes(MAGIC_HEADER + b"\x01rest")
        theirs = tmp_path / "b.txt"
        theirs.write_bytes(b"hello world")
        assert is_encrypted_file(ours) is True
        assert is_encrypted_file(theirs) is False
        assert is_encrypted_file(tmp_path / "missing") is False


# --------------------------------------------------------------------------
# file_utils
# --------------------------------------------------------------------------
class TestFileUtils:
    def test_human_readable_size(self) -> None:
        assert file_utils.human_readable_size(0) == "0 B"
        assert file_utils.human_readable_size(1023) == "1023 B"
        assert file_utils.human_readable_size(1536) == "1.5 KB"
        assert file_utils.human_readable_size(5 * 1024**2) == "5.0 MB"

    def test_collect_files_recursive_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub" / "a.txt").write_text("a")
        files = file_utils.collect_files(tmp_path)
        assert [f.name for f in files] == ["b.txt", "a.txt"]
        assert len(files) == 2

    def test_encrypted_and_decrypted_paths_roundtrip(self, tmp_path: Path) -> None:
        source = tmp_path / "report.pdf"
        enc = file_utils.encrypted_output_path(source)
        assert enc.name == "report.pdf" + ENCRYPTED_EXTENSION
        dec = file_utils.decrypted_output_path(enc)
        assert dec.name == "report.pdf"

    def test_decrypted_path_without_our_extension(self, tmp_path: Path) -> None:
        odd = tmp_path / "mystery.bin"
        assert file_utils.decrypted_output_path(odd).name == "mystery.bin.decrypted"

    def test_ensure_unique_path(self, tmp_path: Path) -> None:
        f = tmp_path / "out.txt"
        assert file_utils.ensure_unique_path(f) == f
        f.write_text("x")
        assert file_utils.ensure_unique_path(f).name == "out (1).txt"
        (tmp_path / "out (1).txt").write_text("x")
        assert file_utils.ensure_unique_path(f).name == "out (2).txt"

    def test_total_size(self, tmp_path: Path) -> None:
        a = tmp_path / "a.bin"
        a.write_bytes(b"12345")
        assert file_utils.total_size([a, tmp_path / "missing"]) == 5

    def test_mirror_subpath(self, tmp_path: Path) -> None:
        src_root = tmp_path / "src"
        (src_root / "nested").mkdir(parents=True)
        src_file = src_root / "nested" / "doc.txt"
        src_file.write_text("x")
        dst_root = tmp_path / "dst"
        result = file_utils.mirror_subpath(src_root, src_file, dst_root)
        assert result == dst_root / "nested" / "doc.txt"
        assert result.parent.is_dir()

    def test_has_enough_disk_space(self, tmp_path: Path) -> None:
        assert file_utils.has_enough_disk_space(tmp_path, 1) is True
        assert file_utils.has_enough_disk_space(tmp_path, 10**18) is False


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
class TestHelpers:
    def test_format_duration(self) -> None:
        assert helpers.format_duration(5) == "5s"
        assert helpers.format_duration(65) == "1m 05s"
        assert helpers.format_duration(3665) == "1h 01m"

    def test_format_speed(self) -> None:
        assert helpers.format_speed(12 * 1024**2) == "12.0 MB/s"

    def test_estimate_remaining(self) -> None:
        # 50 of 100 bytes in 10s at 5 B/s -> 10s left
        assert helpers.estimate_remaining(50, 100, 10.0) == pytest.approx(10.0)
        assert helpers.estimate_remaining(0, 100, 10.0) == 0.0
        assert helpers.estimate_remaining(100, 100, 10.0) == 0.0

    def test_truncate_middle(self) -> None:
        assert helpers.truncate_middle("short", 60) == "short"
        long_path = "C:/very/long/path/to/some/deeply/nested/file.txt"
        result = helpers.truncate_middle(long_path, 20)
        assert len(result) <= 20
        assert "…" in result


# --------------------------------------------------------------------------
# logger
# --------------------------------------------------------------------------
class TestLogger:
    def test_setup_creates_log_file_and_writes(self, tmp_path: Path) -> None:
        log_path = setup_logging(log_dir=tmp_path, console=False)
        logging.getLogger("test").info("hello log")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert log_path.exists()
        assert "hello log" in log_path.read_text(encoding="utf-8")

    def test_repeated_setup_does_not_duplicate_handlers(
        self, tmp_path: Path
    ) -> None:
        setup_logging(log_dir=tmp_path, console=False)
        setup_logging(log_dir=tmp_path, console=False)
        assert len(logging.getLogger().handlers) == 1
