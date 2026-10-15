from pathlib import Path

from policy import UPDATER, apply, rewrite_update_repository, verify, verify_update_repository


VARIANTS = {
    "kosher": {"package": "app.vela.kosher", "kosher": True, "yapchik": True},
}
BUILD_PROFILE = "kosher-with-yapchik-v8"


def configure_updater(root, variant):
    path = root / UPDATER
    source = path.read_text(encoding="utf-8")
    anchor = 'val all = (0 until assets.length()).map { assets.getJSONObject(it) }'
    if source.count(anchor) != 1:
        raise RuntimeError("Upstream APK selection changed; review variant update isolation")
    source = rewrite_update_repository(source)
    source = source.replace(anchor, anchor + '\n            .filter { it.optString("name").startsWith("'
                            + variant + '-vela-") }')
    path.write_text(source, encoding="utf-8")


def customize(root, variant):
    features = VARIANTS[variant]
    apply_features(root, kosher=features["kosher"], yapchik=features["yapchik"])
    configure_updater(root, variant)
    verify_variant(root, variant)


def apply_features(root, kosher=False, yapchik=False):
    if kosher:
        apply(root)
    if yapchik:
        from yapchik import integrate
        integrate(root)


def verify_variant(root, variant):
    features = VARIANTS[variant]
    if features["kosher"]:
        verify(root)
    updater = (root / UPDATER).read_text(encoding="utf-8")
    verify_update_repository(updater)
    if 'startsWith("' + variant + '-vela-")' not in updater or "PimpinPumpkin/Vela" in updater:
        raise RuntimeError("Variant updater can select another variant")
    if features["yapchik"]:
        from yapchik import verify_integration
        verify_integration(root)
