# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung            |
| --------------- | ------------------- |
| Họ và tên       | Ngo Thi Ngoc Phuong |
| MSSV            | 01569               |
| Khóa/Lớp        | K3                  |
| Vai trò chính   | TV3 — Payment Agent |
| Ngày hoàn thành | 2026-08-05          |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | --------------- | ---------- |
| Payment data access | `services/payment_repository.py` (`get_payments`) | `order_id` | Payment rows sort theo `payment_sequential`, load 1 lần bằng `lru_cache` | Hoàn thành |
| Payment reconciliation | `agents/payment_agent.py` (`compute_reconciliation`, `PaymentAgent`) | `order_id` + `item_total_brl`/`freight_total_brl` handoff từ TV2 (Order & Seller Agent) | `payment_total_brl`, `payment_count`, `is_split_payment`, `reconciled`, `payment_ids` (≤5) | Hoàn thành |
| Payment tests | `tests/test_payment.py` (7 test) | Ground truth đối chiếu tay từ CSV thô | 7/7 pass | Hoàn thành |

Vị trí của tôi trong pipeline: nhận item/freight total từ TV2, đối soát với toàn bộ payment row của order, và bàn giao facts (`reconciled`, `is_split_payment`, `payment_total_brl`) cho Policy Agent quyết định `valid_split_payment` hay rơi xuống rule khác theo thứ tự ưu tiên EC_POLICY_V1. Hai trường tôi bàn giao (`payment_total_brl`, `payment_ids`) xuất hiện trực tiếp trong `financial_resolution` và `evidence_ids` của cả 50 output — tức chạm vào 35% trọng số điểm (Tài chính 20% + Bằng chứng 15%).

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Tích hợp pipeline end-to-end (coordinator, policy, delivery, verifier, `run_all.py`) | Cả nhóm | 50/50 output sinh ra trong 16.5s, trace thật tại `logging/trace.jsonl` |
| Đổi model config sang model nhẹ | `shared/constants.py`, `services/model_client.py`, `tests/test_model_config.py` | Qwen3-8B (~16GB) → Qwen2.5-1.5B-Instruct (~3GB), giữ ràng buộc ≤10B |
| Phân tích điểm leaderboard theo từng thành phần | Chiến lược nộp bài của nhóm | Xác định 4 case biên ngày (EC_033/034/037/044) + giả thuyết confidence-scaling; dựng 2 zip thí nghiệm một-biến trong `submissions/` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Tổng payment chính xác, làm tròn 2 chữ số | `compute_reconciliation` | `payment_total_brl` đúng ở 50/50 output | `pytest tests/test_payment.py` + script đối chiếu độc lập đọc CSV thô |
| Nhận diện split payment, đối soát sai số ≤ 0.10 BRL | `compute_reconciliation` | 9 case `valid_split_payment` đúng | So với script độc lập; điểm leaderboard |
| Payment evidence `payment:<order_id>:<seq>`, tối đa 5 | `PaymentAgent.analyze` | `payment_ids` trong evidence/entities của 50 case | `VerifierAgent` kiểm tra từng ID tồn tại trong CSV |
| Không suy diễn refund ledger / transaction ID | Docstring contract + verifier regex 5 định dạng | Không ID ngoài chuẩn trong output | `grep` toàn bộ `output/` |

Output cụ thể phần việc của tôi tạo ra: 9 case `valid_split_payment` (ví dụ `output/EC_004.json` — 2 payment row credit_card + voucher, tổng 211.96 khớp 179.90 + 32.06 trong sai số 0.10) và trường `payment_total_brl` đúng ở toàn bộ 50 case. Bài nộp nhóm đạt **95.3320 điểm**, trong đó thành phần Tài chính đạt 94.80 và Bằng chứng 95.87.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Một order Olist có thể có nhiều payment row (tối đa 29 trong dataset; trong 50 case chính thức tối đa 3); khách hàng thấy nhiều dòng trừ tiền và nghi bị thu trùng. Pipeline cần một nguồn số liệu payment đáng tin: tổng đã trả bao nhiêu, có phải split payment không, và tổng đó có khớp giá trị đơn hàng không — vì rule `valid_split_payment` và mọi khoản refund (`canceled`/`unavailable` hoàn theo tổng payment) đều phụ thuộc con số này.

### Cách triển khai

`get_payments` nạp CSV một lần (`lru_cache`), index theo `order_id`, sort theo `payment_sequential` để evidence ID ổn định. `compute_reconciliation` cộng **toàn bộ** payment row rồi mới làm tròn 2 chữ số — cap 5 ID chỉ áp cho danh sách evidence, không bao giờ áp cho tổng tiền (test bằng order thật có 29 payment row: tổng vẫn đủ 457.99, evidence chỉ lấy 5 ID đầu). Đối soát theo công thức `|payment_total − (item_total + freight_total)| ≤ 0.10 BRL`. Toàn bộ là Python thuần, không đi qua LLM — model chỉ sinh ghi chú tiếng Việt cho trace, không bao giờ tạo số liệu được chấm điểm.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `order_id`; `item_total_brl`, `freight_total_brl` (handoff từ TV2; bằng 0.0 khi order không có item row) |
| Output | `PaymentReconciliation`: `payment_total_brl`, `payment_count`, `is_split_payment`, `reconciled`, `payment_ids` (≤5, dạng `payment:<order_id>:<seq>`) |
| Module phụ thuộc | `services/payment_repository.py`, `shared/constants.py` (tolerance, model name) |
| Module sử dụng output | `agents/policy_agent.py` (quyết định rule), `agents/coordinator_agent.py` (lắp `financial_resolution`, `affected_entities.payment_ids`, `evidence_ids`) |
| Điều kiện lỗi cần xử lý | Order không có payment row → tổng 0.0, list rỗng, không raise; order thiếu item (8 case `unavailable`) → đối soát với 0.0 vẫn trả kết quả hợp lệ để Policy Agent xử lý theo rule ưu tiên cao hơn |

### Cách xác minh

```bash
.venv/bin/python -m pytest tests/test_payment.py -v   # 7/7 pass
.venv/bin/python -m pytest tests/ -q                   # 43/43 pass toàn pipeline
.venv/bin/python run_all.py                            # 50 case, trace tại logging/trace.jsonl
```

- **Kết quả mong đợi:** 7 test payment pass; 50 output có `payment_total_brl` khớp CSV thô.
- **Kết quả thực tế:** 7/7 pass (0.15s); 43/43 pass; 50/50 output khớp script đối chiếu độc lập; leaderboard 95.3320.
- **Artifact/log:** `output/EC_*.json`, `logging/trace.jsonl` (602 events, không chứa secret).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chọn model cho pipeline khi cấu hình ban đầu của nhóm khai báo Qwen3-8B (~16GB weights), thời gian competition chỉ có 3 tiếng.
- **Các phương án đã cân nhắc:** (1) Giữ Qwen3-8B — sinh text tốt hơn nhưng tải rất lâu, rủi ro nghẽn ngay đầu giờ; (2) Qwen2.5-1.5B-Instruct — nhẹ (~3GB), đã cache local; (3) bỏ hẳn LLM — nhanh nhất nhưng làm yếu tính "multi-agent dùng model" của bài.
- **Phương án đã chọn:** Qwen2.5-1.5B-Instruct, greedy decoding, kiến trúc "deterministic core, LLM ở rìa": LLM chỉ phân loại intent và narrate, mọi số liệu được chấm là code thuần.
- **Lý do:** Mọi trường được chấm (số tiền, evidence, primary issue) đều tính bằng code nên model lớn không tăng độ chính xác — chỉ tăng thời gian; model nhỏ vẫn thỏa ràng buộc ≤10B và cho phép chạy cả 50 case trong 16.5s.
- **Bằng chứng quyết định phù hợp:** 50/50 case khớp ground truth độc lập; trace ghi 50 lượt `llm_intent` chạy thật với model 1.5B; điểm 95.33 không mất ở khâu tốc độ hay sai số.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Sau khi merge từ `main`, `tests/test_payment.py` chứa conflict markers (`<<<<<<< HEAD ... >>>>>>> main` — phía main chỉ là placeholder docstring). Sau đó khi chuyển sang branch chung `backup`, `agents/payment_agent.py` và `services/payment_repository.py` là **file rỗng** dù cùng tên với file tôi đã viết.
- **Lệnh hoặc bước tái hiện:** `git merge main` trên nhánh cá nhân → conflict; `git checkout backup` → `head agents/payment_agent.py` ra file trống.
- **Nguyên nhân gốc:** Hai nhánh scaffold cùng cấu trúc file một cách độc lập, không chung lịch sử cho các file đó — nhánh chung tạo stub rỗng trùng tên với file thật của tôi, và công việc của tôi chỉ được commit trên `phuongntn/dev`.
- **Cách xử lý:** Resolve conflict giữ bộ test thật; trên branch chung khôi phục 3 file bằng `git show phuongntn/dev:<path> > <path>`, rồi adapt sang convention chung của nhóm (`shared/constants.py` cho `MODEL_NAME`/tolerance, dùng `QwenModelClient` thay vì tự tạo transformers pipeline riêng).
- **Cách xác minh sau khi sửa:** `pytest tests/` — 43/43 pass, trong đó 7 test payment nguyên vẹn; chạy lại 50 case cho kết quả khớp ground truth độc lập.
- **Điều học được:** Khi nhiều người scaffold cùng cấu trúc, phải thống nhất file owner sớm; luôn commit trước khi đổi nhánh; sau merge phải verify **nội dung** file chứ không tin tên file.

## 7. Hiểu biết về luồng end-to-end

> Bộ câu hỏi trong template thuộc lab khác (Crossref/vector index/retrieval). Phần dưới trả lời theo luồng end-to-end thật của lab Day 9 này.

**Câu trả lời:**

1. **Dữ liệu đi từ input đến output như thế nào?** `input/EC_xxx.json` cho `claimed_order_id` → Coordinator dispatch tuần tự: Order & Seller Agent (status, items, sellers, totals, so `order_delivered_carrier_date` với từng `shipping_limit_date`) → Payment Agent (đối soát payment, phần của tôi) → Delivery Agent (giao thực tế vs estimate) → Policy Agent áp 6 rule EC_POLICY_V1 theo thứ tự ưu tiên trên facts đã kiểm chứng → Verifier gate → ghi `output/EC_xxx.json` + trace.
2. **Điểm mỗi case được đo ra sao?** Tổng có trọng số: primary issue + confidence (20%), affected entities (20%), root cause + parties (15%), evidence (15%), financial (20%), actions (10%); case hard-gate nhận 0 — nên Verifier chặn mọi output sai schema/evidence trước khi ghi.
3. **Kiểm chứng khác gì suy diễn trong lab này?** Mọi evidence ID phải dựng được trực tiếp từ CSV (5 định dạng cho phép); Olist không có refund ledger/transaction ID nên tuyệt đối không suy diễn — Verifier từ chối ID sai định dạng hoặc không tồn tại.
4. **Vì sao Policy Agent chỉ nhận facts, không đọc CSV?** Để cùng một case luôn ra cùng kết luận và mọi quyết định truy vết được về đúng finding trong trace — nếu Policy tự đọc dữ liệu, không thể biết kết luận dựa trên gì khi debug.
5. **Pipeline được xem là thành công dựa trên artifact nào?** 50 file `output/EC_*.json` hợp lệ schema, `logging/trace.jsonl` của lượt chạy thật, 43 test pass, script đối chiếu độc lập 50/50 khớp, và điểm leaderboard 95.3320 có breakdown từng thành phần.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngo Thi Ngoc Phuong
**Ngày xác nhận:** 2026-08-05
