"""
password_manager.py — Secure in-memory password handling.

Passwords live in a mutable ``bytearray`` that is zeroed the moment the
operation finishes (context-manager guaranteed). Nothing is ever written
to disk, the database, or the log.

HONEST LIMITATION: Python strings are immutable, so the string the Qt
line-edit hands us cannot itself be wiped; interpreter internals may
also copy data. Wiping the working buffer is industry best-effort in
managed languages and meaningfully shrinks the exposure window.
"""

from __future__ import annotations

from types import TracebackType

from crypto.utils import wipe
from utils.validator import ValidationError, validate_password


class SecurePassword:
    """Wipeable password container.

    Usage:
        with SecurePassword("hunter2!extra") as pw:
            engine.encrypt_file(src, dst, pw.value)
        # buffer is zeroed here, even on exceptions
    """

    def __init__(
        self,
        password: str,
        confirmation: str | None = None,
        enforce_policy: bool = True,
    ) -> None:
        """Validate and capture the password.

        Args:
            enforce_policy: True for encryption (full password rules);
                False for decryption, where the only requirement is
                non-emptiness — the file may have been created under a
                different policy, and the KCV check decides correctness.

        Raises:
            utils.validator.ValidationError: if validation fails.
        """
        if enforce_policy:
            validate_password(password, confirmation)
        elif not password:
            raise ValidationError("Password must not be empty.")
        self._buffer = bytearray(password.encode("utf-8"))
        self._wiped = False

    # ------------------------------------------------------------------ api
    @property
    def value(self) -> bytes:
        """Password bytes for the KDF.

        Raises:
            RuntimeError: if accessed after :meth:`wipe` — using a wiped
                password is always a programming error, never silent.
        """
        if self._wiped:
            raise RuntimeError("Password has already been wiped.")
        return bytes(self._buffer)

    def wipe(self) -> None:
        """Zero the buffer. Idempotent."""
        if not self._wiped:
            wipe(self._buffer)
            self._wiped = True

    @property
    def is_wiped(self) -> bool:
        return self._wiped

    def __len__(self) -> int:
        return len(self._buffer)

    # -------------------------------------------------------- context mgmt
    def __enter__(self) -> "SecurePassword":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.wipe()

    def __del__(self) -> None:  # last-resort safety net
        try:
            self.wipe()
        except Exception:  # noqa: BLE001 — never raise from a destructor
            pass

    def __repr__(self) -> str:  # never leak contents via repr/logging
        return f"<SecurePassword wiped={self._wiped}>"
