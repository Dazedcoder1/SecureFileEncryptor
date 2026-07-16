# Software Requirements Specification
## Secure File Encryptor Pro — v1.0

### 1. Introduction

**1.1 Purpose.** This document specifies the functional and non-functional
requirements of Secure File Encryptor Pro, a desktop application for
password-based file and folder encryption.

**1.2 Scope.** The system encrypts and decrypts local files and folders using
AES-256-GCM, maintains an operation history, and provides a modern desktop
GUI. It does not provide cloud storage, key escrow, or multi-user features.

**1.3 Definitions.**
- *SFEP container* — the application's encrypted file format (v1).
- *KCV* — key check value; 16 derived bytes stored to detect wrong passwords.
- *Job* — one (source, destination) file pair processed by a worker.

### 2. Overall description

Single-user desktop application. Python 3.10+ / PyQt5 / SQLite / the
`cryptography` library. All state lives in the per-user app-data directory.

### 3. Functional requirements

| ID | Requirement |
|----|-------------|
| FR-1 | Encrypt any file with AES-256-GCM using a user-supplied password |
| FR-2 | Decrypt SFEP files, verifying authentication tags and plaintext hash |
| FR-3 | Derive keys with PBKDF2-HMAC-SHA256, ≥100k iterations (600k default), random 128-bit salt per file |
| FR-4 | Encrypt/decrypt folders recursively, preserving directory structure |
| FR-5 | Report "Integrity Passed/Failed" after every decryption |
| FR-6 | Distinguish wrong-password from corrupted-file errors |
| FR-7 | Accept single files, multiple files, and folders via drag & drop; auto-route encrypted items to decryption |
| FR-8 | Show live progress: current file, N of M, overall %, speed, elapsed, remaining |
| FR-9 | Allow cancelling a running operation; partial output must be removed |
| FR-10 | Record every operation (timestamp, type, file, location, size, duration, status, SHA-256, error) in SQLite |
| FR-11 | History: search, filter by operation/status, sort, delete rows, clear all, export CSV |
| FR-12 | Settings: dark mode, default save location, integrity auto-verify, temp-file clearing, overwrite policy, language (ready), recent-history size |
| FR-13 | Enforce password policy on encryption: min 8 chars, confirmation match, live strength meter |
| FR-14 | Never store, log, or transmit passwords or derived keys |
| FR-15 | Log application start/exit, successes, warnings, and errors to a rotating file |
| FR-16 | Handle gracefully: wrong password, corrupted/truncated file, missing file, permission denied, disk full, invalid folder, non-SFEP input, database errors |

### 4. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | GUI must remain responsive during any operation (crypto on QThread workers) |
| NFR-2 | Memory use independent of file size (streaming, 4 MiB chunks) |
| NFR-3 | Cross-platform file handling via pathlib; no hardcoded paths |
| NFR-4 | Codebase: PEP 8, type hints, docstrings, Clean Architecture layering |
| NFR-5 | Automated test coverage of crypto, database, workers, and GUI |
| NFR-6 | Crash safety: no partially-written output ever appears valid (atomic rename) |
| NFR-7 | Crafted-file inputs must not cause unbounded CPU/memory (header validation) |

### 5. Acceptance criteria

The 134-test suite (`python -m pytest tests/`) encodes the acceptance tests:
roundtrip fidelity, tamper/truncation/wrong-password detection, cancellation
cleanup, history CRUD + injection resistance, settings persistence, GUI
behaviour, and a real-thread end-to-end scenario.
