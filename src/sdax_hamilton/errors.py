"""Secondary diagnostics without replacing the caller's exception identity."""


def failures(exc: BaseException) -> tuple[BaseException, ...]:
    """Return secondary SDAX diagnostics attached to a caller/body exception.

    Ordinary execution aggregates expose their children through ``exceptions``.
    This helper reads only the separate diagnostics attached while propagating an
    existing exception; it does not stringify, flatten or replace those objects.
    """
    value = getattr(exc, "_sdax_hamilton_failures", ())
    return value if isinstance(value, tuple) else ()


def retain(exc: BaseException, secondary: list[BaseException]) -> None:
    combined = list(failures(exc))
    for error in secondary:
        if error is not exc and all(error is not old for old in combined):
            combined.append(error)
    if combined:
        setattr(exc, "_sdax_hamilton_failures", tuple(combined))
        exc.add_note("Additional execution/cleanup diagnostics: sdax_hamilton.failures(exception)")
