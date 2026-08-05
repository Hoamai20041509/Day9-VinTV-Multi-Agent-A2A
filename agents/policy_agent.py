"""Policy agent wrapper around the versioned deterministic engine."""

from services.policy_engine import apply_policy


class PolicyAgent:
    def analyze(self, order_result, payment_result, delivery_result):
        return apply_policy(order_result, payment_result, delivery_result)

    def run(self, order_result, payment_result, delivery_result):
        return self.analyze(order_result, payment_result, delivery_result)
