## What does this PR do?

<!-- One or two sentences. Link related issues: Fixes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / code quality
- [ ] Documentation
- [ ] Security-sensitive change (touches `crypto/` — explain rationale below)

## Checklist

- [ ] `python -m pytest tests/` passes locally
- [ ] New behaviour is covered by new tests
- [ ] Type hints + docstrings on new public functions
- [ ] Layering respected (no Qt in `config/`, `utils/`, `models/`, `crypto/`, `database/`)
- [ ] No secrets in logs, history, or exception messages

## Notes for the reviewer

<!-- Anything that needs special attention -->
