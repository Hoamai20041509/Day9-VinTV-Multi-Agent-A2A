# Báo cáo cá nhân - Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Cao Quế Phương |
| MSSV | 2A202601111 |
| Khóa/Lớp | K3 |
| Vai trò chính | Order & Seller Agent |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Order repository | `services/order_repository.py` | `order_id`, orders CSV | Order row hoặc `None` | Hoàn thành |
| Item/Seller repository | `services/item_repository.py` | `order_id`, item/seller CSV | Item rows và seller rows | Hoàn thành |
| Order & Seller Agent | `agents/order_seller_agent.py` | Claimed order ID | Status, entities, totals, late handoff evidence | Hoàn thành |
| Unit test | `tests/test_order_seller.py` | CSV fixture tạm | Kết quả kiểm tra 5 nhóm hành vi | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tích hợp A2A | Coordinator và Policy Agent | Chuẩn hóa handoff dictionary để ghép output |
| Kiểm chứng evidence | Verifier Agent | Item/seller evidence chỉ lấy từ row tồn tại |
| Kiểm chứng end-to-end | Toàn pipeline | Đối chiếu 50 output với orders/items/sellers CSV |
| Tài liệu | Nhóm | Mô tả vai trò, quyền truy cập và contract handoff trong `architecture.md` |

Vai trò chính của tôi là xử lý domain Order & Seller. Những phần tích hợp ngoài
phạm vi được thực hiện để bảo đảm output của agent có thể được Coordinator,
Policy và Verifier sử dụng đúng contract; tôi không nhận ownership thay cho các
agent domain khác.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Kiểm tra order tồn tại và status | `OrderRepository.get_order` | Trả đúng row hoặc `None` | `test_missing_order` |
| Lấy item và seller | `ItemRepository.get_items`, `get_seller` | ID ổn định theo `order_item_id` | `test_returns_status_entities_totals_and_exact_late_seller` |
| Tính tổng tiền | `OrderSellerAgent.analyze` | `item_total_brl`, `freight_total_brl` làm tròn 2 số | Unit test và oracle CSV |
| Xác định seller bàn giao trễ | `OrderSellerAgent.analyze` | Late item/seller theo từng shipping limit | Test fixture gồm seller trễ và đúng hạn |
| Xử lý order không item | `OrderSellerAgent.analyze` | Entity rỗng, tổng bằng `0.0` | `test_order_without_items_has_zero_totals` |
| Giới hạn entity | `MAX_ENTITIES` | Tối đa 5 item/seller nhưng tổng vẫn dùng toàn bộ row | `test_entity_lists_are_capped_but_totals_use_every_item` |

Artifact cụ thể do phần việc tạo ra là handoff Order & Seller cho mỗi case. Ví dụ
handoff của case seller-late chứa order status, item ID, seller ID, hai tổng BRL,
item vi phạm, seller vi phạm, carrier date và shipping limit date. Handoff này
được ghi trong `logging/trace.jsonl` trước khi Policy Agent ra quyết định.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Nội dung khách hàng chỉ cung cấp claimed order ID và phản ánh giao trễ. Agent
phải kiểm tra order có thật hay không, lấy đúng toàn bộ item/seller, tính tổng
giá trị và xác định seller có bàn giao hàng cho carrier sau hạn của từng item
hay không. Agent không được tin trực tiếp nội dung khiếu nại hoặc tạo tracking
checkpoint không có trong Olist.

### Cách triển khai

`OrderRepository` lazy-load orders CSV và tạo index `order_id -> row`.
`ItemRepository` tạo index `order_id -> item rows` và `seller_id -> seller row`.
Item được sắp xếp số theo `order_item_id` để kết quả ổn định qua nhiều lần chạy.

`OrderSellerAgent.analyze(order_id)` thực hiện:

1. Gọi repository để kiểm tra order tồn tại.
2. Nếu không tồn tại, trả `order_found=false`, entity rỗng và tổng `0.0`.
3. Lấy tất cả item của order.
4. Cộng `price` và `freight_value` bằng `Decimal`.
5. So sánh `order_delivered_carrier_date` với `shipping_limit_date` của từng item.
6. Item bị trễ khi carrier date lớn hơn shipping limit của chính item đó.
7. Suy ra danh sách seller vi phạm từ các late item.
8. Giới hạn danh sách entity ở 5 nhưng vẫn tính tiền và phát hiện trễ trên toàn bộ item.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Chuỗi `claimed_order_id` từ case JSON |
| Output | Dictionary Order & Seller handoff |
| Module phụ thuộc | `OrderRepository`, `ItemRepository` |
| Module sử dụng output | Coordinator, Payment Agent, Delivery Agent, Policy Agent, Verifier |
| Điều kiện lỗi | Order không tồn tại; timestamp sai định dạng; CSV không đọc được |

Các field chính của handoff:

```text
order_found, order_status, order,
item_ids, seller_ids,
item_total_brl, freight_total_brl,
late_handoff, late_item_ids,
late_seller_ids, late_handoffs, evidence_ids
```

### Cách xác minh

```bash
venv/bin/python -m pytest -q tests/test_order_seller.py
```

- **Kết quả mong đợi:** 5 test pass.
- **Kết quả thực tế:** 5 test pass.
- **Artifact/log:** `tests/test_order_seller.py`, `logging/trace.jsonl`.

Kiểm tra toàn hệ thống:

```bash
venv/bin/python -m pytest -q
venv/bin/python -m agents.coordinator_agent
```

- **Kết quả thực tế:** 19 test pass, xử lý 50/50 case và tạo 250 handoff trace.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Có thể dùng float/pandas hoặc `Decimal`/CSV standard library để tính tiền.
- **Các phương án đã cân nhắc:** Dùng pandas cho code ngắn; dùng `csv` và `Decimal` để ít dependency và kiểm soát rounding.
- **Phương án đã chọn:** Repository dùng `csv.DictReader`; agent dùng `Decimal` và `ROUND_HALF_UP`.
- **Lý do:** Tiền là trường leaderboard exact-match. Float có thể tạo sai số nhị phân; pandas không cần thiết cho truy vấn theo ID sau khi đã index.
- **Bằng chứng:** Các tổng item/freight của 50 output khớp oracle đọc trực tiếp từ CSV; unit test kiểm tra trường hợp `10.005 + 20.005` làm tròn thành `30.01` sau khi cộng.

Một quyết định khác là không dùng LLM để so sánh timestamp hoặc tạo evidence.
Qwen3-8B là model được khai báo cho runtime và lớp diễn giải, nhưng domain
handoff được dựng deterministic. Cách này loại bỏ hallucination ID và bảo đảm
chạy lại cho cùng kết quả.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Môi trường ban đầu báo `No module named pytest`.
- **Bước tái hiện:** `python -m pytest -q tests/test_order_seller.py`.
- **Nguyên nhân gốc:** Python hệ thống chưa cài pytest; virtual environment sau đó có pytest.
- **Cách xử lý:** Khai báo `pytest>=8.0,<9.0` trong `requirements.txt` và chạy test bằng `venv/bin/python`.
- **Cách xác minh sau sửa:** `venv/bin/python -m pytest -q` trả về `19 passed`.
- **Điều học được:** Lệnh kiểm chứng phải dùng đúng interpreter của project, không giả định dependency có trong Python hệ thống.

Lỗi tích hợp khác là archive được cập nhật tại chỗ từng chứa cả `output/...` và
50 entry ở root. Archive đó có 101 entry và không đạt hard gate. Tôi đã tạo zip
sạch ở đường dẫn tạm, kiểm tra đúng 50 tên file rồi thay thế atomically
`output.zip`.

## 7. Hiểu biết về luồng end-to-end

1. **Case đi qua hệ thống như thế nào?**

   Data Loader đọc case JSON và lấy claimed order ID. Coordinator gọi Order &
   Seller Agent, Payment Agent và Delivery Agent. Ba handoff được chuyển cho
   Policy Agent. Candidate output sau đó phải qua Verifier trước khi Output
   Writer ghi JSON.

2. **Các bảng được join ra sao?**

   `orders.order_id` nối với `order_items.order_id` và
   `order_payments.order_id`. Từ item, `seller_id` nối với sellers. Mỗi ID trong
   affected entities và evidence đều được dựng từ các key này.

3. **Seller-late khác logistics-late thế nào?**

   Cả hai đều yêu cầu customer delivery sau estimated date. Seller chịu trách
   nhiệm nếu carrier nhận hàng sau shipping limit của item. Nếu seller bàn giao
   không muộn nhưng customer vẫn nhận sau estimate, logistics provider chịu
   trách nhiệm.

4. **Vì sao policy cần priority?**

   Canceled/unavailable paid phải được hoàn toàn bộ payment trước khi xét
   delivery hoặc split payment. Nếu đổi thứ tự, cùng một order có thể bị gán sai
   primary issue và refund.

5. **Verifier bảo vệ output như thế nào?**

   Verifier kiểm schema, giới hạn entity/evidence, định dạng ID, quan hệ
   issue-cause-action, responsible party, case status và refund. Output sai bị
   chặn thay vì tự động sửa hoặc ghi ra.

6. **Trace chứng minh multi-agent thật ra sao?**

   Mỗi case có event riêng cho Order & Seller, Payment, Delivery, Policy và
   Verifier. Payload cho thấy dữ liệu nào được agent trước bàn giao cho agent sau,
   thay vì toàn bộ xử lý nằm trong một prompt duy nhất.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi chỉ ghi kết quả chạy đã được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc thành viên khác.

**Họ và tên:** Cao Quế Phương

**Ngày xác nhận:** 2026-08-05
