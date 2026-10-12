import hashlib
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from kotlin_source import INTEGRATION, parse, parser_classpath
from yapchik import edits_for_file


ARTIFACTS = {
    "org/jetbrains/annotations/13.0/annotations-13.0.jar": "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478",
    "org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar": "66fdef91e9739348df7a096aa384a5685f4e875584cce89386a7a47251c4d8e9",
    "junit/junit/4.13.2/junit-4.13.2.jar": "8e495b634469d64fb8acfa3495a065cbacc8a0fff55ce1e31007be4c16dc57d3",
}


def main():
    cache = INTEGRATION.parents[1] / ".private/kotlin-tests"
    cache.mkdir(parents=True, exist_ok=True)
    dependencies = []
    for artifact, digest in ARTIFACTS.items():
        target = cache / Path(artifact).name
        if not target.exists():
            with urllib.request.urlopen("https://repo.maven.apache.org/maven2/" + artifact, timeout=120) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError("Test dependency digest mismatch: " + artifact)
            target.write_bytes(data)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Test dependency digest mismatch: " + artifact)
        dependencies.append(str(target.resolve()))
    classpath = parser_classpath() + os.pathsep + os.pathsep.join(dependencies)
    with tempfile.TemporaryDirectory() as classes:
        fixture = INTEGRATION / "compiler-fixtures/ValueComposables.kt"
        transformed, report = edits_for_file(parse([fixture])[0])
        if report["unsupported"]:
            raise RuntimeError("Compiler regression fixture has unsupported cases")
        source = Path(classes) / "ValueComposables.kt"
        source.write_bytes(transformed)
        subprocess.run([
            "java", "-cp", classpath, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
            "-no-stdlib", "-no-reflect", "-jvm-target", "17", "-classpath", classpath,
            "-d", classes, str(INTEGRATION / "runtime/ActionStore.kt"),
            str(INTEGRATION / "runtime/MenuPresentation.kt"),
            str(INTEGRATION / "tests/ActionStoreTest.kt"),
            str(INTEGRATION / "tests/MenuPresentationTest.kt"),
            str(source), str(INTEGRATION / "compiler-fixtures/ComposeAnnotation.kt"),
            str(INTEGRATION / "compiler-fixtures/ItemScope.kt"),
        ], check=True)
        subprocess.run([
            "java", "-cp", classes + os.pathsep + classpath,
            "org.junit.runner.JUnitCore", "app.vela.yapchik.ActionStoreTest", "app.vela.yapchik.MenuPresentationTest",
        ], check=True)


if __name__ == "__main__":
    main()
