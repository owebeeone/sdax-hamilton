# Phase A qualification — independent architecture review A6b

Date: 18 September 2026. Scope: A/QA aliases, configuration/exclusion and
metadata on the existing supported graph shapes.

Reviewed worker commit:
`326c18e3276602e49303d0052b66a4303a6723c0`.

This review is independent of other A/QA reviews. It changes no product source,
test, qualification report, workspace configuration or evidence archive. The
workspace instructions, governing decorator-support plan, inventory and reviewed
architecture goals were read. No GWZ command, install, network operation or
evidence-campaign mutation was performed.

## Verdict

**Pass A and proceed through the bounded QA gate.** The implementation is a small
extension of the current compiler/model boundary and reuses Hamilton's expansion
plus the existing parameterization validation and lowering. It adds no adapter
framework, alternate compiler, executable graph, scheduler or backend activation.

The admitted aliases and metadata classes remain exact-class allowlisted. Unknown
subclasses continue to fail closed. Custom configuration predicates execute once
as trusted Driver-construction code. Excluded helpers bypass graph annotation and
resolution, while exclusion cannot erase a frontend shutdown obligation. Cache
and Ray declarations contribute inert tags only; repeated plan execution remains
local and uncached.

There is no stop finding. Two low documentation/evidence notes do not block A/QA
or the independently gated P2/P3 work.

## Architecture and minimality

The persistent model change is one optional `NodeSpec.tags` mapping. The compiler
passes Hamilton's already-resolved node tags into that field, so metadata targeting
and precedence remain Hamilton-owned. `NodeSpec.__post_init__` copies the outer
mapping and the finite list-valued tag containers allowed by Hamilton 1.90.0 while
retaining tag-element and other application-object identity. No generic deep copy,
serialization or metadata interpreter was added.

The compiler allowlist adds the five parameterization convenience classes and the
exact metadata classes. All five aliases are subclasses of the already-supported
`parameterize` implementation, so the existing binding checks and expansion path
remain authoritative. The implementation does not add an adapter class or branch
per spelling. The existing exact-type admission check still rejects third-party
subclasses before expansion.

Exclusion is recognized from Hamilton's exact `hamilton_exclude` marker before
declaration annotation validation or `resolve_nodes`. This permits a genuinely
untyped application helper and prevents an attached unknown resolver from running.
The separately discovered shutdown map is checked first, so an excluded acquisition
owner raises instead of disappearing from the ownership model. This is the minimum
extra ownership rule needed for A; recursive/transformed ownership remains outside
the lane.

Removing the former custom-`ConfigResolver` rejection delegates predicate timing
and selection to Hamilton's real `config` lifecycle. Function-copy isolation and
the Driver's copied configuration mapping remain unchanged. The counted regression
shows the predicate runs once during construction, is not replayed by preparation
or repeated execution, and observes the construction snapshot rather than later
mutation of the caller's configuration mapping.

The cache and Ray tests use their real decorators, then execute the lowered plan
twice. The application callable runs locally twice and produces distinct results,
which demonstrates that preserved tags neither cache the result nor submit remote
work. No cache or Ray runtime adapter is imported or installed by this delta.

## Test evidence

The shared oracle compares generated names, edge contracts, optionality, output
types and selected metadata. The alias fixture covers `parameterize_values`,
`parameterize_sources`, `parametrized`, `parametrized_input` and
`parameterized_inputs` together and compares both graph shape and values with a
fresh stock Hamilton Driver.

Metadata coverage composes direct tags, per-output tags, cache and Ray tags with a
two-output parameterization, proving target-specific results against the oracle.
`schema.output` has its own real dataframe case. Snapshot tests show that later
mutation of the original tag mapping or list does not alter a constructed Driver,
while an identity-sensitive value is retained rather than copied.

Negative controls establish that custom `parameterize` and `tag` subclasses stay
unsupported, an unknown modifier on an excluded helper is not resolved, and an
excluded owner cannot hide its shutdown. These exercise the admission boundary
rather than only happy-path Hamilton behavior.

The complete source suite was run at the frozen worker commit with bytecode and
pytest caches disabled:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m pytest -p no:cacheprovider -q
........................................................................ [ 37%]
........................................................................ [ 75%]
..............................................                           [100%]
190 passed in 1.88s
```

The reviewed diff also passed Git's whitespace check.

## Nonblocking notes

### L1 — legacy warning preservation is established by delegation, not asserted

The qualification report says the three legacy alias forms retain Hamilton's
deprecation behavior. The tests construct and execute all three exact upstream
classes, and the frontend neither wraps their constructors nor filters warnings,
so the claim is credible by direct delegation. The test does not explicitly
capture the emitted deprecation warnings. If QA policy requires every compatibility
claim to have an assertion, one compact warning assertion can cover the three
legacy constructors; no product change or alias-specific implementation is needed.

### L2 — “frozen copy” is stronger than the nested-container contract

`NodeSpec.tags` prevents replacement of mapping entries and copies source lists,
but the copied lists themselves remain mutable through the private `Driver._nodes`
mapping. There is no public tag accessor or current runtime consumer, and mutation
of the user's original metadata cannot affect the Driver, so this satisfies the
plan's bounded snapshot and identity rules for A.

The phrase “frozen copy” in `Phase-A-Qualification.md` can nevertheless be read as
deep immutability. “Isolated snapshot with copied list containers” states the
implemented guarantee more precisely. Do not add generic recursive freezing to
address the wording. If a later public diagnostic or backend consumer exposes tags,
that feature should define and test the exact mutability contract it needs.

## Gate boundary

This pass does not qualify grouped/config-derived bindings, recursive declarations,
extraction, pipelines, validation, I/O adapters, cache execution or Ray execution.
It does not loosen the existing transformed-ownership restrictions. QA may ship
only the compatibility rows named by A, with cache/Ray behavior described as
inactive metadata. The ordinary family and optional-runtime gates remain open.
