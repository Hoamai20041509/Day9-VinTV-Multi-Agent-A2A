# Member Role Report - Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Lương Thị Linh |
| MSSV | 01015 |
| Khóa/Lớp | K3 |
| Vai trò chính | TV5c - Verifier Agent, kiểm chứng output và evidence trước khi ghi file |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Verifier Agent | `agents/verifier_agent.py`: `VerifierAgent.verify`, `_evidence_exists` | Draft output do pipeline tạo sau khi Policy Agent quyết định | Danh sách lỗi kiểm chứng; rỗng nghĩa là output được phép ghi | Hoàn thành |
| Kiểm tra schema output | `shared/schemas.py`: `validate_case_output` | Một object theo format `CaseOutput` | Lỗi về cấu trúc, enum, giới hạn số lượng, số tiền, confidence | Hoàn thành |
| Kiểm tra evidence ID | `shared/evidence.py`: `parse_evidence_id`, vocabulary root cause | `evidence_ids` trong output | Phát hiện ID sai format hoặc không dựng được từ CSV | Hoàn thành |
| Kiểm tra tài chính và trạng thái case | `agents/verifier_agent.py` | `primary_issue`, `case_status`, `financial_resolution` | Bắt lỗi refund sai policy hoặc `case_status` không khớp refund | Hoàn thành |
| Ghi output đã qua kiểm chứng | `services/output_writer.py`: `write_case_output` | Output đã hợp lệ | File `output/EC_xxx.json` UTF-8, indent 2 | Hoàn thành |
| Test verifier | `tests/test_verifier.py` | Case thật `EC_003` và các biến thể lỗi | 7 test kiểm tra valid output, evidence, refund, status, cap, confidence | Hoàn thành |

Ranh giới phần việc của tôi là lớp kiểm chứng cuối trước khi nộp. Tôi không tự tính trạng thái đơn hàng, tổng item/freight, tổng payment, giao trễ hay chọn rule policy thay cho các agent domain. Tôi kiểm tra output mà các phần trước tạo ra có đúng schema, có evidence tồn tại trong dữ liệu thật và có nhất quán với `EC_POLICY_V1` hay không.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Chuẩn hóa định dạng evidence ID | TV2 Order/Seller, TV3 Payment, TV4 Delivery, TV5 Policy | Chốt 5 dạng hợp lệ: `order`, `item`, `payment`, `seller`, `policy` |
| Bổ sung hard gate cho refund | Policy Agent và Coordinator | Output sai số tiền hoàn bị chặn trước khi ghi file |
| Bổ sung test lỗi chủ động | Toàn pipeline | Verifier không chỉ pass happy path mà còn bắt ID sai, evidence không tồn tại, vượt cap và confidence ngoài `[0,1]` |
| Đảm bảo output ghi bằng UTF-8 | Submission artifact | File JSON có tiếng Việt hoặc ký tự đặc biệt không bị lỗi encoding trên Windows |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Kiểm tra output hợp lệ đi qua gate | `VerifierAgent.verify` | Output chuẩn trả `[]` | `python -m pytest -q tests/test_verifier.py` |
| Bắt evidence không tồn tại trong CSV | `_evidence_exists`, repositories | `payment:<fake_order>:1` bị báo `not found in data` | `test_nonexistent_evidence_is_flagged` |
| Bắt evidence sai định dạng | `parse_evidence_id` | `transaction:abc123` bị báo malformed | `test_malformed_evidence_is_flagged` |
| Bắt refund sai rule | `VerifierAgent.verify` | `canceled_order_paid` phải hoàn tổng payment, không được chỉ hoàn freight | `test_refund_mismatching_policy_is_flagged` |
| Bắt `case_status` không nhất quán | `VerifierAgent.verify` | Refund > 0 phải là `action_required`, refund = 0 phải là `no_action` | `test_case_status_inconsistent_with_refund_is_flagged` |
| Bắt vi phạm giới hạn output | `validate_case_output` | Entity vượt 5 ID, evidence vượt 10, confidence ngoài `[0,1]` bị báo lỗi | `test_entity_cap_violation_is_flagged`, `test_confidence_out_of_range_is_flagged` |
| Ghi output đúng tên file | `write_case_output` | Output được ghi thành `<case_id>.json` trong `output/` | Đối chiếu 50 file `output/EC_001.json` đến `output/EC_050.json` |

Một artifact cụ thể cho phần của tôi là bộ test `tests/test_verifier.py`, dùng case thật `EC_003` với order `71303d7e93b399f5bcd537d124c0bcfa`. Case này có order, item, seller, payment và policy evidence hợp lệ nên phù hợp để kiểm chứng toàn bộ đường đi: schema đúng, evidence thật sự tồn tại trong CSV, refund của `canceled_order_paid` bằng tổng payment và `case_status` là `action_required`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Trong bài lab này, output không chỉ cần "trông giống JSON đúng". Mỗi evidence ID phải có thể dựng trực tiếp từ dữ liệu Olist, mỗi khoản refund phải đúng rule, và các mảng phải nằm trong giới hạn chấm điểm. Nếu Verifier lỏng, pipeline có thể nộp ra các ID không tồn tại như transaction/refund ledger, hoặc hoàn sai tiền nhưng vẫn ghi file. Những lỗi này thường bị hard gate hoặc mất điểm nặng ở evidence, financial resolution và primary issue.

### Cách triển khai

Tôi triển khai Verifier theo ba lớp:

1. **Structural gate.** Gọi `validate_case_output` để kiểm tra `case_id`, `primary_issue`, `case_status`, `confidence`, entity sets, ranked causes, responsible parties, evidence, financial fields và resolution actions.
2. **Evidence gate.** Với từng `evidence_id`, dùng `parse_evidence_id` để kiểm tra format. Sau đó `_evidence_exists` đối chiếu dữ liệu thật: order qua `OrderRepository`, item và seller qua `ItemRepository`, payment qua `payment_repository.get_payments`, policy qua tập `ROOT_CAUSE_CODES`.
3. **Finance gate.** Dựa trên `primary_issue`, tính refund kỳ vọng: canceled/unavailable hoàn tổng payment, late seller/logistics hoàn tổng freight, split payment và unsupported claim hoàn `0.0`. Nếu `recommended_refund_brl` khác kỳ vọng thì output bị chặn.
4. **Status consistency gate.** Nếu refund > 0 thì `case_status` phải là `action_required`; nếu refund = 0 thì phải là `no_action`.
5. **Output writer.** Chỉ ghi output sau khi không còn violation; file ghi bằng `encoding="utf-8"`, `ensure_ascii=False`, `indent=2` để artifact đọc được và ổn định khi diff.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Một dict output hoàn chỉnh sau Policy Agent, gồm `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_ids`, `financial_resolution`, `resolution_actions` |
| Output | `list[str]` các lỗi kiểm chứng; danh sách rỗng nghĩa là output được phép ghi |
| Module phụ thuộc | `shared/schemas.py`, `shared/evidence.py`, `services/order_repository.py`, `services/item_repository.py`, `services/payment_repository.py` |
| Module sử dụng output | Coordinator/runner dùng Verifier làm hard gate trước `services/output_writer.py` |
| Điều kiện lỗi cần xử lý | Evidence sai format, evidence không tồn tại, entity/evidence vượt cap, confidence ngoài `[0,1]`, số tiền âm hoặc chưa làm tròn 2 chữ số, refund sai policy, `case_status` sai theo refund |

### Cách xác minh

```powershell
python -m pytest -q tests/test_verifier.py
python -m pytest -q tests/test_policy.py
python -m pytest -q tests/
python run_all.py
```

- **Kết quả mong đợi:** 7 test verifier pass; policy precedence pass; toàn bộ pipeline sinh output hợp lệ.
- **Kết quả thực tế trong repo hiện tại:** `tests/test_verifier.py` có 7 test bao phủ happy path và 6 nhóm lỗi chính. Các output `EC_001.json` đến `EC_050.json` đã có trong thư mục `output/`.
- **Artifact/log:** `output/EC_*.json`, `logging/trace.jsonl`, `metadata.json`. Verifier không đọc `.env`, không gọi network và không tạo secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Có nên chỉ kiểm tra evidence ID bằng regex hay phải đối chiếu sự tồn tại trong CSV?
- **Các phương án đã cân nhắc:** (1) Chỉ kiểm tra prefix/format cho nhanh; (2) cho phép mọi ID miễn đúng pattern; (3) kiểm tra cả format lẫn tồn tại trong dữ liệu thật.
- **Phương án đã chọn:** Phương án 3: evidence phải đúng format và phải tồn tại.
- **Lý do:** README yêu cầu evidence "có thể dựng trực tiếp từ dữ liệu"; nếu chỉ regex thì `payment:000...000:1` vẫn lọt qua dù không có trong CSV. Điều này làm output có vẻ hợp lệ nhưng mất điểm evidence và làm trace không truy vết được.
- **Bằng chứng quyết định phù hợp:** `test_nonexistent_evidence_is_flagged` và `test_malformed_evidence_is_flagged` chứng minh Verifier phân biệt được hai lỗi khác nhau: sai format và đúng format nhưng không tồn tại trong dữ liệu.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Output của một case có `primary_issue = canceled_order_paid` nhưng `recommended_refund_brl` chỉ bằng freight thay vì bằng tổng payment. Schema vẫn có thể đúng nên nếu chỉ validate cấu trúc thì lỗi sẽ lọt qua.
- **Lệnh hoặc bước tái hiện:** Sửa `VALID_OUTPUT` trong `tests/test_verifier.py` để `recommended_refund_brl = 9.34` trong khi `payment_total_brl = 109.34`, rồi gọi `VerifierAgent().verify(output)`.
- **Nguyên nhân gốc:** Schema chỉ biết field là số không âm và làm tròn 2 chữ số; schema không biết business rule của từng `primary_issue`.
- **Cách xử lý:** Thêm finance gate trong `VerifierAgent.verify`: map từng issue sang refund kỳ vọng và báo lỗi nếu số tiền hoàn không khớp. Đồng thời kiểm tra `case_status` theo refund để tránh case có hoàn tiền nhưng lại ghi `no_action`.
- **Cách xác minh sau khi sửa:** `test_refund_mismatching_policy_is_flagged` và `test_case_status_inconsistent_with_refund_is_flagged` đều pass.
- **Điều học được:** Với hệ thống nhiều agent, schema validation là cần nhưng chưa đủ. Các invariant nghiệp vụ quan trọng phải được đặt ở hard gate cuối vì lỗi có thể sinh ra từ bất kỳ agent upstream nào.

## 7. Hiểu biết về luồng end-to-end

1. Runner đọc `input/EC_xxx.json`, lấy `claimed_order_id` và chuyển case cho Coordinator.
2. Order & Seller Agent tra order, item, seller, tổng item/freight và seller bám theo `shipping_limit_date`.
3. Payment Agent cộng toàn bộ payment row, nhận diện split payment và đối soát với tổng item + freight.
4. Delivery Agent so sánh ngày giao thực tế với ngày giao ước tính, đồng thời dùng handoff seller để phân biệt seller hay logistics chịu trách nhiệm.
5. Policy Agent áp `EC_POLICY_V1` theo đúng thứ tự ưu tiên: canceled paid, unavailable paid, late seller, late logistics, valid split payment, unsupported late claim.
6. Verifier Agent, phần tôi phụ trách, là gate cuối: kiểm schema, evidence, refund và `case_status`. Chỉ output không có violation mới được ghi ra `output/EC_xxx.json`.
7. Trace ghi lại handoff của lần chạy mới nhất; artifact nộp cuối cần đúng 50 JSON, không có file thừa, không có secret và model metadata rõ ràng.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Lương Thị Linh

**Ngày xác nhận:** 2026-08-05
