import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sync import (fingerprints, initial_state, list_releases, pending_releases, prune_failures,
                  state_commit_message)


def release(number, tag=None):
    value = {
        "id": str(number), "tag": tag or f"v0.5.{number}", "name": f"Vela {number}",
        "sha": f"{number:040x}", "prerelease": number % 2 == 1,
        "created_at": f"2026-10-{number:02d}T00:00:00Z",
        "published_at": f"2026-10-{number:02d}T00:00:00Z",
        "updated_at": f"2026-10-{number:02d}T00:00:00Z",
        "assets": [{"id": f"RA_{number}", "name": "vela.apk", "size": 100,
                    "updatedAt": f"2026-10-{number:02d}T00:00:00Z", "downloadUrl": "https://example.com/app.apk"}],
    }
    value["build_fingerprint"], value["metadata_fingerprint"] = fingerprints(value)
    return value


class ReleaseTrackingTests(unittest.TestCase):
    def test_failed_build_cooldown_does_not_drop_new_releases(self):
        initial = release(1)
        state = initial_state([initial])
        state["failed"] = {"1": {
            "build_fingerprint": initial["build_fingerprint"],
            "retry_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        }}
        self.assertEqual([entry["id"] for entry in pending_releases([initial, release(2)], state)], ["2"])

    def test_bootstrap_selects_only_five_and_excludes_all_older_releases(self):
        releases = [release(number) for number in range(1, 11)]
        state = initial_state(releases)
        self.assertEqual([entry["id"] for entry in pending_releases(releases, state)], ["6", "7", "8", "9", "10"])
        self.assertEqual(len(state["excluded_release_ids"]), 5)

    def test_more_than_five_new_releases_between_polls_are_all_queued(self):
        initial = [release(number) for number in range(1, 11)]
        state = initial_state(initial)
        state["completed"] = {entry["id"]: entry for entry in pending_releases(initial, state)}
        later = initial + [release(number) for number in range(11, 23)]
        self.assertEqual([entry["id"] for entry in pending_releases(later, state)], [str(number) for number in range(11, 23)])

    def test_successes_are_not_rebuilt_but_failed_builds_remain_pending(self):
        releases = [release(number) for number in range(1, 7)]
        state = initial_state(releases)
        state["completed"]["6"] = releases[-1]
        pending = pending_releases(releases, state)
        self.assertEqual(len(pending), 4)
        self.assertNotIn("6", [entry["id"] for entry in pending])

    def test_stable_promotion_changes_only_metadata(self):
        original = release(1)
        state = initial_state([original])
        state["completed"]["1"] = original
        promoted = copy.deepcopy(original)
        promoted["prerelease"] = False
        promoted["name"] = "Vela stable"
        promoted["build_fingerprint"], promoted["metadata_fingerprint"] = fingerprints(promoted)
        pending = pending_releases([promoted], state)
        self.assertEqual(pending[0]["kind"], "metadata")

    def test_rolling_canary_rebuilds_when_source_or_apk_changes(self):
        original = release(1, "canary")
        state = initial_state([original])
        state["completed"]["1"] = original
        changed = copy.deepcopy(original)
        changed["sha"] = "f" * 40
        changed["assets"][0]["id"] = "new-asset"
        changed["build_fingerprint"], changed["metadata_fingerprint"] = fingerprints(changed)
        self.assertEqual(pending_releases([changed], state)[0]["kind"], "build")

    def test_historical_releases_remain_excluded_even_if_edited(self):
        releases = [release(number) for number in range(1, 7)]
        state = initial_state(releases)
        edited = copy.deepcopy(releases[0])
        edited["sha"] = "f" * 40
        edited["build_fingerprint"], edited["metadata_fingerprint"] = fingerprints(edited)
        self.assertNotIn("1", [entry["id"] for entry in pending_releases([edited], state)])

    def test_failures_for_deleted_releases_are_pruned(self):
        recut = release(2, "canary")
        state = initial_state([recut])
        state["failed"] = {"1": {"tag": "canary"}, "2": {"tag": "canary"}}
        self.assertEqual(prune_failures(state, {recut["id"]}), 1)
        self.assertEqual(list(state["failed"]), ["2"])

    def test_state_commit_message_describes_what_changed(self):
        self.assertEqual(state_commit_message(1, 0, 0), "Record 1 published release")
        self.assertEqual(state_commit_message(0, 1, 0), "Record 1 failed build")
        self.assertEqual(state_commit_message(2, 1, 1),
                         "Record 2 published releases and 1 failed build; clear 1 stale failure")
        self.assertEqual(state_commit_message(0, 0, 2), "Clear 2 stale failures")

    def test_release_listing_visits_every_page_and_filters_data_releases(self):
        class FakeAPI:
            def __init__(self):
                self.cursors = []

            def graphql(self, query, variables):
                self.cursors.append(variables["endCursor"])
                number = len(self.cursors)
                node = {
                    "databaseId": number, "tagName": f"v0.5.{number}", "name": "Vela",
                    "isDraft": False, "isPrerelease": True, "createdAt": "2026-10-01T00:00:00Z",
                    "publishedAt": "2026-10-01T00:00:00Z", "updatedAt": "2026-10-01T00:00:00Z",
                    "tagCommit": {"oid": "a" * 40},
                    "releaseAssets": {"nodes": [{"id": "RA", "name": "app.apk", "size": 100,
                                                  "updatedAt": "2026-10-01T00:00:00Z", "downloadUrl": "url"}],
                                      "pageInfo": {"hasNextPage": False}},
                }
                data = copy.deepcopy(node)
                data["tagName"] = "map-data"
                data["releaseAssets"]["nodes"][0]["name"] = "map.pmtiles"
                return {"repository": {"releases": {
                    "nodes": [node, data],
                    "pageInfo": {"hasNextPage": number < 3, "endCursor": f"page{number}"},
                }}}

        api = FakeAPI()
        self.assertEqual(len(list_releases(api)), 3)
        self.assertEqual(api.cursors, [None, "page1", "page2"])


if __name__ == "__main__":
    unittest.main()
