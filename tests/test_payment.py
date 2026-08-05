import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.payment_agent import PaymentAgent
from services.payment_repository import PaymentRepository
from services.policy_engine import evaluate_rule_5_valid_split_payment


class PaymentAgentTest(unittest.TestCase):
    def _repo(self, rows):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        csv_path = Path(tmp.name) / "payments.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "order_id",
                    "payment_sequential",
                    "payment_type",
                    "payment_installments",
                    "payment_value",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        return PaymentRepository(csv_path)

    def test_valid_split_payment_reconciles_within_tolerance(self):
        repo = self._repo(
            [
                {
                    "order_id": "o1",
                    "payment_sequential": "1",
                    "payment_type": "credit_card",
                    "payment_installments": "1",
                    "payment_value": "40.00",
                },
                {
                    "order_id": "o1",
                    "payment_sequential": "2",
                    "payment_type": "voucher",
                    "payment_installments": "1",
                    "payment_value": "10.05",
                },
            ]
        )

        result = PaymentAgent(repo).analyze("o1", item_total_brl=45, freight_total_brl=5)

        self.assertEqual(result.payment_total_brl, 50.05)
        self.assertEqual(result.payment_row_count, 2)
        self.assertTrue(result.has_split_payment)
        self.assertTrue(result.reconciled_with_order_total)
        self.assertTrue(result.valid_split_payment)
        self.assertEqual(result.payment_ids, ["o1:1", "o1:2"])
        self.assertEqual(result.evidence_ids, ["payment:o1:1", "payment:o1:2"])

    def test_single_payment_is_not_rule_5(self):
        repo = self._repo(
            [
                {
                    "order_id": "o2",
                    "payment_sequential": "1",
                    "payment_type": "credit_card",
                    "payment_installments": "1",
                    "payment_value": "50.00",
                }
            ]
        )

        result = PaymentAgent(repo).analyze("o2", item_total_brl=45, freight_total_brl=5)

        self.assertFalse(result.has_split_payment)
        self.assertTrue(result.reconciled_with_order_total)
        self.assertFalse(result.valid_split_payment)
        self.assertIsNone(evaluate_rule_5_valid_split_payment(result))

    def test_policy_rule_5_decision(self):
        repo = self._repo(
            [
                {
                    "order_id": "o3",
                    "payment_sequential": "1",
                    "payment_type": "voucher",
                    "payment_installments": "1",
                    "payment_value": "20.00",
                },
                {
                    "order_id": "o3",
                    "payment_sequential": "2",
                    "payment_type": "credit_card",
                    "payment_installments": "2",
                    "payment_value": "80.00",
                },
            ]
        )

        result = PaymentAgent(repo).analyze("o3", item_total_brl=90, freight_total_brl=10)
        decision = evaluate_rule_5_valid_split_payment(result)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.primary_issue, "valid_split_payment")
        self.assertEqual(decision.case_status, "no_action")
        self.assertEqual(decision.recommended_refund_brl, 0.0)
        self.assertEqual(decision.resolution_actions, ["explain_valid_split_payment"])
        self.assertIn("policy:MULTIPLE_PAYMENTS_RECONCILED", decision.evidence_ids)


if __name__ == "__main__":
    unittest.main()
