# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                    |
| --------------- | --------------------------- |
| Họ và tên       | [Họ và tên]                 |
| MSSV            | [MSSV]                      |
| Khóa/Lớp        | K3                          |
| Vai trò chính   | TV3 — Payment Agent         |
| Ngày hoàn thành | 2026-08-05                  |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | --------------- | ---------- |
| Payment data access | `services/payment_repository.py` (`get_payments`) | `order_id` | Payment rows sorted theo `payment_sequential` | Hoàn thành |
| Payment reconciliation | `agents/payment_agent.py` (`compute_reconciliation`, `PaymentAgent`) | `order_id` + `item_total_brl`/`freight_total_brl` từ TV2 (Order & Seller Agent) | `payment_total_brl`, `payment_count`, `is_split_payment`, `reconciled`, `payment_ids` | Hoàn thành |
| Payment tests | `tests/test_payment.py` (7 test) | Ground truth đối chiếu tay từ CSV | 7/7 pass | Hoàn thành |

Phần việc của tôi nằm giữa TV2 và Policy Agent: nhận item/freight total từ Order & Seller Agent, đối soát với toàn bộ payment row, và bàn giao facts (`reconciled`, `is_split_payment`, `payment_total_brl`) cho Policy Agent quyết định `valid_split_payment` hay rơi xuống rule khác. Trường `payment_total_brl` và `payment_ids` tôi bàn giao xuất hiện trực tiếp trong `financial_resolution` và `evidence_ids` của cả 50 output.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Tích hợp pipeline end-to-end (coordinator/policy/delivery/verifier, `run_all.py`) | Cả nhóm | 50/50 output sinh ra, trace thật tại `logging/trace.jsonl` |
| Chuyển model config sang model nhẹ | `shared/constants.py`, `services/model_client.py` | Qwen3-8B → Qwen2.5-1.5B-Instruct, giảm thời gian tải từ ~16GB xuống ~3GB |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Tổng payment chính xác, làm tròn 2 chữ số | `compute_reconciliation` | `payment_total_brl` trong 50 output | `pytest tests/test_payment.py` |
| Nhận diện split payment + đối soát sai số 0.10 BRL | `compute_reconciliation` | 9 case `valid_split_payment` đúng | So với script độc lập đọc CSV thô |
| Payment evidence đúng định dạng `payment:<order_id>:<seq>`, tối đa 5 | `PaymentAgent.analyze` | `evidence_ids`/`payment_ids` 50 case | `VerifierAgent` kiểm tra tồn tại trong CSV |
| Không suy diễn refund ledger/transaction ID | docstring contract + verifier | Không ID lạ nào trong output | grep output/ |

Output cụ thể phần việc của tôi tạo ra: 9 case `valid_split_payment` (ví dụ `output/EC_004.json` — 2 payment row, tổng 211.96 khớp 179.90 + 32.06 trong sai số 0.10) và trường `payment_total_brl` đúng ở toàn bộ 50 case, đã đối chiếu bằng script độc lập.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Một order Olist có thể có nhiều payment row (tối đa 29 trong dataset); khách hàng thấy nhiều dòng trừ tiền và nghi bị thu trùng. Pipeline cần một nguồn số liệu payment đáng tin: tổng đã trả, có phải split payment không, và tổng đó có khớp giá trị đơn hàng không — vì rule `valid_split_payment` và mọi khoản refund đều phụ thuộc số này.

### Cách triển khai

`get_payments` nạp CSV một lần (`lru_cache`), index theo `order_id`, sort theo `payment_sequential`. `compute_reconciliation` cộng **toàn bộ** payment row rồi mới làm tròn 2 chữ số (cap 5 ID chỉ áp cho danh sách evidence, không áp cho tổng); đối soát `|payment_total − (item_total + freight_total)| ≤ 0.10 BRL`. Toàn bộ là Python thuần — LLM chỉ sinh ghi chú trace, không bao giờ tạo số liệu được chấm.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `order_id`; `item_total_brl`, `freight_total_brl` (handoff từ TV2, = 0.0 khi order không có item row) |
| Output | `PaymentReconciliation`: `payment_total_brl`, `payment_count`, `is_split_payment`, `reconciled`, `payment_ids` (≤5) |
| Module phụ thuộc | `services/payment_repository.py`, `shared/constants.py` |
| Module sử dụng output | `agents/policy_agent.py` (quyết định rule), `agents/coordinator_agent.py` (lắp `financial_resolution`, `evidence_ids`) |
| Điều kiện lỗi cần xử lý | Order không có payment row → tổng 0.0, list rỗng, không raise; order thiếu item (unavailable) → đối soát với 0.0 vẫn chạy đúng |

### Cách xác minh

```bash
.venv/bin/python -m pytest tests/test_payment.py -v   # 7/7 pass
.venv/bin/python run_all.py                            # 50 case, trace tại logging/trace.jsonl
```

- **Kết quả mong đợi:** 7 test pass; 50 output có `payment_total_brl` khớp CSV.
- **Kết quả thực tế:** 7/7 pass (0.15s); 50/50 output khớp script đối chiếu độc lập.
- **Artifact/log:** `output/EC_*.json`, `logging/trace.jsonl` (không chứa secret).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chọn model cho pipeline khi cấu hình cũ khai báo Qwen3-8B (~16GB weights).
- **Các phương án đã cân nhắc:** (1) Giữ Qwen3-8B — chất lượng sinh text tốt hơn nhưng tải rất lâu; (2) Qwen2.5-1.5B-Instruct — nhẹ (~3GB), đã cache local; (3) không dùng LLM.
- **Phương án đã chọn:** Qwen2.5-1.5B-Instruct, greedy decoding, và thiết kế "deterministic core, LLM ở rìa".
- **Lý do:** Mọi trường được chấm điểm (số tiền, evidence, issue) đều tính bằng code thuần nên model lớn không tăng độ chính xác; model nhỏ giảm thời gian tải/chạy (50 case trong 16.5s) và vẫn thỏa ràng buộc ≤10B.
- **Bằng chứng quyết định phù hợp:** 50/50 case khớp ground truth độc lập; trace ghi 50 lượt `llm_intent` chạy thật.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Trong lúc merge từ `main`, `tests/test_payment.py` bị conflict: nhánh main chỉ chứa placeholder `"""Tests for payment reconciliation."""` đè lên bộ test thật; sau đó khi chuyển sang branch làm việc chung, `agents/payment_agent.py` và `services/payment_repository.py` là file rỗng.
- **Lệnh hoặc bước tái hiện:** `git merge main` trên nhánh cá nhân → conflict markers `<<<<<<< HEAD`; `git checkout backup` → `head agents/payment_agent.py` ra file rỗng.
- **Nguyên nhân gốc:** Hai nhánh khởi tạo scaffold độc lập: main tạo file stub cùng tên với file tôi đã viết, lịch sử không chung một gốc cho các file đó.
- **Cách xử lý:** Resolve conflict giữ bộ test thật; trên branch chung, khôi phục 3 file từ nhánh cá nhân bằng `git show phuongntn/dev:<path> > <path>` rồi adapt import sang convention chung (`shared/constants.py`, `QwenModelClient`).
- **Cách xác minh sau khi sửa:** `pytest tests/` — 43/43 pass (7 test payment nguyên vẹn); chạy lại 50 case khớp ground truth.
- **Điều học được:** Khi nhiều người scaffold cùng cấu trúc, cần thống nhất file owner sớm; luôn commit trước khi đổi nhánh, và verify nội dung file sau merge thay vì tin tên file.

## 7. Hiểu biết về luồng end-to-end

> Bộ câu hỏi trong template thuộc lab khác (Crossref/vector index/retrieval). Phần dưới trả lời theo luồng end-to-end thật của lab Day 9 này.

**Câu trả lời:**

1. **Dữ liệu đi từ input đến output như thế nào?** `input/EC_xxx.json` cho `claimed_order_id` → Coordinator dispatch: Order & Seller Agent (status, items, sellers, totals, mốc bàn giao carrier vs shipping limit) → Payment Agent (đối soát payment) → Delivery Agent (giao thực tế vs estimate) → Policy Agent áp EC_POLICY_V1 theo thứ tự ưu tiên → Verifier kiểm chứng → ghi `output/EC_xxx.json` + trace.
2. **Điểm mỗi case được đo ra sao?** Chấm theo trọng số: primary issue + confidence (20%), affected entities (20%), root cause + responsible parties (15%), evidence (15%), financial resolution (20%), actions (10%); case bị hard gate nhận 0 — vì vậy Verifier chặn mọi output sai schema/evidence trước khi ghi.
3. **Kiểm chứng khác gì suy diễn trong lab này?** Mọi kết luận phải dựng được từ CSV (evidence ID phải tồn tại thật); Olist không có refund ledger/transaction ID nên tuyệt đối không suy diễn — Verifier từ chối ID ngoài 5 định dạng cho phép.
4. **Vì sao cần cùng một bộ facts cho mọi rule?** Policy Agent chỉ nhận facts đã kiểm chứng từ 3 agent domain, không tự đọc CSV — nhờ đó cùng một case luôn ra cùng kết luận và trace giải thích được từng quyết định.
5. **Pipeline được xem là thành công dựa trên artifact nào?** 50 file `output/EC_*.json` hợp lệ schema, `logging/trace.jsonl` của lượt chạy thật (602 events), 43 test pass, và đối chiếu độc lập 50/50 khớp rule.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** [YYYY-MM-DD]
