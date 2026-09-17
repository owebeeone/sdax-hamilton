"""Per-invocation callbacks; the public SDAX processor owns scheduling and policy."""

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any

from sdax import AsyncDagTaskProcessor, AsyncTask, task_func

from ._model import NodeSpec
from ._selection import Selection
from ._types import accepts
from .declarations import Acquisition


@dataclass
class Context:
    values: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)
    acquisitions: dict[str, Acquisition[Any]] = field(default_factory=dict)
    cleanup_faults: dict[str, BaseException] = field(default_factory=dict)
    release_cancellations: dict[str, BaseException] = field(default_factory=dict)
    call_cancellations: dict[str, BaseException] = field(default_factory=dict)


async def resolve(value: Any) -> Any:
    # Intentional awaitables-as-data are outside the admitted type contract.
    while inspect.isawaitable(value):
        value = await value
    return value


def call_callback(spec: NodeSpec):
    async def call(ctx: Context) -> None:
        ctx.call_cancellations.pop(spec.name, None)
        if spec.release is not None:
            ctx.acquisitions[spec.name] = Acquisition(_typ=spec.output_type)
        kwargs = {name: ctx.values[name] for name in spec.inputs if name in ctx.values}
        try:
            value = await resolve(spec.fn(**kwargs))
        except asyncio.CancelledError as exc:
            # TaskGroup treats a self-cancelled child differently from a failed
            # child. Record it so a missing result cannot masquerade as success.
            ctx.call_cancellations[spec.name] = exc
            raise
        if spec.release is not None:
            ctx.acquisitions[spec.name] = Acquisition(value, spec.output_type)
        ctx.raw[spec.name] = value

    return call


def check_callback(spec: NodeSpec, check_outputs: bool):
    async def check(ctx: Context) -> None:
        value = ctx.raw[spec.name]
        if check_outputs and not accepts(value, spec.output_type):
            raise TypeError(f"Invalid output from {spec.name} ({spec.origin})")
        ctx.values[spec.name] = value

    return check


def release_callback(spec: NodeSpec):
    release = spec.release
    assert release is not None

    async def close(ctx: Context) -> None:
        state = ctx.acquisitions.get(spec.name, Acquisition(_typ=spec.output_type))
        ctx.release_cancellations.pop(spec.name, None)
        try:
            result = await resolve(release(state))
        except asyncio.CancelledError as exc:
            ctx.release_cancellations[spec.name] = exc
            raise
        if result is not None:
            # This completed release is not retried for a frontend type error.
            ctx.cleanup_faults[spec.name] = TypeError(f"Shutdown must return None: {spec.name}")

    return close


def build_processor(selection: Selection, check_outputs: bool):
    builder = AsyncDagTaskProcessor.builder()
    for name in sorted(selection.active):
        spec = selection.nodes[name]
        dependencies = tuple(f"check:{dep}" for dep in spec.inputs if dep in selection.active)
        builder.add_task(
            AsyncTask(
                f"call:{name}",
                pre_execute=task_func(call_callback(spec), **spec.policy.settings()),
                post_execute=(
                    task_func(release_callback(spec), **spec.release_policy.settings())
                    if spec.release is not None
                    else None
                ),
            ),
            depends_on=dependencies,
        )
        # Validation cannot replay user effects. Ownership lives on the call task,
        # so failed checks still preserve the dependency-derived release obligation.
        builder.add_task(
            AsyncTask(f"check:{name}", pre_execute=task_func(check_callback(spec, check_outputs))),
            depends_on=(f"call:{name}",),
        )
    return builder.build()
