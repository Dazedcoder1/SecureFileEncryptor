# Changelog

All notable changes to Secure File Encryptor Pro are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-07-16

### Added
- AES-256-GCM streaming file encryption/decryption (SFEP v1 container format)
- PBKDF2-HMAC-SHA256 key derivation (600k iterations, per-file random salt)
- Key check value (KCV) for wrong-password vs. corrupted-file distinction
- SHA-256 integrity verification with explicit passed/failed verdict
- Recursive folder encryption/decryption preserving directory structure
- Drag & drop with automatic encrypt/decrypt routing
- Dark and light QSS themes with runtime toggle
- QThread background workers: live progress (speed / elapsed / remaining),
  per-file error recovery, cooperative cancellation
- SQLite encryption history: search, filter, sort, delete, CSV export, pruning
- Settings dialog (save location, overwrite policy, integrity auto-verify,
  history size, language-ready)
- Rotating file logging; passwords and keys are never logged
- 134 automated tests: unit, crypto attack scenarios, database, GUI (offscreen),
  and real-thread integration
- GitHub Actions CI (Ubuntu + Windows, Python 3.10/3.12), issue and PR templates
