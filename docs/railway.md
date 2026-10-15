# Railway deployment

The local command remains localhost-only. Hosted mode is explicit and must have an HTTPS public origin and either a strong access password or explicit public-access configuration.

## Runtime

- Docker installs Pillow, Tesseract English OCR data and Poppler PDF tools.
- Railway routes HTTPS to the injected PORT on the container.
- CODEWORD_HOSTED=1 enables the hosted listener.
- CODEWORD_PUBLIC_ORIGIN specifies the exact HTTPS origin; RAILWAY_PUBLIC_DOMAIN is the fallback domain.
- CODEWORD_ACCESS_PASSWORD protects the shared workspace with HTTP Basic authentication (username codeword). Use a generated password of at least 16 characters, stored only in Railway variables.
- CODEWORD_ALLOW_PUBLIC=1 explicitly permits unauthenticated access when no password is configured. Anyone with access can view and change the shared workspace. There are no separate user accounts.
- CODEWORD_DATA_DIR=/data points to the attached persistent volume.
- GET /healthz is a minimal unauthenticated health check. All application and data routes follow the configured access policy.
- Keep one replica: solve jobs live in process memory and JSON storage uses process-local locking. In-progress searches end during deployment or restart.

## Data

The build context includes application code and browser assets only. Local puzzles, custom dictionaries, credentials, backups and generated morphology indexes are excluded. A new volume starts with the bundled demonstration vocabulary. Import a dictionary through the app for broader vocabulary. The optional Finnish morphology database must be provisioned separately; the app reports when it is unavailable.

Saved puzzles and dictionaries persist on the volume across deployments. Export important puzzles as JSON as an additional backup. The hosted workspace is separate from the local workspace.

## Verification

Run the full Python and JavaScript suites before publication. Verify that the health check responds, unauthenticated data requests fail for password-protected instances, valid credentials allow use, and foreign Origin/Host values are rejected. Exercise a solve job and storage through the deployed API.

Railway references: https://docs.railway.com/deployments/healthchecks and https://docs.railway.com/volumes.
