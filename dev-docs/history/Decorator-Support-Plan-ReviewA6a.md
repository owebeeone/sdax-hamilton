# Decorator support plan: independent safety review A6a

Date: 18 September 2026. Reviewer: A6a, safety and vulnerability prevention.
Reviewed plan: `Decorator-Support-Plan.md`, proposed implementation, not an
implemented feature. Baseline SHA256:
`ca1efd866cabaeb05309ae9bf3ca1408cb00c08d57368c2befcef99d8ab236dc`.

## Executive verdict

**Viable with targeted amendments before the affected capabilities are enabled.**
The ownership representation, explicit adapters, pre-acquisition rejection,
separate call/check tasks, public regressions and staged releases are strong
foundations. The largest unresolved safety boundary is executing code or effects
outside those protected runtime calls: cache deserialization, compile-time
callbacks, mutable adapter registration and remote execution options.

The plan should make safety an explicit P0 deliverable, with acceptance attached
to existing lanes. It does not need a sandbox, a new SDAX scheduler, a generic
security framework or a universal plugin certification scheme. Core releases
can proceed while unsafe optional cache/remote profiles remain disabled.

| Priority | Finding | Affected gate |
|---|---|---|
| High | S1: upstream persistent cache loading is executable deserialization; trust, secrecy and composition rules are absent | K activation / Z |
| High | S2: remote activation, backend retries and uncertain cancellation need an explicit contract | R activation / Z |
| Medium | S3: the plan does not define trusted construction code versus untrusted invocation data | P0 / QA / QB / X |
| Medium | S4: mutable I/O registries are outside the proposed snapshot contract | F / QB / profiles |
| Medium | S5: generated validation nodes need an explicit override and output-selection policy | E / QB / V / K |
| Medium | S6: upstream validation logs raw diagnostic content automatically | E / QB / V / K |

These are prospective plan gaps, **not claims of exploitable vulnerabilities in
the current frontend**. Its `_SUPPORTED` tuple currently admits only config,
inject, parameterize and tag; the newly reviewed execution paths are not enabled.
Severity describes consequences if the proposed support is shipped without the
specified boundary, not a CVSS assessment.

## Evidence and limits

Read workspace `AGENTS.md`, `AGENTS_GWZ.md`, `EVIDENCE.md`, the plan, linked
inventory and JSON DAG, frontend compiler/selection/runtime/plan/API, packaging
configuration and CI/release workflows. Inspected pinned Hamilton 1.90.0 source
under:

`/Users/owebeeone/limbo/evidence-build-cache/sdax-hamilton-package/release-0.1.0/pypi-smoke/lib/python3.12/site-packages/hamilton`

Below, `H/` means that source root; frontend paths are relative to
`sdax-hamilton/`. Line anchors refer to the original reviewed files. Source
inspection establishes behavior; conditional scenarios are explicitly described
as inferences. No probes, remote jobs, new clones, credentials or experimental
evidence were created. No other review was consulted.

## S1 — High: make cache storage a code-execution and confidentiality boundary

**Anchors.** Plan K, line 183; P3/P4, lines 127–128; gates, lines 215–233.
`H/caching/stores/base.py:221–242`; `H/caching/stores/file.py:48–60,86–119`.
JSON DAG gives K only A/P4 prerequisites and Z joins K with QC without a named
cross-family backend qualification deliverable.

**Confirmed.** `StoredResult.save()` pickles either the result or a loader object.
`StoredResult.load()` calls `pickle.loads()` and can then invoke
`loader.load_data(None)`. Consequently selecting a JSON/CSV-style materializer
does not by itself remove executable pickle metadata. FileResultStore reads
these bytes before returning a value. Later frontend type checks cannot make
that deserialization safe. K currently addresses invalidation and resource
exclusion, but does not state who may write cache bytes or which results may be
persisted.

**Concrete conditional failure.** An application enables the proposed upstream
file cache on a shared CI cache or restores a cache archive produced by a less
trusted party. A substituted entry executes code during a cache hit, before the
claimed output checks. Separately, an otherwise correctly typed result can be a
token, personal record or credential-bearing loader; ownership exclusion does
not prevent it being persisted or shared across security principals. No such
cache use is confirmed in the present frontend.

**Minimal amendment.** K must name its admitted storage trust model before
choosing upstream components. The smallest initial profile is private,
application-controlled storage with explicit trusted-deserialization consent,
no untrusted/shared-cache support, documented access/retention responsibility,
and explicit cache eligibility for sensitive values. Do not call a materializer
safe solely because its payload format is non-pickle. If untrusted cache imports
are required, use a genuinely non-executable end-to-end representation; do not
invent a "restricted unpickler" as a shortcut. Separate cache identity by any
application security context that changes results, or reject sharing across
such contexts. Avoid automatic persistence of full config, captured objects,
adapter credentials or validation diagnostics.

K must also qualify that cache hits cannot suppress required validation or
replay loader/saver effects through a serialized loader outside the designated
effect role. Explicitly test code/config/validation changes and named skipped
dependencies; a type-compatible stale value is still unsafe if validation or
authorization inputs were omitted from its identity.

**Acceptance evidence.** Public temporary-directory tests establish disabled
default behavior; no loading before explicit trusted profile selection; a
benign deserializer spy is never called in a profile claiming non-executable
storage; altered/truncated cache entries follow the documented error/miss
policy; synthetic secret values are not written when ineligible; two distinct
application scopes cannot share a result accidentally; loader/validator/saver
counts and resource ordering remain correct on hit, miss and failure. Do not
use real secrets or execute a malicious pickle to prove the boundary.

**DAG/gate change.** P0 freezes cache trust and data-handling fields. Keep K
implementation dependent on A/P4. Add a cache activation qualification joining
K with E/F (and V or other profiles when advertised); make Z depend on that
qualification. An explicit equivalent acceptance sub-gate is sufficient—no
need to serialize cache implementation behind all core work. K passing isolated
tests is not permission to enable unqualified combinations.

## S2 — High: remote options must not silently acquire execution authority

**Anchors.** Plan scope, lines 21–27; policy targeting, lines 143–147; R, line
184; G3, line 181. `H/function_modifiers/metadata.py:305–335`;
`H/plugins/h_ray.py:52–68,152–166`; `docs/API.md:79–92`;
`src/sdax_hamilton/plan.py:88–117,123–149`.

**Confirmed.** Hamilton encodes options into tags and its Ray adapter forwards
the decoded options to `.options(**ray_options).remote(...)`. The frontend's
current lifetime guarantee drains local forward work before shutdown, and its
API requires a cancelled attempt to finish before retry. K explicitly says
frontend opt-in; R does not define that equivalent activation boundary, which
options can control execution, or what a lost cancellation acknowledgement
means. Ray itself was not executed or separately version-qualified in this
review; actual supported retry/termination controls remain an R question.

**Concrete conditional failure.** An implementation starts dispatching when it
sees a preserved Ray tag or an installed dependency. Values and captured
application state now leave the local process without an application-selected
backend. Alternatively, a forwarded backend retry option repeats an effectful
call beyond the SDAX attempt budget. During a partition, the local future is
cancelled while the worker continues using a dependency that local cleanup
releases. Waiting for a request to cancel is not proof that work stopped.

**Minimal amendment.** Require explicit application-owned remote profile and
destination selection, separate from decorator tags and runtime input data.
Pin a backend version and enumerate supported option semantics. Reject unknown
or conflicting execution/retry/environment settings before submission; harmless
scheduling settings can remain supported. Establish one owner of attempts:
disable backend replay where SDAX owns retries, or explicitly qualify the
combined contract and reject effectful cases that cannot meet it. Do not promise
exactly-once effects. State that worker environments and serialized callables
are trusted code and that submitting data grants that worker access to it.

Define cancellation success as actual termination/completion for the admitted
placement, not local ObjectRef/future cancellation. On lost-worker or partition
uncertainty, do not silently assume stop or run a replacement attempt. The
smallest safe first profile rejects resource-dependent placements for which
stop/join cannot be established. Document any potentially unbounded draining
instead of combining a hard timeout promise with early cleanup. Apply the same
distinction to Spark job cancellation.

**Acceptance evidence.** With only tags present, prove no connection/submission
occurs. Test invalid settings fail before dispatch; serialize only the approved
payload; count attempts under backend failure plus SDAX retries; simulate late
completion, missing cancellation acknowledgement, repeated caller cancellation
and remote exceptions. Assert no dependency cleanup or replacement attempt
while the admitted worker may still use it. Use controlled local workers/fakes;
qualify the fake against a pinned local backend before claiming its semantics.

**DAG/gate change.** P0 owns activation/trust policy; P4 owns its lifetime
invariant; R owns backend proof. Add R activation qualification for actual
supported C/E/F/resource combinations (or explicit rejection fixtures), joining
at Z. G3/QC must record equivalent Spark stop/join limits. Earlier QA/QB/QC
remain independent of effective Ray support.

## S3 — Medium: state which construction-time operations execute trusted code

**Anchors.** Plan lines 31–34, P0/P2, D2/D3/X, and lines 229–231. Inventory
findings 3, 4 and 8. `src/sdax_hamilton/hamilton_compat.py:81–103,144–169,244–246`;
`H/function_modifiers/delayed.py:150–179`;
`H/function_modifiers/macros.py:297–314`;
`src/sdax_hamilton/driver.py:12–25`.

**Confirmed.** Declaration checking evaluates type hints; delayed resolution
calls `decorate_with(**kwargs)` before examining its returned decorator; model
generation constructs the supplied model and calls `get_dependents()`. Function
snapshots retain globals/closures and config values retain object identities.
The plan correctly recognizes import-time `mutate`, but does not define a
threat model or distinguish a safe graph-admission check from arbitrary Python
execution during construction.

**Concrete conditional failure.** A service treats Driver construction as a
safe preview of user-supplied modules, expressions or resolver configuration.
A resolver/model constructor opens a resource or performs I/O, then returns an
unsupported modifier and compilation fails. P4 shutdown cannot clean an
acquisition that occurred outside its graph. Post-expansion validation cannot
undo the effect. This is a trust-boundary mistake, not evidence that malicious
Python can be safely sandboxed by this frontend.

**Minimal amendment.** Add an explicit P0 safety statement: module imports,
annotations, modifiers, resolver/model/validator/adapter classes, extension
registrations and backend settings are trusted application code/control inputs.
Runtime inputs and declared override *values* may be untrusted data, subject to
type/shape checks; graph/output/override selection is an application-controlled
capability, not an authorization service. Such values must not choose imports,
enable execution profiles or register code through a new convenience feature.
Upstream power-user mode is a readability opt-in, not a sandbox.

Clarify "fail before acquisition" to mean scheduled graph acquisitions. Require
trusted construction hooks to avoid externally owned resources/effects unless a
separate construction lifetime contract is explicitly designed; the smallest
solution documents such constructors as unsupported. Preserve shallow
application-object identity semantics and document reentrancy responsibility.
Do not deep-copy arbitrary objects or run speculative callbacks twice as a
"validation" mechanism.

**Acceptance evidence.** Counter-based trusted fixtures prove the exact
construction/prepare/execute call counts, including constructor failure;
unsupported returned modifiers never invoke their graph callables; runtime
values cannot alter registered code or activation settings. Document import and
annotation evaluation and test that unknown static modifier classes are
rejected before their expansion methods are called where inspection permits.
Do not assert that rejected Python declarations had no import-time effects.

**DAG/gate change.** Extend P0/P1 acceptance; propagate to A/D2/D3/F/X and
QA/QB. Existing edges suffice. X remains optional and its post-expansion checks
must never be described as certification or isolation of third-party code.

## S4 — Medium: snapshot selected adapter identity, not only declarations

**Anchors.** Plan P2, F and X; inventory's open-registry scope.
`H/registry.py:65–76,79–114,220–233`;
`H/function_modifiers/adapters.py:119–147,188–220,368–369,537–566`.

**Confirmed.** Hamilton's process-wide loader/saver registries append classes;
resolution chooses the last applicable registration. Plugin loading imports
installed extension code and its autoload state can be affected by a user-level
Hamilton configuration file. Expansion selects an adapter class and captures
its factory. Thus package pins alone do not establish which adapter executes.

**Concrete conditional failure.** Two independently configured Drivers share a
process. An optional integration registers the same loader name between their
construction; identical source/config selects a different implementation and
potentially a different I/O behavior. A conformance test passing on an author's
plugin-rich machine is then misleading on clean CI. This is an ambient-state
and qualified-profile problem; code already allowed to register arbitrary
adapters is trusted code, not an attacker defeated by this contract.

**Minimal amendment.** P2/F record selected adapter class identity, qualified
profile and binding provenance. Snapshot the registry candidates/selection at
the documented construction boundary, with no runtime re-resolution. Preserve
upstream precedence explicitly or reject ambiguity in a qualified profile;
document the choice. New registrations must not mutate an existing Driver's
semantics. CI starts profiles in isolated processes with controlled autoload
configuration before Hamilton import; do not alter process-global autoload
settings opportunistically while constructing one Driver. Custom I/O protocol
support must remain distinct from individually qualified implementations.

**Acceptance evidence.** Register two synthetic same-name adapters in controlled
orders, construct separate Drivers, mutate registration afterwards, and verify
both identity and behavior. Test optional-import absence and clean startup;
record selected implementation in ledger/provenance without dumping credentials.
Use temporary in-memory adapters only.

**DAG/gate change.** Put registry snapshot/interface fields into P0/P2, concrete
qualification in F, and require them at QB and relevant optional profile gates.
No new dependency on optional X is needed for core I/O support.

## S5 — Medium: decide whether validation intermediates are bypass capabilities

**Anchors.** Plan P4/E/V, lines 128,164,182, and negative controls at 227–228.
`H/function_modifiers/validation.py:94–148`;
`src/sdax_hamilton/_selection.py:73–85`;
`src/sdax_hamilton/plan.py:68–74`; `docs/API.md:18–28`.

**Confirmed.** Upstream separates raw data, a `ValidationResult` node and the
final gate that acts on failures. The current selector prunes dependencies for
ordinary overridden/config-replaced nodes; replacement checks enforce nominal
types. The plan protects *owned* aliases explicitly but does not decide the
equivalent policy for non-owned validation evidence or raw outputs.

**Concrete conditional failure.** After E is implemented, a broadly generated
override surface permits replacing a validator result with a passing typed
object, or replacing a final gate output with an unchecked value. A downstream
saver receives data the application assumed had passed validation. Selecting a
raw generated output can likewise avoid the gate. These are conditional
admission-policy gaps; an application deliberately choosing an override is
already exercising trusted authority, not an exploit by an ordinary fixed-shape
input alone.

**Minimal amendment.** P0/E/P4 must specify which generated roles are selectable,
config-replaceable or overrideable and what validation guarantee remains. The
smallest safe checked profile makes validation evidence/gates internal and
non-replaceable, or clearly exposes raw/bypass selection only as a trusted
application capability with a visibly weaker guarantee. Do not claim all
returned values were validated when trusted bypasses are admitted. Preserve
mandatory Hamilton fail-validation when `check_outputs=False` only disables
frontend type checking, unless a separate deliberate contract states otherwise.

**Acceptance evidence.** Test config and declared overrides against raw,
validator and final roles; test raw selection and downstream saver effects;
test `check_outputs=False`; prove failing data cannot reach a consumer in the
checked profile. Repeat on cache hits and schema-validation profiles. Existing
"drop an edge" negative controls do not replace these legal-API-path tests.

**DAG/gate change.** P0 fixes policy, P2 records roles, E/P4 jointly implement
selection constraints; QB is their gate. V and cache activation inherit this
contract. Existing family edges suffice, plus S1's cache composition gate.

## S6 — Medium: preserving diagnostics currently imports automatic data logging

**Anchors.** Plan P2 metadata, D2 reporting, E diagnostics, F metadata, K storage,
and preservation of exception identity in integration test 3.
`H/data_quality/base.py:112–147`;
`H/function_modifiers/validation.py:112–131`.

**Confirmed.** Hamilton's warning and failure actions stringify the validator's
message and arbitrary diagnostics dictionary to logs. Failures also construct
an exception containing that text. E intends to reuse the generated validation
graph and preserve exceptions. The plan contains no decision about this new
automatic data-output channel.

**Concrete conditional failure.** A validator includes a rejected record or a
secret-bearing value in its diagnostic dictionary. Enabling E causes it to be
written automatically to centralized application/CI logs, even if the caller
catches the error without logging it. A future graph/provenance report that
prints captured bindings has a similar risk, but that extra reporting behavior
is not yet implemented and is not asserted as a defect.

**Minimal amendment.** P0 declares library-generated diagnostics data-minimal
by default and identifies upstream diagnostic behavior as an explicit
compatibility choice. E must either provide a qualified mode that suppresses
automatic raw diagnostic logging, or visibly require application opt-in to
upstream raw diagnostics before claiming sensitive-data-safe operation. Keep
original user exception objects for programmatic handling; do not promise
their contents are sanitized or rewrite every exception to satisfy logging.
Structured support/provenance reports should use names, types and identities,
not config/literal/result reprs. Applications remain responsible for their own
logging and deliberately sensitive return values; no automatic taint system is
needed.

**Acceptance evidence.** Use synthetic sentinel strings in config, literals,
loader metadata and validation diagnostics. Capture frontend/upstream logs and
generated reports in the selected safe mode; prove sentinels are absent while
node/validator identity and exception behavior remain diagnosable. Test and
document the explicit raw-diagnostics mode separately. Include cache files and
metadata in K's confidentiality test, not just console logs.

**DAG/gate change.** P0/P1 define and test the policy; E/F/K implement applicable
outputs; QB, V/QC and cache qualification enforce it. No new global logging
framework or scheduling dependency is required.

## Explicit safety goals and non-goals for P0

Adopt the following compact contract as a plan goal, with ledger fields for
trusted construction hooks, effect role, backend/cache eligibility, selection
and override permissions, and diagnostic handling:

1. Untrusted invocation data does not gain code-selection, backend-activation
   or registration authority. Python declarations, plugins and application
   configuration are trusted code/control inputs.
2. Invalid admitted graph/binding shapes fail before scheduled effects;
   construction-time Python execution and its side effects are outside that
   promise and explicitly constrained/documented.
3. Each actual acquisition has one owner; known generated borrows preserve its
   lifetime through failure, selection, validation, caching and cancellation.
   Type-check or validator failure cannot create a new user-effect attempt.
4. Optional execution and persistence capabilities activate only through trusted
   application configuration and only for qualified combinations. Backend
   retries or cache hits cannot silently weaken the local contract.
5. Deserialization trust, sensitive data persistence and automatic diagnostics
   are explicit profile choices with public synthetic-data regressions.
6. Every public build/test/release is reproducible without private evidence;
   private copies and artifacts retain their access restrictions.

Non-goals: sandboxing hostile Python or arbitrary object protocols; proving
arbitrary user functions are pure or idempotent; discovering all Python aliasing;
securing a Ray/Spark cluster; terminating uncooperative work on a hard deadline;
exactly-once distributed I/O; automatic secret discovery/redaction inside user
objects or exception contents; and certification of arbitrary registered code.
Reject or qualify combinations that require these guarantees rather than
quietly claiming them.

## Clone, evidence, CI and release assessment

The plan already supplies the important integrity controls: GWZ-only structural
changes, serial quiet cloning, package-only commits, integrator-only publication,
no disposal of inherited dirty work, standalone public gates and private raw
evidence separation. I found no reason to replace this workflow or require
private evidence in CI. Wheel/sdist include scopes are already narrow, and the
publish job has a separate tag condition and trusted-publishing permission.

Add two precise operational notes, without introducing new release machinery:

- A verbatim clone also copies any private evidence, local ignored data and
  credentials that happen to exist in the source tree. All lane destinations
  must have the same access restrictions; do not upload whole-clone archives or
  repurpose them as public CI caches. `local dispose --keep` preserves those
  copies. This is a consequence of the documented clone semantics, not evidence
  that credentials were found here. A package-only diff plus sdist/wheel content
  inspection is sufficient release evidence; no scan of unrelated private data
  needs to be published.
- Tag creation/push is an actual publication trigger: current
  `.github/workflows/publish.yml:94–106` publishes on `v*` tag pushes after its
  build and wheel tests. Do not use release-looking tags for qualification and
  then describe them as inert gate runs. When optional profiles become a
  release claim, make their required qualification explicit in release
  readiness, rather than relying on an unrelated optional job's success.

Attach these to clone provisioning and existing gate item 6, not to a new
mandatory security lane. P0 and QA can proceed after the policy amendments;
S1/S2 block activation of their respective optional profiles, not useful core
support.

---

## Secondary independent safety review — revised plan

Date: 18 September 2026. Same reviewer A6a. The first review above is preserved;
these dispositions apply only to the revised documentation identified below.
Read the revised plan, inventory and JSON DAG without consulting the other
review. Reused the pinned-source evidence documented in the first pass. No
product code was changed or implementation/remote experiments performed.

| Reviewed artifact | Verified SHA256 |
|---|---|
| `Decorator-Support-Plan.md` | `dba5f0c287155f40d9b8a240ca45348581d3abc7fc3162846947eb4efc85a25e` |
| `Decorator-Support-Inventory.md` | `437161aaff7ac794b7d1797ec0fd8a506723be6ed89a187dc2149741948bb6ba` |
| `decorator-support-dag.json` | `54c0b58da609e1eea54f0cde0d590f8a8b53aac4aecbf67c39e066f8ea18458f` |

### Verdict: proceed with the revised plan

**No remaining plan-level safety blocker identified.** S1–S6 are resolved as
planning findings: each now has an explicit policy, responsible implementation
work and an activation or release gate. None is an implemented or tested safety
guarantee yet. Proceed with P0/P1, the bounded feasibility work and the qualified
early path. Cache/Ray remain disabled until their respective QK/QR proofs; a
failed backend feasibility or unresolved placement need not block static support.

The revised plan chooses concrete restrictions instead of creating a general
security framework. In particular, its trusted-code boundary, default internal
validation roles and private-cache-only starting profile narrow what must be
proved. Preserving original user exceptions while changing generated validation
messages is now explicitly distinguished, resolving the previous ambiguity.

### Disposition of the first-pass findings

| Finding | Secondary disposition and revised anchors |
|---|---|
| **S1 — cache trust/confidentiality** | **Resolved in plan.** Mandatory goals at lines 47–54 and cache section 330–357 require explicit activation and trusted deserialization consent, value eligibility, no untrusted/shared/restored archives, context-aware identity, resource/borrow exclusion and qualified serialized-loader effects. QK joins K with QB's E/F/P4 and only enables tested formats/combinations. Synthetic-secret, tamper, cross-context and effect-spy evidence is named. |
| **S2 — remote authority/attempts/termination** | **Resolved in plan.** Lines 359–384 define application-selected destination/options, tags-only inactivity, one attempt owner, pinned backend proof and no retry/cleanup on uncertain stop. QR joins implementation with core effect/lifetime contracts. G3 at line 313 and QC apply the same actual-stop distinction to Spark. Unsafe placements can remain rejected without a full-coverage claim. |
| **S3 — construction trust boundary** | **Resolved in plan.** Lines 37–46 and 60–64 explicitly identify imports, annotation evaluation, constructors and registrations as trusted execution, exclude sandboxing, and distinguish scheduled graph effects from construction effects. Lines 85–90 place graph shape under application authority. P1/S count actual resolution contexts and D3 rejects untracked externally owned construction resources. |
| **S4 — registry snapshot boundary** | **Resolved in plan.** P2/F and “Registry and construction policy” explicitly retain resolved adapter class/factory and binding provenance, preserve upstream precedence, prohibit runtime re-resolution, and test later competing registration. Controlled autoload is established before import in isolated conformance processes without per-Driver global toggles. |
| **S5 — validation bypasses** | **Resolved in plan.** Lines 277–289 make generated raw/evidence nodes internal, prohibit ordinary override/config replacement of evidence/gates, reject user-declared bypass edges, keep final checked outputs selectable and preserve fail-validation with `check_outputs=False`. P4/E own this and QB/V/QK must qualify legal API paths. The stricter Hamilton compatibility difference is explicit in both plan and inventory. |
| **S6 — raw automatic diagnostics** | **Resolved in plan.** Lines 291–305 choose data-minimal generated logging/messages, a narrow final-gate correction, compatible generated exception class and original user exception identity. Raw diagnostics require a separate trusted option, no tags/input activation and no global logger mutation. Sentinel evidence covers automatic logs/reports; K additionally covers persistence. |

“Resolved in plan” means the first-pass requested decision and gate are present.
It must not be translated into a passing support-ledger row before implementation
and public regression evidence exist.

### Gate and DAG audit

A read-only structural check validated all **33 tasks and 63 edges**: JSON and
Mermaid edge sets are identical; every dependency names an existing task and has
a matching `consumes` entry; the graph is acyclic. Additional reachability checks
confirmed these safety joins:

- QA inherits P0/P1 through A. Its removal of a P4 prerequisite is acceptable
  because QA is now explicitly limited to existing graph/ownership shapes and
  retains unsupported transformed/recursive ownership rejection. It does not
  authorize broad generated-resource support.
- QB joins P4, E, F and both upstream corrections, with the full core-family
  dependency set. Independent C/F development therefore does not remove the
  correction requirement from activation.
- QC joins QB with G3 and V (and the dataframe profiles), retaining generated
  lifecycle/diagnostic policy for optional static support.
- QK joins K with QB, transitively requiring K0 plus validation, I/O and ownership
  qualification. QR does the corresponding R0/R/QB join. Neither implementation
  task can independently authorize its backend profile.
- ZR joins Z/QK/QR. Separating static Z from effective-runtime ZR is safe because
  the revised coverage language explicitly distinguishes those claims. Optional
  plugin/backend combinations require their own cases; passing two independent
  profiles does not establish their combined behavior.

The inventory agrees with these boundaries and identifies them as proposed
policies, not released behavior. The shared gate section attaches the rules to
public tests and the release workflow for every claimed profile. Clone access
restrictions, package artifact inspection and the real `v*` publication trigger
are now explicit. No additional security lane or new dependency edge is required
by this secondary review.

### New or regression findings

**None requiring another plan revision.** Moving feasibility earlier and allowing
smaller early releases does not create a safety bypass under the documented
activation rules. Shared-state identity and trusted user-code side effects are
now explicit limitations rather than implied guarantees.

The following are implementation acceptance obligations, not remaining plan
blockers or new scope:

1. **Actually control the import boundary.** The first-pass source establishes
   upstream autoload via process/user configuration. Base-only installation
   success alone cannot prove that optional packages stay unloaded when already
   installed. Qualify the stated on-demand guarantee with the relevant controlled
   startup states and installed-but-unselected profiles; avoid a global toggle
   performed by one Driver. If the pinned upstream boundary cannot meet that
   goal, report the precise limitation before the affected gate passes.
2. **Prove enforcement, not only role labels.** Internal validation names must
   remain protected through mounts, delayed resolution and every admitted config,
   selection and override path. Preserve acquisition retry/cleanup restrictions
   across new roles; retaining the baseline is a behavior requirement, not merely
   keeping existing test files.
3. **Qualify backend combinations explicitly.** A cache hit plus a remote callable
   is an enabled combination only after corresponding composition evidence, or
   must be rejected. Confirm actual pinned backend retries and termination; fakes
   alone cannot establish them. Trusted private-cache consent is not a claim
   that pickle bytes are intrinsically safe.
4. **Exercise the default diagnostic path.** Do not pass the sentinel tests by
   muting process-wide logging or rewriting arbitrary user exceptions. Preserve
   the deliberately distinct generated-versus-user exception contract and prove
   concurrent Drivers with different explicit diagnostic settings remain isolated.
5. **Require claimed profiles in release readiness.** Current source has not yet
   acquired these tests or workflow dependencies. Gates remain planned until the
   shipped public fixtures, installed-wheel runs and applicable release jobs
   establish the advertised guarantees without private evidence access.

There is no further safety amendment requested before implementation starts.
Failure of one of these proofs should keep the affected support combination
inactive and its qualification status open, as the revised plan already requires.

### Final-hash addendum — scope wording clarification

Verified final plan SHA256
`cd4358d97305c82483f7e87e29417ea0e28b72e25be11971dd673e91c2504627`.
The only change since this secondary review adds “for the capabilities being
activated, run the applicable compositions” to shared gate item 5. Reversing that
exact substitution restores secondary-reviewed SHA256
`dba5f0c287155f40d9b8a240ca45348581d3abc7fc3162846947eb4efc85a25e`.

The **proceed** safety verdict carries forward. This clarification limits early
gates to relevant capability combinations; it does not waive composition proof
for any combination being activated. No broad rereview or new safety finding is
needed. Implementation acceptance obligations above remain unchanged.
