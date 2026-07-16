# Architecture Document
## Secure File Encryptor Pro — v1.0

### 1. Style

Clean Architecture: source-level dependencies point inward only.

```
UI  →  Workers  →  Crypto / Database  →  Models · Utils · Config
```

- **Innermost:** `models/` (dataclasses/enums), `config/` (constants,
  settings), `utils/` (logging, validation, filesystem) — all Qt-free and
  headlessly testable.
- **Core services:** `crypto/` (the engine never imports Qt or the DB),
  `database/` (never imports Qt or crypto).
- **Orchestration:** `workers/` — the only layer that knows both crypto and
  persistence; QThread subclasses translating engine callbacks into signals.
- **Outermost:** `ui/` — views render and emit; `MainWindow` is the single
  controller; `app.py` is the composition root.

### 2. SOLID mapping

- **S** — each module has one reason to change (e.g., `integrity.py` only
  hashes; `history_window.py` only displays).
- **O** — new operations extend `BaseCryptoWorker` via two hooks without
  modifying the batch loop (Template Method).
- **L** — `EncryptWorker`/`DecryptWorker` are interchangeable wherever a
  `BaseCryptoWorker` is expected (`MainWindow._launch` proves it).
- **I** — signals expose narrow, typed interfaces (`ProgressUpdate`,
  `CryptoResult`) instead of leaking worker internals.
- **D** — injectable dependencies everywhere: `SettingsManager(config_dir)`,
  `HistoryDatabase(db_path)`, workers receive their database; tests exploit
  this with tmp_path fixtures.

### 3. The SFEP v1 container format

```
HEADER (85 bytes, AAD for every chunk)
  magic        4   b"SFEP"
  version      1   uint8
  iterations   4   uint32 BE (PBKDF2 rounds used for THIS file)
  salt        16   random
  nonce_prefix 4   random
  total_size   8   uint64 BE (plaintext length)
  kcv         16   key check value
  sha256      32   plaintext hash
BODY
  repeat: [len uint32 BE][AES-256-GCM ciphertext of ≤4 MiB chunk]
```

Key derivation: `PBKDF2(password, salt, iterations) → 48 bytes = key(32) ‖ kcv(16)`.
Per-chunk nonce: `nonce_prefix ‖ chunk_index(8 BE)` — unique per file & chunk;
reordered chunks fail their tag because the reader derives nonces from its
own counter.

Failure taxonomy: bad magic/header → `InvalidFileFormatError`; newer version →
`UnsupportedVersionError`; KCV mismatch → `WrongPasswordError`; tag/size
failure → `CorruptedFileError`; user abort → `OperationCancelledError`.

### 4. Threading model

One `BaseCryptoWorker` (QThread) at a time, owned by `MainWindow`.
Cross-thread communication is signal-only (Qt queued connections); the
worker never touches widgets. Cancellation is cooperative: a bool flag
polled between chunks; the engine removes partial output before raising.
The password is wiped in a `finally` block — it cannot outlive the batch.

SQLite safety: `HistoryDatabase` opens a short-lived connection per call,
so worker and GUI threads never share a connection.

### 5. Error-handling strategy

Every expected failure becomes a typed exception at the layer that detects
it, is mapped to a user-safe message in exactly one place
(`BaseCryptoWorker._user_message`), lands in the history DB, and surfaces as
a banner — while the batch continues with the next file. Unexpected
exceptions hit the global excepthook: logged with traceback, generic dialog.

### 6. Persistence

- **Settings** — JSON in the app-data dir; dataclass-introspected
  load/save with type validation and corruption fallback.
- **History** — SQLite with CHECK constraints mirroring the enums,
  whitelisted sort columns, parameterized queries throughout.
- **Logs** — rotating file (2 MiB × 3); secrets are never logged.
