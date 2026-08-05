from services.policy_engine import evaluate_rule_5_valid_split_payment


class PolicyAgent:
    """Policy shell for merge work. Currently implements only EC_POLICY_V1 rule 5."""

    def evaluate_rule_5(self, payment_handoff: dict) -> dict | None:
        decision = evaluate_rule_5_valid_split_payment(payment_handoff)
        return decision.to_dict() if decision else None
