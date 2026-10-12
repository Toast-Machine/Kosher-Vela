# Yapchik integration plan

Status: implemented on the `Yapchik` branch; the signed `v0.5.2493` APK from
`0b16b49` passed CI and Options device regression checks on a Sonim X320.
The design below is retained as the acceptance contract.

## Implementation status

- `scripts/yapchik.py` instruments customized source through Kotlin compiler PSI 2.1.20,
  validates generated syntax before replacing files, and writes `yapchik-coverage.json`.
  Recognized unsupported patterns fail the build for review.
- `integration/yapchik/runtime` supplies lifecycle-aware action references, original-site
  callback/state capture, live clipped bounds, ownership, and the themed D-pad Options
  overlay. Native Dialog/Popup windows suppress underlying bindings.
- Yapchik revision `bf5021c648ae6adff60644a7cf2633c938d70ead` is vendored with its
  license/notices and digest lock, independently of the Kosher policy.
- Repeated lazy/list/for-loop controls include item scopes and separate composition
  instance identities, including duplicate item IDs. Custom composable call sites
  also contribute scopes. Multiple activations sharing a control require adapter review.
- `scripts/variants.py` supports neither/either/both features internally. Releases build
  only Kosher with Yapchik (`app.vela.kosher`) from an isolated exact-commit tree,
  run app unit tests, and verify package/version/signature. Standalone Yapchik,
  Kosher-only, and separate combined-package releases have been removed; existing
  Kosher installations gain Yapchik in place. Release CI supports pushes and manual
  dispatch on `Yapchik`, with branch-specific state and keepalive updates.
- Local checks cover parser fixtures, variants, updater isolation, publication
  prerequisites, and Kotlin action-store behavior. Runtime plus vendored library compile
  against real Android/Compose artifacts. Fresh upstream integration instruments 347
  controls in the combined build with no recognized unsupported cases.
- Full Android Gradle/APK compilation and publication passed in GitHub Actions run
  `38197530960`; the Android SDK is not installed locally. Device checks verified
  vendor and standard left softkeys, repeated Options activation, on-screen Options,
  D-pad focus and Settings activation, Back dismissal, and right-softkey Search.
  The installed APK checksum matched publication provenance, diagnostics were off,
  and the tested process produced no crash entries. Broader multi-device insets,
  calibration, and focus acceptance remain outside these regression checks.
- Elevated category chips retain their current callbacks and presentation. Device
  selection of Restaurants, Coffee, and Gas from Options opened the corresponding
  search results. Parking's custom keyboard/tap control uses a validated adapter
  capturing its original `onOk` callback; its P icon appears and receives D-pad
  focus in Options. Parking activation was not exercised to avoid saving a test
  parking location. Original tap/long-press/key handlers remain unchanged, and a
  changed adapter shape fails build-time validation.
- The follow-up accessibility labeling change passed 60 Python and 21 Kotlin tests,
  real Compose compilation, and the signed release build. Device checks confirmed
  existing descriptions display as labels in Map and Settings Options, including
  Save parking spot, Center on my location, and Back. Existing category text remains
  unchanged; D-pad scrolling and Settings activation passed without crash entries.

Options uses an idempotent open command because a device can emit multiple Yapchik
key aliases for one softkey press. Yapchik still owns profile resolution and dispatch;
the application does not add device-specific key handlers. Options list saveable keys
are stable `Long` values; action identity and dispatch retain the original identities.

The actual hide-buttons option and map-control changes remain deferred.

## Agreed behavior

Add hardware softkeys and a live Options menu to the main screen and its relevant
panels. Entries reference existing UI actions, not a separate command catalog.

| Softkey | Binding |
| --- | --- |
| Left | Options |
| Right | Search when applicable; otherwise blank and unbound |

Options includes all eligible control actions **except the Search action assigned
to the right softkey**. Do not duplicate that action in Options. Options never moves
to the right. Other distinct search actions are not excluded merely by their name.
Search invokes the original control's current handler.

Keep existing on-screen controls initially. Per the follow-up labeling request,
icon-only menu entries display their existing nonblank accessibility descriptions
as text labels. Existing text labels take precedence; descriptions are not invented
where none exist, and a description rendered as text is not repeated on its icon.
Options is a bottom-start panel capped at half the available screen width and
height, excluding system insets. Overflowing lists scroll; each overly wide option
scales its complete icon/text/toggle presentation uniformly to fit without
truncating labels. Outside taps and Back dismiss the panel. The Yapchik settings
entry reuses the native Settings hub row and appears immediately below Appearance.
Text controls retain text; controls with both retain both. Non-interactive text,
images, and decorations are not actions.

Map movement, zoom modes, crosshair selection, and related key changes are deferred
to another task. Gesture-only actions are outside this initial button/click scope.

## Independence from kashering

Keep the library, application bridge, instrumentation, configuration, and tests
separate from kashering. Neither feature may depend on the other.

Support applying neither feature, Yapchik only, kashering only, or both. This is
feature modularity. The revised implementation request specifies only `app.vela.kosher`
with both features, retaining the existing signing key and Kosher updater asset prefix.
When both are selected, apply existing customization patches first and
instrument the resulting source. Use a separate integration entry point called by
the build orchestrator, not transformations inside `scripts/policy.py`.

## Build-time instrumentation

On every app build:

1. Check out the exact upstream release source.
2. Apply independently selected customization features.
3. Add pinned Yapchik and our runtime when selected.
4. Instrument relevant UI source and validate coverage.
5. Compile, test, and build before publication.

Use syntax-aware Kotlin processing with import/symbol resolution as needed, not
regular-expression rewriting or patches tied to button names or line numbers.
Validate the precise parser/tooling choice during the prototype.

Recognize standard buttons, icon/floating buttons, clickable surfaces,
`clickable`/`combinedClickable`, and supported toggle/select controls. Process
supporting components, not just the main screen function. Instrument an action
once, not both its custom component and inner control.

New upstream controls using supported mechanisms should participate automatically.
Preserve handlers, conditions, enabled states, modifiers, and layout. Do not simulate
coordinate taps or reconstruct business logic. Custom input/presentation patterns
may need adapters.

Report discovered, instrumented, excluded, and unsupported cases. Unresolved or
unsupported cases in scope stop the build for review rather than generate guessed
entries. Static discovery cannot guarantee detection of arbitrary future input code.

## Runtime references and presentation

Each registered control supplies:

- An instance identity and owning screen/window/overlay scope.
- Current text/icon values and accessibility description.
- Enabled and selected/checked state, where applicable.
- Its original, current activation handler.
- Bounds, clipping/viewport information, and eligibility state.

The button and menu use the same handler. Update registrations after successful
composition and remove them when owners leave. Proposed Compose plumbing uses
`DisposableEffect` for cleanup, `SideEffect` for updates, and
`rememberUpdatedState` for current callbacks. Do not mutate the registry directly
during composition.

Repeated controls get separate identities, using stable data-item IDs where
available rather than labels or list positions. Menu focus follows identity when
entries change; a reference must never switch silently to a different item.

Capture supported visual values, not an arbitrary original content function that
could repeat stateful UI or registration inside the menu. Prove automatic text/icon
capture with real upstream components before claiming complete coverage.

## Visibility and ownership

Normally, include only actionable controls currently visible on the active
screen/panel. Being composed or registered is insufficient.

- Exclude off-screen list items, fully clipped controls, inactive screens, and
  controls behind blocking overlays.
- Keep disabled controls as disabled entries that cannot invoke their handler.
- Remove actions when their normal applicability conditions become false.
- Do not include every backing-list item or every possible source action.

Central screen/dialog infrastructure assigns ownership scopes. Blocking surfaces
deactivate underlying scopes even when their content remains composed. Bounds alone
cannot detect arbitrary visual occlusion; do not promise pixel-level occlusion detection.

Opening our Options menu preserves the eligible underlying actions. Its rows and
the softkey bar never register themselves. Other dialogs need validated local
bindings or suppression of the underlying bar, never covered map actions.

## Future hide-on-screen-buttons option

Prepare for this option, but do not implement or enable it in the initial task.
Separate normal action eligibility from drawing the original button.

| Reason a control is absent visually | Menu behavior |
| --- | --- |
| Hidden specifically by our future hide-buttons option | Retain its otherwise eligible action |
| Not applicable in the current state | Exclude |
| Off-screen, inactive, or behind a blocking surface | Exclude |

Register outside the presentation-only hide condition, but inside normal
applicability/ownership conditions. Hiding presentation must not remove handlers,
icons/text, or the right-softkey Search binding. Search remains excluded from
Options while assigned to the right, whether its on-screen control is drawn or not.

This is an explicit exception to the normal "currently visible" rule, not permission
to expose arbitrary upstream-hidden controls. Hiding controls can change layout;
vanished bounds cannot be the option's sole eligibility signal. The future task must
define and test layout-independent eligibility or retained layout anchors before
enabling hiding. Separate registration from presentation now to support that work.

## Yapchik bridge and Options UI

Vendor a pinned Yapchik revision as a separately replaceable module, retaining its
license and notices. Initialize once and use Vela's keypad-device detection for
automatic activation. Provide enable/disable and key calibration. Follow the app
theme, reserve bar space, and validate insets on small screens. Preserve ordinary
touch behavior when softkeys are inactive.

Borrow AllTechDev's initialization, current-callback, theme, and lifecycle patterns,
not his hard-coded action menus, prompt-specific bindings, or button decluttering.

Build a scrollable menu from eligible references. Use clear D-pad focus styling,
up/down traversal, OK activation, and Back dismissal. Order approximately
top-to-bottom then left-to-right; preserve focus by identity with a deterministic
fallback when an entry disappears.

At activation, revalidate the live reference and enabled state, dismiss Options,
and invoke the current original handler exactly once. Dispatch must remain safe
if dismissal changes composition or focus. Search uses the same validation path.
Clear bindings on inactive screens. Do not add movement/zoom mode commands.

## Milestones and acceptance tests

First prove one text button, one icon button, one modifier-based clickable control,
and a repeated list item end-to-end. Then extend main-screen coverage and integrate
with automatic builds. Parser choice, presentation capture, and visibility handling
are prototype work, not already proven implementation details.

Required validation:

- Left is Options; right is Search when applicable, otherwise blank and unbound.
- Right-bound Search is absent from Options; other eligible actions are represented
  without duplicate registration.
- Original-button and menu activation use the same handler exactly once.
- Text/icons, checked/disabled states, and callbacks update with current state.
- Scrolling, clipping, list reorder/removal, overlays, and screen transitions preserve
  identities and exclude unavailable controls.
- Opening Options retains underlying entries and does not register menu rows.
- A synthetic supported upstream control addition is included automatically; a
  recognized unsupported pattern produces a reviewable build failure.
- Yapchik and kashering can be applied independently and together.
- Registration is structurally independent of drawing controls. The actual future
  hide-buttons option also needs separate visibility/layout tests.
- Key profiles, calibration, theme/insets, and focus work on representative small
  keypad displays, with ordinary touch behavior preserved when inactive.

Handle upstream tooling/library changes and newly unsupported mechanisms when
encountered. Do not promise maintenance-free support for arbitrary future source.
The implementation changes customization and release workflows. Published APKs require
the release workflow to pass; local source/parser validation does not publish builds.

## Design references

- Yapchik: https://github.com/theOnionsAreWatching/yapchik
- AllTechDev integration: https://github.com/alltechdev/vela-dpad
- Fork integration notes: `docs/softkeys.md` in that repository.
- Fork bridge: `app/src/main/java/app/vela/ui/softkey/VelaSoftkeys.kt`.
- Fork contextual bindings/menus: `app/src/main/java/app/vela/ui/map/MapScreen.kt`.

These are references, not instructions to adopt the fork wholesale.
