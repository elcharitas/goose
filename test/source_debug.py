"""Native debug information resolves to Goose source in each imported file."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import toolchain as tc


def check_source_debug(exe, base):
    lldb = shutil.which("lldb")
    if not lldb:
        return "lldb not found"
    base = (Path(base) / "source-debug").resolve()
    suffix = "source space \u00e9" if tc.IS_WINDOWS else 'source space \u00e9 "quoted"'
    sources = base / suffix
    sources.mkdir(parents=True, exist_ok=True)
    main = sources / "main.goose"
    helper = sources / "helpers.goose"
    helper.write_text("fn bump(value: i64) -> i64 {\n"
                      "    let incremented = value + 2;\n"
                      "    return incremented;\n}\n"
                      "simd fn twice(value: i64) -> i64 {\n"
                      "    let doubled = value * 2;\n"
                      "    return doubled;\n}\n", encoding="utf-8")
    main.write_text("import std;\nimport .helpers;\n"
                    "struct Point { x: i64, y: i64 }\n"
                    "fn main() {\n"
                    "    let point = Point { x: 3, y: 4 };\n"
                    "    let answer = bump(point.x) + point.y;\n"
                    "    print(twice(answer));\n}\n", encoding="utf-8")
    binary = base / ("program" + tc.EXE_SUFFIX)
    env = dict(os.environ, GOOSE_HOME=str(base / "home"))
    built = subprocess.run([str(exe), "build", "--offline", "--debug", "-O0", "-o", str(binary), str(main)],
                           env=env, capture_output=True, text=True, errors="replace", timeout=120)
    if built.returncode:
        raise RuntimeError(f"source debug build:\n{built.stdout}{built.stderr}")
    code, out, err = tc.run_capture([binary])
    if code or out != "18\n":
        raise RuntimeError(f"source debug program (exit {code}):\n{out}{err}")
    for path, line in ((main, 5), (main, 6), (main, 7), (helper, 1), (helper, 2), (helper, 5), (helper, 6)):
        result = subprocess.run([lldb, "--batch", "-o", f"image lookup -v -f {path.name} -l {line}", str(binary)],
                                capture_output=True, text=True, errors="replace", timeout=30)
        location = rf"LineEntry: [^\n]*\): {re.escape(str(path))}:{line}(?::|\s|$)"
        if result.returncode or not re.search(location, result.stdout):
            raise RuntimeError(f"no native debug location for {path}:{line}:\n{result.stdout}{result.stderr}")
    return None
