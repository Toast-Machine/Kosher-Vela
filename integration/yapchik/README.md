# Yapchik integration

This directory is independent of `scripts/policy.py`. `scripts/variants.py` applies
the Kosher policy before Yapchik instrumentation when both features are selected.

## Components

- `vendor/yapchik`: pinned upstream library, license, notices, and our Gradle adapter.
  `vendor-lock.json` verifies upstream file digests before and after integration,
  using canonical LF text so Windows checkout conversion cannot invalidate CI hashes.
- `tools/KotlinSyntax.java`: Kotlin compiler PSI syntax/argument/lambda/loop discovery.
  `parser-lock.json` pins the compiler dependencies and verifies cached/downloaded jars.
- `runtime`: Compose action registration, current original handlers/presentation,
  clipped bounds, ownership, native-window suppression, softkeys, and Options UI.
- `tests`: pure JVM action-store tests, also copied into customized app unit tests.
- `compiler-fixtures`: type-checking regressions for transformed source, compiled
  with minimal annotation/scope stubs by the local and CI Kotlin validation script.

`scripts/yapchik.py` instruments supported Material controls and activation modifiers,
captures original text/icons/state without replaying content lambdas, and wraps repeated
and custom composable call sites with identity scopes. Separate composition instances
prevent duplicate logical item IDs from overwriting each other. Recognized unsupported
patterns generate a coverage report and fail closed; this is not semantic coverage of
arbitrary Kotlin or every possible future UI toolkit.

Only provably Unit-returning custom composables receive UI ownership/item wrappers.
Value-returning composables and expression bodies with unknown inferred return types
remain unchanged, so remembered state/focus objects retain their original values.

Known app adapters cover the Activity root, Search activation, persistent map ownership,
full-screen blocking content, and the settings entry. Partial sheets retain visible
map actions; native modal windows still suppress the app menu. Upstream changes to
these adapters require review.
Gesture-only controls and map-key redesign are excluded. Touch controls remain visible;
the future hide-buttons feature needs explicit layout-independent eligibility tests.

## Validation

For device key failures, manually dispatch the release workflow on the integration
branch with `key_diagnostics=true` and an existing upstream `release_tag`. It builds
only that tag and uploads a temporary signed APK/source artifact, without publishing
or changing release state. The APK logs non-printing key events and the resolved
Yapchik profile under `VelaYapchikKeys`; every event is delegated unchanged to Yapchik.
Normal builds disable this observer. Diagnostic provenance is rejected by the release
publication gate. Replace the diagnostic APK with a normal build after testing.

The Options binding opens the menu idempotently rather than toggling it. Some ROMs
emit both a vendor softkey and a synthetic MENU press for one physical press; both
are valid left-slot events in Yapchik's universal profile. Repeated open requests
must leave Options open. Back dismisses it. No phone-specific numeric key mapping
or replacement key handler is needed. A normal manual workflow run can set
`release_tag` to rebuild and publish one existing tag before rebuilding the backlog.
Normal builds also accept comma-separated tags to rebuild an explicit batch in one
workflow run; diagnostic builds remain limited to a single existing tag. Unknown,
duplicate, or empty batch tags fail planning before any builds or state changes.

Elevated assist/suggestion chips use the same live action instrumentation as their
non-elevated counterparts, including repeated category shortcuts. Parking uses a
PSI-validated adapter for its custom focusable keyboard/tap Box: Options captures
the existing `onOk` callback and original icon at the control site. Original tap,
long-press, and keyboard handlers remain unchanged. An unexpected Parking control
shape or activation fails coverage validation rather than guessing a new handler.

Options renders existing icon accessibility descriptions as visible text when an
entry has no text label. Text-labeled entries retain their original presentation;
unlabeled controls without descriptions receive no invented names. Rows merge
descendant semantics, and fallback labels are not duplicated on their icons.

Options is constrained to half the available width and three quarters of the height,
anchored at the bottom-start above system insets. The list scrolls and follows D-pad
focus. Icons and toggles keep their full size; a row is as tall as its tallest
full-size part, and its labels take the largest text size whose lines, wrapped only
at legal line breaks, fit that height. A long label therefore shrinks until a second
line fits, then wraps. Labels are never truncated; only a row whose icons alone exceed
the menu width scales uniformly.
The Softkeys entry uses the upstream Settings hub's own themed `HubRow`, inserted
directly after Appearance through a validated PSI anchor, with the hub's return-focus
modifier, a section title, and settings-search entries. It opens the existing
native Settings destination using the app's `SettingsScaffold`, `SettingsGroup`,
`SelectableRow`, and `GroupDivider`, with the same spacing as upstream pages.
Mode/profile changes and calibration use Yapchik's public APIs and persistence; a
changed insertion anchor, row-focus helper, or `SEARCH_INDEX` fails coverage validation.
Page, softkey, and Options text lives in `res/values*/yapchik_strings.xml`, copied
into the app beside upstream strings for every app language except Kurmanji, which
falls back to English. The calibration dialog belongs to the pinned library and stays English.

Vela's window theme is a framework theme, so Yapchik grows the bar by its nav guard to keep
labels above an on-screen navigation bar. The Softkeys page's "Navigation bar space" setting
(`runtime/NavBarSpace*.kt`, stored in `vela_settings`) drives the public `Yapchik.navGuardDp`: Off sets 0, On reserves
the declared navigation bar height, and Automatic (the default) keeps Yapchik's estimate only
when the phone has an on-screen navigation bar. On Android 11 and later that is the system's
navigation bar size ignoring visibility; earlier, a declared bar on a phone that is not
keypad-first. The choice is reapplied on every host composition.

Backups and device transfers carry Yapchik's own `yapchik.xml` preferences (mode, key
layout, calibrated keys) beside `vela_settings.xml`: the build adds it to every section of
`backup_rules.xml` and `data_extraction_rules.xml` and stops if their anchors change.
Calibrated keys belong to one phone; after restoring onto another model, recalibrate or
pick a built-in layout.

The bar reapplies the current Material theme to existing Yapchik views, because
the pinned library reads bar colors only at construction. Options intercepts
complete standard navigation/activation gestures at the window boundary before
underlying Compose controls see them, including releases after dismissal. Physical
softkeys remain owned by Yapchik and its selected device profile. Selection scrolls
only when a row falls outside the list viewport, not on every D-pad press.

Run from the automation repository with Python and Java/Javac 17 or newer:

```text
python -m unittest discover -s tests -v
python scripts/test_yapchik_runtime.py
python scripts/yapchik.py path/to/fresh/upstream
```

Use a fresh checkout per customization; instrumentation refuses reapplication. Compiler
and test jars are downloaded into ignored `.private` caches with SHA-256 verification.
Release CI runs `:app:testDebugUnitTest` and `:app:assembleRelease` for each variant.

Local runtime/library compilation and fresh-source instrumentation have passed. Complete
Android APK compilation and physical/emulated keypad acceptance remain outstanding;
parser validation alone is not a successful Android build. Test native windows,
sheet ownership, clipped/scrolled rows, key calibration, D-pad focus, lifecycle transitions,
and theme/insets on representative small displays before accepting the device behavior.
