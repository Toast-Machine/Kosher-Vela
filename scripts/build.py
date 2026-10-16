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
from sync import DESTINATION, UPSTREAM, UpstreamChanged, current_release, write_json
from variants import VARIANTS, customize, verify_variant


def verify_signer(certificates, expected):
    digests = re.findall(
        r"^(?:Signer #\d+|V[234](?:\.\d+)? Signer):? certificate SHA-256 digest:\s*([0-9a-fA-F]{64})\s*$",
        certificates, re.M,
    )
    if not digests or any(digest.lower() != expected.lower() for digest in digests):
        raise RuntimeError(
            "APK was not signed with the permanent Kosher Vela key. "
            + "Expected public certificate SHA-256: " + expected
            + "\nAPK certificate details:\n" + certificates
        )


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


def prepare(api, item, root, variant="kosher"):
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
    customize(root, variant)
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
    environment = {
        "VELA_KEYSTORE_PATH": str(keystore_path.resolve()), "APP_VERSION_NAME": version["version_name"],
        "APP_VERSION_CODE": str(version["version_code"]), "EXPECTED_SIGNER_SHA256": signer,
        "APP_PACKAGE": VARIANTS[variant]["package"],
    }
    os.environ.update(environment)
    if os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
            output.writelines(f"{key}={value}\n" for key, value in environment.items())
    info = {
        **item, **version, "package": VARIANTS[variant]["package"], "variant": variant,
        "features": VARIANTS[variant], "upstream_repository": UPSTREAM,
        "upstream_apk_sha256": hashlib.sha256(upstream_apk.read_bytes()).hexdigest(),
        "runtime_files": runtime_files, "automation_sha": os.environ["GITHUB_SHA"],
        "key_diagnostics": os.environ.get("YAPCHIK_DIAGNOSTICS") == "true",
        "locked_settings": {"show_reviews": False, "live_reviews_panel": False,
                            "load_photos": False, "hide_external_links": True} if VARIANTS[variant]["kosher"] else {},
    }
    if VARIANTS[variant]["yapchik"]:
        info["yapchik"] = json.loads((root / "yapchik-coverage.json").read_text())
    write_json(f"out/{variant}-build-info.json", info)
    return info


def package(root, variant="kosher"):
    verify_variant(root, variant)
    info = json.loads(Path(f"out/{variant}-build-info.json").read_text())
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
    verify_signer(certificates, os.environ["EXPECTED_SIGNER_SHA256"])
    info["signer_sha256"] = os.environ["EXPECTED_SIGNER_SHA256"]
    target = Path("out/assets")
    target.mkdir(parents=True, exist_ok=True)
    safe_tag = re.sub(r"[^A-Za-z0-9._-]", "_", info["tag"])
    apk = target / f"{variant}-vela-{safe_tag}.apk"
    shutil.copyfile(apks[0], apk)
    info["apk_sha256"] = hashlib.sha256(apk.read_bytes()).hexdigest()
    write_json(target / f"{variant}-build.json", info)
    write_json(root / "VARIANT_BUILD.json", info)
    (root / "VARIANT_BUILD.md").write_text(
        f"# Vela: {variant}\n\nModified from {UPSTREAM}. Package: {info['package']}.\n\n"
        f"Kosher policy: {VARIANTS[variant]['kosher']}. Yapchik softkeys: {VARIANTS[variant]['yapchik']}.\n"
        f"Updates use {DESTINATION} and only this variant's APKs.\n\n"
        "VARIANT_BUILD.json records exact source, features, dependencies and build arguments.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "add", "-f", "app/libs", "core/libs"], cwd=root, check=True)
    tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()
    source = (target / f"{variant}-vela-{safe_tag}-source.tar.gz").resolve()
    subprocess.run(["git", "archive", "--format=tar.gz", "--output=" + str(source), tree], cwd=root, check=True)
    info["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(target / f"{variant}-build.json", info)
    checksum_lines = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name
                      for path in sorted(target.iterdir()) if path.is_file() and path.name != "SHA256SUMS"]
    (target / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def build_variants(api, item, root):
    infos = []
    for variant in VARIANTS:
        source = Path("out/sources") / variant
        if source.exists():
            raise RuntimeError("Refusing to reuse a potentially customized source tree: " + str(source))
        subprocess.run(["git", "clone", "--no-hardlinks", str(root.resolve()), str(source)], check=True)
        subprocess.run(["git", "checkout", "--detach", item["sha"]], cwd=source, check=True)
        info = prepare(api, item, source, variant)
        wrapper = "gradlew.bat" if os.name == "nt" else "./gradlew"
        if os.name != "nt":
            (source / "gradlew").chmod(0o755)
        tasks = [":app:testDebugUnitTest", ":app:assembleRelease"]
        subprocess.run([
            wrapper, *tasks, "--no-daemon", "-PappId=" + info["package"],
            "-PappVersionName=" + info["version_name"], "-PappVersionCode=" + str(info["version_code"]),
        ], cwd=source, check=True, env={**os.environ, "VELA_KEY_ALIAS": "kosher-vela"})
        package(source, variant)
        infos.append(info)
    write_json("out/build-info.json", {"variants": infos})


def validate_assets(directory, item):
    directory = Path(directory)
    safe_tag = re.sub(r"[^A-Za-z0-9._-]", "_", item["tag"])
    expected_apks = {f"{variant}-vela-{safe_tag}.apk" for variant in VARIANTS}
    if {path.name for path in directory.glob("*.apk")} != expected_apks:
        raise RuntimeError("Release must contain only the configured Kosher APK")
    for variant, features in VARIANTS.items():
        path = directory / f"{variant}-build.json"
        info = json.loads(path.read_text())
        if info.get("key_diagnostics"):
            raise RuntimeError("Diagnostic APKs must not be published as releases")
        if info["variant"] != variant or info["package"] != features["package"] or info["sha"] != item["sha"]:
            raise RuntimeError("Incorrect variant provenance: " + variant)
        safe_tag = re.sub(r"[^A-Za-z0-9._-]", "_", item["tag"])
        apk = directory / f"{variant}-vela-{safe_tag}.apk"
        source = directory / f"{variant}-vela-{safe_tag}-source.tar.gz"
        if (not source.is_file() or not apk.is_file()
                or hashlib.sha256(apk.read_bytes()).hexdigest() != info["apk_sha256"]
                or hashlib.sha256(source.read_bytes()).hexdigest() != info["source_sha256"]):
            raise RuntimeError("Incomplete Kosher Yapchik release: " + variant)


def gh(*arguments):
    subprocess.run(["gh", *arguments, "--repo", DESTINATION], check=True)


def publish(api, item):
    upstream, fresh = current_release(api, item)
    destination = api.request(f"repos/{DESTINATION}/releases/tags/" + quote(item["tag"], safe=""), missing_ok=True)
    if item["kind"] == "metadata":
        if not destination or destination["draft"]:
            raise RuntimeError("Cannot update metadata without a published customized build")
        body = upstream["body"] or ""
        body += variant_description()
        api.request(f"repos/{DESTINATION}/releases/{destination['id']}", {
            "name": fresh["name"], "body": body, "prerelease": fresh["prerelease"], "make_latest": "false",
        }, method="PATCH")
    else:
        validate_assets("out/assets", item)
        info = json.loads(Path("out/build-info.json").read_text())["variants"][0]
        body = (upstream["body"] or "") + (
            variant_description() +
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
        elif not destination["draft"]:
            api.request(f"repos/{DESTINATION}/releases/{destination['id']}", {"draft": True}, method="PATCH")
        paths = [str(path) for path in Path("out/assets").iterdir() if path.is_file()]
        gh("release", "upload", item["tag"], *paths, "--clobber")
        upstream, fresh = current_release(api, item)
        api.request(f"repos/{DESTINATION}/releases/{destination['id']}", {
            "name": fresh["name"], "body": body, "draft": False,
            "prerelease": fresh["prerelease"], "make_latest": "false",
        }, method="PATCH")
    write_json("out/receipt/receipt.json", fresh)
    print("Published " + item["tag"])


def variant_description():
    return (
        "\n\n---\nKosher Vela with Yapchik:\n"
        "- Kosher (`app.vela.kosher`): locked content policy and Yapchik hardware softkeys.\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "package", "variants", "publish"])
    parser.add_argument("--source", type=Path, default=Path("upstream"))
    parser.add_argument("--variant", choices=VARIANTS, default="kosher")
    args = parser.parse_args()
    if args.command == "package":
        package(args.source, args.variant)
    else:
        item = json.loads(os.environ["RELEASE_JSON"])
        try:
            if args.command == "prepare":
                prepare(GitHub(), item, args.source, args.variant)
            elif args.command == "variants":
                build_variants(GitHub(), item, args.source)
            else:
                publish(GitHub(), item)
        except UpstreamChanged as error:
            # A superseded release is not a failure: skip it without a receipt so
            # the next poll plans the replacement, and don't send a failure email.
            print(f"::notice::{item['tag']} skipped: {error}")
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                    output.write("superseded=true\n")
