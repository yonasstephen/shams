// Bundles each extension entry point separately.
//
// MV3 content scripts are not ES modules, so every entry is emitted as a self-contained
// IIFE. esbuild alone is enough here — the draft assistant's "nothing between you and a
// working tool" instinct applies to season day too, and a one-file build script is easier
// to reason about at 7pm on a Tuesday than a plugin chain.
import { build, context } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";

const outdir = "dist";
const watch = process.argv.includes("--watch");

const entries = {
  background: "src/background.ts",
  "content-team": "src/content/team.ts",
  "content-matchup": "src/content/matchup.ts",
  "popup/popup": "src/popup/popup.ts",
};

const options = {
  entryPoints: Object.entries(entries).map(([out, input]) => ({ out, in: input })),
  bundle: true,
  format: "iife",
  target: ["chrome114"],
  outdir,
  sourcemap: watch ? "inline" : false,
  minify: !watch,
  logLevel: "info",
};

async function copyStatic() {
  await cp("manifest.json", `${outdir}/manifest.json`);
  await cp("src/overlay/overlay.css", `${outdir}/overlay.css`);
  await mkdir(`${outdir}/popup`, { recursive: true });
  await cp("src/popup/popup.html", `${outdir}/popup/popup.html`);
}

await rm(outdir, { recursive: true, force: true });
await mkdir(outdir, { recursive: true });

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  await copyStatic();
  console.log("watching…  (load dist/ as an unpacked extension)");
} else {
  await build(options);
  await copyStatic();
  console.log(`built -> ${outdir}/`);
}
