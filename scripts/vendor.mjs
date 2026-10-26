import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

await mkdir("static/vendor", { recursive: true });
await mkdir("static/fonts", { recursive: true });
for (const [entry, filename] of [
  ["@soundtouchjs/audio-worklet", "soundtouch.js"],
  ["@soundtouchjs/audio-worklet/processor", "soundtouch-processor.js"],
]) {
  await build({
    entryPoints: [entry],
    outfile: `static/vendor/${filename}`,
    bundle: true,
    format: "esm",
    minify: true,
    legalComments: "none",
  });
}
await copyFile(
  "node_modules/@soundtouchjs/audio-worklet/LICENSE",
  "static/vendor/SOUNDTOUCH-LICENSE",
);
await copyFile(
  "node_modules/@fontsource-variable/manrope/LICENSE",
  "static/fonts/MANROPE-LICENSE",
);
for (const subset of ["cyrillic", "latin"]) {
  await copyFile(
    `node_modules/@fontsource-variable/manrope/files/manrope-${subset}-wght-normal.woff2`,
    `static/fonts/manrope-${subset}.woff2`,
  );
}
