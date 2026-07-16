"""
decrypt_worker.py — Background decryption worker + job planning.

Mirror image of encrypt_worker: expands selections into jobs up front,
rejects files that are not SFEP containers, and reports integrity
verdicts through the CryptoResult it emits per file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from crypto.password_manager import SecurePassword
from database.database import HistoryDatabase
from models.records import CryptoResult, OperationType
from utils.file_utils import (
    collect_files,
    decrypted_output_path,
    mirror_subpath,
)
from utils.validator import ValidationError, is_encrypted_file, validate_input_file
from workers.base_worker import BaseCryptoWorker, Job


def build_decrypt_jobs(
    paths: Iterable[Path], output_dir: Path | None = None
) -> list[Job]:
    """Expand user selections into decryption jobs.

    * File  -> ``<output>/<original name>`` (``.sfep`` stripped)
    * Folder-> recursive over SFEP files only:
      ``<output>/<folder>_decrypted/<relative original name>``
    """
    jobs: list[Job] = []
    for path in paths:
        if path.is_dir():
            root_out = (output_dir if output_dir is not None else path.parent) / (
                f"{path.name}_decrypted"
            )
            for source in collect_files(path):
                if not is_encrypted_file(source):
                    continue  # skip foreign files inside the folder
                mirrored = mirror_subpath(path, source, root_out)
                jobs.append(
                    (source, mirrored.parent / decrypted_output_path(source).name)
                )
        else:
            jobs.append((path, decrypted_output_path(path, output_dir)))
    return jobs


class DecryptWorker(BaseCryptoWorker):
    """Decrypts every job and verifies plaintext integrity."""

    operation = OperationType.DECRYPT

    def _validate_source(self, source: Path) -> None:
        validate_input_file(source)
        if not is_encrypted_file(source):
            raise ValidationError(
                f"Not a Secure File Encryptor Pro file: {source.name}"
            )

    def _run_engine(
        self, source: Path, destination: Path, progress_cb
    ) -> CryptoResult:
        return self._engine.decrypt_file(
            source,
            destination,
            self._password.value,
            progress_callback=progress_cb,
            cancel_callback=self._is_cancelled,
        )
