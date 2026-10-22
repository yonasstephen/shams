// Bundles each extension entry point separately, once per browser.
//
// MV3 content scripts are not ES modules, so every entry is emitted as a self-contained
// IIFE. esbuild alone is enough here — the draft assistant's "nothing between you and a
// working tool" instinct applies to season day too, and a one-file build script is easier
// to reason about at 7pm on a Tuesday than a plugin chain.
//
// Chrome and Firefox run the same bundles. What differs is deployment config only:
// manifest.json holds everything shared, and platforms/{chrome,firefox}.json the keys
// that differ (how the background script is declared, the Firefox add-on id), merged over
// it into dist/chrome/ and dist/firefox/.
//
//   node build.mjs                     both browsers
//   node build.mjs --target firefox    one of them
//   node build.mjs --watch             rebuild both on change
import { build, context } from "esbuild";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";

const PLATFORMS = ["chrome", "firefox"];

const watch = process.argv.includes("--watch");
const targetFlag = process.argv.indexOf("--target");
const requested = targetFlag === -1 ? PLATFORMS : [process.argv[targetFlag + 1]];
if (!requested.every((platform) => PLATFORMS.includes(platform))) {
  console.error(`--target must be one of: ${PLATFORMS.join(", ")}`);
  process.exit(1);
}

const entries = {
  background: "src/background.ts",
  "content-team": "src/content/team.ts",
  "content-matchup": "src/content/matchup.ts",
  "content-tradehub": "src/content/tradeHub.ts",
  "content-transactions": "src/content/transactions.ts",
  "popup/popup": "src/popup/popup.ts",
};

function options(outdir) {
  return {
    entryPoints: Object.entries(entries).map(([out, input]) => ({ out, in: input })),
    bundle: true,
    format: "iife",
    // One target list for both, so the two builds carry identical code.
    target: ["chrome114", "firefox140"],
    outdir,
    sourcemap: watch ? "inline" : false,
    minify: !watch,
    logLevel: "info",
  };
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function copyStatic(platform, outdir) {
  const manifest = { ...(await readJson("manifest.json")), ...(await readJson(`platforms/${platform}.json`)) };
  await writeFile(`${outdir}/manifest.json`, `${JSON.stringify(manifest, null, 2)}\n`);
  await cp("src/overlay/overlay.css", `${outdir}/overlay.css`);
  await mkdir(`${outdir}/popup`, { recursive: true });
  await cp("src/popup/popup.html", `${outdir}/popup/popup.html`);
}

for (const platform of requested) {
  const outdir = `dist/${platform}`;
  await rm(outdir, { recursive: true, force: true });
  await mkdir(outdir, { recursive: true });

  if (watch) {
    const ctx = await context(options(outdir));
    await ctx.watch();
    await copyStatic(platform, outdir);
  } else {
    await build(options(outdir));
    await copyStatic(platform, outdir);
    console.log(`built ${platform} -> ${outdir}/`);
  }
}

if (watch) {
  console.log("watching…  (load dist/chrome/ unpacked in Chrome, or run `npm run firefox`)");
}
