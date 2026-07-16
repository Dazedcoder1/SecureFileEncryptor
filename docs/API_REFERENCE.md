# API Reference
## Secure File Encryptor Pro — v1.0

Public surface per module (see docstrings for full parameter documentation).

### crypto.aes_engine

```python
class AESGCMFileEngine:                      # stateless, thread-safe
    encrypt_file(source, destination, password: bytes,
                 iterations=600_000,
                 progress_callback=None, cancel_callback=None) -> CryptoResult
    decrypt_file(source, destination, password: bytes,
                 progress_callback=None, cancel_callback=None) -> CryptoResult
HEADER_SIZE: int                             # 85
```
Raises: `InvalidFileFormatError`, `UnsupportedVersionError`,
`WrongPasswordError`, `CorruptedFileError`, `OperationCancelledError`.

### crypto.key_derivation / crypto.integrity / crypto.password_manager

```python
derive_key_material(password: bytes, salt: bytes,
                    iterations=600_000) -> tuple[key32, kcv16]
hash_file(path, progress_callback=None, cancel_callback=None) -> bytes  # 32
verify_file(path, expected_digest: bytes) -> bool

class SecurePassword:                        # context manager
    SecurePassword(password, confirmation=None, enforce_policy=True)
    value: bytes;  wipe();  is_wiped: bool
```

### workers

```python
build_encrypt_jobs(paths, output_dir=None) -> list[(src, dst)]
build_decrypt_jobs(paths, output_dir=None) -> list[(src, dst)]

class BaseCryptoWorker(QThread):
    progress_updated = pyqtSignal(object)    # ProgressUpdate
    file_completed  = pyqtSignal(object)     # CryptoResult
    file_failed     = pyqtSignal(str, str)   # filename, reason
    batch_finished  = pyqtSignal(int, int, bool)  # ok, failed, cancelled
    request_cancel()

class EncryptWorker(BaseCryptoWorker):       # + iterations parameter
class DecryptWorker(BaseCryptoWorker):
```

### database.database

```python
class HistoryDatabase:
    HistoryDatabase(db_path: Path | None = None)
    add_record(record: HistoryRecord) -> int
    get_records(limit=None, offset=0, operation=None, status=None,
                search=None, sort_by="timestamp", descending=True)
                -> list[HistoryRecord]
    count_records() -> int
    delete_record(record_id) -> bool
    clear_history() -> int
    prune(max_rows=500) -> int
    export_csv(destination, **filters) -> int
```
Raises `DatabaseError`; `ValueError` for non-whitelisted `sort_by`.

### config

```python
class SettingsManager:
    SettingsManager(config_dir: Path | None = None)
    get(key) / set(key, value, persist=True) / reset_to_defaults()
    settings: AppSettings;  path: Path
get_app_data_dir() -> Path
constants: APP_NAME, KEY_SIZE, NONCE_SIZE, SALT_SIZE, PBKDF2_ITERATIONS,
           CHUNK_SIZE, ENCRYPTED_EXTENSION, MAGIC_HEADER, ...
```

### utils

```python
validator:  password_issues, validate_password, password_strength,
            validate_input_file, validate_input_folder,
            validate_output_location, is_encrypted_file, ValidationError,
            PasswordStrength
file_utils: human_readable_size, collect_files, total_size,
            encrypted_output_path, decrypted_output_path,
            ensure_unique_path, has_enough_disk_space, mirror_subpath
helpers:    format_duration, format_speed, estimate_remaining,
            now_timestamp, truncate_middle
logger:     setup_logging, get_logger, log_app_start, log_app_exit
```

### models.records

```python
OperationType(Enum): ENCRYPT, DECRYPT
OperationStatus(Enum): SUCCESS, FAILED, CANCELLED
CryptoResult(frozen): source, destination, size_bytes, sha256_hex,
                      duration_seconds, integrity_ok
ProgressUpdate(frozen): current_file, file_index, file_count, done_bytes,
                        total_bytes, percent, speed_bps, elapsed_seconds,
                        remaining_seconds
HistoryRecord: record_id, timestamp, operation, filename, location,
               size_bytes, duration_seconds, status, sha256_hex,
               error_message
```

### ui

```python
MainWindow(settings, database)               # controller; classify_paths()
Dashboard;  EncryptDialog;  DecryptDialog;  HistoryWindow
SettingsWindow(settings_changed signal);  AboutWindow
widgets: DropZone, PasswordField, StrengthMeter, ProgressPanel,
         NotificationBanner
theme:   apply_theme(app, dark), load_stylesheet(dark), repolish(widget)
```
