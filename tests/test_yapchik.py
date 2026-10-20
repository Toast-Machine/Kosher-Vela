import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kotlin_source import INTEGRATION, parse
from yapchik import configure_diagnostics, edits_for_file, include_yapchik_backup, instrument, ui_composables, vendor_digest, verify_vendor


class InstrumentationTests(unittest.TestCase):
    fixtures = {
        "value_composables": (INTEGRATION / "compiler-fixtures/ValueComposables.kt").read_text(encoding="utf-8"),
        "named_window": '''package fixture
import androidx.compose.ui.window.Dialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(callback: () -> Unit) {
    Dialog(onDismissRequest = callback, content = {
        Button(onClick = callback) { Text("Close") }
    })
}
''',
        "loop": '''package fixture
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(values: List<String>, callback: (String) -> Unit) {
    for (value in values) {
        if (value.isEmpty()) continue
        Button(onClick = { callback(value) }) { Text(value) }
    }
}
''',
        "buttons": '''package fixture
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(enabled: Boolean, callback: () -> Unit) {
    Button(onClick = callback, enabled = enabled) { Text("Run") }
}
''',
        "icon": '''package fixture
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
@Composable fun Screen(icon: ImageVector, callback: () -> Unit) {
    IconButton(onClick = callback) { Icon(icon, contentDescription = "Details") }
}
''',
        "modifier": '''package fixture
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(callback: () -> Unit) {
    Row(Modifier.clickable { callback() }) { Text("Run") }
}
''',
        "repeated": '''package fixture
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(values: List<Item>, callback: (Item) -> Unit) {
    LazyColumn { items(values, key = { it.id }) { item ->
        Button(onClick = { callback(item) }) { Text(item.name) }
    } }
}
''',
        "alias": '''package fixture
import androidx.compose.material3.Button as ActionButton
import androidx.compose.material3.Text as Label
import androidx.compose.runtime.Composable
@Composable fun Screen(callback: () -> Unit) {
    ActionButton(onClick = callback) { Label("Hello 👋") }
}
''',
        "toggle": '''package fixture
import androidx.compose.material3.Checkbox
import androidx.compose.runtime.Composable
@Composable fun Screen(checked: Boolean, callback: (Boolean) -> Unit) {
    Checkbox(checked = checked, onCheckedChange = callback)
}
''',
        "unsupported": '''package fixture
import androidx.compose.foundation.selection.triStateToggleable
import androidx.compose.foundation.layout.Row
import androidx.compose.runtime.Composable
@Composable fun Screen(callback: () -> Unit) {
    Row(Modifier.triStateToggleable(state = state, onClick = callback)) {}
}
''',
        "conditional": '''package fixture
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(active: Boolean, callback: (() -> Unit)?) {
    Row(Modifier.then(if (active) Modifier.clickable(onClick = callback!!) else Modifier)) { Text("Run") }
}
''',
        "window": '''package fixture
import androidx.compose.ui.window.Dialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(callback: () -> Unit) {
    Dialog(onDismissRequest = callback) { Button(onClick = callback) { Text("Close") } }
}
''',
    }

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.paths = {}
        for name, source in cls.fixtures.items():
            path = Path(cls.directory.name) / (name + ".kt")
            path.write_text(source, encoding="utf-8")
            cls.paths[name] = path
        cls.syntax = {Path(value["path"]).stem: value for value in parse(cls.paths.values())}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def transformed(self, name):
        result, report = edits_for_file(self.syntax[name])
        self.assertEqual([], report["unsupported"])
        return result.decode("utf-8"), report

    def test_named_native_window_content_suppresses_underlying_actions(self):
        source, report = self.transformed("named_window")
        self.assertIn('content = {', source)
        self.assertIn('YapchikScope(blocking = true, suppress = true)', source)

    def test_yapchik_settings_reuses_native_row_below_appearance(self):
        source = '''package app.vela.ui.settings
import androidx.compose.runtime.Composable
@Composable fun SettingsHub() {
    val sectionTitles = mapOf(
        SettingsSection.APPEARANCE to stringResource(R.string.settings_appearance),
        SettingsSection.MAP to stringResource(R.string.settings_map),
    )
    @Composable
    fun rowModifier(section: SettingsSection, first: Boolean): Modifier {
        return Modifier
    }
    HubRow(title = stringResource(R.string.settings_appearance), onClick = {})
    HubRow(title = stringResource(R.string.settings_map), onClick = {})
}
@Composable private fun HubRow(title: String, onClick: () -> Unit) {}
private val SEARCH_INDEX: List<Pair<Int, SettingsSection>> = listOf(
    // Appearance
    R.string.settings_theme_light to SettingsSection.APPEARANCE,
    R.string.settings_units to SettingsSection.APPEARANCE,
)
'''
        path = Path(self.directory.name) / 'SettingsHub.kt'
        path.write_text(source, encoding='utf-8')
        report = instrument([path], Path(self.directory.name) / 'settings-placement.json')
        transformed = path.read_text(encoding='utf-8')
        self.assertEqual([], report['unsupported'])
        row = transformed.index('HubRow(icon = YapchikDialpad')
        self.assertLess(transformed.index('HubRow(title = stringResource(R.string.settings_appearance)'), row)
        self.assertLess(row, transformed.index('HubRow(title = stringResource(R.string.settings_map)'))
        self.assertIn('title = stringResource(R.string.yapchik_settings_title)', transformed)
        self.assertIn('modifier = rowModifier(SettingsSection.YAPCHIK, first = false)', transformed)
        self.assertIn('onOpen(SettingsSection.YAPCHIK, null)', transformed)
        self.assertIn('SettingsSection.YAPCHIK to stringResource(R.string.yapchik_settings_title),', transformed)
        index = transformed[transformed.index('SEARCH_INDEX'):]
        for key in ('yapchik_softkey_bar', 'yapchik_mode_auto', 'yapchik_nav_space', 'yapchik_key_layout', 'yapchik_profile_custom'):
            self.assertIn(f'R.string.{key} to SettingsSection.YAPCHIK,', index)
        self.assertNotIn('YapchikPreferences()', transformed)

    def test_changed_settings_hub_fails_closed(self):
        path = Path(self.directory.name) / 'SettingsHub.kt'
        path.write_text('package app.vela.ui.settings\nfun SettingsHub() {}', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'requiring review'):
            instrument([path], Path(self.directory.name) / 'settings-changed.json')

    def test_settings_hub_without_search_index_fails_closed(self):
        source = '''package app.vela.ui.settings
import androidx.compose.runtime.Composable
@Composable fun SettingsHub() {
    val sectionTitles = mapOf(SettingsSection.APPEARANCE to stringResource(R.string.settings_appearance),)
    @Composable
    fun rowModifier(section: SettingsSection, first: Boolean): Modifier = Modifier
    HubRow(title = stringResource(R.string.settings_appearance), onClick = {})
}
@Composable private fun HubRow(title: String, onClick: () -> Unit) {}
'''
        path = Path(self.directory.name) / 'SettingsHub.kt'
        path.write_text(source, encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'requiring review'):
            instrument([path], Path(self.directory.name) / 'settings-no-index.json')

    def test_yapchik_strings_match_across_locales(self):
        import xml.etree.ElementTree as ElementTree
        files = sorted((INTEGRATION / 'res').glob('values*/yapchik_strings.xml'))
        self.assertIn('values', [path.parent.name for path in files])
        def strings(path):
            return {node.get('name'): node.text for node in ElementTree.parse(path).getroot()}
        english = strings(INTEGRATION / 'res/values/yapchik_strings.xml')
        settings = (INTEGRATION / 'settings/YapchikSettings.kt').read_text(encoding='utf-8')
        runtime = (INTEGRATION / 'runtime/YapchikRuntime.kt').read_text(encoding='utf-8')
        for name in english:
            self.assertTrue(f'R.string.{name}' in settings + runtime or name == 'yapchik_settings_sub', name)
        for path in files:
            translated = strings(path)
            self.assertEqual(set(english), set(translated), path.parent.name)
            for name, value in translated.items():
                self.assertEqual(re.findall(r'%\d\$s', english[name]), re.findall(r'%\d\$s', value), (path.parent.name, name))
                self.assertNotIn('—', value)

    def test_partial_sheet_does_not_hide_visible_map_controls(self):
        source = '''package fixture
import androidx.compose.runtime.Composable
@Composable fun Screen() { PlaceSheet(); FullScreenReviewsContent() }
@Composable fun PlaceSheet() {}
@Composable fun FullScreenReviewsContent() {}
'''
        path = Path(self.directory.name) / 'PartialSheet.kt'
        path.write_text(source, encoding='utf-8')
        instrument([path], Path(self.directory.name) / 'partial-sheet.json')
        transformed = path.read_text(encoding='utf-8')
        self.assertEqual(1, transformed.count('YapchikScope(blocking = true)'))
        self.assertLess(transformed.index('PlaceSheet()'), transformed.index('YapchikScope(blocking = true)'))
        self.assertLess(transformed.index('YapchikScope(blocking = true)'), transformed.index('FullScreenReviewsContent()'))

    def test_yapchik_settings_has_native_navigation_destination(self):
        routes = Path(self.directory.name) / 'SettingsRoutes.kt'
        screen = Path(self.directory.name) / 'SettingsScreen.kt'
        routes.write_text('package fixture\nenum class SettingsSection { HUB, APPEARANCE, MAP }', encoding='utf-8')
        screen.write_text('package fixture\nfun screen(section: SettingsSection) { when(section) { SettingsSection.APPEARANCE -> appearance(); else -> hub() } }', encoding='utf-8')
        instrument([routes, screen], Path(self.directory.name) / 'settings-route.json')
        self.assertIn('HUB, APPEARANCE, YAPCHIK,', routes.read_text(encoding='utf-8'))
        self.assertIn('SettingsSection.YAPCHIK -> YapchikSettingsScreen(onBack = toHub)', screen.read_text(encoding='utf-8'))

    def test_options_dimensions_and_overflow_remain_bounded(self):
        source = (INTEGRATION / 'runtime/YapchikRuntime.kt').read_text(encoding='utf-8')
        self.assertIn('.width(maxWidth / 2).heightIn(max = maxHeight * 3 / 4)', source)
        self.assertIn('Modifier.weight(1f, fill = false)', source)
        self.assertIn('MenuEntry(menuPresentation(reference.presentation))', source)
        self.assertNotIn('ScaleToMenuWidth', source)
        menu_entry = source[source.index('private fun MenuEntry('):source.index('private fun applyBarTheme(')]
        self.assertIn('subcompose(index) { fixed(visual) }.firstOrNull()?.let {\n                fixedParts[index] = it.measure(Constraints())', menu_entry)
        self.assertIn('segments[i] * scale <= widths[i]', menu_entry)
        self.assertIn('.size.height <= height', menu_entry)
        self.assertIn('Text(label.second, style = textStyle)', menu_entry)
        self.assertIn('menuContentScale(rowWidth, constraints.maxWidth)', menu_entry)
        self.assertIn('part.placeRelativeWithLayer', menu_entry)

    def test_options_scrolls_down_one_row_at_a_time(self):
        source = (INTEGRATION / 'runtime/YapchikRuntime.kt').read_text(encoding='utf-8')
        self.assertIn('index == rows.last().index + 1 ->', source)
        self.assertIn('scroll.scrollBy((visible.offset + visible.size - layout.viewportEndOffset).toFloat())', source)
        self.assertNotIn('scroll.scrollToItem(layout.visibleItemsInfo.first().index', source)

    def test_yapchik_preferences_join_every_backup_section(self):
        rules = Path(self.directory.name) / 'app/src/main/res/xml'
        rules.mkdir(parents=True)
        anchor = '        <include domain="sharedpref" path="vela_settings.xml" />'
        (rules / 'backup_rules.xml').write_text(
            '\n'.join(['<full-backup-content>', anchor, '</full-backup-content>', '']), encoding='utf-8')
        (rules / 'data_extraction_rules.xml').write_text('\n'.join([
            '<data-extraction-rules>', '<cloud-backup>', anchor, '</cloud-backup>',
            '<device-transfer>', anchor, '</device-transfer>', '</data-extraction-rules>', '']), encoding='utf-8')
        include_yapchik_backup(Path(self.directory.name))
        include = '        <include domain="sharedpref" path="yapchik.xml" />'
        self.assertEqual(1, (rules / 'backup_rules.xml').read_text(encoding='utf-8').count(include))
        self.assertEqual(2, (rules / 'data_extraction_rules.xml').read_text(encoding='utf-8').count(include))
        with self.assertRaisesRegex(RuntimeError, 'backup rules changed'):
            include_yapchik_backup(Path(self.directory.name))

    def test_navigation_bar_space_is_kept_in_backed_up_settings(self):
        source = (INTEGRATION / 'runtime/NavBarSpaceSetting.kt').read_text(encoding='utf-8')
        self.assertIn('private const val FILE = "vela_settings"', source)

    def test_navigation_bar_space_setting_defaults_to_automatic_and_is_applied(self):
        settings = (INTEGRATION / 'settings/YapchikSettings.kt').read_text(encoding='utf-8')
        runtime = (INTEGRATION / 'runtime/YapchikRuntime.kt').read_text(encoding='utf-8')
        self.assertIn('listOf(NavBarSpace.AUTO, NavBarSpace.OFF, NavBarSpace.ON)', settings)
        self.assertIn('NavBarSpaceSetting.set(activity, choice)', settings)
        self.assertIn('NavBarSpaceSetting.apply(activity)', runtime)

    def test_value_returning_composables_keep_their_values_in_both_repeat_forms(self):
        source, report = self.transformed("value_composables")
        for assignment in ('val remembered = rememberDpadFocusKeeper()',
                           'val explicit = KeeperFactory()', 'val inferred = InferredKeeperFactory()'):
            self.assertEqual(2, source.count(assignment))
        self.assertIn('YapchikItem', source)
        self.assertIn(' { KeeperRow(remembered)', source)
        self.assertIn(' { ExplicitUnitRow(explicit)', source)

    def test_ui_scope_candidates_require_a_unit_return_type(self):
        candidates = ui_composables([self.syntax["value_composables"]])
        self.assertIn('fixture.KeeperRow', candidates)
        self.assertIn('fixture.ExplicitUnitRow', candidates)
        self.assertNotIn('fixture.rememberDpadFocusKeeper', candidates)
        self.assertNotIn('fixture.KeeperFactory', candidates)
        self.assertNotIn('fixture.InferredKeeperFactory', candidates)

    def test_empty_cross_file_ui_candidates_do_not_fall_back_to_local_symbols(self):
        source, report = edits_for_file(self.syntax["value_composables"], set())
        self.assertNotIn(b'YapchikItem', source)

    def test_multiple_activations_on_one_control_fail_for_review(self):
        source = self.fixtures["modifier"].replace('import androidx.compose.foundation.clickable',
            'import androidx.compose.foundation.clickable\nimport androidx.compose.foundation.combinedClickable')
        source = source.replace('Modifier.clickable { callback() }',
            'Modifier.clickable { callback() }.combinedClickable(onClick = callback)')
        path = Path(self.directory.name) / 'multiple-activations.kt'
        path.write_text(source, encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'requiring review'):
            instrument([path], Path(self.directory.name) / 'multiple-coverage.json')
        self.assertEqual(source, path.read_text(encoding='utf-8'))

    def test_for_loop_controls_capture_item_without_wrapping_continue(self):
        source, report = self.transformed("loop")
        self.assertIn('YapchikItem("fixture.loop:loop:', source)
        self.assertIn(', value) { ', source)
        self.assertLess(source.index('continue'), source.index('YapchikItem'))
        self.assertEqual(1, len(report["instrumented"]))

    def test_text_button_uses_live_original_handler_once(self):
        source, report = self.transformed("buttons")
        self.assertEqual(1, len(report["instrumented"]))
        self.assertIn('.bind(callback)', source)
        self.assertEqual(1, source.count('.bind(callback)'))
        self.assertIn('.trackEnabled(enabled)', source)
        self.assertIn('YapchikText("Run")', source)
        self.assertNotIn('YapchikAction("fixture.buttons:6:', source.split('callback: () -> Unit)')[0])

    def test_elevated_chips_keep_handlers_enabled_state_and_presentation(self):
        source = '''package fixture
import androidx.compose.material3.ElevatedAssistChip
import androidx.compose.material3.ElevatedSuggestionChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
@Composable fun Screen(callback: () -> Unit, enabled: Boolean) {
    ElevatedAssistChip(onClick = callback, label = { Text("Restaurants") }, enabled = enabled)
    ElevatedSuggestionChip(callback, { Text("Coffee") }, Modifier, enabled)
}
'''
        path = Path(self.directory.name) / 'ElevatedChips.kt'
        path.write_text(source, encoding='utf-8')
        report = instrument([path], Path(self.directory.name) / 'chips-coverage.json')
        transformed = path.read_text(encoding='utf-8')
        self.assertEqual(2, len(report['instrumented']))
        self.assertEqual(2, transformed.count('.bind(callback)'))
        self.assertEqual(2, transformed.count('.trackEnabled(enabled)'))
        self.assertEqual(2, transformed.count('.modifier'))
        self.assertIn('YapchikText("Restaurants")', transformed)
        self.assertIn('YapchikText("Coffee")', transformed)

    def parking_source(self):
        return '''package app.vela.ui.map
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
@Composable private fun ParkingControl(onOk: () -> Unit, onTap: () -> Unit, history: () -> Unit) {
    Box(Modifier.size(48.dp).onKeyEvent { ev ->
        if (ev.type == KeyUp) { onOk(); true } else false
    }.focusable().pointerInput(Unit) {
        detectTapGestures(onTap = { onTap() }, onLongPress = { history() })
    }) { Icon(Sym.LocalParking, contentDescription = "Save parking") }
}
'''

    def test_parking_adapter_captures_original_keyboard_callback_and_keeps_gestures(self):
        path = Path(self.directory.name) / 'MapScreen.kt'
        path.write_text(self.parking_source(), encoding='utf-8')
        report = instrument([path], Path(self.directory.name) / 'parking-coverage.json')
        transformed = path.read_text(encoding='utf-8')
        self.assertEqual(1, len(report['instrumented']))
        self.assertIn(', onOk) { yapchikAction', transformed)
        self.assertIn('.then(yapchikAction', transformed)
        self.assertIn('if (ev.type == KeyUp) { onOk(); true } else false', transformed)
        self.assertIn('detectTapGestures(onTap = { onTap() }, onLongPress = { history() })', transformed)
        self.assertIn('YapchikIcon(Sym.LocalParking, "Save parking")', transformed)
        self.assertNotIn('.bind(', transformed)

    def test_changed_parking_activation_fails_closed_without_writing_source(self):
        source = self.parking_source().replace('onOk(); true', 'differentCallback(); true')
        path = Path(self.directory.name) / 'MapScreen.kt'
        path.write_text(source, encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'requiring review'):
            instrument([path], Path(self.directory.name) / 'parking-changed.json')
        self.assertEqual(source, path.read_text(encoding='utf-8'))

    def test_icon_only_has_icon_and_accessibility_not_invented_text(self):
        source, report = self.transformed("icon")
        self.assertIn('YapchikIcon(icon, "Details")', source)
        self.assertNotIn('YapchikText', source)

    def test_modifier_trailing_lambda_becomes_valid_named_argument(self):
        source, report = self.transformed("modifier")
        self.assertIn('.clickable (onClick = ', source)
        self.assertIn('.bind({ callback() })', source)
        self.assertIn('.modifier)', source)

    def test_repeated_item_supplies_data_identity_and_keeps_lazy_key(self):
        source, report = self.transformed("repeated")
        self.assertIn('key = { it.id }', source)
        self.assertIn(', item) {', source)
        self.assertLess(source.index('YapchikItem'), source.index('YapchikAction'))

    def test_import_aliases_and_non_bmp_offsets(self):
        source, report = self.transformed("alias")
        self.assertEqual(1, len(report["instrumented"]))
        self.assertIn('YapchikText("Hello 👋")', source)

    def test_toggle_tracks_state_without_drawing_condition(self):
        source, report = self.transformed("toggle")
        self.assertIn('.trackSelected(checked)', source)
        self.assertIn('.bindNullableToggle(callback)', source)
        self.assertIn('control = "Checkbox"', source)

    def test_conditional_callbacks_are_not_hoisted_or_evaluated_twice(self):
        source, report = self.transformed("conditional")
        self.assertIn('if (active) Modifier.clickable(onClick = ', source)
        self.assertEqual(1, source.count('callback!!'))
        self.assertIn('YapchikAction("', source)
        self.assertIn(', null)', source)

    def test_native_window_suppresses_covered_actions(self):
        source, report = self.transformed("window")
        self.assertIn('YapchikScope(blocking = true, suppress = true)', source)

    def test_unsupported_pattern_fails_without_modifying_source(self):
        path = self.paths["unsupported"]
        original = path.read_bytes()
        report = Path(self.directory.name) / "coverage.json"
        with self.assertRaisesRegex(RuntimeError, "requiring review"):
            instrument([path], report)
        self.assertEqual(original, path.read_bytes())
        self.assertEqual("triStateToggleable", json.loads(report.read_text())["unsupported"][0]["symbol"])

    def test_supported_upstream_addition_is_automatically_discovered(self):
        path = Path(self.directory.name) / "addition.kt"
        source = self.fixtures["buttons"].replace('Text("Run") }', 'Text("Run") }\n    Button(onClick = callback) { Text("New") }')
        path.write_text(source, encoding="utf-8")
        file = parse([path])[0]
        result, report = edits_for_file(file)
        self.assertEqual(2, len(report["instrumented"]))
        self.assertIn(b'YapchikText("New")', result)

    def test_transformed_fixtures_remain_valid_kotlin(self):
        outputs = []
        for name in self.fixtures:
            if name == "unsupported":
                continue
            source, report = self.transformed(name)
            path = Path(self.directory.name) / ("out-" + name + ".kt")
            path.write_text(source, encoding="utf-8")
            outputs.append(path)
        self.assertEqual(len(outputs), len(parse(outputs)))

    def test_pinned_library_notices_and_sources_have_verified_digests(self):
        lock = verify_vendor()
        self.assertIn("LICENSE", lock["files"])
        self.assertIn("NOTICE", lock["files"])

    def test_options_menu_uses_saveable_store_keys(self):
        source = (INTEGRATION / "runtime/YapchikRuntime.kt").read_text(encoding="utf-8")
        self.assertIn("items(entries, key = { store.lazyKey(it.identity) })", source)
        self.assertNotIn("items(entries, key = { it.identity })", source)

    def test_options_binding_opens_idempotently_for_aliased_key_events(self):
        source = (INTEGRATION / "runtime/YapchikRuntime.kt").read_text(encoding="utf-8")
        self.assertIn('left(optionsLabel) { menuOpen = true }', source)
        self.assertNotIn('menuOpen = !menuOpen', source)
        self.assertIn("BackHandler(onBack = dismiss)", source)

    def test_key_diagnostics_are_opt_in_and_delegate_to_yapchik(self):
        source = (INTEGRATION / "runtime/KeyDiagnostics.kt").read_text(encoding="utf-8")
        self.assertIn("val handled = wrapped.dispatchKeyEvent(event)", source)
        self.assertIn("return handled", source)
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            path = runtime / "KeyDiagnostics.kt"
            path.write_text(source, encoding="utf-8")
            with patch.dict(os.environ, {"YAPCHIK_DIAGNOSTICS": "false"}):
                configure_diagnostics(runtime)
            self.assertEqual(source, path.read_text(encoding="utf-8"))
            with patch.dict(os.environ, {"YAPCHIK_DIAGNOSTICS": "true"}):
                configure_diagnostics(runtime)
            self.assertIn("private const val KEY_DIAGNOSTICS = true", path.read_text(encoding="utf-8"))

    def test_vendor_digests_ignore_only_checkout_line_ending_conversion(self):
        path = Path(self.directory.name) / "vendor-line-endings.kt"
        path.write_bytes(b"first\nsecond\n")
        expected = vendor_digest(path)
        path.write_bytes(b"first\r\nsecond\r\n")
        self.assertEqual(expected, vendor_digest(path))
        path.write_bytes(b"first\r\nchanged\r\n")
        self.assertNotEqual(expected, vendor_digest(path))


if __name__ == "__main__":
    unittest.main()
