# Module 7: Time, Ordering & Coordination

This Python simulation demonstrates how a distributed order-processing system
can handle out-of-order delivery, duplicate messages, missing versions, and
stale workers. Each order event contains an `order_id`, `version`, and `status`.
The processor buffers future versions until every preceding version arrives,
and fencing tokens prevent an old worker from overwriting a newer worker's
result.

## Requirements

- Python 3.10 or newer
- No third-party packages

## Run the simulation

From the repository root:

```bash
python3 demo.py
```

Run the automated tests:

```bash
python3 -m unittest discover -s tests -v
```

## Design

`OrderProcessor.deliver()` compares an incoming version with the next expected
version. A future event is stored in a per-order pending map; when the missing
event arrives, the processor applies it and drains every now-contiguous pending
event. Versions already applied or already pending are duplicates and are
ignored. Workers receive monotonically increasing fencing tokens, and an update
is rejected when its token is lower than the highest token previously accepted
for that order.

## Evidence

The complete reproducible transcript is stored in
[`evidence/sample-output.txt`](evidence/sample-output.txt).

### Correct event ordering and duplicate handling

The required delivery sequence is version 2, version 1, then version 2 again:

```text
Delivering: version=2 status=PAID
  PENDING: order=order-100 received_version=2 missing_versions=[1] pending_versions=[2]
  Outcome: BUFFERED
Delivering: version=1 status=CREATED
  APPLIED: order=order-100 version=1 status=CREATED
  RELEASED pending event: order=order-100 version=2
  APPLIED: order=order-100 version=2 status=PAID
  Outcome: APPLIED
Delivering: version=2 status=PAID
  DUPLICATE ignored: order=order-100 version=2 current_version=2
  Outcome: DUPLICATE_IGNORED
```

Version 2 does not apply when it arrives first. After version 1 arrives, the
processor applies version 1 and then releases version 2. The repeated version 2
does not modify state.

### Missing-event case

Only version 3 is delivered for a new order:

```text
PENDING: order=order-200 received_version=3 missing_versions=[1, 2] pending_versions=[3]
Final state: {"highest_fencing_token": 0, "order_id": "order-200", "pending_versions": [3], "status": "NOT_CREATED", "version": 0}
```

The order remains at version 0 instead of incorrectly jumping to `SHIPPED`.
Version 3 is recorded as pending, and versions 1 and 2 are reported missing.

### Stale-worker rejection

Worker A receives token 1 and worker B receives token 2. Worker B updates the
order first; when worker A later resumes with token 1, its update is rejected:

```text
WORKER UPDATE applied: order=order-300 worker=worker-B token=2 status=SHIPPED
STALE WORKER rejected: order=order-300 worker=worker-A token=1 highest_token=2
Final state: {"highest_fencing_token": 2, "order_id": "order-300", "pending_versions": [], "status": "SHIPPED", "version": 0}
```

The rejected worker cannot overwrite `SHIPPED` with its stale `CANCELLED`
update.

## Reflection: why timestamps are not enough

Timestamps alone cannot guarantee event ordering because clocks on different
machines may drift and are rarely perfectly synchronized. Network delay can
also cause an earlier event to arrive after a later event even when both
timestamps are accurate. Clock adjustments and limited timestamp resolution
can produce equal or misleading values. Explicit sequence numbers or versions,
combined with duplicate detection and buffering, express causal order without
depending on wall-clock accuracy.

## Repository layout

```text
.
├── README.md
├── demo.py
├── evidence/
│   └── sample-output.txt
├── order_coordination/
│   ├── __init__.py
│   └── processor.py
└── tests/
    └── test_processor.py
```
