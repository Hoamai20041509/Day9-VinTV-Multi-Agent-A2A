# Multi-Agent Dispute Resolution Architecture

## Goals

The system processes `input/EC_001.json` through `EC_050.json`, collects
verifiable evidence from domain agents, applies `EC_POLICY_V1`, verifies the
result, and writes one matching JSON file per case. Domain calculations remain
outside the coordinator.

## Components And Ownership

| Component | Owner | Data access | Responsibility |
| --- | --- | --- | --- |
| Coordinator Agent | TV1 | Input cases and agent responses | Orchestration, timeout/retry, correlation, trace, and output handoff |
| Order & Seller Agent | TV2 | orders, order_items, sellers | Order state, items, sellers, totals, and late seller handoff evidence |
| Payment Agent | TV3 | order_payments | Payment rows, totals, split-payment detection, and reconciliation |
| Delivery Agent | TV4 | order timestamps plus TV2 handoff | Late/on-time classification and delivery cause candidate |
| Policy Agent | TV5 | Structured results from TV2-TV4 | Ordered application of `EC_POLICY_V1` |
| Verifier Agent | TV5 | Draft output and source data when needed | Schema, evidence, ID, money, and limit validation |
| Output Writer | TV5 | Verified output only | Atomic JSON output creation |

The coordinator must not query CSV files or reproduce calculations owned by a
domain agent. The verifier is the final gate before any output is written.

## Runtime Flow

```mermaid
sequenceDiagram
    participant R as run_all.py
    participant C as Coordinator
    participant O as OrderSellerAgent
    participant P as PaymentAgent
    participant D as DeliveryAgent
    participant E as PolicyAgent
    participant V as VerifierAgent
    participant W as OutputWriter

    R->>C: CaseInput
    C->>O: order_seller.request
    O-->>C: order_seller.result
    C->>P: payment.request + order financial totals
    P-->>C: payment.result
    C->>D: delivery.request + seller handoff result
    D-->>C: delivery.result
    C->>E: policy.request + all domain results
    E-->>C: policy.result (draft CaseOutput)
    C->>V: verifier.request + draft CaseOutput
    V-->>C: verifier.result
    alt verified
        C->>W: verified CaseOutput
    else rejected
        C-->>R: case error; no output written
    end
```

Payment and delivery are downstream of Order & Seller because both need its
normalized totals or handoff findings. They may be parallelized later without
changing the message contracts.

## A2A Contract

All calls implement `AgentPort.handle(A2AMessage) -> A2AMessage` from
`shared/a2a_messages.py`. Each response must preserve:

- the request `correlation_id`;
- the input `case_id`;
- the request ID as `causation_id`;
- the expected sender, recipient, and response message type.

Payloads are validated using the models in `shared/schemas.py`. Extra fields are
rejected so contract drift is detected during integration rather than silently
ignored.

## Agent Construction Contract

`run_all.py` composes teammate-owned classes with these public constructors:

```python
OrderSellerAgent(data_dir: Path)
PaymentAgent(data_dir: Path)
DeliveryAgent(data_dir: Path)
PolicyAgent()
VerifierAgent(data_dir: Path)
OutputWriter(output_dir: Path)
```

Each agent exposes the correct `AgentName` in its `name` attribute and implements
`handle`. `OutputWriter.write(CaseOutput)` must write atomically and return only
after the JSON file is complete.

## Failure And Timeout Behavior

- Every agent call has a configurable timeout, defaulting to 30 seconds.
- Failed responses are retried only when marked retryable; exceptions and
  timeouts use the configured retry count.
- A failed case never receives fabricated domain evidence or an unverified
  output.
- The 50-case runner continues with later cases by default and returns a nonzero
  exit code if any case fails. `--fail-fast` stops on the first error.
- Response case/order identity is checked to prevent cross-case contamination.

## Trace

`trace.jsonl` is truncated at the start of every run. It contains run, case,
handoff, timeout/error, and completion events. Each case uses one correlation ID
through all five agent stages. Test traces are written to temporary directories;
the root trace is reserved for the latest real run.

## Validation And Submission

```powershell
python run_all.py --all --validate-only
python run_all.py --case EC_001
python run_all.py --all
pytest -q
```

The submission archive must select exactly `output/EC_001.json` through
`output/EC_050.json`. Repository placeholders, source, trace, metadata, and
secrets must not be included. Models used by agents must have at most 10 billion
parameters, and the exact model names must be declared in source and recorded in
`metadata.json`.
