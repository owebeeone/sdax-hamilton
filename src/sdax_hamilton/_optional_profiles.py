"""Identify explicitly used shipped modifiers without importing optional backends.

Identification is not admission: the compiler still owns each family's gate.
The fixed dependency profiles pin the versions used by the qualification tests;
their presence here does not claim that a family has passed its gate.
"""

import sys
from importlib import metadata
from typing import Any

_MODIFIERS = (
    ("hamilton.plugins.h_pandas", "with_columns", "pandas"),
    (
        "hamilton.experimental.decorators.parameterize_frame",
        "parameterize_frame",
        "pandas",
    ),
    ("hamilton.plugins.h_polars", "with_columns", "polars"),
    ("hamilton.plugins.h_polars_lazyframe", "with_columns", "polars"),
    ("hamilton.plugins.h_spark", "with_columns", "spark"),
    ("hamilton.plugins.h_spark", "select", "spark"),
    ("hamilton.plugins.h_spark", "require_columns", "spark"),
    ("hamilton.plugins.h_pydantic", "check_output", "pydantic"),
    ("hamilton.plugins.h_pandera", "check_output", "pandera"),
)
_VERSIONS = {
    "pandas": {"pandas": "3.0.6"},
    "polars": {"polars": "1.44.2"},
    "pydantic": {"pydantic": "2.13.5"},
    "pandera": {"pandera": "0.33.1", "pandas": "3.0.6"},
    "spark": {"pyspark": "4.0.1", "pandas": "2.3.3", "pyarrow": "21.0.0"},
}


def identify_optional_modifier(modifier: Any) -> str | None:
    """Match an exact, already loaded shipped class; subclasses stay unsupported."""
    cls = type(modifier)
    for module_name, attribute, profile in _MODIFIERS:
        if cls.__module__ != module_name:
            continue
        module = sys.modules.get(module_name)
        # Inspect the module dictionary directly: no module __getattr__ callback.
        if module is not None and vars(module).get(attribute) is cls:
            return profile
    return None


def validate_optional_profile(profile: str) -> None:
    """Check declared distributions only after an admitted modifier requests them."""
    if profile not in _VERSIONS:
        raise ValueError(f"Unknown Hamilton dependency profile: {profile}")
    for distribution, expected in _VERSIONS[profile].items():
        try:
            installed = metadata.version(distribution)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"Hamilton {profile} profile requires {distribution}=={expected}"
            ) from exc
        if installed != expected:
            raise RuntimeError(
                f"Hamilton {profile} profile requires {distribution}=={expected}; "
                f"found {installed}"
            )
