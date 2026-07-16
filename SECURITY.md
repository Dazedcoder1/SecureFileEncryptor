# Security Policy

## Reporting a vulnerability

Please email **tahzibshams@gmail.com** with details. Do **not** open a public
GitHub issue for security problems. You can expect an acknowledgement within
72 hours. Please include reproduction steps and an assessment of impact.

## Threat model (what this app defends against)

| Threat | Defense |
|---|---|
| Offline brute force of the password | PBKDF2-HMAC-SHA256, 600,000 iterations, 128-bit random per-file salt |
| Ciphertext tampering / bit flips | AES-256-GCM 128-bit authentication tags per 4 MiB chunk |
| Header tampering (salt, size, stored hash…) | Entire header is AAD for every chunk |
| Chunk reordering or duplication | Per-chunk counter nonces — wrong position ⇒ tag failure |
| File truncation | Authenticated plaintext length; size mismatch ⇒ error |
| Silent corruption at rest | SHA-256 plaintext digest verified after decryption |
| Crafted files causing DoS | Magic/version/iteration-count validation before any KDF work; frame-length bounds |
| Password disclosure via app data | Passwords never stored, logged, or written to the history DB; in-memory buffers zeroed after use |

## Known limitations (honest disclosure)

- **Python memory model** — strings are immutable; the wipeable buffer is
  best-effort. A local attacker with memory-dump capability during an
  operation may recover secrets. This is inherent to managed runtimes.
- **Plaintext hash in header** — the SHA-256 of the original file is stored
  (authenticated but not encrypted). An attacker holding a candidate file
  can confirm it matches an encrypted container. If this matters for your
  use case, treat the `.sfep` files themselves as confidential.
- **Metadata** — file names and sizes (approximately) are visible from the
  container; encryption protects contents, not existence.
- **No protection against keyloggers** or a compromised operating system.

## Supported versions

| Version | Supported |
|---|---|
| 1.x | ✅ |
