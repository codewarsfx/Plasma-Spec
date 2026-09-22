const childProcess = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

function run(command, args, options = {}) {
  const result = childProcess.spawnSync(command, args, {
    stdio: "inherit",
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed`);
  }
}

function shouldAdHocSign() {
  if (process.env.PLASMA_SPEC_ADHOC_SIGN === "1") return true;
  if (process.env.CSC_IDENTITY_AUTO_DISCOVERY === "false" && !process.env.CSC_LINK && !process.env.CSC_NAME) {
    return true;
  }
  return false;
}

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== "darwin" || !shouldAdHocSign()) {
    return;
  }

  const appName = `${context.packager.appInfo.productFilename}.app`;
  const appPath = path.join(context.appOutDir, appName);
  if (!fs.existsSync(appPath)) {
    throw new Error(`macOS app bundle not found for ad-hoc signing: ${appPath}`);
  }

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "plasmaspec-sign-"));
  const tempAppPath = path.join(tempRoot, appName);
  const entitlements = path.join(context.packager.projectDir, "desktop", "entitlements.mac.plist");

  try {
    run("ditto", ["--norsrc", "--noextattr", appPath, tempAppPath]);
    run("codesign", [
      "--force",
      "--deep",
      "--sign",
      "-",
      "--options",
      "runtime",
      "--entitlements",
      entitlements,
      tempAppPath,
    ]);
    run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", tempAppPath]);
    fs.rmSync(appPath, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
    run("ditto", ["--norsrc", "--noextattr", tempAppPath, appPath]);
    run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  }
};
