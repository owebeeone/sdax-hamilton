"""Run the base conformance profile without ambient optional backend imports."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import sdax_hamilton


def test_hamilton_imports_stay_inside_the_compiler_boundary():
    """Inspect all branches of installed source, including inactive imports."""
    package = Path(sdax_hamilton.__file__).resolve().parent
    compiler_modules = {"hamilton_compat", "_construction", "_discovery"}
    violations = []
    for path in package.glob("*.py"):
        if path.stem in compiler_modules or path.stem.startswith("_hamilton_"):
            continue
        for statement in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(statement, ast.Import):
                names = [alias.name for alias in statement.names]
            elif isinstance(statement, ast.ImportFrom) and statement.level == 0:
                names = [statement.module or ""]
            if any(name.split(".")[0] == "hamilton" for name in names):
                violations.append(f"{path.name}:{statement.lineno}")
    assert not violations, f"Hamilton imports outside compiler boundary: {violations}"


def test_base_profile_runs_with_optional_packages_unavailable(tmp_path):
    source = '''
import asyncio
import importlib.abc
import sys
import types

# Hamilton reads its user configuration when registry is imported. Override
# autoload only in this isolated process, before importing either driver.
from hamilton import registry
registry.disable_autoload()
attempted_optional_imports = []

class OptionalPackagesUnavailable(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"ray", "polars", "pyspark", "pandera", "pydantic"}:
            # Hamilton probes installed validators independently of registry
            # autoload. Isolate the base profile even on a developer's rich env.
            attempted_optional_imports.append(fullname.split(".")[0])
            raise ModuleNotFoundError("Unavailable in base profile: " + fullname, name=fullname)
        return None

sys.meta_path.insert(0, OptionalPackagesUnavailable())
from hamilton import driver
from sdax_hamilton import Driver

module = types.ModuleType("isolated_base_profile")
sys.modules[module.__name__] = module
exec("""
from hamilton.function_modifiers import cache
from hamilton.function_modifiers.metadata import ray_remote_options
calls = []
@cache(behavior="default", format="pickle")
@ray_remote_options(num_cpus=1)
def result() -> int:
    calls.append("local")
    return len(calls)
""", module.__dict__)

oracle = driver.Builder().with_modules(module).build()
assert oracle.execute(["result"]) == {"result": 1}
plan = Driver(module).prepare(["result"])
assert asyncio.run(plan.execute()) == {"result": 2}
assert asyncio.run(plan.execute()) == {"result": 3}
assert module.calls == ["local", "local", "local"]
assert not {"ray", "polars", "pyspark", "pandera", "pydantic"}.intersection(sys.modules)
# Pin the upstream distinction: default-validator discovery can probe Pandera;
# inactive Ray metadata never asks for the remote runtime.
assert "pandera" in attempted_optional_imports
assert "ray" not in attempted_optional_imports
'''
    environment = dict(os.environ)
    # Works both for source qualification and an installed wheel/sdist.
    environment["PYTHONPATH"] = str(Path(sdax_hamilton.__file__).resolve().parent.parent)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", "-c", source],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
