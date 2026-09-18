# Configured models and delayed resolvers

This qualification targets `apache-hamilton==1.90.0` through the public
`sdax_hamilton.Driver` boundary. `model` and `dynamic_transform` are configured
node creators, not dynamic runtime graph expansion. `resolve` and
`resolve_from_config` resolve a modifier while a Driver is constructed.

## Construction and state

Hamilton receives a copied declaration for each Driver. A configured model is
constructed once for that declaration in that Driver, and its bound `compute`
method is the callable retained in the resulting `NodeSpec`. Its configuration
value and extra constructor arguments retain application identity; the Driver
only copies its top-level configuration mapping.

The same constructed model is used by all prepared plans and invocations from a
Driver, so its ordinary mutable state is intentionally shared. SDAX adds no
model lock, state snapshot, or reentrancy claim. An application that invokes a
stateful model concurrently must make that model safe for concurrent use. Model
constructors are trusted application code and are not resource acquisitions;
they do not gain shutdown ownership from this integration.

### U3: pinned configuration-filtering correction

Hamilton 1.90.0's `dynamic_transform` defines `require_config`, while its
construction pipeline calls `required_config`. Consequently, stock Hamilton
filters out the declared configuration key and rejects a provided model
configuration as missing. SDAX corrects that one pinned defect only on copied,
exact `model` and `dynamic_transform` modifier instances: their
`required_config` delegates to the existing `require_config` implementation.
It does not copy Hamilton's creator algorithm, alter user modifier instances,
or admit subclasses. The correction is version-gated with the Hamilton 1.90.0
boundary and can be removed after a pinned upstream version supplies the proper
method and requalification confirms it.

## Delayed resolution

`resolve` and `resolve_from_config` run once per declared function for each
Driver. They preserve Hamilton's explicit
`hamilton.enable_power_user_mode=True` requirement and its required and optional
factory-parameter rules, including factory defaults. The returned modifier is
checked by the same exact-class admission boundary before Hamilton invokes its
lifecycle, so a subclass or an unreviewed modifier remains rejected.

Ordinary exceptions raised by model construction, resolution, or a returned
modifier lifecycle leave the compatibility boundary as the original exception.
Hamilton does not emit its `resolve_nodes` construction log for those failures.
Interrupt, process-exit, and cancellation exceptions are never transported.

## Qualification coverage

`tests/test_models_resolvers.py` proves public Driver construction counts,
shared sequential model state, application identity for model arguments, both
delayed resolver entry points, `resolve_from_config` defaults and power-user
enforcement, exact returned modifier rejection, and one unlogged resolver
failure. It also retains the stock U3 reproduction and proves the corrected
missing-configuration and constructor-error contracts. The configured-model
tests cover both Hamilton aliases; their upstream behavior shares the same node
creator implementation.
