# Developer Guide
## Secure File Encryptor Pro — v1.0

### 1. Environment

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -v          # must be green before you start
python app.py                       # run the app
```

GUI tests run headlessly (`QT_QPA_PLATFORM=offscreen` is set inside the test
files), so the suite works in CI without a display.

### 2. Layering rules (enforced by review)

- `config/`, `utils/`, `models/` — **no Qt imports, ever.**
- `crypto/` — no Qt, no database. Callbacks only (`progress_callback`,
  `cancel_callback`).
- `database/` — no Qt, no crypto.
- `workers/` — the only place crypto meets persistence; communicates
  upward via signals only.
- `ui/` — views emit signals and render state; only `MainWindow` makes
  decisions; only `app.py` builds the object graph.

### 3. Common tasks

**Add a setting** — add one field to `AppSettings` (config/settings.py).
Load/save/validation are automatic. Bind a widget in
`ui/settings_window.py` (`_load_from_settings` + `_on_save`).

**Add a history column** — extend the schema + `HistoryRecord` +
`_row_to_record` (database/database.py), add to `_COLUMNS` and the populate
loop in `ui/history_window.py`, and to `_CSV_HEADER`/`export_csv`.

**Add a new operation type** — subclass `BaseCryptoWorker`, implement
`_validate_source` and `_run_engine`, add an `OperationType` member, wire a
launcher in `MainWindow`.

**Change the file format** — bump `FORMAT_VERSION`, keep the v1 read path,
gate on the version byte in `AESGCMFileEngine._read_header`. Never break
decryption of existing files.

### 4. Testing conventions

- Every module has a `tests/test_<module>.py`; tests use `tmp_path` and the
  injectable constructor parameters — no global state, no real app-data dir.
- Crypto tests use `iterations=2048` for speed; the production floor
  (≥100k) is pinned by `test_config.py::test_pbkdf2_iterations_meet_minimum`.
- Worker logic is tested by calling `run()` synchronously; genuine
  cross-thread behaviour is covered once in `tests/test_app.py`.
- GUI tests construct widgets directly and call slots — no `exec_()` loops.
- PyQt gotcha: keep a Python reference to any `QMimeData` you attach to a
  hand-made event (see `drop_event_for` in test_widgets.py).

### 5. Security invariants (do not break)

1. Passwords: only inside `SecurePassword`; wiped in worker `finally`.
2. No secrets in logs, history rows, or exception messages.
3. Salt and nonce-prefix: fresh `os.urandom` per file, every time.
4. Header fields are AAD — any format change must keep header authentication.
5. Output goes to `.part` then `os.replace` — atomicity is load-bearing.
6. Validate untrusted input (header) before doing expensive work (KDF).

### 6. Building a Windows executable (optional)

```bash
pip install pyinstaller
pyinstaller --noconsole --name "SecureFileEncryptorPro" ^
  --add-data "assets;assets" app.py
```

`ui/theme.py` already resolves the assets path via `sys._MEIPASS` when frozen.
