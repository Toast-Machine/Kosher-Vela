import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from kotlin_source import INTEGRATION, contains, parse, rewrite, text


PIN = "bf5021c648ae6adff60644a7cf2633c938d70ead"
RUNTIME = "app.vela.yapchik."
BUTTONS = {
    "Button", "TextButton", "OutlinedButton", "ElevatedButton", "FilledTonalButton", "IconButton",
    "FilledIconButton", "FilledTonalIconButton", "OutlinedIconButton", "FloatingActionButton",
    "SmallFloatingActionButton", "LargeFloatingActionButton", "ExtendedFloatingActionButton",
    "DropdownMenuItem", "AssistChip", "SuggestionChip", "InputChip", "FilterChip", "RadioButton",
    "Surface", "Card", "ElevatedCard", "OutlinedCard", "Checkbox", "Switch", "IconToggleButton",
    "FilledIconToggleButton", "FilledTonalIconToggleButton", "OutlinedIconToggleButton",
}
MODIFIERS = {"clickable", "combinedClickable", "selectable", "toggleable", "dpadClickable"}
TOGGLES = {"Checkbox", "Switch", "IconToggleButton", "FilledIconToggleButton", "FilledTonalIconToggleButton", "OutlinedIconToggleButton"}
WINDOWS = {"Dialog", "Popup", "ModalBottomSheet", "DropdownMenu", "BasicAlertDialog", "AlertDialog"}
PRESENTATION = {"Text", "Icon", "BasicTextField", "TextField", "OutlinedTextField"}
REPEATS = {"items", "itemsIndexed", "forEach", "forEachIndexed"}
UNSUPPORTED = {"triStateToggleable", "TriStateCheckbox"}
MODIFIER_POSITIONS = {name: 1 for name in BUTTONS}
MODIFIER_POSITIONS.update({name: 2 for name in TOGGLES | {"RadioButton", "DropdownMenuItem", "AssistChip", "SuggestionChip"}})
MODIFIER_POSITIONS.update({"FilterChip": 3, "InputChip": 3})


def argument(call, name, position=None):
    named = [value for value in call["arguments"] if value["name"] == name]
    if named:
        return named[0]["value"]
    positional = [value for value in call["arguments"] if value["name"] is None]
    return positional[position]["value"] if position is not None and len(positional) > position else None


def resolve(file, call, source):
    name = call["callee"]
    full = text(source, call["full"])
    if full.startswith(("androidx.", "app.vela.")) and full.split("(", 1)[0].endswith("." + name):
        return full.split("(", 1)[0]
    local = [function for function in file["functions"] if function["name"] == name]
    if local:
        return file["package"] + "." + name
    exact = [entry["name"] for entry in file["imports"]
             if not entry["star"] and (entry["alias"] or entry["name"].rsplit(".", 1)[-1]) == name]
    if len(exact) == 1:
        return exact[0]
    stars = [entry["name"] + "." + name for entry in file["imports"] if entry["star"]
             and entry["name"] in ("androidx.compose.material3", "androidx.compose.material",
                                    "androidx.compose.foundation", "androidx.compose.foundation.selection",
                                    "androidx.compose.foundation.layout", "androidx.compose.ui.window")]
    return stars[0] if len(stars) == 1 else None


def ui_composables(files):
    candidates = {}
    for file in files:
        for function in file["functions"]:
            if not function["composable"]:
                continue
            symbol = file["package"] + "." + function["name"]
            result = function["return_type"]
            unit = result in {"Unit", "kotlin.Unit"} or result is None and function["block_body"]
            candidates.setdefault(symbol, []).append(unit)
    return {symbol for symbol, overloads in candidates.items() if all(overloads)}


def edits_for_file(file, composables=None):
    path = Path(file["path"])
    source = path.read_bytes().replace(b"\r\n", b"\n")
    edits = []
    report = {"discovered": [], "instrumented": [], "excluded": [], "unsupported": []}
    calls = file["calls"]
    functions = {tuple(function["span"]): function for function in file["functions"]}
    if composables is None:
        composables = ui_composables([file])
    actions = []

    def record(category, call, reason):
        report[category].append({"file": path.name, "line": call["line"], "symbol": call["callee"], "reason": reason})

    def insert(span, value):
        edits.append((span[0], span[0], value))

    def wrap(span, before, after):
        edits.extend([(span[0], span[0], before), (span[1], span[1], after)])

    for call in calls:
        symbol = resolve(file, call, source)
        name = symbol.rsplit(".", 1)[-1] if symbol else call["callee"]
        recognized = name in BUTTONS | MODIFIERS | UNSUPPORTED
        if not recognized:
            if name in {"pointerInput", "detectTapGestures", "detectDragGestures"}:
                record("excluded", call, "Gesture-only input; outside button/click scope")
            continue
        if symbol and not symbol.startswith("androidx.compose.") and symbol != "app.vela.ui.dpadClickable":
            continue
        is_modifier = name in MODIFIERS
        if name in {"Surface", "Card", "ElevatedCard", "OutlinedCard"} and not argument(call, "onClick"):
            continue
        record("discovered", call, "Supported activation mechanism")
        if symbol is None and name == "dpadClickable" and file["package"] == "app.vela.ui":
            symbol = "app.vela.ui.dpadClickable"
        if symbol is None or name in UNSUPPORTED:
            record("unsupported", call, "Unresolved import or unsupported toggle state; adapter review required")
            continue
        function = functions.get(tuple(call["function"] or []))
        if function and function["name"] == "dpadClickable" and path.name == "DpadFocus.kt":
            record("excluded", call, "Instrumented at dpadClickable caller, not again inside its adapter")
            continue
        toggle = name in TOGGLES or name == "toggleable"
        selected = argument(call, "value" if name == "toggleable" else "checked" if toggle else "selected", 0 if toggle or name in {"RadioButton", "FilterChip", "InputChip", "selectable"} else None)
        handler = argument(call, "onCheckedChange" if name in TOGGLES else "onValueChange" if name == "toggleable" else "onClick",
                           1 if name in TOGGLES | {"RadioButton", "FilterChip", "InputChip", "DropdownMenuItem"} else 0 if name in BUTTONS else None)
        trailing_handler = handler is None and is_modifier and bool(call["lambdas"])
        if trailing_handler:
            handler = call["lambdas"][-1]["span"]
        if handler is None or text(source, handler) == "null":
            record("excluded" if handler else "unsupported", call, "No activation callback" if handler else "Cannot resolve activation callback")
            continue
        target = call
        if is_modifier:
            candidates = [outer for outer in calls if outer != call and outer["callee"][:1].isupper()
                          and any(value["value"] and contains(value["value"], call["full"]) for value in outer["arguments"])]
            if not candidates:
                record("unsupported", call, "Modifier activation is not owned by a supported composable control")
                continue
            target = min(candidates, key=lambda outer: outer["full"][1] - outer["full"][0])
        if any(previous["full"] == target["full"] for previous_call, previous in actions):
            record("unsupported", call, "Multiple activations share one control; presentation ownership requires adapter review")
            continue
        enabled_position = (3 if name in TOGGLES | {"RadioButton", "DropdownMenuItem", "AssistChip", "SuggestionChip"}
                            else 4 if name in {"FilterChip", "InputChip"}
                            else 2 if name in {"Surface", "Card", "ElevatedCard", "OutlinedCard"} or name.endswith("Button") and "Floating" not in name
                            else None)
        enabled = argument(call, "enabled", enabled_position)
        source_id = file["package"] + "." + path.stem
        source_id += ":" + str(call["line"]) + ":" + str(call["span"][0])
        variable = "yapchikAction" + str(call["span"][0])
        search = path.name == "SearchBar.kt" and function and function["name"] == "SearchBar" and is_modifier and "fieldArmed = true" in text(source, handler)
        before = RUNTIME + f'YapchikAction({json.dumps(source_id)}, null'
        if search:
            before += ", search = true"
        if name in {"Checkbox", "Switch", "RadioButton"}:
            before += ", control = " + json.dumps(name)
        before += f") {{ {variable} -> "
        if toggle:
            if selected is None:
                record("unsupported", call, "Toggle checked state could not be resolved")
                continue
            binding = "bindNullableToggle" if name in {"Checkbox", "Switch"} else "bindToggle"
            edits.append((*handler, variable + "." + binding + "(" + text(source, handler) + ")"))
            edits.append((*selected, variable + ".trackSelected(" + text(source, selected) + ")"))
        else:
            binding = "bindNullable" if name == "RadioButton" else "bind"
            edits.append((*handler, variable + "." + binding + "(" + text(source, handler) + ")"))
            if selected:
                edits.append((*selected, variable + ".trackSelected(" + text(source, selected) + ")"))
        if enabled:
            edits.append((*enabled, variable + ".trackEnabled(" + text(source, enabled) + ")"))
        if trailing_handler:
            replacement_index = next(index for index, edit in enumerate(edits) if edit[:2] == tuple(handler))
            replacement = edits[replacement_index][2]
            parameter_name = "onValueChange" if toggle else "onClick"
            if call["arguments_span"]:
                point = call["arguments_span"][1] - 1
                previous = source[call["arguments_span"][0] + 1:point].rstrip()
                separator = " " if not previous or previous.endswith(b",") else ", "
                insert([point, point], separator + parameter_name + " = " + replacement)
                edits[replacement_index] = (*handler, "")
            else:
                edits[replacement_index] = (*handler, "(" + parameter_name + " = " + replacement + ")")
        wrap(target["full"], before, " }")
        if is_modifier:
            insert([call["full"][1], call["full"][1]], f".then({variable}.modifier)")
        else:
            modifier = argument(call, "modifier", MODIFIER_POSITIONS[name])
            if modifier:
                wrap(modifier, "(", f").then({variable}.modifier)")
            elif call["arguments_span"]:
                point = call["arguments_span"][1] - 1
                previous = source[call["arguments_span"][0] + 1:point].rstrip()
                separator = " " if not previous or previous.endswith(b",") else ", "
                insert([point, point], separator + f"modifier = {variable}.modifier")
            else:
                record("unsupported", call, "Button argument list is unavailable")
                continue
        actions.append((call, target))
        record("instrumented", call, "Live action reference; original callback and presentation retained")

    for call in calls:
        symbol = resolve(file, call, source)
        name = symbol.rsplit(".", 1)[-1] if symbol else call["callee"]
        if name in PRESENTATION and symbol and symbol.startswith("androidx.compose."):
            value = argument(call, "imageVector", 0) if name == "Icon" else argument(call, "text" if name == "Text" else "value", 0)
            if value is None:
                if name == "Icon":
                    value = argument(call, "painter") or argument(call, "bitmap")
            if value:
                variable = "yapchikVisual" + str(call["span"][0])
                if name == "Icon":
                    description = argument(call, "contentDescription", 1)
                    if description is None:
                        record("unsupported", call, "Icon accessibility value could not be resolved")
                        continue
                    wrap(call["full"], RUNTIME + f"YapchikIcon({text(source, value)}, {text(source, description)}) {{ {variable}, yapchikDescription -> ", " }")
                    edits.append((*description, "yapchikDescription"))
                else:
                    wrap(call["full"], RUNTIME + f"YapchikText({text(source, value)}) {{ {variable} -> ", " }")
                edits.append((*value, variable))
        if name in WINDOWS and symbol and symbol.startswith("androidx.compose."):
            slots = {"content", "confirmButton", "dismissButton", "title", "text", "icon"}
            content_callbacks = call["lambdas"] + [entry["lambda"] for entry in call.get("named_lambdas", []) if entry["name"] in slots]
            if not content_callbacks:
                record("unsupported", call, "Native window content requires an ownership adapter")
            for callback in content_callbacks:
                if callback["body"]:
                    wrap(callback["body"], RUNTIME + "YapchikScope(blocking = true, suppress = true) { ", " }")
                    record("excluded", call, "Blocking native window suppresses underlying softkeys")
        repeat_callbacks = call["lambdas"] + [entry["lambda"] for entry in call.get("named_lambdas", []) if entry["name"] in {"itemContent", "action"}]
        if name in REPEATS and repeat_callbacks:
            callback = repeat_callbacks[-1]
            body = callback["body"]
            children = [child for child in calls if body and contains(body, child["span"]) and
                        (resolve(file, child, source) in composables or
                         (resolve(file, child, source) or "").startswith(("androidx.compose.material", "androidx.compose.foundation.layout"))
                         and child["callee"][:1].isupper())]
            if not children:
                continue
            parameters = callback["parameters"]
            parameter = parameters[-1] if parameters else "it"
            top_level = [child for child in children if not any(other != child and contains(other["full"], child["full"]) for other in children)]
            for child in top_level:
                site = json.dumps(file["package"] + "." + path.stem + ":repeat:" + str(call["span"][0]))
                edits.append((child["full"][0], child["full"][0], RUNTIME + f"YapchikItem({site}, {parameter}) {{ "))
                edits.append((child["full"][1], child["full"][1], " }"))
        if symbol in composables and name[:1].isupper() and name not in {"YapchikHost", "YapchikPreferences"}:
            site = json.dumps(file["package"] + "." + path.stem + ":component:" + str(call["span"][0]))
            edits.append((call["full"][0], call["full"][0], RUNTIME + f"YapchikItem({site}, Unit) {{ "))
            edits.append((call["full"][1], call["full"][1], " }"))
        if symbol in composables and (name.endswith("Sheet") or name in {"FullScreenReviewsContent", "PhotoGalleryContent", "StreetViewScreen"}):
            edits.append((call["full"][0], call["full"][0], RUNTIME + "YapchikScope(blocking = true) { "))
            edits.append((call["full"][1], call["full"][1], " }"))

    for loop in file.get("loops", []):
        body = loop["body"]
        children = [child for child in calls if body and contains(body, child["full"]) and
                    (resolve(file, child, source) in composables or
                     (resolve(file, child, source) or "").startswith(("androidx.compose.material", "androidx.compose.foundation.layout"))
                     and child["callee"][:1].isupper())]
        for child in children:
            if any(other != child and contains(other["full"], child["full"]) for other in children):
                continue
            if not loop["parameter"] or loop["parameter"] == "_":
                record("unsupported", child, "Repeated control has no usable loop identity")
                continue
            site = json.dumps(file["package"] + "." + path.stem + ":loop:" + str(loop["span"][0]))
            wrap(child["full"], RUNTIME + f'YapchikItem({site}, {loop["parameter"]}) {{ ', " }")

    if path.name == "MainActivity.kt":
        roots = [call for call in calls if call["callee"] == "VelaRoot"]
        if len(roots) != 1:
            report["unsupported"].append({"file": path.name, "reason": "Main activity root changed"})
        else:
            wrap(roots[0]["full"], RUNTIME + "YapchikHost { ", " }")
    if path.name == "SearchBar.kt":
        searches = [call for call in calls if call["callee"] == "clickable" and
                    any("fieldArmed = true" in text(source, callback["span"]) for callback in call["lambdas"])]
        if len(searches) != 1:
            report["unsupported"].append({"file": path.name, "reason": "Search activation adapter changed; review right-softkey ownership"})
    if path.name == "VelaRoot.kt":
        for call in calls:
            if call["callee"] == "MapScreen":
                if "val showSettings" not in source.decode("utf-8"):
                    record("unsupported", call, "Persistent map ownership adapter changed")
                else:
                    wrap(call["full"], RUNTIME + "YapchikScope(active = !showSettings) { ", " }")
    if path.name == "SettingsHub.kt":
        scaffold = [call for call in calls if call["callee"] == "SettingsScaffold" and call["lambdas"]]
        if len(scaffold) != 1:
            report["unsupported"].append({"file": path.name, "reason": "Softkey settings insertion point changed"})
        else:
            insert(scaffold[0]["lambdas"][0]["body"], RUNTIME + "YapchikPreferences()\n")
    return rewrite(source, edits), report


def instrument(paths, report_path):
    files = parse(paths)
    report = {"parser": "Kotlin PSI 2.1.20", "yapchik_revision": PIN,
              "discovered": [], "instrumented": [], "excluded": [], "unsupported": []}
    prepared = []
    composables = ui_composables(files)
    for file in files:
        result, coverage = edits_for_file(file, composables)
        prepared.append((Path(file["path"]), result))
        for category in coverage:
            report[category].extend(coverage[category])
    Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["unsupported"]:
        raise RuntimeError(f"Yapchik coverage has {len(report['unsupported'])} cases requiring review; see {report_path}")
    with tempfile.TemporaryDirectory() as temporary:
        candidates = []
        for index, (path, result) in enumerate(prepared):
            candidate = Path(temporary) / (str(index) + "-" + path.name)
            candidate.write_bytes(result)
            candidates.append(candidate)
        try:
            parse(candidates)
        except RuntimeError as error:
            report["unsupported"].append({"reason": "Transformed Kotlin validation failed", "detail": str(error)})
            Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            raise
    for path, result in prepared:
        path.write_bytes(result)
    return report


def configure_diagnostics(runtime):
    if os.environ.get("YAPCHIK_DIAGNOSTICS") != "true":
        return
    path = runtime / "KeyDiagnostics.kt"
    source = path.read_text(encoding="utf-8")
    anchor = "private const val KEY_DIAGNOSTICS = false"
    if source.count(anchor) != 1:
        raise RuntimeError("Yapchik diagnostics flag changed; refusing an ambiguous diagnostic build")
    path.write_text(source.replace(anchor, "private const val KEY_DIAGNOSTICS = true"), encoding="utf-8")


def integrate(root):
    root = Path(root)
    if (root / "yapchik-coverage.json").exists():
        raise RuntimeError("Yapchik instrumentation must run once on a fresh checkout")
    paths = list((root / "app/src/main/java/app/vela/ui").rglob("*.kt"))
    paths.append(root / "app/src/main/java/app/vela/MainActivity.kt")
    report = instrument(paths, root / "yapchik-coverage.json")
    if not report["instrumented"]:
        raise RuntimeError("No Yapchik controls discovered")
    module = root / "yapchik"
    verify_vendor()
    shutil.copytree(INTEGRATION / "vendor/yapchik", module)
    app_gradle = (root / "app/build.gradle.kts").read_text(encoding="utf-8")
    sdk = re.search(r"compileSdk\s*=\s*(\d+)", app_gradle)
    if not sdk:
        raise RuntimeError("Upstream compileSdk configuration changed")
    module_gradle = (module / "build.gradle.kts").read_text()
    module_gradle = module_gradle.replace("compileSdk = 37", "compileSdk = " + sdk[1])
    if "alias(libs.plugins.kotlin.android)" in app_gradle:
        module_gradle = module_gradle.replace("alias(libs.plugins.android.library)", "alias(libs.plugins.android.library)\n    alias(libs.plugins.kotlin.android)")
    (module / "build.gradle.kts").write_text(module_gradle, encoding="utf-8")
    settings = root / "settings.gradle.kts"
    settings.write_text(settings.read_text() + '\ninclude(":yapchik")\n', encoding="utf-8")
    (root / "app/build.gradle.kts").write_text(app_gradle + '\ndependencies { implementation(project(":yapchik")) }\n', encoding="utf-8")
    runtime = root / "app/src/main/java/app/vela/yapchik"
    shutil.copytree(INTEGRATION / "runtime", runtime)
    configure_diagnostics(runtime)
    tests = root / "app/src/test/java/app/vela/yapchik"
    shutil.copytree(INTEGRATION / "tests", tests)
    verify_integration(root)
    return report


def verify_integration(root):
    report = json.loads((root / "yapchik-coverage.json").read_text())
    if report["unsupported"] or not report["instrumented"] or report["yapchik_revision"] != PIN:
        raise RuntimeError("Yapchik coverage or pinned revision is invalid")
    if not (root / "yapchik/LICENSE").exists() or not (root / "yapchik/NOTICE").exists():
        raise RuntimeError("Missing Yapchik license or notices")
    lock = verify_vendor()
    for relative, digest in lock["files"].items():
        installed = root / "yapchik" / relative
        if vendor_digest(installed) != digest:
            raise RuntimeError("Pinned Yapchik source was modified: " + str(installed))


def vendor_digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_vendor():
    lock = json.loads((INTEGRATION / "vendor-lock.json").read_text())
    if lock["revision"] != PIN:
        raise RuntimeError("Yapchik vendor lock has an unexpected revision")
    for relative, digest in lock["files"].items():
        path = INTEGRATION / "vendor/yapchik" / relative
        if vendor_digest(path) != digest:
            raise RuntimeError("Vendored Yapchik digest mismatch: " + relative)
    return lock


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    verify_integration(args.root) if args.verify_only else integrate(args.root)
