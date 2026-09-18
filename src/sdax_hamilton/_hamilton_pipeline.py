"""Private correction for Hamilton 1.90.0 async output-pipeline expansion.

This module operates only on modifier instances already copied by
``hamilton_compat._copy_function``. It does not admit pipeline decorators to the
frontend; phase C must call it after separately qualifying the supported forms.
"""

import inspect
from copy import copy
from types import FunctionType, MethodType
from typing import Any, Callable, Mapping, get_type_hints

from hamilton.function_modifiers.configuration import ConfigResolver
from hamilton.function_modifiers.dependencies import LiteralDependency, UpstreamDependency
from hamilton.function_modifiers.macros import Applicable, does, pipe, pipe_input, pipe_output

from ._hamilton_bindings import _merged_default
from ._model import MISSING, InputSpec
from ._types import accepts, compatible, validate_type

_CORRECTION_MARKER = "__sdax_hamilton_async_output_pipeline_corrected__"
_PIPE_MODIFIERS = (pipe_input, pipe, pipe_output)
_SELECTOR_FACTORIES = (
    (ConfigResolver.when().resolves.__code__, ("key_value_pairs",), ConfigResolver.when),
    (ConfigResolver.when_not().resolves.__code__, ("key_value_pairs",), ConfigResolver.when_not),
    (ConfigResolver.when_in().resolves.__code__, ("key_value_group_pairs",), ConfigResolver.when_in),
    (
        ConfigResolver.when_not_in().resolves.__code__,
        ("key_value_group_pairs",),
        ConfigResolver.when_not_in,
    ),
)


def _synchronous_expansion_context(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Supply only the name context used by the pinned upstream transformer.

    The actual producer remains on the input ``Node`` and retains its coroutine
    callable. The proxy is never emitted as a Hamilton node.
    """

    def context(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    context.__name__ = fn.__name__
    context.__qualname__ = fn.__qualname__
    return context


def _corrected_transform_node(original: Callable[..., Any]) -> Callable[..., Any]:
    """Delegate pinned ``pipe_output`` expansion with a synchronous name context."""

    def transform_node(self: pipe_output, node_: Any, config: dict[str, Any], fn: Callable[..., Any]):
        if inspect.iscoroutinefunction(fn):
            return original(node_, config, _synchronous_expansion_context(fn))
        return original(node_, config, fn)

    return transform_node


def correct_copied_async_output_pipelines(fn: Callable[..., Any]) -> None:
    """Correct exact copied ``pipe_output`` modifiers for Hamilton 1.90.0.

    Calling this function repeatedly is idempotent. The caller must pass an
    isolated declaration copy and retain the current frontend's separate
    decorator-admission checks.
    """

    if not inspect.iscoroutinefunction(fn):
        return
    for modifier in getattr(fn, "transform", ()):
        correct_copied_async_output_pipeline(fn, modifier)


def correct_copied_async_output_pipeline(
    fn: Callable[..., Any], modifier: Any
) -> None:
    """Correct one exact copied output pipeline returned by a delayed resolver."""
    if (
        not inspect.iscoroutinefunction(fn)
        or type(modifier) is not pipe_output
        or getattr(modifier, _CORRECTION_MARKER, False)
    ):
        return
    original = modifier.transform_node
    modifier.transform_node = MethodType(_corrected_transform_node(original), modifier)
    setattr(modifier, _CORRECTION_MARKER, True)


def _copy_metadata_container(value: Any) -> Any:
    """Copy finite Hamilton metadata containers while keeping application values intact."""
    if type(value) is list:
        return list(value)
    if type(value) is tuple:
        return tuple(value)
    if type(value) is set:
        return set(value)
    if type(value) is frozenset:
        return frozenset(value)
    return value


def _copy_config_resolver(resolver: ConfigResolver) -> ConfigResolver:
    """Rebuild one known built-in step selector without retaining its closure mapping."""
    if type(resolver) is not ConfigResolver:
        raise ValueError("pipeline steps require a built-in Hamilton configuration selector")
    resolve = resolver.resolves
    if resolve.__closure__ is None or len(resolve.__closure__) != 1:
        raise ValueError("unsupported Hamilton pipeline configuration selector")
    for code, freevars, factory in _SELECTOR_FACTORIES:
        if resolve.__code__ is not code or resolve.__code__.co_freevars != freevars:
            continue
        (pairs,) = (cell.cell_contents for cell in resolve.__closure__)
        if type(pairs) is not dict or any(type(name) is not str for name in pairs):
            raise ValueError("unsupported Hamilton pipeline configuration selector")
        snapshot = {name: _copy_metadata_container(value) for name, value in pairs.items()}
        return factory(**snapshot)
    raise ValueError("unsupported Hamilton pipeline configuration selector")


def _copy_dependency(value: Any) -> Any:
    """Copy binding metadata while retaining literal application values by identity."""
    if type(value) is LiteralDependency or type(value) is UpstreamDependency:
        return copy(value)
    return value


def _copy_applicable(
    applicable: Applicable, copy_function: Callable[[FunctionType], FunctionType]
) -> Applicable:
    """Snapshot one exact pipeline declaration without traversing helper decorators."""
    if type(applicable) is not Applicable:
        raise ValueError("pipeline steps require Hamilton Applicable declarations")
    snapshot = copy(applicable)
    snapshot.args = tuple(_copy_dependency(value) for value in applicable.args)
    snapshot.kwargs = {
        name: _copy_dependency(value) for name, value in applicable.kwargs.items()
    }
    snapshot.resolvers = [_copy_config_resolver(resolver) for resolver in applicable.resolvers]
    snapshot.target = _copy_metadata_container(applicable.target)
    if type(applicable.fn) is not FunctionType:
        raise ValueError("pipeline steps require plain functions")
    snapshot.fn = copy_function(applicable.fn)
    # ``target_fn`` points at the import-time mutation target. It is not called
    # during this expansion, so retaining it does not retain executable helper
    # code or recursively admit that target's decorators.
    return snapshot


def _copy_plain_helper_function(fn: FunctionType) -> FunctionType:
    """Make a direct executable snapshot without traversing its decorator graph."""
    clone = FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__)
    clone.__kwdefaults__ = dict(fn.__kwdefaults__ or {})
    clone.__annotations__ = dict(fn.__annotations__)
    clone.__dict__.update(fn.__dict__)
    clone.__module__ = fn.__module__
    clone.__qualname__ = fn.__qualname__
    clone.__doc__ = fn.__doc__
    return clone


def snapshot_copied_macro_bindings(
    fn: Callable[..., Any], copy_function: Callable[[FunctionType], FunctionType] | None = None
) -> None:
    """Snapshot exact macro binding containers on a declaration copy.

    This is a private construction helper. P2 owns provenance capture and C's
    later compiler admission; callers must pass a declaration already copied by
    ``hamilton_compat._copy_function``.
    """

    helper_memo: dict[int, FunctionType] = {}

    def copy_helper(value: FunctionType) -> FunctionType:
        if copy_function is not None:
            return copy_function(value)
        cached = helper_memo.get(id(value))
        if cached is None:
            cached = _copy_plain_helper_function(value)
            helper_memo[id(value)] = cached
        return cached

    for modifier in getattr(fn, "generate", ()):
        snapshot_copied_macro_modifier(modifier, copy_function=copy_helper)
    for lifecycle in ("inject", "transform"):
        for modifier in getattr(fn, lifecycle, ()):
            snapshot_copied_macro_modifier(modifier, copy_function=copy_helper)


def snapshot_copied_macro_modifier(
    modifier: Any, *, copy_function: Callable[[FunctionType], FunctionType]
) -> None:
    """Snapshot one exact copied macro modifier without resolving or expanding it."""
    if type(modifier) is does:
        modifier.argument_mapping = dict(modifier.argument_mapping)
        if type(modifier.replacing_function) is not FunctionType:
            raise ValueError("does replacements require plain functions")
        modifier.replacing_function = copy_function(modifier.replacing_function)
    elif type(modifier) in _PIPE_MODIFIERS:
        modifier.transforms = tuple(
            _copy_applicable(item, copy_function) for item in modifier.transforms
        )
        for applicable in modifier.transforms:
            _install_selected_step_contract(applicable)


def _function_contract(
    callable_: Callable[..., Any], label: str
) -> tuple[inspect.Signature, dict[str, Any] | None]:
    """Read the bounded contract Hamilton reads for one direct helper callable."""
    signature = inspect.signature(callable_)
    if type(callable_) is not FunctionType:
        # Hamilton accepts callable instances. Their implementation-defined type
        # metadata is not a second annotation language for this frontend.
        return signature, None
    hints = get_type_hints(callable_, include_extras=True)
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise TypeError(f"{label}.{parameter.name}: unsupported helper parameter kind")
        if parameter.name not in hints:
            raise TypeError(f"{label}.{parameter.name}: missing type")
        validate_type(hints[parameter.name])
        if parameter.default is not inspect.Parameter.empty and not accepts(
            parameter.default, hints[parameter.name]
        ):
            raise TypeError(f"{label}.{parameter.name}: invalid default")
    if "return" not in hints:
        raise TypeError(f"{label}: missing return type")
    validate_type(hints["return"])
    return signature, hints


def _ensure_compatible(produced: Any, required: Any, label: str) -> None:
    if not compatible(produced, required):
        raise TypeError(f"{label}: incompatible binding")


def _validate_does_binding(fn: Callable[..., Any], modifier: does) -> None:
    """Check the placeholder/replacement contract before Hamilton adds its wrapper."""
    original_signature, original_hints = _function_contract(fn, fn.__name__)
    if original_hints is None:
        raise TypeError(f"{fn.__name__}: does declaration requires a plain function")
    replacement = modifier.replacing_function
    replacement_signature, replacement_hints = _function_contract(
        replacement, f"{fn.__name__}: replacement"
    )
    original_values = {name: object() for name in original_signature.parameters}
    try:
        replacement_signature.bind(**does.map_kwargs(original_values, modifier.argument_mapping))
    except TypeError as exc:
        raise TypeError(f"{fn.__name__}: replacement binding is invalid") from exc
    if replacement_hints is None:
        return
    _ensure_compatible(
        replacement_hints["return"],
        original_hints["return"],
        f"{fn.__name__}: replacement return",
    )
    for replacement_name in replacement_signature.parameters:
        original_name = modifier.argument_mapping.get(replacement_name, replacement_name)
        if original_name not in original_hints:
            continue
        _ensure_compatible(
            original_hints[original_name],
            replacement_hints[replacement_name],
            f"{fn.__name__}: replacement {replacement_name}",
        )


def _validate_bound_applicable(applicable: Applicable, literal_inputs: dict[str, Any]) -> None:
    """Validate a selected step after Hamilton has bound its direct values."""
    if not callable(applicable.fn):
        raise TypeError("pipeline step requires a callable")
    _, hints = _function_contract(applicable.fn, "pipeline step")
    if hints is None:
        return
    for name, value in literal_inputs.items():
        if not accepts(value, hints[name]):
            raise TypeError(f"pipeline step.{name}: bound literal has wrong type")


def selected_step_input_contracts(
    applicable: Applicable, upstream_inputs: Mapping[str, str]
) -> Mapping[str, InputSpec]:
    """Keep a selected plain helper's contracts after Hamilton merges input names.

    Hamilton's ``Node.reassign_inputs`` retains only one declared type/default
    when several helper parameters bind to the same upstream source. The caller
    invokes this only after Hamilton has selected and bound an exact ``Applicable``.
    """

    signature, hints = _function_contract(applicable.fn, "pipeline step")
    if hints is None:
        return {}
    requirements: dict[str, list[Any]] = {}
    defaults: dict[str, list[object]] = {}
    required = set()
    for parameter in signature.parameters.values():
        source = upstream_inputs.get(parameter.name)
        if source is None:
            continue
        requirements.setdefault(source, []).append(hints[parameter.name])
        if parameter.default is inspect.Parameter.empty:
            required.add(source)
        else:
            defaults.setdefault(source, []).append(parameter.default)
    return {
        source: InputSpec(
            requirements[source][-1],
            (
                MISSING
                if source in required
                else _merged_default(applicable.fn, source, defaults.get(source, []))
            ),
            requirements=tuple(requirements[source]),
        )
        for source in requirements
    }


def _install_selected_step_contract(applicable: Applicable) -> None:
    """Check only transforms Hamilton selected for this expansion path.

    ``chain_transforms`` calls ``Applicable.bind_function_args`` only after its
    configuration resolvers have selected the step. Delegating to the exact
    class method preserves Hamilton's bind behavior and avoids a second selector
    evaluation or a parallel chain interpreter.
    """

    def bind_function_args(self: Applicable, current_param: str | None):
        upstream_inputs, literal_inputs = Applicable.bind_function_args(self, current_param)
        _validate_bound_applicable(self, literal_inputs)
        return upstream_inputs, literal_inputs

    def namespaced(self: Applicable, namespace: Any) -> Applicable:
        derived = Applicable.namespaced(self, namespace)
        _install_selected_step_contract(derived)
        return derived

    applicable.bind_function_args = MethodType(bind_function_args, applicable)
    # ``chain_transforms`` makes this exact derived object before it checks the
    # resolver when a pipeline supplies a namespace. Carry the private bound-step
    # hook onto it without changing Hamilton's class or unrelated instances.
    applicable.namespaced = MethodType(namespaced, applicable)


def validate_copied_macro_bindings(fn: Callable[..., Any]) -> None:
    """Preflight exact copied C-family bindings before wrapper expansion.

    Pipeline literal and default checks are installed on copied ``Applicable``
    objects by ``snapshot_copied_macro_bindings``. They run only after Hamilton
    selects a step for the active configuration path. This function handles the
    ``does`` wrapper contract before its generated callable loses that identity.
    """
    for modifier in getattr(fn, "generate", ()):
        validate_copied_macro_modifier(fn, modifier)


def validate_copied_macro_modifier(fn: Callable[..., Any], modifier: Any) -> None:
    """Preflight one exact copied macro modifier returned by a delayed resolver."""
    if type(modifier) is does:
        _validate_does_binding(fn, modifier)
