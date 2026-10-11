import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path


INTEGRATION = Path(__file__).resolve().parents[1] / "integration/yapchik"


def parser_classpath():
    cache = Path(os.environ.get("YAPCHIK_PARSER_CACHE", INTEGRATION.parents[1] / ".private/kotlin-parser"))
    cache.mkdir(parents=True, exist_ok=True)
    jars = []
    for artifact in json.loads((INTEGRATION / "parser-lock.json").read_text()):
        target = cache / artifact["name"]
        if not target.exists():
            partial = target.with_suffix(".part")
            try:
                with urllib.request.urlopen(artifact["url"], timeout=120) as response, partial.open("wb") as output:
                    shutil.copyfileobj(response, output)
                if hashlib.sha256(partial.read_bytes()).hexdigest() != artifact["sha256"]:
                    raise RuntimeError("Kotlin parser digest mismatch: " + artifact["name"])
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != artifact["sha256"]:
            raise RuntimeError("Kotlin parser digest mismatch: " + artifact["name"])
        jars.append(str(target.resolve()))
    classpath = os.pathsep.join(jars)
    source = INTEGRATION / "tools/KotlinSyntax.java"
    signature = hashlib.sha256(source.read_bytes()).hexdigest()
    marker = cache / "parser-source.sha256"
    if not marker.exists() or marker.read_text() != signature or not (cache / "KotlinSyntax.class").exists():
        subprocess.run(["javac", "-encoding", "UTF-8", "-cp", classpath, "-d", str(cache), str(source)], check=True)
        marker.write_text(signature)
    return str(cache.resolve()) + os.pathsep + classpath


def parse(paths):
    paths = list(paths)
    if not paths:
        return []
    classpath = parser_classpath()
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "sources.txt"
        manifest.write_text("\n".join(str(Path(path).resolve()) for path in paths), encoding="utf-8")
        output = subprocess.check_output(
            ["java", "-Xmx1g", "-cp", classpath, "KotlinSyntax", str(manifest)], encoding="utf-8",
        )
    files = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    if len(files) != len(paths):
        raise RuntimeError("Kotlin parser did not return every requested file")
    for source in files:
        if source["errors"]:
            raise RuntimeError(f"Invalid Kotlin in {source['path']}: {source['errors']}")
    return files


def text(source, span):
    return source[span[0]:span[1]].decode("utf-8") if span else ""


def contains(outer, inner):
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def rewrite(source, edits):
    replacements = sorted((start, end) for start, end, value in edits if start != end)
    for previous, current in zip(replacements, replacements[1:]):
        if current[0] < previous[1]:
            raise RuntimeError("Overlapping Kotlin rewrites; adapter review required")
    for start, end, replacement in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        source = source[:start] + replacement.encode("utf-8") + source[end:]
    return source
