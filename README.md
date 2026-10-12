# Kosher Vela

An automated, patch-only build of [PimpinPumpkin/Vela](https://github.com/PimpinPumpkin/Vela).
Each mirrored release produces one universal APK with both kashering and Yapchik:

| Build | Android application ID | Features |
| --- | --- | --- |
| Kosher | `app.vela.kosher` | Locked content settings and Yapchik hardware softkeys |

The updater selects only Kosher APKs. Existing Kosher installations retain their
application ID and signing key and gain Yapchik when updated. There are no standalone
Yapchik, Kosher-only, or separate combined-package releases. Feature transformations
remain independent internally.

## Yapchik integration

The [integration plan and implementation status](docs/yapchik-integration-plan.md)
describe the softkey/menu design. Yapchik builds bind left to Options and right to
Search when applicable, otherwise blank. Options references live UI handlers, keeps
text/icons and checked/disabled state, and excludes only the right-bound Search action.
Existing touch controls remain visible. Hardware mode and calibration are available
in Settings. Map-control changes and hiding on-screen buttons remain deferred.

Build-time Kotlin PSI instrumentation generates a coverage report and fails for
recognized unsupported controls. The vendored library and parser dependencies are
pinned with verified SHA-256 digests. See `integration/yapchik/README.md` for details.

## Locked settings

| Setting | Permanent value |
| --- | --- |
| Show reviews | Off |
| Read all reviews button | Off |
| Load photos | Off |
| Hide website & external links | On |

In the Kosher build, these four settings use immutable state, ignore stored preferences, and ignore attempts to
change them. Their controls are removed from Places, Privacy, onboarding and settings search.
The dependent "reviews on tap" and "photos on tap" options are also removed.

This enforces the existing upstream switches; it is not a complete content-filtering or
tamper-proof device-management system. Other upstream features are not silently disabled.

## Automatic releases

- GitHub Actions checks upstream every five minutes, at minutes 2, 7, 12, and so on.
  GitHub scheduling is best-effort, so checks and builds may be delayed.
- Release CI also runs on code/workflow pushes to `main` and `Yapchik`, and can be
  manually dispatched with `Yapchik` selected. State and keepalive commits target
  the run's branch, not hard-coded `main`; state-only pushes do not retrigger builds.
  Scheduled events still run only on GitHub's default branch. Push/manual runs let
  `Yapchik` build and publish without merging; they do not add a second cron scheduler.
- The one-time bootstrap queues **only the five newest published app releases**, including
  prereleases and canary. All older releases are permanently excluded in `.state/releases.json`.
- Every later poll visits **every page** of upstream releases. There is no five-release limit
  on future updates. Every new app release with an APK is eligible, whatever its tag or channel.
  Batches over 200 are processed in subsequent polls without dropping the remaining releases.
- Stable, nightly and canary builds retain their **exact upstream tags**, titles and prerelease
  status. Stable promotion updates metadata without rebuilding an unchanged APK.
- The rolling `canary` release is rebuilt when its source commit or APK changes. A canary
  replaced between polls cannot be recovered unless upstream preserves it separately.
- Map-data, voice-model and runtime-library releases are not app releases and are not mirrored.
  The app continues to download those resources from upstream.
- Builds use the upstream tag's exact commit and read the version name/code from its APK.
  The in-app APK updater points here, not to upstream Vela.
- Patches must apply cleanly. Static policy/instrumentation checks, Kotlin regression tests and APK identity /
  signature checks must pass before publication. Failed releases remain pending and retry
  after six hours, or immediately on a manual workflow run or a changed upstream build;
  successful releases are recorded independently even when another build fails.
- Builds run two at a time. All polling, builds, signing, publishing and state updates run on
  GitHub. No computer needs to remain on.
- If there have been no commits for 30 days, a scheduled run commits a small keepalive file
  to avoid GitHub's 60-day public-repository scheduled-workflow inactivity cutoff.

Each release includes one signed APK, `kosher-build.json` provenance, SHA-256
checksums, and a full patched-source archive including its runtime binaries.
The combined build must verify before publication; an incomplete replacement
remains draft. The source
archive is the customized app source; GitHub's automatic source downloads describe this
automation repository instead. Preserve the upstream GPL license and bundled license notices.

## Signing

The release workflow requires `VELA_KEYSTORE_BASE64` and `VELA_KEYSTORE_PASSWORD` repository
secrets, with key alias `kosher-vela`. It refuses to publish a debug-signed fallback.
Keep an offline backup of the signing key and password. Losing the key means existing
installations cannot accept updates signed with a replacement key.

## Operation

Use **Actions → Mirror Vela app releases → Run workflow** for an immediate check. This does
not reset the initial five-release boundary. Completed releases with an older build profile
are rebuilt once for the Kosher-with-Yapchik build profile; excluded historical releases stay
excluded. The workflow also
accepts `repository_dispatch` with type `upstream-release` if direct notifications are added
later; dispatch payloads are never trusted as source/build inputs.

Check failed runs in Actions if upstream refactors the patched settings or build dependencies.
Update the patch and rerun the workflow after reviewing those changes. Never delete/reset the
release state to fix a build, because it defines which historical releases are excluded.

Local automation tests: `python -m unittest discover -s tests -v`.
Pure Kotlin action-store tests (Java 17+): `python scripts/test_yapchik_runtime.py`.
Policy checks against a clean upstream checkout: `python scripts/policy.py path/to/source`.
Yapchik-only integration against a fresh checkout: `python scripts/yapchik.py path/to/source`.
Bootstrap is a one-time setup command and refuses to overwrite existing state.

## Source and license

Upstream: https://github.com/PimpinPumpkin/Vela. This repository and the customized app use
the GPL-3.0 license in `LICENSE`. See upstream source and bundled notices for dependency licenses.
