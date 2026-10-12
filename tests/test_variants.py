import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import publish, validate_assets
from variants import VARIANTS, apply_features, configure_updater, customize


class VariantTests(unittest.TestCase):
    def test_diagnostic_apks_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "kosher-vela-v1.apk").write_bytes(b"diagnostic")
            (directory / "kosher-build.json").write_text(json.dumps({"key_diagnostics": True}))
            with self.assertRaisesRegex(RuntimeError, "must not be published"):
                validate_assets(directory, {"tag": "v1", "sha": "source"})

    def test_only_kosher_package_is_released_with_both_features(self):
        self.assertEqual({"kosher"}, set(VARIANTS))
        self.assertEqual("app.vela.kosher", VARIANTS["kosher"]["package"])
        self.assertEqual(1, len({value["package"] for value in VARIANTS.values()}))
        self.assertTrue(all(value["yapchik"] for value in VARIANTS.values()))
        self.assertTrue(VARIANTS["kosher"]["kosher"])

    def test_only_selected_independent_features_are_applied_in_order(self):
        for variant, features in VARIANTS.items():
            calls = []
            with patch("variants.apply", side_effect=lambda root: calls.append("kosher")), \
                 patch("variants.configure_updater", side_effect=lambda root, selected: calls.append("updater")), \
                 patch("variants.verify_variant"), \
                 patch("yapchik.integrate", side_effect=lambda root: calls.append("yapchik")):
                customize(Path("source"), variant)
            expected = (["kosher"] if features["kosher"] else []) + (["yapchik"] if features["yapchik"] else []) + ["updater"]
            self.assertEqual(expected, calls)

    def test_neither_feature_leaves_upstream_untouched(self):
        with patch("variants.apply") as kosher, patch("yapchik.integrate") as yapchik:
            apply_features(Path("source"))
        kosher.assert_not_called()
        yapchik.assert_not_called()

    def test_updater_isolated_by_variant_asset_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            updater = root / "app/src/main/java/app/vela/update/SelfUpdater.kt"
            updater.parent.mkdir(parents=True)
            for variant in VARIANTS:
                updater.write_text('val repository = "PimpinPumpkin/Vela"\nval all = (0 until assets.length()).map { assets.getJSONObject(it) }')
                configure_updater(root, variant)
                source = updater.read_text()
                self.assertNotIn("PimpinPumpkin/Vela", source)
                self.assertIn(f'startsWith("{variant}-vela-")', source)

    def test_updater_source_change_fails_for_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            updater = root / "app/src/main/java/app/vela/update/SelfUpdater.kt"
            updater.parent.mkdir(parents=True)
            updater.write_text("fun pickApk() = unknown()")
            with self.assertRaisesRegex(RuntimeError, "selection changed"):
                configure_updater(root, "kosher")

    def test_release_requires_kosher_apk_and_source_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            item = {"sha": "source", "tag": "v0.5.1"}
            for variant, features in VARIANTS.items():
                apk = directory / f"{variant}-vela-v0.5.1.apk"
                apk.write_bytes(variant.encode())
                (directory / f"{variant}-vela-v0.5.1-source.tar.gz").write_bytes(b"source")
                (directory / f"{variant}-build.json").write_text(json.dumps({
                    "variant": variant, "package": features["package"], "sha": "source",
                    "apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
                    "source_sha256": hashlib.sha256(b"source").hexdigest(),
                }))
            validate_assets(directory, item)
            (directory / "kosher-vela-v0.5.1.apk").write_bytes(b"corrupted")
            with self.assertRaisesRegex(RuntimeError, "Incomplete Kosher Yapchik"):
                validate_assets(directory, item)
            (directory / "kosher-vela-v0.5.1.apk").write_bytes(b"kosher")
            (directory / "yapchik-vela-v0.5.1.apk").write_bytes(b"obsolete")
            with self.assertRaisesRegex(RuntimeError, "only the configured Kosher APK"):
                validate_assets(directory, item)
            (directory / "yapchik-vela-v0.5.1.apk").unlink()
            (directory / "kosher-vela-v0.5.1-source.tar.gz").write_bytes(b"corrupted")
            with self.assertRaisesRegex(RuntimeError, "Incomplete Kosher Yapchik"):
                validate_assets(directory, item)

    def test_legacy_completed_release_is_rebuilt_for_combined_profile(self):
        from sync import digest, fingerprints, initial_state, pending_releases
        from test_sync import release
        item = release(1)
        state = initial_state([item])
        assets = [{key: asset[key] for key in ("id", "name", "size", "updatedAt")} for asset in item["assets"]]
        state["completed"]["1"] = {**item, "build_fingerprint": digest({"id": item["id"], "sha": item["sha"], "assets": assets})}
        self.assertEqual("build", pending_releases([item], state)[0]["kind"])

    def test_previous_build_profiles_are_rebuilt(self):
        from sync import digest, initial_state, pending_releases
        from test_sync import release
        item = release(1)
        state = initial_state([item])
        assets = sorted([{key: asset[key] for key in ("id", "name", "size", "updatedAt")} for asset in item["assets"]], key=lambda asset: asset["name"])
        for profile in ("three-variants-v1", "two-variants-yapchik-v1", "kosher-with-yapchik-v1", "kosher-with-yapchik-v2"):
            state["completed"]["1"] = {**item, "build_fingerprint": digest({
                "id": item["id"], "sha": item["sha"], "assets": assets, "profile": profile,
            })}
            self.assertEqual("build", pending_releases([item], state)[0]["kind"])

    def test_corrected_recipe_retries_old_failures_without_resetting_state(self):
        from datetime import datetime, timedelta, timezone
        from sync import digest, initial_state, pending_releases
        from test_sync import release
        item = release(1)
        state = initial_state([item])
        excluded = list(state["excluded_release_ids"])
        assets = sorted([{key: asset[key] for key in ("id", "name", "size", "updatedAt")} for asset in item["assets"]], key=lambda asset: asset["name"])
        state["failed"] = {item["id"]: {
            "build_fingerprint": digest({"id": item["id"], "sha": item["sha"], "assets": assets, "profile": "kosher-with-yapchik-v1"}),
            "retry_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        }}
        self.assertEqual("build", pending_releases([item], state)[0]["kind"])
        self.assertEqual(excluded, state["excluded_release_ids"])

    def test_missing_variant_does_not_start_publication(self):
        api = Mock()
        with patch('build.current_release', return_value=({'body': ''}, {})), \
                patch('build.validate_assets', side_effect=RuntimeError('missing variant')), \
                patch('build.gh') as upload, patch('build.write_json') as write:
            with self.assertRaisesRegex(RuntimeError, 'missing variant'):
                publish(api, {'kind': 'build', 'tag': 'v1'})
        self.assertEqual(1, api.request.call_count)
        upload.assert_not_called()
        write.assert_not_called()

    def test_failed_upload_leaves_replacement_draft_without_success_receipt(self):
        api = Mock()
        api.request.return_value = {'id': 12, 'draft': False}
        item = {'kind': 'build', 'tag': 'v1', 'sha': 'source'}
        fresh = {'name': 'v1', 'prerelease': False}
        info = json.dumps({'variants': [{'version_name': '1', 'version_code': 1}]})
        with patch('build.current_release', return_value=({'body': ''}, fresh)), \
                patch('build.validate_assets'), patch('build.Path.read_text', return_value=info), \
                patch('build.Path.iterdir', return_value=[]), \
                patch('build.gh', side_effect=RuntimeError('upload failed')), \
                patch('build.write_json') as write:
            with self.assertRaisesRegex(RuntimeError, 'upload failed'):
                publish(api, item)
        self.assertEqual(2, api.request.call_count)
        self.assertEqual({'draft': True}, api.request.call_args.args[1])
        self.assertEqual('PATCH', api.request.call_args.kwargs['method'])
        self.assertEqual(['out/release.json'], [call.args[0] for call in write.call_args_list])


if __name__ == "__main__":
    unittest.main()
