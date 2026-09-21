# Phase F I/O qualification review — A6b

## Verdict and boundary

Proceed with the frozen phase F private I/O provenance foundation. This is a
bounded pass for exact Hamilton 1.90 I/O modifiers after the existing compiler
version and family admission decisions. It does not open public F admission, and
it does not complete the pending B-to-`save_to` nonempty input-contract
composition gate.

The reviewed source was synchronized onto commit
`3a606071261a3462dff869bcd40952480b515de6`. The frozen file hashes are:

- `_hamilton_provenance.py`:
  `a3f1dd9aefade1c62e1ba1859566bea48370c422a5612cb1cf796b19b5539ce3`
- `test_io_driver.py`:
  `3b3330d6ce08a29cd41cce9495e3297d5efe4739fe06b9c5b8c3f86249606453`
- `Loader-Correction.md`:
  `1e084e187edd9ccad611a2e1143c93e7cf050ff23e19c9e9f30775d3cc45565e`

The worker's wider focused selection passed 40 tests with Ruff, changed-source
mypy and the diff check clean. My independent I/O contract, correction and Driver
selection passed 27 tests with caches disabled.

## Architecture assessment

The four hooks delegate once to the copied exact Hamilton modifier and classify
only the returned expansion. `load_from` and `dataloader` require an exact
two-node collection with one tagged raw loader and one tagged projection that
consumes that raw node. `save_to` requires its exact two-node transformed shape,
and `datasaver` requires its one tagged saver node. This uses the pinned returned
shape and tags; it does not scan the compiled graph, infer roles from generated
names or reproduce Hamilton's adapter dispatch.

Hamilton's existing `AdapterFactory` remains the sole registry selection and
captured adapter state. The existing copied modifier preflight validates the
factory and resolved literals after the native generation call without selecting
or constructing an adapter again. A registry precedence and mutation witness
shows that an existing Driver retains the selected last-applicable adapter while
a later Driver sees the later registry contents. Construction performs no
load/save effect.

The provenance distinctions match the actual callbacks. A `load_from` raw node
executes a selected adapter and is not forged as a call to the decorated consumer;
the consumer remains the actual declaration call. A `dataloader` raw tuple is the
actual decorated declaration call, while its public data projection borrows that
tuple. A real owned dataloader witness attaches shutdown to the raw tuple, keeps
the projected handle live inside `open()`, and releases that exact raw acquisition
once on exit. A `datasaver` is one ordinary public value-producing effect and has
a real Driver execution witness, while Hamilton's pinned exact built-in `dict`
return restriction remains enforced.

`save_to` produces fresh effect metadata. Its ordinary input edge keeps an owned
producer live until `save_data` finishes; the metadata does not alias the producer
after the trusted callback returns. It is therefore an ordinary `VALUE` with
`borrows=False`, allowing `execute()` to return the metadata after cleanup. The
lifecycle witness proves acquire, save, then release order. The documented
boundary requires trusted saver callbacks not to publish a live resource alias in
their metadata; arbitrary aliases in Python values cannot be inferred safely.

The transformed declaration is handed back through the shared seam with
`_handoff(..., before=entry)`, so incoming declaration, role, public name,
ownership and input contracts are retained subject to the ordered input-shape
check. The validation composition witness also proves that a saver targeted at a
validated result consumes the gate rather than bypassing it.

No second adapter registry, selection cache, I/O executor, graph, intermediate
representation or version boundary was added.

## Remaining gates

Public `_SUPPORTED` admission remains test-only. Before phase F can be advertised,
the integrated snapshot must exercise a nonempty B-produced input contract across
the `save_to` handoff and complete the final public family qualification. Delayed
resolver and recursive-mount combinations remain owned by their respective D
composition gates rather than this narrow F foundation.

## Final policy and B-composition disposition

The integrated refreeze closes the policy-routing issue and the B-to-`save_to`
gate identified above. It is a bounded final pass for phase F production, still
without public family admission. The integrated base is
`67db48504c760c7d3e870adf0d32709957f91c2b`; its frozen hashes are:

- `_hamilton_provenance.py`:
  `2e35d66db93c7c2b535a996053ac4bd1bd0c51349ae74179c94c7c03ab30cf6c`
- `hamilton_compat.py`:
  `28796668b3af5861f6b5fde1610160fd25538fb97217dc0c41cdfddaa1738aac`
- `test_io_driver.py`:
  `e10052c3a07792ccf52d723d3294e6455caf2b50818c30ffc3840c363c3e8c5e`
- `Loader-Correction.md`:
  `2b1fc8c8b03de503c528126f1c1dfafd4384d5250b626f7a7e5740243c4b2b90`

The integrated suite reported 398 passing tests and 15 expected optional-profile
skips, with Ruff, mypy and the diff check clean.

`_CapturedFact.policy_target` is construction-only. Exact `load_from` raw and
`save_to` sink effect nodes set it without claiming that either is the decorated
declaration's acquisition call. Default policies and shutdowns still select only
actual calls. An explicit execution target may additionally select one of these
effect nodes, so its timeout and retry wrap the adapter factory construction and
the load or save callback. Retry witnesses show a fresh adapter construction on
each attempt; SaveTo retries do not rerun the producer.

Direct actual or policy candidates are selected before alias traversal. Alias
traversal starts only from same-owner facts with `borrows=True`, then follows
ordinary graph inputs within the same mount back to an eligible candidate. This
retains established public projection, extraction, validation and pipeline target
semantics. It also prevents a fresh non-borrowing SaveTo metadata sink from being
used as a shutdown alias for its producer. Direct tests cover both the synthetic
sink shutdown rejection and an extracted projection's successful shutdown
targeting.

The policy-target fact is carried only while a raw identity is transformed by
bindings, extraction, validation or a pipeline step. Generated projections and
validation gates do not become policy targets. A validated SaveTo sink remains an
explicit retry target because its raw effect identity survives behind the gate.
This reuses the existing provenance fact and target traversal; it introduces no
persistent `NodeSpec` field, runtime dispatch branch or adapter state.

The final namespaced composition witness applies `inject` with two original
contracts and an optional default under `parameterized_subdag`, then applies
`save_to`. The generated component retains
`InputSpec(int | str, default=3, requirements=(int, int | str))`; an invalid
optional input rejects before the producer or saver runs. The shared ordered
handoff therefore carries the nonempty B contract through F without a second
contract map. Public F admission and the overall integrated family qualification
remain the only F-facing gates.
