import json
import os
import subprocess
import time
import urllib.error
import urllib.request


class GitHub:
    def __init__(self):
        self.token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            self.token = subprocess.check_output(
                ["gh", "auth", "token"], text=True
            ).strip()

    def request(self, path, data=None, method=None, missing_ok=False):
        payload = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(
            "https://api.github.com/" + path,
            data=payload,
            method=method or ("GET" if payload is None else "POST"),
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "Kosher-Vela-release-sync",
            },
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if missing_ok and error.code == 404:
                    return None
                limited = error.code == 403 and error.headers.get(
                    "X-RateLimit-Remaining"
                ) == "0"
                if attempt == 4 or (error.code not in (429, 500, 502, 503, 504) and not limited):
                    raise RuntimeError(
                        f"GitHub {request.method} {path}: {error.code} "
                        + error.read().decode(errors="replace")
                    ) from error
                time.sleep(min(int(error.headers.get("Retry-After", 5 * (attempt + 1))), 60))
            except (TimeoutError, urllib.error.URLError):
                if attempt == 4:
                    raise
                time.sleep(5 * (attempt + 1))

    def graphql(self, query, variables):
        result = self.request("graphql", {"query": query, "variables": variables})
        if result.get("errors"):
            raise RuntimeError(json.dumps(result["errors"]))
        return result["data"]
