import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from policy import HIDDEN, SETTINGS_HUB, apply, remove_hidden_search_entries, rewrite_update_repository, verify_update_repository


class SettingsSearchTests(unittest.TestCase):
    def index(self, entries):
        return ('private val SEARCH_INDEX: List<Pair<Int, SettingsSection>> = listOf(\n'
                + entries + ')\n')

    def entry(self, key):
        return f'    R.string.settings_{key} to SettingsSection.PLACES,\n'

    def test_removes_only_hidden_entries_regardless_of_neighbors_and_order(self):
        for keys in (HIDDEN, tuple(reversed(HIDDEN))):
            with self.subTest(keys=keys):
                neighbors = ('    // Navigation entries may appear between hidden settings.\n'
                             '    R.string.settings_zoom_to_turn to SettingsSection.NAVIGATION,\n'
                             '    R.string.settings_zoom_to_turn_floor to SettingsSection.NAVIGATION,\n\n')
                entries = ''.join(self.entry(key) + neighbors for key in keys)
                outside = 'val other = listOf(\n' + self.entry('show_reviews') + ')\n'
                source = outside + self.index(entries) + 'fun unrelated() = Unit\n'
                self.assertEqual(
                    outside + self.index(neighbors * len(keys)) + 'fun unrelated() = Unit\n',
                    remove_hidden_search_entries(source),
                )

    def test_missing_entry_fails_for_review(self):
        for missing in HIDDEN:
            with self.subTest(missing=missing):
                source = self.index(''.join(self.entry(key) for key in HIDDEN if key != missing))
                with self.assertRaisesRegex(RuntimeError, f'settings_{missing}.*found 0'):
                    remove_hidden_search_entries(source)

    def test_duplicate_entry_fails_for_review(self):
        for duplicate in HIDDEN:
            with self.subTest(duplicate=duplicate):
                source = self.index(''.join(self.entry(key) for key in HIDDEN) + self.entry(duplicate))
                with self.assertRaisesRegex(RuntimeError, f'settings_{duplicate}.*found 2'):
                    remove_hidden_search_entries(source)

    def test_unknown_or_ambiguous_list_structure_fails_for_review(self):
        source = self.index(''.join(self.entry(key) for key in HIDDEN))
        for changed in (source.replace('SEARCH_INDEX', 'OTHER_INDEX'),
                        source.replace('listOf(', 'buildList('),
                        source.replace(')\n', ''), source + source):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(RuntimeError, 'SEARCH_INDEX structure changed'):
                    remove_hidden_search_entries(changed)

    def test_changed_target_expression_fails_for_review(self):
        source = self.index(''.join(self.entry(key) for key in HIDDEN))
        source = source.replace('settings_show_reviews to', 'settings_show_reviews + 1 to')
        with self.assertRaisesRegex(RuntimeError, 'settings_show_reviews.*found 0'):
            remove_hidden_search_entries(source)

    def test_entry_whitespace_and_trailing_comments_are_supported(self):
        entries = ''.join(self.entry(key).replace('    ', '\t').replace(' to ', '  to\t')
                          .replace(',\n', ', // Hide this setting.\n') for key in HIDDEN)
        self.assertEqual(self.index(''), remove_hidden_search_entries(self.index(entries)))

    def test_search_validation_fails_before_applying_patches_or_writing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hub = root / SETTINGS_HUB
            hub.parent.mkdir(parents=True)
            source = self.index(self.entry('show_reviews'))
            hub.write_text(source, encoding='utf-8')
            with patch('policy.subprocess.run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Expected exactly one'):
                    apply(root)
                run.assert_not_called()
            self.assertEqual(source, hub.read_text(encoding='utf-8'))


class UpdateRepositoryTests(unittest.TestCase):
    def test_legacy_updater_uses_kosher_repository(self):
        source = 'val url = "https://api.github.com/repos/PimpinPumpkin/Vela/releases/latest"'
        rewritten = rewrite_update_repository(source)
        self.assertEqual(source.replace("PimpinPumpkin/Vela", "Toast-Machine/Kosher-Vela"), rewritten)

    def test_shared_api_is_pinned_for_every_update_channel(self):
        paths = ("/releases/latest", "/releases/tags/canary", "/git/matching-refs/tags/v0.", "/releases/tags/$tag")
        for path in paths:
            with self.subTest(path=path):
                source = f'getJson(app.vela.core.config.VelaLinks.api("{path}"))'
                rewritten = rewrite_update_repository(source)
                self.assertEqual(
                    f'getJson(("https://api.github.com/repos/Toast-Machine/Kosher-Vela" + "{path}"))',
                    rewritten,
                )
                verify_update_repository(rewritten)
                self.assertEqual(rewritten, rewrite_update_repository(rewritten))

    def test_unknown_updater_fails_for_review(self):
        with self.assertRaisesRegex(RuntimeError, "expected upstream update endpoints"):
            rewrite_update_repository('getJson(otherApi("/releases/latest"))')

    def test_shared_api_cannot_remain_beside_kosher_endpoint(self):
        for api in ("VelaLinks.api(", "VelaLinks . api ("):
            with self.subTest(api=api):
                source = 'val repo = "Toast-Machine/Kosher-Vela"\n' + api + '"/releases/latest")'
                with self.assertRaisesRegex(RuntimeError, "exclusively to Kosher-Vela"):
                    verify_update_repository(source)
                with self.assertRaisesRegex(RuntimeError, "exclusively to Kosher-Vela"):
                    rewrite_update_repository(source)

    def test_verification_rejects_upstream_and_missing_repository(self):
        for source in ('"PimpinPumpkin/Vela" "Toast-Machine/Kosher-Vela"', 'getJson(otherApi())'):
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError, "exclusively to Kosher-Vela"):
                    verify_update_repository(source)


if __name__ == "__main__":
    unittest.main()
