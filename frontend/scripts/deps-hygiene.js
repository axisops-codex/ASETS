#!/usr/bin/env node
// Dependency hygiene check — the classes of rot that yarn only ever *warns* about,
// turned into something a person or CI can act on.
//
// Every pin in `resolutions` was added to escape a specific advisory or an
// unmaintained package. Nothing re-checks that claim afterwards, so a pin quietly
// drifts below the version that actually fixes the thing it was added for, while
// still looking like protection. That is what happened here: every pin in the block
// had fallen behind its own advisory.
//
//   node ./scripts/deps-hygiene.js            offline checks, warn only
//   node ./scripts/deps-hygiene.js --audit    also cross-check pins against advisories (network)
//   node ./scripts/deps-hygiene.js --strict   exit 1 on any finding (for CI)
//
// Runs from postinstall in warn mode, so a stale pin surfaces on every install
// without ever breaking one.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = process.cwd();
const AUDIT = process.argv.includes("--audit");
const STRICT = process.argv.includes("--strict");

let semver;
try {
  semver = require("semver");
} catch {
  // Hoisted transitive dep: absent only before the first install, when there is
  // no tree to check anyway.
  console.log("deps-hygiene: semver unavailable (pre-install tree); skipping.");
  process.exit(0);
}

const findings = [];
const add = (check, msg, fix) => findings.push({ check, msg, fix });

const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const resolutions = pkg.resolutions || {};
const rationale = pkg.resolutionsRationale || {};

// A resolutions key may be a path glob ("**/@expo/xcpretty/js-yaml"); the pinned
// package is the last segment, scope included.
const pinnedName = (key) => {
  const parts = key.split("/");
  const last = parts[parts.length - 1];
  return parts.length > 1 && parts[parts.length - 2].startsWith("@")
    ? `${parts[parts.length - 2]}/${last}`
    : last;
};

// ---------------------------------------------------------------------------
// Walk node_modules once: who requests what, and at which versions is each
// package actually installed.
// ---------------------------------------------------------------------------
const requestedBy = new Map(); // name -> [{ range, from }]
const installed = new Map(); // name -> Set(version)

function walk(dir, depth) {
  if (depth > 6) return;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    if (!e.isDirectory() && !e.isSymbolicLink()) continue;
    const full = path.join(dir, e.name);
    if (e.name === "node_modules") {
      walk(full, depth + 1);
      continue;
    }
    if (e.name.startsWith("@")) {
      walk(full, depth);
      continue;
    }
    let m;
    try {
      m = JSON.parse(fs.readFileSync(path.join(full, "package.json"), "utf8"));
    } catch {
      continue;
    }
    if (m.name && m.version) {
      if (!installed.has(m.name)) installed.set(m.name, new Set());
      installed.get(m.name).add(m.version);
    }
    for (const [dep, range] of Object.entries(m.dependencies || {})) {
      if (!requestedBy.has(dep)) requestedBy.set(dep, []);
      requestedBy.get(dep).push({ range, from: `${m.name}@${m.version}` });
    }
    const nested = path.join(full, "node_modules");
    if (fs.existsSync(nested)) walk(nested, depth + 1);
  }
}
walk(path.join(ROOT, "node_modules"), 0);

// ---------------------------------------------------------------------------
// 1. Every pin states why it exists. A pin nobody can justify is a pin nobody
//    will know how to retire.
// ---------------------------------------------------------------------------
for (const key of Object.keys(resolutions)) {
  if (!rationale[key]) {
    add(
      "unjustified-pin",
      `resolutions["${key}"] has no entry in resolutionsRationale.`,
      "Record what advisory or deprecation it escapes, so the next person can tell whether it is still needed.",
    );
  }
}
for (const key of Object.keys(rationale)) {
  if (!resolutions[key]) {
    add("orphan-rationale", `resolutionsRationale["${key}"] describes a pin that no longer exists.`, "Delete the stale entry.");
  }
}

// ---------------------------------------------------------------------------
// 2. A pin that satisfies no declared range is a deliberate override — the thing
//    yarn prints "Resolution field ... is incompatible" about. Fine, but it has to
//    be a decision, not a leftover.
// ---------------------------------------------------------------------------
for (const [key, version] of Object.entries(resolutions)) {
  const name = pinnedName(key);
  const wants = requestedBy.get(name) || [];
  if (wants.length === 0) continue;
  const satisfied = wants.filter((w) => {
    try {
      return semver.satisfies(version, w.range, { includePrerelease: true });
    } catch {
      return false;
    }
  });
  if (satisfied.length === 0) {
    const ranges = [...new Set(wants.map((w) => w.range))].join(", ");
    const why = rationale[key] || "";
    if (!/deliberate override/i.test(why)) {
      add(
        "undeclared-override",
        `resolutions["${key}"] = ${version} satisfies none of the declared ranges (${ranges}). yarn warns about this on every install.`,
        'If the override is intended, say "deliberate override" in its rationale; otherwise pin a version inside the range.',
      );
    }
  }
}

// ---------------------------------------------------------------------------
// 3. Two copies of a direct dependency means the tree is resolving it twice, and
//    the copies can want incompatible versions of their own deps — which is how a
//    single global pin ends up satisfying neither of them.
// ---------------------------------------------------------------------------
const direct = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
for (const name of direct) {
  const versions = installed.get(name);
  if (versions && versions.size > 1) {
    add(
      "duplicate-dependency",
      `${name} is installed at ${[...versions].sort().join(" and ")}.`,
      "Align the declared version with what the other dependents ask for so the tree dedupes.",
    );
  }
}

// ---------------------------------------------------------------------------
// 4. A package.json or node_modules above the repo makes yarn validate a manifest
//    nobody owns, and puts packages nobody declared on Node's resolution path.
// ---------------------------------------------------------------------------
const repoRoot = (() => {
  const r = spawnSync("git", ["rev-parse", "--show-toplevel"], { cwd: ROOT, encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : ROOT;
})();
for (let dir = path.dirname(repoRoot); dir !== path.dirname(dir); dir = path.dirname(dir)) {
  const stray = path.join(dir, "package.json");
  if (fs.existsSync(stray)) {
    // yarn validates every manifest it finds walking up, and warns unless the
    // manifest opts out. Only flag the ones that will actually make it warn.
    let m = {};
    try {
      m = JSON.parse(fs.readFileSync(stray, "utf8"));
    } catch {}
    if (!m.private && !m.license) {
      add(
        "stray-ancestor",
        `${stray} sits above the repo root with no license and no "private": true.`,
        'yarn validates it on every install ("No license field"). Remove it, or set "private": true.',
      );
    }
  }
  const strayModules = path.join(dir, "node_modules");
  if (fs.existsSync(strayModules)) {
    add(
      "stray-ancestor",
      `${strayModules} sits above the repo root.`,
      "Node resolves modules from here whenever the project tree misses one, so an undeclared package can satisfy an import. Remove it unless something outside the repo needs it.",
    );
  }
}

// ---------------------------------------------------------------------------
// 4b. app.json is rewritten in place by tooling (eas-cli re-serialises the
//     *resolved* config, plugin contributions included). That is how RECORD_AUDIO
//     — added by expo-image-picker unless microphonePermission is false — once got
//     baked into the requested permissions of a finance app, duplicated, and listed
//     as blocked at the same time. Cheap to check, expensive to notice in review.
// ---------------------------------------------------------------------------
try {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "app.json"), "utf8")).expo || {};
  const android = manifest.android || {};
  const asked = android.permissions || [];
  const blocked = android.blockedPermissions || [];
  for (const [label, list] of [["permissions", asked], ["blockedPermissions", blocked]]) {
    const dupes = [...new Set(list.filter((x, i) => list.indexOf(x) !== i))];
    if (dupes.length) {
      add(
        "manifest-duplicate-permission",
        `app.json android.${label} lists ${dupes.join(", ")} more than once.`,
        "A tool rewrote the config in place. Deduplicate, and check what else that write changed.",
      );
    }
  }
  const both = asked.filter((x) => blocked.includes(x));
  if (both.length) {
    add(
      "manifest-contradictory-permission",
      `app.json both requests and blocks ${both.join(", ")}.`,
      "Configure the plugin that adds it (e.g. expo-image-picker's microphonePermission: false) instead of blocking it after the fact.",
    );
  }
} catch {
  // No app.json, or unparseable: not this check's business.
}

// ---------------------------------------------------------------------------
// 5. --audit: the check that would have caught today's failure. For every advisory
//    against a pinned package, the pin must land in the patched range.
// ---------------------------------------------------------------------------
if (AUDIT) {
  const res = spawnSync("yarn", ["audit", "--json"], { cwd: ROOT, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  const lines = (res.stdout || "").split("\n");
  const advisories = [];
  for (const line of lines) {
    let o;
    try {
      o = JSON.parse(line);
    } catch {
      continue;
    }
    if (o.type === "auditAdvisory") advisories.push(o.data.advisory);
  }
  if (advisories.length === 0 && res.status === null) {
    add("audit-unavailable", "`yarn audit` produced no parseable output.", "Run it directly to see why (network, registry auth).");
  }
  const pinnedNames = new Map(Object.entries(resolutions).map(([k, v]) => [pinnedName(k), { key: k, version: v }]));
  const seen = new Set();
  for (const a of advisories) {
    const pin = pinnedNames.get(a.module_name);
    if (!pin) continue;
    let vulnerable = false;
    try {
      vulnerable = semver.satisfies(pin.version, a.vulnerable_versions, { includePrerelease: true });
    } catch {
      continue;
    }
    const id = `${pin.key}|${a.patched_versions}`;
    if (!vulnerable || seen.has(id)) continue;
    seen.add(id);
    add(
      "stale-pin",
      `resolutions["${pin.key}"] = ${pin.version} is itself vulnerable (${a.severity}: ${a.title || a.module_name} ${a.vulnerable_versions}).`,
      `Raise the pin to ${a.patched_versions} — the pin exists to escape this, and no longer does.`,
    );
  }
}

// ---------------------------------------------------------------------------
if (findings.length === 0) {
  console.log(`deps-hygiene: clean${AUDIT ? " (pins checked against advisories)" : ""}.`);
  process.exit(0);
}
console.log("");
console.log(`deps-hygiene: ${findings.length} finding${findings.length === 1 ? "" : "s"}`);
for (const f of findings) {
  console.log("");
  console.log(`  [${f.check}] ${f.msg}`);
  console.log(`      -> ${f.fix}`);
}
console.log("");
process.exit(STRICT ? 1 : 0);
