# Multi-Agent Architecture

## Ownership

This repo follows the README split by data domain. Each agent owns a narrow data surface and hands structured evidence to the coordinator/policy layer instead of putting all reasoning in one prompt.

## Rule 5 Scope: Payment Agent

Owner module:

- `agents/payment_agent.py`
- `services/payment_repository.py`
- `services/policy_engine.py` for the isolated rule-5 evaluator
- `shared/schemas.py`, `shared/evidence.py`, `shared/constants.py` for handoff contracts

Data access:

- Reads only `data/olist_order_payments_dataset.csv`.
- Receives `item_total_brl` and `freight_total_brl` from Order & Seller Agent.
- Does not infer refund ledgers, transaction IDs, or missing payment events.

Handoff payload:

- `payment_rows`
- `payment_total_brl`
- `payment_row_count`
- `payment_ids`
- `evidence_ids`
- `has_split_payment`
- `reconciled_with_order_total`
- `reconciliation_delta_brl`
- `valid_split_payment`

Rule 5 condition:

`valid_split_payment = payment_row_count >= 2 and abs(payment_total_brl - (item_total_brl + freight_total_brl)) <= 0.10`

When the policy layer calls rule 5 after rules 1-4, a matched case returns:

- `primary_issue`: `valid_split_payment`
- `case_status`: `no_action`
- `root_cause`: `MULTIPLE_PAYMENTS_RECONCILED`
- `responsible_party`: `none`
- `recommended_refund_brl`: `0.0`
- `resolution_actions`: `explain_valid_split_payment`

## Handoff Flow

```text
Coordinator
    -> Order & Seller Agent
        -> item_total_brl, freight_total_brl, item/seller evidence
    -> Payment Agent
        -> payment total, payment rows, split-payment reconciliation
    -> Delivery Agent
        -> delivery timing and candidate cause

Policy Agent
    -> applies EC_POLICY_V1 in README priority order
    -> rule 5 is evaluated only after canceled/unavailable/late-delivery rules

Verifier Agent
    -> validates schema, evidence ID formats, array limits, money values
```
