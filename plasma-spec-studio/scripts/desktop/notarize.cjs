const { notarize } = require("@electron/notarize");

function shouldSkip() {
  // Matches after-pack.cjs's shouldAdHocSign(): an ad-hoc/unsigned build has
  // no real Developer ID signature, and Apple's notary service rejects those
  // outright, so there's nothing useful to submit.
  if (process.env.PLASMA_SPEC_ADHOC_SIGN === "1") return true;
  if (process.env.CSC_IDENTITY_AUTO_DISCOVERY === "false" && !process.env.CSC_LINK && !process.env.CSC_NAME) {
    return true;
  }
  return false;
}

function appleCredentials() {
  if (process.env.APPLE_API_KEY && process.env.APPLE_API_KEY_ID && process.env.APPLE_API_ISSUER) {
    return {
      appleApiKey: process.env.APPLE_API_KEY,
      appleApiKeyId: process.env.APPLE_API_KEY_ID,
      appleApiIssuer: process.env.APPLE_API_ISSUER,
    };
  }
  if (process.env.APPLE_ID && process.env.APPLE_APP_SPECIFIC_PASSWORD && process.env.APPLE_TEAM_ID) {
    return {
      appleId: process.env.APPLE_ID,
      appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
      teamId: process.env.APPLE_TEAM_ID,
    };
  }
  return null;
}

exports.default = async function notarizeHook(context) {
  if (context.electronPlatformName !== "darwin") return;

  if (shouldSkip()) {
    console.log("[notarize] Ad-hoc/unsigned build -- skipping notarization.");
    return;
  }

  const credentials = appleCredentials();
  if (!credentials) {
    // This is the gap the audit flagged: hardenedRuntime + entitlements were
    // configured, but nothing ever actually notarized a build, so a
    // Developer-ID-signed DMG built this way would still be Gatekeeper
    // -blocked for anyone who isn't the machine that built it. Warn loudly
    // rather than silently shipping a notarization-less "signed" build.
    console.warn(
      "[notarize] WARNING: no Apple credentials found (set APPLE_ID + " +
        "APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID, or APPLE_API_KEY + " +
        "APPLE_API_KEY_ID + APPLE_API_ISSUER). Skipping notarization -- this " +
        "build will be Gatekeeper-blocked for anyone besides the machine " +
        "it was built on. See DESKTOP_RELEASE.md's Public Distribution Checklist.",
    );
    return;
  }

  const appName = `${context.packager.appInfo.productFilename}.app`;
  const appPath = `${context.appOutDir}/${appName}`;
  const appBundleId = context.packager.config.appId;

  console.log(`[notarize] Submitting ${appPath} (${appBundleId}) for notarization...`);
  await notarize({ appBundleId, appPath, ...credentials });
  console.log("[notarize] Notarization complete.");
};
