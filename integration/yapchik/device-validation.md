# Menu and theme device validation

Validated October 14, 2026 on the connected Sonim X320 using ADB.
The normal signed `app.vela.kosher` APK was installed with `adb install -r`,
without uninstalling or clearing application data.

- Release: `v0.5.2493`, version code `44930`.
- Automation source: `6b5e21910a6d78b33f9de76f5279a7c630a8c7f2`.
- Successful workflow: `38616420631`.
- APK SHA-256: `8b07b46762b1f1be763eec4fd0c0d7cc0658828a56df7f141c36a53ff3b9c8b8`.
- Downloaded APK hash and normal-build provenance matched before installation.
- 68 Python tests and 27 JVM tests passed; runtime/vendor Compose compilation passed.

## Phone results

- Switching Appearance between Dark and Light updates the existing softkey bar,
  including its background, divider and labels. AMOLED black also matched the app.
- With the underlying On setting highlighted, Options selected Off using CENTER.
  Off remained selected and the bar disappeared: the underlying On control did
  not activate. Automatic mode was restored after testing.
- With Central Park's place sheet open, Options included the visible Voice search,
  Settings and Layers actions above the sheet, alongside Save, Share, Close,
  Directions and Start. Selecting Layers from Options successfully opened the
  original map-layer popup; the native popup suppressed the softkey bar.
- D-pad selection moved through visible Options rows without moving the list.
  The list scrolled only when selection advanced past its viewport.
- Yapchik opened as a native Settings page below Appearance, with the same
  scaffold, groups, radio rows and typography in both Light and Dark themes.
- The running application's crash buffer contained no entries after testing.

Evidence screenshots are retained locally under `.private/fixed-v8/` rather than
committed, because map/search screens can contain personal information.
The original Day and night appearance and Automatic softkey mode were restored.
