import argparse
import re
import shutil
import subprocess
from pathlib import Path


POLICY = {"ShowReviews": False, "LoadPhotos": False, "LiveReviews": False, "HideExternalLinks": True}
HIDDEN = ("show_reviews", "read_all_reviews", "load_photos", "hide_external_links", "reviews_on_tap", "photos_on_tap")
UPDATER = "app/src/main/java/app/vela/update/SelfUpdater.kt"
SETTINGS_HUB = "app/src/main/java/app/vela/ui/settings/SettingsHub.kt"


def remove_hidden_search_entries(source):
    indexes = list(re.finditer(
        r"(?m)^private val SEARCH_INDEX: List<Pair<Int, SettingsSection>> = listOf\(\n"
        r"(?P<entries>(?:[ \t]+[^\n]*\n|\n)*)^\)", source,
    ))
    if len(indexes) != 1:
        raise RuntimeError("Upstream settings SEARCH_INDEX structure changed; review hidden settings removal")
    index = indexes[0]
    entries = index["entries"]
    for key in HIDDEN:
        pattern = (r"(?m)^[ \t]*R\.string\.settings_" + key
                   + r"[ \t]+to[ \t]+SettingsSection\.[A-Z_]+,[ \t]*(?://[^\n]*)?\n")
        entries, count = re.subn(pattern, "", entries)
        if count != 1:
            raise RuntimeError(f"Expected exactly one settings_{key} entry in SEARCH_INDEX; found {count}")
    return source[:index.start("entries")] + entries + source[index.end("entries"):]


def verify_update_repository(source):
    if ("PimpinPumpkin/Vela" in source or "Toast-Machine/Kosher-Vela" not in source
            or re.search(r"\bVelaLinks\s*\.\s*api\s*\(", source)):
        raise RuntimeError("The APK updater does not point exclusively to Kosher-Vela")


def rewrite_update_repository(source):
    shared_api = "app.vela.core.config.VelaLinks.api("
    if not any(anchor in source for anchor in ("PimpinPumpkin/Vela", "Toast-Machine/Kosher-Vela", shared_api)):
        raise RuntimeError("Cannot find the expected upstream update endpoints")
    source = source.replace("PimpinPumpkin/Vela", "Toast-Machine/Kosher-Vela")
    source = source.replace(shared_api, '("https://api.github.com/repos/Toast-Machine/Kosher-Vela" + ')
    verify_update_repository(source)
    return source


def verify(root):
    source = root / "app/src/main/java"
    for name, value in POLICY.items():
        filename = "LiveReviews.kt" if name == "LiveReviews" else "PlaceContent.kt"
        text = (source / "app/vela/ui" / filename).read_text(encoding="utf-8")
        start = text.index(f"object {name} {{")
        end = text.index("\n}", start)
        body = text[start:end]
        expected = "val on: State<Boolean> = object : State<Boolean> { override val value = " + str(value).lower() + " }"
        if expected not in body or "getSharedPreferences" in body or "on.value =" in body:
            raise RuntimeError(f"{name} is not locked to {value}")
        for signature in ("fun init(context: Context) = Unit", "fun set(context: Context, value: Boolean) = Unit"):
            if signature not in body:
                raise RuntimeError(f"{name} has an unexpected preference initialization/setter")
    for path in source.rglob("*.kt"):
        text = path.read_text(encoding="utf-8")
        for key in HIDDEN:
            if re.search(r"R\.string\.settings_" + key + r"\b", text):
                raise RuntimeError(f"Hidden setting {key} is still referenced by {path}")
    updater = (root / UPDATER).read_text(encoding="utf-8")
    verify_update_repository(updater)
    gradle = (root / "app/build.gradle.kts").read_text(encoding="utf-8")
    if 'project.findProperty("appId")' not in gradle:
        raise RuntimeError("Upstream removed its applicationId override; review the build configuration")
    print("Verified immutable policy, hidden options, updater, and package override")


def apply(root):
    hub = root / SETTINGS_HUB
    search_source = remove_hidden_search_entries(hub.read_text(encoding="utf-8"))
    filename = "locked-settings.patch" if (root / "app/src/main/java/app/vela/ui/settings/sections/GoogleUses.kt").exists() else "legacy-locked-settings.patch"
    patch = Path(__file__).resolve().parents[1] / "patches" / filename
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=root, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
    hub.write_text(search_source, encoding="utf-8")
    updater = root / UPDATER
    text = updater.read_text(encoding="utf-8")
    updater.write_text(rewrite_update_repository(text), encoding="utf-8")
    test = root / "app/src/test/java/app/vela/ui/KosherPolicyTest.kt"
    test.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "policy-tests/KosherPolicyTest.kt", test)
    verify(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    verify(args.root) if args.verify_only else apply(args.root)
