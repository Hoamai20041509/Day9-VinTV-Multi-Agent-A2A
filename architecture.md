# Bao cao kien truc Multi-Agent

## 1. Nguyen tac thiet ke

He thong dung mo hinh multi-agent theo domain. Moi agent co mot nhiem vu hep,
quyen doc rieng va contract handoff ro rang. Coordinator khong tu suy dien
fact; no chi truyen case, nhan handoff va lap output cuoi.

Model duoc khai bao thong nhat cho runtime la:

```text
Model: Qwen/Qwen3-8B
Parameters: 8.2B
Framework: Hugging Face Transformers
Runtime: local
Thinking mode: false cho tac vu structured
```

Qwen3-8B nam trong gioi han 10B cua bai. Tuy nhien cac quyet dinh co tinh
chinh xac cao (ID, timestamp, BRL, policy code) duoc thuc hien bang domain
logic deterministic. Model client lazy-load chi dung cho lop dien giai khi can;
LLM khong duoc phep thay doi evidence, refund, responsible party hoac action.

## 2. So do agent va thu tu handoff

```text
Case JSON
   |
   v
[Coordinator Agent]
   |
   +--> [Order & Seller Agent] -- order/seller handoff --+
   |                                                     |
   +--> [Payment Agent] -------- payment handoff --------+--> [Policy Agent]
   |                                                     |       |
   +--> [Delivery Agent] ------- delivery handoff -------+       v
   |                                                          [Verifier]
   |                                                             |
   +------------------------- trace ----------------------------+
                                                                 v
                                                          Final JSON output
```

Thu tu thuc thi mot case:

```text
Coordinator
  -> Order & Seller
  -> Payment
  -> Delivery
  -> Policy
  -> Verifier
  -> Output Writer
```

Moi case tao 5 agent handoff. 50 case tao 250 event trong
`logging/trace.jsonl` de kiem tra A2A flow.

## 3. Agent responsibilities

### 3.1 Coordinator Agent

**File:** `agents/coordinator_agent.py`

**Model:** Qwen3-8B duoc khai bao; orchestration chinh la deterministic.

**Nhiem vu:**

- Doc `case_id` va `claimed_order_id`.
- Goi cac domain agent theo thu tu.
- Truyen output cua agent truoc vao agent sau.
- Lap output schema duy nhat.
- Gui candidate output qua Verifier truoc khi ghi file.

**Khong lam:** khong tu cong tien, khong tu so sanh timestamp, khong tu chon
root cause.

### 3.2 Order & Seller Agent

**File:** `agents/order_seller_agent.py`

**Repository:** `services/order_repository.py`, `services/item_repository.py`.

**Model:** Qwen3-8B la model runtime duoc khai bao; phan truy xuat va tinh toan
khong dung sampling.

**Nhiem vu:**

- Kiem tra order ton tai va tra `order_status`.
- Lay item IDs va seller IDs, gioi han toi da 5.
- Tinh `item_total_brl` va `freight_total_brl` bang `Decimal`.
- So sanh `order_delivered_carrier_date` voi `shipping_limit_date` cua tung item.
- Tra `late_item_ids`, `late_seller_ids` va `late_handoffs`.

**Handoff:**

```text
order_found, order_status, order,
item_ids, seller_ids,
item_total_brl, freight_total_brl,
late_handoff, late_item_ids, late_seller_ids, late_handoffs
```

### 3.3 Payment Agent

**File:** `agents/payment_agent.py`

**Repository:** `services/payment_repository.py`.

**Model:** Qwen3-8B duoc khai bao; phep cong payment la deterministic.

**Nhiem vu:**

- Lay payment rows va payment IDs.
- Cong tung `payment_value`, khong nhan voi installments.
- Tinh expected total tu item + freight handoff.
- Xac dinh `is_split_payment` va `payment_matches` trong sai so `0.10 BRL`.

**Handoff:**

```text
payment_ids, payment_count, payment_total_brl,
expected_total_brl, difference_brl,
payment_matches, is_split_payment
```

### 3.4 Delivery Agent

**File:** `agents/delivery_agent.py`

**Service:** `services/delivery_analysis.py`.

**Model:** Qwen3-8B duoc khai bao; timestamp comparison la deterministic.

**Nhiem vu:**

- Doc delivered customer date va estimated delivery date tu order handoff.
- Tra `delivered_late` hoac `delivered_within_estimate`.
- Khong tu suy dien carrier checkpoint hay seller responsibility.

**Handoff:**

```text
order_delivered_customer_date,
order_estimated_delivery_date,
delivered_late, delivered_within_estimate
```

### 3.5 Policy Agent

**Files:** `agents/policy_agent.py`, `services/policy_engine.py`.

**Model:** Qwen3-8B duoc khai bao; policy engine deterministic de tranh hallucination.

**Nhiem vu:** nhan ba handoff va ap dung `EC_POLICY_V1` theo priority:

1. `canceled_order_paid`
2. `unavailable_order_paid`
3. `late_delivery_seller`
4. `late_delivery_logistics`
5. `valid_split_payment`
6. `unsupported_late_claim`

**Handoff:**

```text
primary_issue, case_status, confidence,
cause_code, responsible_parties,
recommended_refund_brl, resolution_actions
```

### 3.6 Verifier Agent

**File:** `agents/verifier_agent.py`

**Model:** Qwen3-8B khong duoc phep sua candidate output; verifier la code-based.

**Nhiem vu:**

- Kiem top-level schema va enum values.
- Kiem gioi han: 5 entities, 10 evidence, 3 causes, 3 parties, 5 actions.
- Kiem evidence ID dung format va thuoc entity/cause handoff.
- Kiem root cause khop primary issue.
- Kiem action va refund khop policy.
- Kiem `case_status` khop refund.

Chi output pass verifier moi duoc `Output Writer` ghi vao `output/EC_*.json`.

## 4. A2A contract va ownership

| Handoff | Producer | Consumer | Du lieu chinh |
| --- | --- | --- | --- |
| Order/Seller | Order & Seller | Coordinator, Policy | status, entities, totals, late seller |
| Payment | Payment | Coordinator, Policy | payments, reconciliation |
| Delivery | Delivery | Coordinator, Policy | late/within estimate |
| Policy | Policy | Coordinator, Verifier | issue, cause, party, refund, action |
| Candidate output | Coordinator | Verifier | final schema draft |
| Verified output | Verifier | Output Writer | JSON duoc phep nop |

Agent chi so huu output cua minh. Consumer khong ghi nguoc vao producer state;
vi vay co the replay trace va tim dung agent gay sai.

## 5. Model strategy

Qwen3-8B duoc ghi ro trong `shared/constants.py` va `logging/metadata.json`.
`services/model_client.py` su dung lazy loading, `device_map="auto"` va
`torch_dtype="auto"`; test nghiep vu khong can tai weights.

Ly do khong de LLM tu sinh ket qua:

- ID CSV phai exact-match.
- Timestamp va Decimal can ket qua lap lai.
- Evidence khong duoc la su kien tuong tuong.
- Policy co priority ro rang va de test bang unit test.

Model phu hop cho lop language/explanation, con domain agents la cac tool
structured ma model co the goi khi runtime duoc bat.

## 6. Audit va reproducibility

```bash
venv/bin/python -m agents.coordinator_agent
venv/bin/python -m pytest -q
```

Coordinator truncate trace truoc moi run. Output writer ghi atomic qua file tam.
Archive nop bai chi nen tao tu cac JSON:

```bash
rm -f output.zip
zip -j -q output.zip output/EC_*.json
```

Kiem chung hien tai: 50/50 case, 250 handoff trace va 19 automated tests pass.
