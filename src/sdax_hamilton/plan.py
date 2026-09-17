"""Reusable, immutable prepared plans with fresh per-invocation state."""

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from ._model import NodeSpec
from ._runtime import Context, build_processor
from ._selection import Selection, select
from ._types import accepts
from .errors import retain


@dataclass(frozen=True, slots=True, init=False)
class PreparedPlan:
    """Compile once, then execute repeatedly or concurrently without shared results."""

    _selection: Selection
    _processor: Any

    def __init__(
        self,
        nodes: Mapping[str, NodeSpec],
        final_vars: Iterable[str],
        *,
        config: Mapping[str, Any] | None = None,
        optional_inputs: Iterable[str] = (),
        override_nodes: Iterable[str] = (),
        check_outputs: bool = True,
    ) -> None:
        if type(check_outputs) is not bool:
            raise TypeError("check_outputs must be a boolean")
        selection = select(
            nodes,
            final_vars,
            config=config,
            optional_inputs=optional_inputs,
            override_nodes=override_nodes,
        )
        object.__setattr__(self, "_selection", selection)
        object.__setattr__(self, "_processor", build_processor(selection, check_outputs))

    @property
    def outputs(self) -> tuple[str, ...]:
        return self._selection.outputs

    @property
    def required_inputs(self) -> Mapping[str, tuple[Any, ...]]:
        return self._selection.external

    @property
    def override_nodes(self) -> frozenset[str]:
        return self._selection.overrides

    def _context(
        self, inputs: Mapping[str, Any] | None, overrides: Mapping[str, Any] | None
    ) -> Context:
        supplied, replacements = dict(inputs or {}), dict(overrides or {})
        shape = self._selection
        if supplied.keys() != shape.external.keys():
            raise ValueError(
                f"Input shape mismatch: expected {sorted(shape.external)}, got {sorted(supplied)}"
            )
        if replacements.keys() != shape.overrides:
            raise ValueError(f"Override shape mismatch: expected {sorted(shape.overrides)}")
        for name, requirements in shape.external.items():
            if not all(accepts(supplied[name], typ) for typ in requirements):
                raise TypeError(f"Invalid input: {name}")
        for name, value in replacements.items():
            if not accepts(value, shape.nodes[name].output_type):
                raise TypeError(f"Invalid override: {name}")
        return Context({**shape.config, **supplied, **replacements})

    @asynccontextmanager
    async def open(
        self,
        *,
        inputs: Mapping[str, Any] | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield selected values while owned resources remain alive, then drain shutdown."""
        ctx = self._context(inputs, overrides)
        runner = self._processor.open(ctx)
        primary: BaseException | None = None
        secondary: list[BaseException] = []
        try:
            await runner.run_next()
            if not runner.has_failures() and not ctx.call_cancellations:
                yield {name: ctx.values[name] for name in self.outputs}
        except BaseException as exc:
            primary = exc
        finally:
            # This one owned drain task is always joined. All lifecycle ordering
            # remains inside SDAX; shield only protects cleanup from the caller.
            drain = asyncio.create_task(runner.aclose(), name="sdax-hamilton-shutdown")
            while not drain.done():
                try:
                    await asyncio.shield(drain)
                except asyncio.CancelledError as exc:
                    if not isinstance(primary, asyncio.CancelledError):
                        if primary is not None:
                            secondary.append(primary)
                        primary = exc
                except BaseException:
                    break
            try:
                drain.result()
            except BaseException as exc:
                secondary.append(exc)
            core_errors = runner.failures()
            # Sibling/timeout cancellation is expected when another failure already
            # explains termination. Preserve spontaneous forward cancellation when
            # it would otherwise be swallowed as a successful TaskGroup outcome.
            if primary is None and not core_errors:
                secondary.extend(ctx.call_cancellations.values())
            secondary.extend(core_errors)
            secondary.extend(ctx.cleanup_faults.values())
            secondary.extend(ctx.release_cancellations.values())
            if primary is not None:
                retain(primary, secondary)
                raise primary
            if secondary:
                raise BaseExceptionGroup("SDAX Hamilton execution/cleanup failed", secondary)

    async def execute(
        self,
        *,
        inputs: Mapping[str, Any] | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return ordinary results after shutdown; resource outputs require open()."""
        if any(self._selection.nodes[name].release is not None for name in self.outputs):
            raise ValueError("Use open() to access resource outputs within their lifetime")
        async with self.open(inputs=inputs, overrides=overrides) as result:
            return result
