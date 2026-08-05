
def order_evidence_id(order_id: str) -> str:
    return f"order:{order_id}"


def payment_entity_id(order_id: str, payment_sequential: int | str) -> str:
    return f"{order_id}:{payment_sequential}"


def payment_evidence_id(order_id: str, payment_sequential: int | str) -> str:
    return f"payment:{payment_entity_id(order_id, payment_sequential)}"


def policy_evidence_id(root_cause_code: str) -> str:
    return f"policy:{root_cause_code}"
