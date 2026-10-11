import argparse
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from github_api import GitHub


UPSTREAM = "PimpinPumpkin/Vela"
DESTINATION = "Toast-Machine/Kosher-Vela"
STATE_PATH = ".state/releases.json"
QUERY = """
query($owner:String!,$name:String!,$endCursor:String){
  repository(owner:$owner,name:$name){
    releases(first:100,after:$endCursor,orderBy:{field:CREATED_AT,direction:DESC}){
      nodes{
        databaseId tagName name isDraft isPrerelease createdAt publishedAt updatedAt
        tagCommit{oid}
        releaseAssets(first:10){
          nodes{id name size updatedAt downloadUrl}
          pageInfo{hasNextPage}
        }
      }
      pageInfo{hasNextPage endCursor}
    }
  }
}
"""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fingerprints(release):
    assets = sorted(
        [{key: asset[key] for key in ("id", "name", "size", "updatedAt")}
         for asset in release["assets"]],
        key=lambda asset: asset["name"],
    )
    build = digest({"id": release["id"], "sha": release["sha"], "assets": assets})
    metadata = digest({key: release[key] for key in ("name", "prerelease", "updated_at")})
    return build, metadata


def list_releases(api):
    cursor = None
    releases = []
    while True:
        connection = api.graphql(QUERY, {
            "owner": "PimpinPumpkin", "name": "Vela", "endCursor": cursor,
        })["repository"]["releases"]
        for node in connection["nodes"]:
            if node["isDraft"]:
                continue
            assets = [asset for asset in node["releaseAssets"]["nodes"]
                      if asset["name"].lower().endswith(".apk")]
            if not assets:
                continue
            if node["releaseAssets"]["pageInfo"]["hasNextPage"]:
                raise RuntimeError(f"App release {node['tagName']} has more than 10 assets; expand pagination before publishing")
            if not node["tagCommit"]:
                continue
            release = {
                "id": str(node["databaseId"]), "tag": node["tagName"],
                "name": node["name"] or node["tagName"], "sha": node["tagCommit"]["oid"],
                "prerelease": node["isPrerelease"], "created_at": node["createdAt"],
                "published_at": node["publishedAt"], "updated_at": node["updatedAt"],
                "assets": assets,
            }
            release["build_fingerprint"], release["metadata_fingerprint"] = fingerprints(release)
            releases.append(release)
        if not connection["pageInfo"]["hasNextPage"]:
            return releases
        cursor = connection["pageInfo"]["endCursor"]


def initial_state(releases, count=5):
    newest = sorted(releases, key=lambda release: release["published_at"], reverse=True)[:count]
    selected = {release["id"] for release in newest}
    return {
        "schema": 1,
        "bootstrap_at": datetime.now(timezone.utc).isoformat(),
        "initial_tags": [release["tag"] for release in newest],
        "excluded_release_ids": sorted(release["id"] for release in releases if release["id"] not in selected),
        "completed": {},
    }


def pending_releases(releases, state):
    excluded = set(state["excluded_release_ids"])
    pending = []
    for release in releases:
        if release["id"] in excluded:
            continue
        failure = state.get("failed", {}).get(release["id"])
        if failure and os.environ.get("RETRY_FAILURES") != "true":
            same = failure["build_fingerprint"] == release["build_fingerprint"]
            retry_at = datetime.fromisoformat(failure["retry_at"])
            if same and datetime.now(timezone.utc) < retry_at:
                continue
        previous = state["completed"].get(release["id"])
        if previous and previous["build_fingerprint"] == release["build_fingerprint"]:
            if previous["metadata_fingerprint"] == release["metadata_fingerprint"]:
                continue
            kind = "metadata"
        else:
            kind = "build"
        pending.append({**release, "kind": kind})
    return sorted(pending, key=lambda release: release["published_at"])


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_remote_state(api):
    remote = api.request(f"repos/{DESTINATION}/contents/{STATE_PATH}?ref=main")
    return json.loads(base64.b64decode(remote["content"])), remote["sha"]


def resolve_tag(api, tag):
    ref = api.request(f"repos/{UPSTREAM}/git/ref/tags/{quote(tag, safe='')}")
    target = ref["object"]
    while target["type"] == "tag":
        target = api.request(f"repos/{UPSTREAM}/git/tags/{target['sha']}")["object"]
    if target["type"] != "commit":
        raise RuntimeError("Upstream tag does not point to a commit")
    return target["sha"]


def current_release(api, item):
    release = api.request(f"repos/{UPSTREAM}/releases/tags/{quote(item['tag'], safe='')}")
    if release["draft"]:
        raise RuntimeError("Upstream release became a draft; refusing publication")
    assets = [
        {"id": asset["node_id"], "name": asset["name"], "size": asset["size"],
         "updatedAt": asset["updated_at"], "downloadUrl": asset["browser_download_url"]}
        for asset in release["assets"] if asset["name"].lower().endswith(".apk")
    ]
    normalized = {
        **item, "id": str(release["id"]), "sha": resolve_tag(api, item["tag"]),
        "name": release["name"] or item["tag"], "prerelease": release["prerelease"],
        "updated_at": release["updated_at"], "assets": assets,
    }
    build, metadata = fingerprints(normalized)
    if build != item["build_fingerprint"]:
        raise RuntimeError("Upstream changed while this build ran; retry the current release next poll")
    return release, {**normalized, "build_fingerprint": build, "metadata_fingerprint": metadata}


def prune_failures(state, live_ids):
    failed = state.get("failed", {})
    stale = [release_id for release_id in failed if release_id not in live_ids]
    for release_id in stale:
        del failed[release_id]
    return len(stale)


def plural(count, noun):
    return f"{count} {noun}" + ("" if count == 1 else "s")


def state_commit_message(published, failed, cleared):
    parts = []
    if published:
        parts.append(plural(published, "published release"))
    if failed:
        parts.append(plural(failed, "failed build"))
    if not parts:
        return f"Clear {plural(cleared, 'stale failure')}"
    message = "Record " + " and ".join(parts)
    if cleared:
        message += f"; clear {plural(cleared, 'stale failure')}"
    return message


def record_completion(api, receipts):
    state, sha = read_remote_state(api)
    previous = json.dumps(state, sort_keys=True)
    published = failed = 0
    for path in Path(receipts).glob("**/receipt.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        state.setdefault("failed", {}).pop(item["id"], None)
        state["completed"][item["id"]] = {
            "tag": item["tag"], "source_sha": item["sha"],
            "build_fingerprint": item["build_fingerprint"],
            "metadata_fingerprint": item["metadata_fingerprint"],
        }
        published += 1
    for path in Path(receipts).glob("**/failure.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        state.setdefault("failed", {})[item["id"]] = item
        failed += 1
    cleared = 0
    if state.get("failed"):
        # Rolling tags like canary get a new release id on every re-cut, so
        # failures for deleted releases would otherwise never be retried or cleared.
        cleared = prune_failures(state, {release["id"] for release in list_releases(api)})
    if json.dumps(state, sort_keys=True) != previous:
        content = base64.b64encode((json.dumps(state, indent=2) + "\n").encode()).decode()
        api.request(f"repos/{DESTINATION}/contents/{STATE_PATH}", {
            "message": state_commit_message(published, failed, cleared), "content": content,
            "sha": sha, "branch": "main",
        }, method="PUT")
    upstream_latest = api.request(f"repos/{UPSTREAM}/releases/latest", missing_ok=True)
    if upstream_latest and any(entry["tag"] == upstream_latest["tag_name"] for entry in state["completed"].values()):
        target = api.request(
            f"repos/{DESTINATION}/releases/tags/{quote(upstream_latest['tag_name'], safe='')}",
            missing_ok=True,
        )
        if target and not target["draft"] and not target["prerelease"]:
            api.request(f"repos/{DESTINATION}/releases/{target['id']}", {"make_latest": "true"}, method="PATCH")


def keepalive(api):
    commits = api.request(f"repos/{DESTINATION}/commits?sha=main&per_page=1")
    latest = datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if (now - latest).days < 30:
        return
    path = ".github/keepalive.txt"
    previous = api.request(f"repos/{DESTINATION}/contents/{path}?ref=main", missing_ok=True)
    payload = {
        "message": "Keep release polling active", "branch": "main",
        "content": base64.b64encode((now.isoformat() + "\n").encode()).decode(),
    }
    if previous:
        payload["sha"] = previous["sha"]
    api.request(f"repos/{DESTINATION}/contents/{path}", payload, method="PUT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap", "plan", "finish", "failure"])
    parser.add_argument("--receipts", default="receipts")
    args = parser.parse_args()
    if args.command == "failure":
        item = json.loads(os.environ["RELEASE_JSON"])
        item["retry_at"] = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        write_json("out/receipt/failure.json", item)
        return
    api = GitHub()
    if args.command == "bootstrap":
        if Path(STATE_PATH).exists():
            raise RuntimeError("Bootstrap is one-time only; refusing to reset the release history")
        releases = list_releases(api)
        state = initial_state(releases)
        write_json(STATE_PATH, state)
        print("Initial five app releases: " + ", ".join(state["initial_tags"]))
        print(f"Excluded {len(state['excluded_release_ids'])} older app releases")
    elif args.command == "plan":
        state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
        pending = pending_releases(list_releases(api), state)
        batch = pending[:200]
        print(f"{len(pending)} pending releases; {len(batch)} in this batch")
        if len(pending) > len(batch):
            print("Remaining releases stay pending and will be built in following polls")
        matrix = {"include": batch}
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write("matrix=" + json.dumps(matrix, separators=(",", ":")) + "\n")
                output.write("has_work=" + str(bool(batch)).lower() + "\n")
        write_json("out/plan.json", matrix)
    else:
        record_completion(api, args.receipts)
        keepalive(api)


if __name__ == "__main__":
    main()
