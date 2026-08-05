# Member Role Report - Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trần Thị Hoa Mai |
| MSSV | 22028141 |
| Khóa/Lớp | K3 |
| Vai trò chính | Thành viên 1 - Coordinator Agent và Tech Lead |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Schema dùng chung | `shared/schemas.py` | Yêu cầu input/output trong README và contract từ các domain agent | Các Pydantic model có validation cho input, handoff và output | Hoàn thành |
| A2A message contract | `shared/a2a_messages.py` | Tên agent, loại request/response, payload domain | `A2AMessage`, correlation, causation, status và error contract | Hoàn thành |
| Coordinator Agent | `agents/coordinator_agent.py` | `CaseInput` và năm agent được inject qua `AgentPort` | `BatchRunResult` và `CaseOutput` đã qua Verifier | Hoàn thành trong phạm vi orchestration |
| Trace | `shared/trace.py` | Run event, case event và A2A message | JSONL UTF-8 của lượt chạy mới nhất | Code hoàn thành; trace thật chờ tích hợp domain agent |
| CLI chạy hệ thống | `run_all.py` | `--case EC_001`, `--all`, đường dẫn data/input/output | Validate input hoặc kích hoạt toàn bộ pipeline | Hoàn thành; chạy thật chờ TV2-TV5 |
| Kiến trúc hệ thống | `architecture.md` | Phân công nhóm và yêu cầu README | Sơ đồ sequence, quyền dữ liệu, handoff và failure behavior | Hoàn thành |
| Kiểm thử TV1 | `tests/test_schemas.py`, `tests/test_coordinator.py`, `tests/test_integration.py` | Schema và fake agent tuân thủ A2A contract | 7 test kiểm tra schema, timeout, trace, 1 case và 50 case | Hoàn thành |

Coordinator chỉ điều phối và kiểm tra contract. Tôi không đưa logic đọc CSV, tính tiền, xác định giao trễ hay áp policy vào coordinator vì các phần đó thuộc ownership của TV2-TV5.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Chuẩn hóa constructor và A2A interface | TV2-TV5 | Chốt `AgentPort.handle(A2AMessage)` và constructor contract trong `architecture.md` |
| Rà dữ liệu tích hợp | TV2-TV5 | Xác nhận đủ 50 order; phát hiện 8 order không có item và các timestamp nullable cần xử lý |
| Chuẩn hóa schema kết quả domain | Order/Seller, Payment, Delivery, Policy, Verifier | Cung cấp model `OrderSellerResult`, `PaymentResult`, `DeliveryResult`, `PolicyResult`, `VerificationResult` |
| Kiểm tra luồng 50 case | Toàn nhóm | Test orchestration chạy 50 input bằng test doubles, không sử dụng kết quả này làm output nộp bài |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Kiểm tra input chính thức | `run_all.load_cases` | Đủ `EC_001`-`EC_050`, case ID khớp filename, 50 order ID duy nhất | `python run_all.py --all --validate-only` |
| Xây dựng output schema | `shared/schemas.py` | Giới hạn 5 entity, 10 evidence, 3 cause, 3 party, 5 action; confidence trong `[0,1]` | `python -m pytest -q tests/test_schemas.py` |
| Xây dựng handoff | `shared/a2a_messages.py` | Response phải giữ đúng correlation, causation, case, sender và message type | `python -m pytest -q tests/test_coordinator.py` |
| Điều phối pipeline | `CoordinatorAgent.process_case` | Order/Seller → Payment → Delivery → Policy → Verifier → OutputWriter | `python -m pytest -q tests/test_coordinator.py` |
| Quản lý lỗi | `CoordinatorAgent._dispatch` | Timeout, retry, failed response, payload sai và cross-case response đều bị chặn | Test timeout trong `tests/test_coordinator.py` |
| Kiểm thử batch | `tests/test_integration.py` | 50/50 input đi qua đủ năm handoff bằng fake agents | `python -m pytest -q tests/test_integration.py` |
| Viết tài liệu kiến trúc | `architecture.md` | Sơ đồ agent, quyền dữ liệu, message contract, failure behavior và lệnh chạy | Đọc `architecture.md` và đối chiếu source |

Một artifact cụ thể tôi tạo ra là trace JSONL trong integration test. Với mỗi case, trace chứa `case_started`, năm cặp `handoff_sent`/`handoff_received`, `case_finished` và được liên kết bằng một `correlation_id`. Test batch xác nhận đủ 50 case và event cuối ghi `succeeded: 50`, `failed: 0`. Đây là trace kiểm thử bằng test doubles; `trace.jsonl` tại root vẫn được giữ trống cho đến khi toàn bộ domain agent chạy dữ liệu thật.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần của tôi giải quyết việc ghép nhiều domain agent thành một pipeline có thể kiểm tra và tái hiện. Rủi ro chính là mỗi thành viên trả một cấu trúc dict khác nhau, response của case này bị gắn nhầm sang case khác, agent treo làm dừng toàn bộ batch hoặc coordinator tự tính thay domain agent. Ngoài ra hệ thống phải bảo đảm output chỉ được ghi sau khi Verifier chấp nhận.

### Cách triển khai

Tôi triển khai theo hướng contract-first:

1. Dùng Pydantic model với `extra="forbid"` để phát hiện field sai hoặc contract drift ngay khi tích hợp.
2. Mỗi input được parse thành `CaseInput`; order ID chỉ lấy từ `customer_request.claimed_order_id`.
3. Coordinator gửi `A2AMessage` cho Order/Seller Agent trước. Kết quả chuẩn hóa từ TV2 cung cấp totals cho Payment Agent và seller handoff cho Delivery Agent.
4. Ba kết quả domain được gửi sang Policy Agent theo đúng luồng, nhưng thứ tự policy do TV5 chịu trách nhiệm.
5. Draft `CaseOutput` được gửi sang Verifier Agent. Coordinator chỉ gọi `OutputWriter.write` khi `VerificationResult.is_valid = true` và có `verified_output`.
6. Mỗi response phải khớp `case_id`, `correlation_id`, `causation_id`, sender, recipient và message type. Response sai bị loại, không được dùng để tạo evidence.
7. Mỗi agent call có timeout và retry cấu hình được. Batch mặc định tiếp tục case tiếp theo và trả exit code khác 0 nếu có case lỗi.
8. `TraceWriter.start_run` ghi đè trace cũ thay vì append, đúng yêu cầu README chỉ giữ lượt chạy mới nhất.

Coordinator không chuyển múi giờ cho timestamp CSV và không suy diễn refund ledger, transaction ID hay evidence không tồn tại.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `CaseInput`: `case_id`, `opened_at`, `customer_request`, `policy_version=EC_POLICY_V1` |
| Output | `CaseOutput` đã được Verifier chấp nhận; batch trả `BatchRunResult` gồm outputs và errors |
| Module phụ thuộc | `OrderSellerAgent`, `PaymentAgent`, `DeliveryAgent`, `PolicyAgent`, `VerifierAgent`, `OutputWriter` |
| Module sử dụng output | `OutputWriter`, runner 1/50 case và integration test |
| Điều kiện lỗi cần xử lý | Input sai schema, thiếu case, duplicate case ID, timeout, response failed, sai correlation/case/order, payload sai schema, verifier từ chối, lỗi ghi output |

Constructor contract được công bố cho nhóm:

```python
OrderSellerAgent(data_dir)
PaymentAgent(data_dir)
DeliveryAgent(data_dir)
PolicyAgent()
VerifierAgent(data_dir)
OutputWriter(output_dir)
```

Mỗi agent phải có thuộc tính `name` đúng `AgentName` và hàm `handle(message)` trả về `A2AMessage`.

### Cách xác minh

```powershell
python -m compileall -q agents shared tests run_all.py
python run_all.py --case EC_001 --validate-only
python run_all.py --all --validate-only
python -m pytest -q
python run_all.py --case EC_001
```

- **Kết quả mong đợi:** Code import được; validate được 1 và 50 input; test coordinator chạy đủ handoff; khi domain agent chưa tồn tại, runner báo đúng dependency thay vì tạo output giả.
- **Kết quả thực tế:** `7 passed`; validate thành công 1/1 và 50/50 input. Lệnh chạy thật dừng với `agents.order_seller_agent.OrderSellerAgent is not implemented` vì module TV2 chưa cung cấp class runtime.
- **Artifact/log:** `architecture.md`; trace tạm của pytest trong thư mục `tmp_path`. Root `trace.jsonl` chưa phải artifact nghiệm thu cuối.

### Kiểm tra dữ liệu phục vụ tích hợp

Tôi kiểm tra 50 `claimed_order_id` trên các CSV liên quan để xác nhận contract có bao phủ dữ liệu thực tế:

| Chỉ số | Kết quả |
| --- | ---: |
| Claimed order | 50 |
| Order tìm thấy trong orders CSV | 50 |
| Order không có item row | 8 |
| Order không có payment row | 0 |
| Số item tối đa trên một order | 3 |
| Số payment row tối đa trên một order | 3 |
| Thiếu `order_delivered_carrier_date` | 15 |
| Thiếu `order_delivered_customer_date` | 16 |
| Thiếu `order_estimated_delivery_date` | 0 |
| Phân bố trạng thái | 34 delivered, 8 canceled, 8 unavailable |

Vì vậy timestamp delivery trong handoff được khai báo nullable, và schema cho phép order không có item với totals bằng `0.0`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Các agent do nhiều thành viên phát triển độc lập. Nếu coordinator nhận dict tự do hoặc import logic domain trực tiếp, lỗi contract chỉ xuất hiện muộn và coordinator dễ vi phạm ranh giới trách nhiệm.
- **Các phương án đã cân nhắc:** (1) Gọi trực tiếp các hàm và truyền dict không schema; (2) dùng dataclass chuẩn thư viện; (3) dùng Pydantic model và một A2A envelope chung.
- **Phương án đã chọn:** Pydantic v2 kết hợp `A2AMessage` và dependency injection qua `AgentPort`.
- **Lý do:** Pydantic kiểm tra field, enum, pattern, giới hạn mảng và tiền tại runtime; envelope cho phép trace quan hệ request-response; dependency injection giúp kiểm thử coordinator không cần đọc CSV hoặc dùng model thật.
- **Bằng chứng quyết định phù hợp:** Test phát hiện được case ID sai, entity vượt giới hạn và timeout; integration test đưa 50 case qua năm handoff với một correlation ID cho từng case. Toàn bộ 7 test hiện đều pass.

## 6. Một lỗi hoặc blocker đã xử lý

### Lỗi encoding trace trên Windows

- **Triệu chứng/lỗi nguyên văn:** `UnicodeDecodeError: 'charmap' codec can't decode byte ...` khi test đọc trace có message tiếng Việt.
- **Lệnh hoặc bước tái hiện:** `python -m pytest -q tests/test_coordinator.py tests/test_integration.py`.
- **Nguyên nhân gốc:** `TraceWriter` ghi đúng UTF-8 nhưng `Path.read_text()` trong test dùng encoding mặc định CP1252 của Windows.
- **Cách xử lý:** Chỉ định `encoding="utf-8"` khi đọc trace trong test, đồng nhất với writer.
- **Cách xác minh sau khi sửa:** `python -m pytest -q` trả về `7 passed`.
- **Điều học được:** Encoding phải là một phần rõ ràng của contract file, đặc biệt khi payload chứa tiếng Việt và chạy trên nhiều hệ điều hành.

### Blocker tích hợp còn tồn tại

- **Phạm vi bị ảnh hưởng:** Chưa thể chạy dữ liệu thật để sinh 50 output và root `trace.jsonl`.
- **Triệu chứng:** `python run_all.py --case EC_001` báo `OrderSellerAgent is not implemented`.
- **Nguyên nhân:** Các module runtime của TV2-TV5 hiện mới là placeholder, chưa cung cấp các class theo constructor/A2A contract.
- **Những gì đã loại trừ:** 50 input hợp lệ; schema import được; coordinator, timeout và batch orchestration đã pass test doubles; lỗi không nằm ở input loader hoặc A2A envelope.
- **Bước tiếp theo:** Tích hợp lần lượt TV2, TV3, TV4 và TV5 theo contract; chạy `EC_001`; sau đó chạy 50 case thật, kiểm tra output và ghi đè root trace.

## 7. Hiểu biết về luồng end-to-end

1. Runner đọc JSON input và xác thực `case_id`, `claimed_order_id`, `policy_version`. Coordinator tạo một correlation ID riêng cho case.
2. Order & Seller Agent tra order, item và seller để trả trạng thái, entity, tổng item/freight và các vi phạm `shipping_limit_date`.
3. Payment Agent lấy mọi payment row, tính tổng, kiểm tra split payment và đối soát với tổng item cộng freight trong sai số 0.10 BRL. Delivery Agent so sánh delivery date với estimated date và kết hợp seller handoff để đề xuất nguyên nhân.
4. Policy Agent nhận kết quả có cấu trúc và áp dụng rule theo thứ tự bắt buộc: canceled paid, unavailable paid, late seller, late logistics, valid split payment, unsupported late claim.
5. Verifier kiểm tra schema, evidence ID tồn tại, giới hạn mảng, tiền, confidence, responsible party và action. Chỉ output đã xác minh mới được ghi ra `output/EC_xxx.json`.
6. Trace ghi lại các handoff thật trong lần chạy mới nhất. Sau khi chạy đủ 50 case, nhóm phải kiểm tra có đúng 50 JSON và tạo ZIP chỉ chứa `EC_001.json`-`EC_050.json`.

Thành công end-to-end không chỉ là chương trình không lỗi. Cần đồng thời có 50 output hợp lệ, trace thật thể hiện rõ handoff, evidence dựng được từ CSV, policy đúng thứ tự, tiền làm tròn đúng và ZIP không có file thừa.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** **Trần Thị Hoa Mai**

**Ngày xác nhận:** 2026-08-05
