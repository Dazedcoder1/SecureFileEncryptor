# 🛡 Secure File Encryptor Pro

![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-41cd52?logo=qt&logoColor=white)
![Encryption](https://img.shields.io/badge/Encryption-AES--256--GCM-orange)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088ff?logo=githubactions&logoColor=white)
![Tests](https://img.shields.io/badge/tests-134%20passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

A professional desktop application for encrypting and decrypting files and folders with industry-standard authenticated cryptography — built with Python, PyQt5, and the `cryptography` library using Clean Architecture principles.

---

## ✨ Features

- **AES-256-GCM authenticated encryption** — confidentiality *and* tamper detection in one primitive
- **Password-based key derivation** — PBKDF2-HMAC-SHA256 with 600,000 iterations and a random per-file salt
- **Streaming engine** — files are processed in 4 MiB chunks, so a 20 GB video never sits in RAM
- **Folder encryption** — recursive, preserving the directory structure exactly
- **Integrity verification** — SHA-256 of the plaintext is stored (authenticated) and re-checked after decryption: explicit *Integrity Passed / Failed* verdict
- **Wrong-password vs. corrupted-file detection** — a key check value (KCV) in the header distinguishes the two error cases
- **Drag & drop** — single files, multiple files, or whole folders; encrypted items are auto-routed to decryption
- **Modern GUI with dark & light themes** — rounded controls, hover states, accent colors, one-click toggle
- **Live progress** — current file, overall percentage, speed, elapsed and remaining time
- **Fully responsive** — all crypto runs on QThread workers with cooperative cancellation; the UI never freezes
- **Encryption history** — SQLite-backed log with search, filter, sort, delete, and CSV export
- **Settings** — default save location, overwrite policy, integrity auto-verify, history size, language-ready
- **Secure by design** — passwords never stored or logged, wipeable password buffers, atomic output files, crafted-file hardening

## 📸 Screenshots

**Dashboard (dark mode)** — drag & drop zone with automatic encrypt/decrypt routing:

![Dashboard](docs/screenshots/dashboard_dark.png)

| Encrypt dialog — live strength meter | Decrypt dialog — auto integrity check |
|---|---|
| ![Encrypt dialog](docs/screenshots/encrypt_dialog.png) | ![Decrypt dialog](docs/screenshots/decrypt_dialog.png) |

**Encryption history** — search, filter, sort, CSV export, SHA-256 per file:

![History window](docs/screenshots/history_window.png)

## 🚀 Installation

```bash
git clone https://github.com/Dazedcoder1/SecureFileEncryptor.git
cd SecureFileEncryptor
python -m venv .venv
.venv\Scripts\activate          # Windows   (source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
python app.py
```

Requires **Python 3.10+** (3.12 recommended).

## 📖 Usage

1. **Encrypt** — click *Encrypt Files…* (or drop files/folders on the drop zone), choose a strong password, optionally pick an output folder. Each file becomes `name.ext.sfep`.
2. **Decrypt** — drop `.sfep` files (auto-detected) or click *Decrypt Files…* and enter the password. Integrity is verified automatically.
3. **History** — searchable, sortable log of every operation with SHA-256 hashes; export to CSV.
4. **Settings** — theme, default output folder, overwrite policy, history size.

Command-line test run:

```bash
python -m pytest tests/ -v        # 134 tests
```

## 🏗 Architecture

Clean Architecture with strict inward-pointing dependencies:

```
        ┌────────────────────────────────────────┐
        │  UI (PyQt5 windows, dialogs, widgets)  │
        ├────────────────────────────────────────┤
        │  Workers (QThread batch orchestration) │
        ├──────────────┬─────────────────────────┤
        │ Crypto Engine│  Database (SQLite)      │
        ├──────────────┴─────────────────────────┤
        │  Models · Utils · Config (no Qt here)  │
        └────────────────────────────────────────┘
```

- **models/** — pure dataclasses/enums, zero dependencies
- **crypto/** — AES-GCM streaming engine, KDF, integrity, password container
- **database/** — connection-per-operation SQLite gateway (thread-safe)
- **workers/** — Template-Method QThread workers emitting typed signals
- **ui/** — views render and emit; `MainWindow` is the single controller
- **config/ · utils/** — constants, settings, logging, validation (Qt-free)

## 📁 Folder Structure

```
SecureFileEncryptor/
├── app.py                  # entry point
├── config/                 # constants.py, settings.py
├── crypto/                 # aes_engine, key_derivation, integrity, password_manager, utils
├── database/               # database.py (history gateway)
├── models/                 # records.py (domain types)
├── ui/                     # main_window, dashboard, dialogs, history, settings, about, widgets, theme
├── workers/                # base_worker, encrypt_worker, decrypt_worker
├── utils/                  # logger, validator, file_utils, helpers
├── assets/themes/          # dark.qss, light.qss
├── tests/                  # 134 unit + GUI + integration tests
└── docs/                   # SRS, architecture, user manual, developer guide, API
```

## 🔐 Security Features

| Mechanism | Detail |
|---|---|
| Cipher | AES-256-GCM (authenticated encryption, 128-bit tags) |
| KDF | PBKDF2-HMAC-SHA256, 600k iterations, 128-bit random salt per file |
| Nonces | 96-bit: random 4-byte file prefix + 8-byte chunk counter (never reused) |
| Header authentication | Full 85-byte header is AAD for every chunk — tampering breaks decryption |
| Truncation defense | Plaintext size stored in the authenticated header |
| Wrong password | 128-bit key check value — distinct error from corruption |
| Integrity | SHA-256 plaintext hash verified after decryption |
| Memory hygiene | Passwords in wipeable `bytearray`s, zeroed after use |
| Crash safety | Output written to `.part`, atomically renamed on success |
| Hardening | Magic header, version gate, KDF iteration cap against crafted files |

See [SECURITY.md](SECURITY.md) for the threat model and reporting policy.

## 🗺 Roadmap

- [ ] Argon2id as an alternative KDF
- [ ] Encrypted filename option for folder encryption
- [ ] Portable single-EXE build (PyInstaller) with signed releases
- [ ] Translations (the settings layer is already language-ready)
- [ ] Key-file (two-factor) encryption mode

## 🤝 Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md).

## 📄 License

MIT — see [LICENSE](LICENSE).
