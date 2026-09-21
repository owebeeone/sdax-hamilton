# Hamilton I/O contract probes

These direct Hamilton 1.90.0 tests establish the narrow facts phase F must
preserve when the compiler later admits I/O decorators. They are not frontend
driver qualification and do not enable any I/O decorator in the current public
subset.

`load_from.<registered-adapter>` and `save_to.<registered-adapter>` receive the
registry's candidate sequence at decorator construction. Hamilton resolves the
last applicable candidate while it creates the generated node and captures that
class in the generated callable's `AdapterFactory`. A later registry mutation
does not change that callable. The tests use isolated in-memory adapters to
exercise this behavior and prove that adapter construction and load/save effects
do not occur during generated-node construction.

The private `install_load_from_correction()` seam accepts one already-copied,
exact `LoadFromDecorator` after the enclosing compatibility version gate. It
copies only the finite candidate sequence and binding map, preserving application
values and adapter classes by identity. A method wrapper then delegates once to
the copied instance's original `get_loader_nodes()` method and applies the U2
annotation correction to that exact returned pair before Hamilton merges it with
other nodes. The application decorator, Hamilton registry, and unrelated
declarations remain unchanged.

`dataloader` exposes its raw `(data, metadata)` tuple and the projected data
node, while `datasaver` in this pinned Hamilton release accepts only the exact
built-in `dict` return annotation. These upstream behaviors are recorded as
contract probes. Selection policy, metadata reporting, registry startup control,
adapter snapshot reporting, and execution effects remain phase F/P2/P4 work.
