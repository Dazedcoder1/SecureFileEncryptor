# Contributing to Secure File Encryptor Pro

Thanks for your interest in contributing!

## Getting started

```bash
git clone https://github.com/Dazedcoder1/SecureFileEncryptor.git
cd SecureFileEncryptor
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Ground rules

- **All tests must pass** (`python -m pytest tests/`) and new features need new tests.
- **PEP 8 + type hints + docstrings** on every public function and class.
- **Respect the architecture**: dependencies point inward only. UI may import
  workers/crypto/database; crypto must never import UI. `config/`, `utils/`,
  and `models/` stay Qt-free.
- **Security-sensitive changes** (anything in `crypto/`) require a clear
  rationale in the PR description and must not weaken existing tests
  (e.g., the KDF iteration floor asserted in `tests/test_config.py`).
- **Never log or persist secrets.** No passwords, keys, or plaintext in logs,
  history, or exception messages.

## Workflow

1. Fork, then create a topic branch: `git checkout -b feature/my-feature`
2. Make focused commits with clear messages.
3. Run the full test suite.
4. Open a pull request describing *what* and *why*.

## Reporting bugs

Open an issue with steps to reproduce, expected vs. actual behaviour, OS,
and Python version. For security vulnerabilities, see [SECURITY.md](SECURITY.md)
— please do **not** open public issues for those.
