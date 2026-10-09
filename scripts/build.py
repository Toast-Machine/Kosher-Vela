import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

from github_api import GitHub
from policy import apply, verify
from sync import DESTINATION, UPSTREAM, current_release, write_json


PACKAGE = "app.vela.kosher"


def binary(name):
    android = Path(os.environ.get("ANDROID_HOME") or os.environ["ANDROID_SDK_ROOT"])
    candidates = sorted((android / "build-tools").glob("*/" + name))
    if not candidates:
        subprocess.run(["sdkmanager", "build-tools;36.0.0"], check=True)
        candidates = sorted((android / "build-tools").glob("*/" + name))
    if not candidates:
        raise RuntimeError(f"Cannot find Android build tool {name}")
    return str(candidates[-1])


def download(url, path, size=None, sha256=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            if size is not None and partial.stat().st_size != size:
                raise RuntimeError(f"Incomplete download: {path.name}")
            if sha256 and hashlib.sha256(partial.read_bytes()).hexdigest() != sha256:
                raise RuntimeError(f"Download digest mismatch: {path.name}")
            partial.replace(path)
            return
        except Exception:
            partial.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def apk_info(path):
    output = subprocess.check_output([binary("aapt"), "dump", "badging", str(path)], text=True)
    match = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", output)
    if not match:
        raise RuntimeError("Cannot read APK package and version")
    return {"package": match[1], "version_code": int(match[2]), "version_name": match[3]}


def prepare(api, item, root):
    release, item = current_release(api, item)
    apk_assets = [asset for asset in release["assets"] if asset["name"].lower().endswith(".apk")]
    universal = [asset for asset in apk_assets if not re.search(r"-(armv7|arm64|x86|x86_64)\.apk$", asset["name"])]
    asset = (universal or apk_assets)[0]
    digest = asset.get("digest") or ""
    upstream_apk = Path("out/upstream.apk")
    download(asset["browser_download_url"], upstream_apk, size=asset["size"],
             sha256=digest.removeprefix("sha256:") if digest.startswith("sha256:") else None)
    version = apk_info(upstream_apk)
    if version["package"] != "app.vela":
        raise RuntimeError("Unexpected upstream APK package; review before building")
    apply(root)
    gradle = (root / "app/build.gradle.kts").read_text(encoding="utf-8")
    runtime = re.search(r'implementation\(files\("libs/(sherpa-onnx-[^"/]+\.aar)"\)\)', gradle)
    cronet = re.search(r"^vela\.cronetVersion=(\S+)", (root / "gradle.properties").read_text(), re.M)
    if not runtime or not cronet:
        raise RuntimeError("Upstream runtime dependencies changed; review downloads")
    files = [
        ("tts-runtime", "app/libs/" + runtime[1]),
        ("cronet-runtime", f"app/libs/cronet-{cronet[1]}.aar"),
    ] + [("obf-runtime", "core/libs/" + name) for name in (
        "osmand-java.jar", "osmand-shared-jvm.jar", "gnu-trove-osmand.jar", "kxml2-vela.jar",
    )]
    runtime_files = []
    for tag, relative in files:
        path = root / relative
        url = f"https://github.com/{UPSTREAM}/releases/download/{tag}/{path.name}"
        download(url, path)
        if path.stat().st_size < 10000:
            raise RuntimeError(f"Runtime file unexpectedly small: {path.name}")
        runtime_files.append({"path": relative, "url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    keystore = os.environ.get("VELA_KEYSTORE_BASE64", "")
    if not keystore or not os.environ.get("VELA_KEYSTORE_PASSWORD"):
        raise RuntimeError("Signing secrets are required; never publish a temporary debug-signed build")
    keystore_path = Path(os.environ["RUNNER_TEMP"]) / "kosher-vela-release.p12"
    keystore_path.write_bytes(base64.b64decode(keystore, validate=True))
    keystore_path.chmod(0o600)
    certificate = subprocess.check_output([
        "keytool", "-list", "-rfc", "-keystore", str(keystore_path),
        "-storepass:env", "VELA_KEYSTORE_PASSWORD", "-alias", "kosher-vela",
    ], text=True)
    match = re.search(r"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----", certificate, re.S)
    if not match:
        raise RuntimeError("Cannot read the permanent signing certificate")
    signer = hashlib.sha256(base64.b64decode(match[1])).hexdigest()
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
        output.write(f"VELA_KEYSTORE_PATH={keystore_path}\n")
        output.write(f"APP_VERSION_NAME={version['version_name']}\n")
        output.write(f"APP_VERSION_CODE={version['version_code']}\n")
        output.write(f"EXPECTED_SIGNER_SHA256={signer}\n")
    write_json("out/build-info.json", {
        **item, **version, "package": PACKAGE, "upstream_repository": UPSTREAM,
        "upstream_apk_sha256": hashlib.sha256(upstream_apk.read_bytes()).hexdigest(),
        "runtime_files": runtime_files, "automation_sha": os.environ["GITHUB_SHA"],
        "locked_settings": {"show_reviews": False, "live_reviews_panel": False,
                            "load_photos": False, "hide_external_links": True},
    })


def package(root):
    verify(root)
    info = json.loads(Path("out/build-info.json").read_text())
    apks = list((root / "app/build/outputs/apk/release").glob("*.apk"))
    if len(apks) != 1:
        raise RuntimeError("Expected exactly one universal release APK")
    actual = apk_info(apks[0])
    for key in ("package", "version_code", "version_name"):
        if actual[key] != info[key]:
            raise RuntimeError(f"Built APK has wrong {key}: {actual[key]}")
    certificates = subprocess.check_output([
        binary("apksigner"), "verify", "--print-certs", str(apks[0]),
    ], text=True)
    expected = "Signer #1 certificate SHA-256 digest: " + os.environ["EXPECTED_SIGNER_SHA256"]
    if expected not in certificates:
        raise RuntimeError("APK was not signed with the permanent Kosher Vela key")
    info["signer_sha256"] = os.environ["EXPECTED_SIGNER_SHA256"]
    target = Path("out/assets")
    target.mkdir(parents=True, exist_ok=True)
    safe_tag = re.sub(r"[^A-Za-z0-9._-]", "_", info["tag"])
    apk = target / f"kosher-vela-{safe_tag}.apk"
    shutil.copyfile(apks[0], apk)
    info["apk_sha256"] = hashlib.sha256(apk.read_bytes()).hexdigest()
    write_json(target / "kosher-build.json", info)
    write_json(root / "KOSHER_BUILD.json", info)
    (root / "KOSHER_BUILD.md").write_text(
        "# Kosher Vela\n\nThis source snapshot is modified from " + UPSTREAM + ".\n\n"
        "Reviews, full-review panels and photos are permanently disabled. External place links "
        "are permanently hidden. The four controls and their settings-search entries are removed, "
        "including Privacy and onboarding. Popular-times retries and adult-category filtering "
        "remain configurable. The package is app.vela.kosher and APK updates use " + DESTINATION + ".\n\n"
        "The upstream documentation describes upstream behavior; KOSHER_BUILD.json records "
        "this variant's exact source revision, policy, dependencies and version arguments.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "add", "-f", "app/libs", "core/libs"], cwd=root, check=True)
    tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()
    source = (target / f"kosher-vela-{safe_tag}-source.tar.gz").resolve()
    subprocess.run(["git", "archive", "--format=tar.gz", "--output=" + str(source), tree], cwd=root, check=True)
    checksum_lines = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name
                      for path in sorted(target.iterdir()) if path.is_file()]
    (target / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def gh(*arguments):
    subprocess.run(["gh", *arguments, "--repo", DESTINATION], check=True)


def publish(api, item):
    upstream, fresh = current_release(api, item)
    destination = api.request(f"repos/{DESTINATION}/releases/tags/" + quote(item["tag"], safe=""), missing_ok=True)
    if item["kind"] == "metadata":
        if not destination or destination["draft"]:
            raise RuntimeError("Cannot update metadata without a published customized build")
        body = upstream["body"] or ""
        body += "\n\n---\nKosher Vela (`app.vela.kosher`). Reviews and photos disabled; external place links hidden.\n"
        api.request(f"repos/{DESTINATION}/releases/{destination['id']}", {
            "name": fresh["name"], "body": body, "prerelease": fresh["prerelease"], "make_latest": "false",
        }, method="PATCH")
    else:
        info = json.loads(Path("out/build-info.json").read_text())
        body = (upstream["body"] or "") + (
            "\n\n---\nKosher Vela (`app.vela.kosher`). Reviews and photos disabled; external place links hidden.\n"
            f"\nversionName: {info['version_name']}\nversionCode: {info['version_code']}\n"
            f"\nUpstream source: `{item['sha']}`. Patched source and build provenance are attached.\n"
        )
        write_json("out/release.json", fresh)
        if destination is None:
            destination = api.request(f"repos/{DESTINATION}/releases", {
                "tag_name": item["tag"], "target_commitish": os.environ["GITHUB_SHA"],
                "name": fresh["name"], "body": body, "draft": True,
                "prerelease": fresh["prerelease"], "make_latest": "false",
            })
        paths = [str(path) for path in Path("out/assets").iterdir() if path.is_file()]
        gh("release", "upload", item["tag"], *paths, "--clobber")
        upstream, fresh = current_release(api, item)
        api.request(f"repos/{DESTINATION}/releases/{destination['id']}", {
            "name": fresh["name"], "body": body, "draft": False,
            "prerelease": fresh["prerelease"], "make_latest": "false",
        }, method="PATCH")
    write_json("out/receipt/receipt.json", fresh)
    print("Published " + item["tag"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "package", "publish"])
    parser.add_argument("--source", type=Path, default=Path("upstream"))
    args = parser.parse_args()
    if args.command == "package":
        package(args.source)
    else:
        item = json.loads(os.environ["RELEASE_JSON"])
        if args.command == "prepare":
            prepare(GitHub(), item, args.source)
        else:
            publish(GitHub(), item)
