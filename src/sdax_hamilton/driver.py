"""Construct a Hamilton graph once and prepare independent reusable SDAX plans."""

from collections.abc import Iterable, Mapping
from types import MappingProxyType, ModuleType
from typing import Any

from .hamilton_compat import compile_modules
from .plan import PreparedPlan


class Driver:
    """A snapshot of module declarations and configuration, with SDAX execution.

    Container mappings are copied; application objects supplied as configuration
    retain their identities. Construct another Driver to change declarations.
    """

    def __init__(self, *modules: ModuleType, config: Mapping[str, Any] | None = None) -> None:
        if config is not None and not isinstance(config, Mapping):
            raise TypeError("Configuration must be a mapping")
        configuration = dict(config) if config is not None else {}
        if any(not isinstance(name, str) or not name for name in configuration):
            raise TypeError("Configuration keys must be nonempty strings")
        self._config = MappingProxyType(configuration)
        self._nodes = compile_modules(modules, self._config)

    def prepare(
        self,
        final_vars: Iterable[str],
        *,
        optional_inputs: Iterable[str] = (),
        override_nodes: Iterable[str] = (),
        check_outputs: bool = True,
    ) -> PreparedPlan:
        """Build one plan for a fixed output, optional-input and override shape."""
        return PreparedPlan(
            self._nodes,
            final_vars,
            config=self._config,
            optional_inputs=optional_inputs,
            override_nodes=override_nodes,
            check_outputs=check_outputs,
        )
