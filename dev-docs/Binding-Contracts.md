# Binding contracts

`InputSpec` retains the declared effective input type and may also retain the
original consumer requirements that were merged into that input. An empty
`requirements` tuple means the declared type is the only requirement. Otherwise,
every listed requirement applies; this is a finite conjunction, not a new type
language or an inferred intersection type.

These contracts are declaration metadata only. They preserve the identity of
contained application types and do not freeze application values or introduce a
second graph representation.

The existing `_types` checker remains the sole vocabulary. Selection checks every
effective requirement for static producer edges, defaults, and configuration.
Prepared invocation checks all external inputs and override values before a task
starts. A generated value is checked by the consuming callback before that callback
can run, including when output checking is disabled. The producer's declared output
check remains controlled by `check_outputs`.

The current compiler continues to create `InputSpec` values without additional
requirements, so its declared type is the fallback contract. Phase B owns capture
of distinct original requirements from merged Hamilton bindings. Its existing
rejections stay in place until that capture is qualified.
