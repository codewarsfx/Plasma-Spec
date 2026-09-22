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

## What Gets Bundled

- `desktop-dist/frontend`: Next.js standalone server and static assets
- `desktop-dist/backend`: PyInstaller backend executable
- `desktop-dist/molecular`: MassiveOES-style SQLite molecular line databases
- backend storage is created per user under the desktop app's user-data directory

## Public Distribution Checklist

Internal unsigned builds are useful for lab testing, but public downloads should add:

- Apple Developer ID certificate
- macOS notarization credentials
- Windows code-signing certificate
- clean-machine install tests on Windows 10/11 and macOS Intel/Apple Silicon
- an update strategy, such as GitHub Releases plus a signed auto-updater

Without signing, Windows SmartScreen and macOS Gatekeeper can warn users even when the installer is technically valid.

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
