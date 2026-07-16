# User Manual
## Secure File Encryptor Pro — v1.0

### 1. Starting the application

Install dependencies once (`pip install -r requirements.txt`), then run
`python app.py`. The dashboard opens with a drop zone, action buttons, and
your recent activity.

### 2. Encrypting

**Any of these work:**
- Drag files or folders onto the drop zone
- Click **Encrypt Files…** and pick files
- Toolbar → **Encrypt Folder** for a whole directory tree

Then, in the dialog:
1. Enter a password (minimum 8 characters). The colored meter rates its
   strength — aim for *Good* or *Strong*.
2. Confirm the password.
3. Optionally choose an output folder (default: next to each source file).
4. Click **Encrypt**.

Each file becomes `name.ext.sfep`. Folders become `folder_encrypted/` with
the same internal structure. Progress, speed, and remaining time appear at
the bottom; **Cancel** stops cleanly (no partial files are left).

> ⚠ **There is no password recovery.** If you forget the password, the data
> is unrecoverable — that is the point of strong encryption.

### 3. Decrypting

Drop `.sfep` files (the app detects them automatically) or click
**Decrypt Files…**. Enter the password and click **Decrypt**.

- Wrong password → clear "Incorrect password" message per file.
- Damaged/tampered file → "corrupted or tampered" message.
- After success, the banner confirms **Integrity verified** — the decrypted
  content is byte-for-byte identical to the original.

### 4. History

Toolbar → **History**. Every operation is listed with timestamp, type, file,
location, size, duration, status, and SHA-256 hash (hover for the full hash;
failed rows show the error on hover).

- **Search** by filename or location; **filter** by operation or status.
- Click a column header to **sort**.
- **Delete Selected** / **Clear All** to manage records.
- **Export CSV…** writes exactly what the current filters show.

### 5. Settings

Toolbar → **Settings**: dark mode, verify-integrity toggle, temp-file
clearing, default overwrite behaviour, default save location, recent-items
count. **Restore Defaults** resets everything. The 🌓 toolbar button toggles
the theme instantly.

### 6. Troubleshooting

| Symptom | Explanation / fix |
|---|---|
| "Incorrect password for this file." | The password does not match — check keyboard layout/caps lock. |
| "File is corrupted or has been tampered with." | The container failed authentication; restore from a backup copy. |
| "Not a Secure File Encryptor Pro file." | The file was not created by this app (or lost its header). |
| "Output already exists…" | Enable overwrite in Settings, or the app will auto-create "name (1)". |
| "Disk is full…" | Free space; the app pre-checks before writing. |
| Where are logs? | `%APPDATA%\SecureFileEncryptorPro\secure_file_encryptor.log` |
