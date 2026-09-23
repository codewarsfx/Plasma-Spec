# Desktop Release

PlasmaSpec Studio can be shipped as a downloadable macOS DMG and Windows EXE installer. The desktop app uses Electron for the shell, a PyInstaller-built FastAPI backend sidecar, and the Next.js standalone frontend server.

## Local Builds

Install dependencies once:

```bash
npm install
cd frontend && npm install
cd ../backend && .venv/bin/python -m pip install -r requirements-build.txt
```

Build the staged desktop payload:

```bash
npm run desktop:prepare
```

Build installers:

```bash
npm run dist:mac
npm run dist:win
```

Outputs are written to `release/`.

For local unsigned macOS test builds, use:

```bash
npm run dist:mac:local
```

This creates an ad-hoc signed DMG. It is still not a public notarized build, but it avoids broken local signatures that macOS may report as "damaged".

## GitHub Release Builds

The workflow at `.github/workflows/desktop-release.yml` builds:

- macOS `.dmg`
- Windows `.exe` NSIS installer

Run it manually from GitHub Actions, or push a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Tagged builds upload the installers to the GitHub release.

## Product Site Download Links

The portfolio site links to:

- `/downloads/mac`
- `/downloads/windows`

Those routes serve local files from `release/` when valid artifacts are present. For a hosted public site, set these environment variables so the routes redirect to the official release assets:

```bash
PLASMA_SPEC_MAC_DOWNLOAD_URL=https://example.com/PlasmaSpec-Studio.dmg
PLASMA_SPEC_WINDOWS_DOWNLOAD_URL=https://example.com/PlasmaSpec-Studio-Setup.exe
```

Build the Windows installer on Windows, not by cross-building from macOS. The Windows app needs a PyInstaller-built `plasma-spec-backend.exe` sidecar; a macOS cross-build can package the wrong backend binary.

## Google Sign-In / Supabase in Desktop Builds

Set these before `npm run desktop:prepare` (or `dist:mac`/`dist:win`, which call it) if you want the packaged app to have Google sign-in and Supabase-backed persistence baked in, same as the web app's `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY`:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-public-key
```

`scripts/desktop/build-frontend.mjs` bakes these into the renderer's Next bundle (as usual for `NEXT_PUBLIC_*`) and also writes `desktop/env.generated.cjs` (gitignored, regenerated every build) so `desktop/main.cjs`'s own Google sign-in flow -- which runs in the Electron main process, not through Next's webpack build -- has them too, without requiring an end user to set environment variables to launch the app. Without them, the packaged app still works, just with local-only storage and no sign-in button (same as running the web app with no Supabase env vars).

The Python backend sidecar separately needs `PLASMA_SPEC_STORAGE_BACKEND=supabase` + `SUPABASE_URL`/`SUPABASE_ANON_KEY` in its own environment to turn on Supabase mode (`startBackend()` already forwards `desktop/main.cjs`'s entire `process.env` into the spawned backend, so setting these in the shell that launches the app -- `npm run desktop:dev`, or the packaged app's launch environment -- is enough; no code change needed).

**`SUPABASE_JWT_SECRET` is optional and deliberately not auto-baked**: `backend/app/auth.py` verifies tokens against the project's public JWKS by default (Supabase's now-standard asymmetric ES256 signing keys), which only needs the already-public `SUPABASE_URL` -- no secret involved. `SUPABASE_JWT_SECRET` is only a fallback for a project still on (or mid-migration off of) the legacy shared HS256 secret, and unlike the anon key it's a real secret -- anyone who extracted it from a distributed binary could forge a valid access token for *any* user in the project, not just their own. It is intentionally NOT written into `env.generated.cjs` the way the URL/anon key are; set it in the launch environment directly if you still need it, same as the other two.

`package.json`'s electron-builder `files` list includes `node_modules/**/*` (needed so `@supabase/supabase-js` -- a root-level `dependencies` entry, not `devDependencies` -- gets bundled into the packaged app; electron-builder's default pruning still correctly excludes `electron`/`electron-builder` themselves). Run `npm install` at the repo root (not just inside `frontend/`) after pulling this change.

## What Gets Bundled

- `desktop-dist/frontend`: Next.js standalone server and static assets
- `desktop-dist/backend`: PyInstaller backend executable
- `desktop-dist/molecular`: MassiveOES-style SQLite molecular line databases
- root `node_modules/@supabase/**` (see above)
- backend storage (spectra, exports, recipes) and the NIST live-refresh cache / user atomic-line overrides are created per user under the desktop app's user-data directory (`app.getPath("userData")`), not inside the read-only `.app` bundle -- or, with `PLASMA_SPEC_STORAGE_BACKEND=supabase`, persisted to Supabase instead

`npm run desktop:build:backend` looks for the molecular `.db` files in a sibling `Molecular Line Data/` folder next to this repo (gitignored -- it's real lab data, not tracked in git). **The build now fails loudly if it can't find them**, since a "successful" build without them ships with molecular band fitting completely broken. If you're intentionally building a demo-only package, set `PLASMA_SPEC_ALLOW_MISSING_MOLECULAR_DB=1` to acknowledge that and continue anyway. `.github/workflows/desktop-release.yml` only checks out this repo, so CI has no access to that data either -- until it's provided as a secret/private artifact step in that workflow, CI desktop builds will fail this check rather than silently ship broken installers.

## Public Distribution Checklist

Internal unsigned builds are useful for lab testing, but public downloads should add:

- Apple Developer ID certificate (`CSC_LINK` + `CSC_KEY_PASSWORD`, or `CSC_NAME`, for electron-builder)
- macOS notarization credentials (see below -- the hook exists, but does nothing without these)
- Windows code-signing certificate
- clean-machine install tests on Windows 10/11 and macOS Intel/Apple Silicon
- an update strategy, such as GitHub Releases plus a signed auto-updater

Without signing, Windows SmartScreen and macOS Gatekeeper can warn users even when the installer is technically valid.

### macOS notarization

`npm run dist:mac` (real Developer-ID-signed builds, not `:local`) runs `scripts/desktop/notarize.cjs` as electron-builder's `afterSign` hook. It only submits to Apple's notary service when it finds credentials in the environment -- either:

```bash
APPLE_API_KEY=...        # path to the .p8 key, or its contents depending on your CI setup
APPLE_API_KEY_ID=...
APPLE_API_ISSUER=...
```

or:

```bash
APPLE_ID=you@example.com
APPLE_APP_SPECIFIC_PASSWORD=...   # generated at appleid.apple.com, not your account password
APPLE_TEAM_ID=...
```

Without one of those sets, the hook logs a warning and skips notarization -- the build still "succeeds," but the resulting DMG will be Gatekeeper-blocked for anyone besides the machine that built it. `.github/workflows/desktop-release.yml` does not currently set any of these secrets, so **GitHub-released DMGs are not notarized today**; add the secrets to the repo and pass them through to the `dist:mac` step to close that gap.

## macOS "Damaged App" During Local Testing

If a locally downloaded unsigned build shows:

```text
"PlasmaSpec Studio" is damaged and can't be opened. You should move it to the Bin.
```

that is macOS Gatekeeper/quarantine rejecting a non-notarized download. For your own machine only, remove the quarantine flag after installing:

```bash
xattr -dr com.apple.quarantine "/Applications/PlasmaSpec Studio.app"
```

For public users, do not rely on that workaround. Ship a Developer ID signed and notarized DMG.
