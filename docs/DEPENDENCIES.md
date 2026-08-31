# Dependency pins and install warnings

## What went wrong

Every entry in `frontend/package.json` → `resolutions` was added to escape a
specific advisory. Nothing re-checked those pins afterwards, so each one drifted
below the version that fixed the thing it was added for:

| pin | was | patched at | status when found |
| --- | --- | --- | --- |
| `postcss` | 8.5.10 | >= 8.5.23 | vulnerable |
| `undici` | 6.27.0 | >= 6.28.0 | vulnerable |
| `tar` | 7.5.19 | >= 7.5.21 | vulnerable |
| `js-yaml` (v4) | 4.3.0 | >= 4.3.1 | vulnerable |
| `js-yaml` (v3) | 3.15.0 | >= 3.15.1 | vulnerable |

The block still looked like protection. It was not: 62 high + 5 moderate
advisories, down to 52 high + 0 moderate once the pins were repaired.

Separately, `@eslint/plugin-kit` was pinned to `0.3.4` while two copies of eslint
in the tree asked for `^0.2.8` and `^0.4.1` — a pin satisfying neither. The root
cause was the duplicate eslint, not the pin; declaring `eslint@9.39.4` (inside
what `eslint-config-expo` and `eslint-plugin-expo` both accept) deduped the tree
and the pin became unnecessary.

## The rules

1. **Every pin states why it exists.** `resolutionsRationale` mirrors
   `resolutions` key for key. A pin nobody can justify is a pin nobody will know
   how to retire.
2. **Pin to the newest version inside the declared range.** A pin that lands in
   range fixes the advisory *and* stays silent. Only override a range when no
   in-range version is patched.
3. **A deliberate override says so.** yarn prints
   `Resolution field ... is incompatible` on every install for an out-of-range
   pin and offers no way to suppress it, so the rationale must contain the words
   `deliberate override`. That turns a permanent warning into a recorded
   decision.

## The check

`frontend/scripts/deps-hygiene.js` enforces the rules and runs from `postinstall`
in warn mode, so drift surfaces on every install without ever breaking one.

```
yarn deps:check     # offline, exits 1 on any finding
yarn deps:audit     # also cross-checks every pin against live advisories
```

It reports: pins with no rationale, out-of-range pins not declared as deliberate,
pins that no longer clear their own advisory (`--audit`), a direct dependency
installed at two versions, and stray `package.json` / `node_modules` above the
repo root.

Run `yarn deps:audit` when touching `resolutions`, and periodically — advisories
move, pins do not.

## Accepted exceptions

Two overrides are deliberate, and their warnings are expected on every install:

- **postcss** — every 8.4.x is vulnerable, and `@expo/metro-config` declares
  `~8.4.32`. Being safe requires leaving the range.
- **uuid** — `xcode@3.0.1` declares `^7.0.3`, a line npm marks unsupported. It
  calls only `uuid.v4()`, which v11 still exports.

## Not fixable from this repo

`DeprecationWarning: url.parse()` (DEP0169) comes from yarn 1.22.22 itself — 15
call sites in its own bundle — and fires before any project code runs. Yarn 1 is
in maintenance and will not be patched, so the only real fixes are moving to a
current package manager or pinning an older Node. To silence just that code for
one command, without hiding any other deprecation:

```
NODE_OPTIONS=--disable-warning=DEP0169 yarn install
```
