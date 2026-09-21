# Phase A qualification: independent safety review A6a

Date: 18 September 2026. Reviewed commit:
`326c18e3276602e49303d0052b66a4303a6723c0` (`Add qualified Hamilton alias and
metadata support`). Scope: A/QA safety and retained-boundary review only; this
is not qualification of recursive decorators, extraction, cache execution, Ray
execution, or publication.

## Verdict

**PASS for integration and the bounded QA safety gate. No blocking safety
finding.**

The change admits only the named Hamilton 1.90.0 classes, reuses the existing
expansion, checking, selection, and SDAX execution paths, and preserves the
current ownership behavior. Exclusion cannot hide a shutdown obligation.
Metadata is copied within the documented finite boundary and remains inert:
cache and Ray tags neither select a backend nor alter local execution.

## Exact admission and construction behavior

`_validate_declaration()` uses `type(modifier) not in _SUPPORTED`, so subclasses
of admitted decorators remain rejected. `_excluded()` likewise recognizes only
the exact Hamilton exclusion class. The negative regressions instantiate
subclasses of `parameterize` and `tag` and confirm fail-closed rejection; the
common exact-type check applies to config and the remaining metadata classes as
well.

The parameterization convenience and legacy classes run through the same
binding validation and lowering used by direct `parameterize`. The
implementation copies each parameterization mapping and binding container
before Hamilton resolution. The stock-Hamilton oracle comparison covers
generated names, edges, types, and results for all five newly admitted aliases.
Because the real Hamilton decorators are used, the legacy forms retain upstream
deprecation behavior rather than reimplementing it.

Custom config predicates are correctly treated as trusted application
construction code. The regression shows the predicate receives the Driver's
copied configuration, runs once during construction, and is not replayed by
preparation or repeated execution. Mutation of the caller's top-level config
mapping after construction does not alter that decision. This is not a sandbox
claim, and the documentation does not present it as one.

## Exclusion and ownership

Excluded helpers are identified before graph type validation or Hamilton
lifecycle expansion. An untyped helper is therefore allowed, while a
deliberately unknown resolver attached to an excluded helper is never invoked.
This preserves Hamilton's exclusion role without letting an ignored helper
execute an unreviewed expansion path.

Shutdown discovery occurs independently, and every excluded owner present in
the ownership map is rejected before ordinary declaration expansion with
`excluded declaration cannot own a shutdown`. The focused regression proves the
formerly dangerous shape fails during Driver construction. A shutdown function
carrying Hamilton decorators also remains rejected by the pre-existing shutdown
contract.

The complete suite retains direct parameterized ownership: two generated
acquisitions each release exactly once; a selected sibling without a shutdown
assignment cannot escape; and owned outputs cannot be replaced through config
or overrides. Unsupported transformed/recursive ownership remains fail-closed
through the existing declaration negatives.

## Metadata snapshot and identity boundary

`NodeSpec` copies the tag mapping into a `MappingProxyType`. It also copies each
known list-valued tag container, which is the only mutable value shape Hamilton's
admitted `tag` contract accepts. The regressions show later mutation of the
source list does not affect the Driver snapshot and mapping assignment is
rejected. A direct identity sentinel confirms non-container application objects
are retained by identity rather than generically cloned.

This is a shallow, finite metadata snapshot. List elements and other values
intentionally retain application identity, and list values inside the private
node model are not converted into immutable tuples. The qualification document
states that boundary. Future code that begins consuming tags for execution,
selection, persistence, or public diagnostics must define its own trusted schema
and mutation behavior; this commit gives tags no such authority.

`tag_outputs`, `schema.output`, cache directives, and Ray directives are lowered
only from Hamilton's resolved node tags. Stock-Hamilton signature comparisons
cover the named metadata. The qualification environment has no Ray installation,
yet the suite imports and processes `ray_remote_options` successfully, which
confirms this path does not require or connect to Ray.

## Cache and Ray inactivity

The runtime and selection paths do not inspect `NodeSpec.tags`. The focused
async regression executes a function carrying both cache and Ray tags twice and
observes two local calls with increasing results. This rules out hidden result
reuse and remote submission in the admitted path. The documentation explicitly
reserves effective caching for K0/K/QK and remote execution for R0/R/QR.

Metadata values remain trusted declaration/control data. This slice contains no
path by which invocation values can activate caching, remote execution, imports,
or registration. Preserving the strings is not an authorization decision.

## Verification

Against exact commit `326c18e3276602e49303d0052b66a4303a6723c0` in the
external qualification environment:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m pytest -p no:cacheprovider -q
190 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m ruff check --no-cache src tests
All checks passed!
```

`git diff --check` passed and the reviewed lane was clean at the frozen commit.

## Retained limits

- Exact-class admission is an allowlist for the tested Hamilton 1.90.0 surface,
  not permission for arbitrary subclasses or decorator combinations.
- Exclusion prevents graph admission and expansion; it cannot undo import-time
  effects from trusted Python.
- Metadata is preserved for parity but has no execution authority. Effective
  cache/Ray behavior remains prohibited until its separate trust, retry,
  persistence, and stop/join gates pass.
- The finite tag snapshot is deliberately shallow. Later metadata consumers
  must not infer deep immutability or safety from it.
- Recursive ownership, projection borrowing, validation roles, and plugin
  metadata remain outside A/QA.

No other reviewer findings were consulted. I made no changes in the Phase A
lane.
