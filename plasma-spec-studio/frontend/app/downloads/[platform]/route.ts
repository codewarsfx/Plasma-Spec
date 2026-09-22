import { createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Platform = "mac" | "windows";

const downloads: Record<Platform, {
  contentType: string;
  envUrl: string;
  filenames: string[];
}> = {
  mac: {
    contentType: "application/x-apple-diskimage",
    envUrl: "PLASMA_SPEC_MAC_DOWNLOAD_URL",
    filenames: [
      "PlasmaSpec Studio-0.1.0-arm64.dmg",
      "PlasmaSpec Studio-0.1.0-x64.dmg",
      "PlasmaSpec Studio-0.1.0.dmg",
    ],
  },
  windows: {
    contentType: "application/vnd.microsoft.portable-executable",
    envUrl: "PLASMA_SPEC_WINDOWS_DOWNLOAD_URL",
    filenames: [
      "PlasmaSpec Studio-0.1.0-Setup.exe",
      "PlasmaSpec-Studio-0.1.0-Setup.exe",
    ],
  },
};

function releaseCandidates(filename: string) {
  return [
    path.resolve(process.cwd(), "..", "release", filename),
    path.resolve(process.cwd(), "..", "..", "release", filename),
    path.resolve(process.cwd(), "release", filename),
  ];
}

function findLocalArtifact(platform: Platform) {
  // Previously this gated on a `win-unpacked/resources/backend/...exe`
  // sidecar path, which only exists for an unpacked `--dir` target build.
  // The actual Windows installer (from `dist:win`, and what CI uploads to
  // GitHub Releases) is just `release/*.exe` -- the loop below already
  // checks for that file directly, so the extra gate only produced false
  // 404s when a valid installer was present without also having a
  // `win-unpacked` directory next to it.
  for (const filename of downloads[platform].filenames) {
    const candidate = releaseCandidates(filename).find((artifactPath) => existsSync(artifactPath));
    if (candidate) {
      return { filename, artifactPath: candidate };
    }
  }
  return null;
}

function artifactHeaders(platform: Platform, filename: string, size: number) {
  return {
    "content-disposition": `attachment; filename="${filename}"`,
    "content-length": String(size),
    "content-type": downloads[platform].contentType,
  };
}

export async function HEAD(
  _request: NextRequest,
  context: { params: Promise<{ platform: string }> },
) {
  const { platform: platformParam } = await context.params;
  if (platformParam !== "mac" && platformParam !== "windows") {
    return new Response(null, { status: 404 });
  }

  const platform = platformParam as Platform;
  const externalUrl = process.env[downloads[platform].envUrl];
  if (externalUrl) {
    return NextResponse.redirect(externalUrl);
  }

  const artifact = findLocalArtifact(platform);
  if (!artifact) {
    return new Response(null, { status: 404 });
  }

  const stats = statSync(artifact.artifactPath);
  return new Response(null, {
    headers: artifactHeaders(platform, artifact.filename, stats.size),
  });
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ platform: string }> },
) {
  const { platform: platformParam } = await context.params;
  if (platformParam !== "mac" && platformParam !== "windows") {
    return new Response("Unknown download platform.", { status: 404 });
  }

  const platform = platformParam as Platform;
  const externalUrl = process.env[downloads[platform].envUrl];
  if (externalUrl) {
    return NextResponse.redirect(externalUrl);
  }

  const artifact = findLocalArtifact(platform);
  if (!artifact) {
    return new Response(
      `${platform === "mac" ? "macOS DMG" : "Windows EXE"} artifact is not present on this server yet. Build installers with npm run dist:mac or npm run dist:win, or set ${downloads[platform].envUrl} to a hosted release URL.`,
      {
        status: 404,
        headers: { "content-type": "text/plain; charset=utf-8" },
      },
    );
  }

  const stats = statSync(artifact.artifactPath);
  const stream = Readable.toWeb(createReadStream(artifact.artifactPath));

  return new Response(stream as BodyInit, {
    headers: artifactHeaders(platform, artifact.filename, stats.size),
  });
}
