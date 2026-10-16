# Railway deployment

The local command remains localhost-only. Hosted mode is explicit and must have an HTTPS public origin and an explicit access policy: guest access, a user-mode password, or both.

## Access policy

| Variables | Visitors start in | User mode |
| --- | --- | --- |
| `CODEWORD_ALLOW_PUBLIC=1` and `CODEWORD_ACCESS_PASSWORD` | Guest mode | Available with the password |
| `CODEWORD_ACCESS_PASSWORD` only | Password prompt | Required for any use |
| `CODEWORD_ALLOW_PUBLIC=1` only | Guest mode | Not available |

- **Guest mode** stores nothing on the data volume. Puzzles stay in the visitor's browser (IndexedDB recovery copy, Export/Import JSON). Saved-puzzle and server-autosave routes return 403. Guests see the bundled demonstration vocabularies, never the persistent dictionaries. Their dictionary imports and edits go to a per-browser-session folder in the container's temporary directory, identified by an HttpOnly `cw_guest` session cookie. Limits: 200,000 words and 4 MB per list, at most ten guest dictionary folders at once, removed after two hours without use and on restart. Guests may use the optional Finnish morphology index read-only.
- **User mode** uses the persistent data directory (`CODEWORD_DATA_DIR`), exactly like the local app. The visitor enters `CODEWORD_ACCESS_PASSWORD` in the app; the server then sets a signed `cw_user` cookie (HttpOnly, Secure, SameSite=Strict) valid for 14 days. **Leave user mode** clears it. Changing the password ends every user session. Everyone with the password shares one workspace; there are no separate accounts.
- Wrong passwords are limited to ten per minute across the server.
- Guests can hold at most one of the two concurrent solve, OCR, PDF or straightening slots, so user mode always has one free.

## Runtime

- Docker installs Pillow, Tesseract English OCR data and Poppler PDF tools.
- Railway routes HTTPS to the injected PORT on the container.
- CODEWORD_HOSTED=1 enables the hosted listener.
- CODEWORD_PUBLIC_ORIGIN specifies the exact HTTPS origin; RAILWAY_PUBLIC_DOMAIN is the fallback domain.
- CODEWORD_ACCESS_PASSWORD enables user mode. Use a generated password of at least 16 characters, stored only in Railway variables. Delete the variable to disable user mode; an empty value is rejected at startup.
- CODEWORD_ALLOW_PUBLIC=1 enables guest mode.
- CODEWORD_DATA_DIR=/data points to the attached persistent volume.
- GET /healthz is a minimal unauthenticated health check. The app shell, `GET /api/session` and sign-in are open; all other application and data routes follow the access policy.
- Keep one replica: solve jobs and guest workspaces live in process memory and temporary storage, and JSON storage uses process-local locking. In-progress searches and guest dictionaries end during deployment or restart.

## Data

The build context includes application code and browser assets only. Local puzzles, custom dictionaries, credentials, backups and generated morphology indexes are excluded. A new volume starts with the bundled demonstration vocabulary. Import a dictionary through the app in user mode for broader vocabulary. The optional Finnish morphology database must be provisioned separately; the app reports when it is unavailable.

Saved puzzles and dictionaries persist on the volume across deployments. Export important puzzles as JSON as an additional backup. The hosted workspace is separate from the local workspace. The volume's `autosave.json` is used only by the local app; hosted recovery copies stay in each browser.

## Verification

Run the full Python and JavaScript suites before publication. Verify that the health check responds, guests cannot read or change saved puzzles or the persistent dictionaries, a wrong password is refused, the right password enables saving, and foreign Origin/Host values are rejected. Exercise a solve job and storage through the deployed API in both modes.

Railway references: https://docs.railway.com/deployments/healthchecks and https://docs.railway.com/volumes.
