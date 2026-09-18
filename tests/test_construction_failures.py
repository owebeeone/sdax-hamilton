"""Construction errors cross the Hamilton compatibility boundary without logging."""

import asyncio
import logging
import traceback

import pytest

from sdax_hamilton._construction import resolve_nodes, wrap_lifecycle
from sdax_hamilton.hamilton_compat import _copy_function


def _wrapped_config_function(module_factory, predicate):
    module = module_factory(
        """
from hamilton.function_modifiers import config
@config(predicate)
def result() -> int:
    return 7
""",
        predicate=predicate,
    )
    copied = _copy_function(module.result)
    for modifier in copied.resolve:
        wrap_lifecycle(modifier)
    return copied


def test_custom_config_error_is_original_once_and_is_not_logged(module_factory, caplog):
    sentinel = ValueError("private predicate sentinel")
    calls = []
    hamilton_logger = logging.getLogger("hamilton.function_modifiers.base")
    state = (hamilton_logger.level, hamilton_logger.propagate, tuple(hamilton_logger.handlers))

    def predicate(values):
        calls.append(dict(values))
        raise sentinel

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError) as caught:
            resolve_nodes(_wrapped_config_function(module_factory, predicate), {"enabled": True})

    assert caught.value is sentinel
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert "_ConstructionFailure" not in "".join(traceback.format_exception(caught.value))
    assert calls == [{"enabled": True}]
    assert "private predicate sentinel" not in caplog.text
    assert not [record for record in caplog.records if record.name == hamilton_logger.name]
    assert (hamilton_logger.level, hamilton_logger.propagate, tuple(hamilton_logger.handlers)) == state


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(), asyncio.CancelledError()])
def test_base_exceptions_pass_through_unwrapped(module_factory, failure):
    def predicate(_):
        raise failure

    with pytest.raises(type(failure)) as caught:
        resolve_nodes(_wrapped_config_function(module_factory, predicate), {})

    assert caught.value is failure


def test_nested_wrappers_preserve_the_original_exception_identity(monkeypatch):
    sentinel = ValueError("nested sentinel")

    class Modifier:
        @classmethod
        def get_lifecycle_name(cls):
            return "resolve"

        def resolve(self, *_args, **_kwargs):
            raise sentinel

    inner = wrap_lifecycle(Modifier())

    class Outer:
        @classmethod
        def get_lifecycle_name(cls):
            return "resolve"

        def resolve(self, *_args, **_kwargs):
            return inner.resolve()

    outer = wrap_lifecycle(Outer())
    monkeypatch.setattr(
        "sdax_hamilton._construction.base.resolve_nodes",
        lambda *_args, **_kwargs: outer.resolve(),
    )

    with pytest.raises(ValueError) as caught:
        resolve_nodes(lambda: None, {})

    assert caught.value is sentinel
    assert caught.value.__context__ is None
