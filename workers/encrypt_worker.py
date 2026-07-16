"""
encrypt_worker.py — Background encryption worker + job planning.

``build_encrypt_jobs`` turns whatever the user dropped (files, folders,
a mix) into explicit (source, destination) pairs BEFORE the worker
starts, so the UI can show 'N files, X MB total' up front and the worker
loop stays dumb and testable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from config.constants import ENCRYPTED_EXTENSION, PBKDF2_ITERATIONS
from crypto.password_manager import SecurePassword
from database.database import HistoryDatabase
from models.records import CryptoResult, OperationType
from utils.file_utils import (
    collect_files,
    encrypted_output_path,
    mirror_subpath,
)
from utils.validator import validate_input_file
from workers.base_worker import BaseCryptoWorker, Job


def build_encrypt_jobs(
    paths: Iterable[Path], output_dir: Path | None = None
) -> list[Job]:
    """Expand user selections into encryption jobs.

    * File  -> ``<output>/<name>.sfep``
    * Folder-> recursive: ``<output>/<folder>_encrypted/<relative>.sfep``
      (directory structure preserved via mirror_subpath).
    """
    jobs: list[Job] = []
    for path in paths:
        if path.is_dir():
            root_out = (output_dir if output_dir is not None else path.parent) / (
                f"{path.name}_encrypted"
            )
            for source in collect_files(path):
                mirrored = mirror_subpath(path, source, root_out)
                jobs.append(
                    (source, mirrored.parent / (source.name + ENCRYPTED_EXTENSION))
                )
        else:
            jobs.append((path, encrypted_output_path(path, output_dir)))
    return jobs


class EncryptWorker(BaseCryptoWorker):
    """Encrypts every job with AES-256-GCM off the GUI thread."""

    operation = OperationType.ENCRYPT

    def __init__(
        self,
        jobs: list[Job],
        password: SecurePassword,
        database: HistoryDatabase | None = None,
        overwrite: bool = False,
        iterations: int = PBKDF2_ITERATIONS,
        parent=None,
    ) -> None:
        super().__init__(jobs, password, database, overwrite, parent)
        self._iterations = iterations

    def _validate_source(self, source: Path) -> None:
        validate_input_file(source)

    def _run_engine(
        self, source: Path, destination: Path, progress_cb
    ) -> CryptoResult:
        return self._engine.encrypt_file(
            source,
            destination,
            self._password.value,
            iterations=self._iterations,
            progress_callback=progress_cb,
            cancel_callback=self._is_cancelled,
        )
