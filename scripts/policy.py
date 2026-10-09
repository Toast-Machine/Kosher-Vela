import argparse
import re
import shutil
import subprocess
from pathlib import Path


POLICY = {"ShowReviews": False, "LoadPhotos": False, "LiveReviews": False, "HideExternalLinks": True}
HIDDEN = ("show_reviews", "read_all_reviews", "load_photos", "hide_external_links", "reviews_on_tap", "photos_on_tap")
UPDATER = "app/src/main/java/app/vela/update/SelfUpdater.kt"


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
    if "PimpinPumpkin/Vela" in updater or "Toast-Machine/Kosher-Vela" not in updater:
        raise RuntimeError("The APK updater does not point exclusively to Kosher-Vela")
    gradle = (root / "app/build.gradle.kts").read_text(encoding="utf-8")
    if 'project.findProperty("appId")' not in gradle:
        raise RuntimeError("Upstream removed its applicationId override; review the build configuration")
    print("Verified immutable policy, hidden options, updater, and package override")


def apply(root):
    filename = "locked-settings.patch" if (root / "app/src/main/java/app/vela/ui/settings/sections/GoogleUses.kt").exists() else "legacy-locked-settings.patch"
    patch = Path(__file__).resolve().parents[1] / "patches" / filename
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=root, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
    updater = root / UPDATER
    text = updater.read_text(encoding="utf-8")
    if "PimpinPumpkin/Vela" not in text:
        raise RuntimeError("Cannot find the expected upstream update endpoints")
    updater.write_text(text.replace("PimpinPumpkin/Vela", "Toast-Machine/Kosher-Vela"), encoding="utf-8")
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
