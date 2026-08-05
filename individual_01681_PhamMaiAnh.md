# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                    |
| --------------- | ------------------------------------------- |
| Họ và tên       | Phạm Mai Anh                                |
| MSSV            | 2A202601681                                 |
| Khóa/Lớp        | K3                                          |
| Vai trò chính   | TV4 — Delivery Agent (agent domain giao hàng) |
| Ngày hoàn thành | 2026-08-05                                  |

## 2. Vai trò và phạm vi công việc

Theo bảng phân công, TV4 phụ trách **domain thời gian giao hàng**: so sánh `order_delivered_customer_date` với `order_estimated_delivery_date` để xác định giao trễ hay đúng hạn, rồi kết hợp kết quả handoff seller từ TV2 để phân biệt ba nhánh `late_delivery_seller`, `late_delivery_logistics`, `unsupported_late_claim`, và **không chuyển múi giờ**.

Ranh giới tôi giữ đúng: tôi không đọc CSV trực tiếp (nhận timestamp và shipping limit qua handoff), không tính tiền hoàn, không chọn `primary_issue` cuối cùng và không ghi file output. Đó là phạm vi của TV2 (tổng item/freight), TV3 (payment) và TV5 (policy, verifier, submission).

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | --------------- | ---------- |
| Domain logic phân tích mốc giao hàng | `services/delivery_analysis.py`: `parse_timestamp`, `is_delivered_late`, `delivery_delay_days`, `late_seller_ids`, `worst_handoff_delay_days`, `rank_delivery_causes`, `_build_evidence`, `analyze_delivery` | Timeline order (`order_delivered_customer_date`, `order_estimated_delivery_date`, `order_delivered_carrier_date`, `order_status`) + item rows mang `seller_id` và `shipping_limit_date` từ TV2 | `DeliveryFinding`: `delivery_verdict`, `late_vs_estimate`, `delay_days`, `seller_handoff_late`, `late_seller_ids`, `handoff_delay_days`, `cause_candidates`, `issue_candidate`, `responsible_parties`, `confidence`, `evidence_ids` | Hoàn thành |
| Delivery Agent (lớp giao tiếp A2A) | `agents/delivery_agent.py`: `DeliveryAgent.handle`, `DeliveryAgent.analyze`, `DeliveryAgent.agent_card`, `_parse_task`, `_trace`, `_trace_handoff`, `run_selftest`, `main` | Task JSON `{case_id, order, items}` do Coordinator (TV1) gửi | Envelope `{agent_name, status, result, summary, error}`; trace event và handoff edge sang Policy Agent | Hoàn thành |
| `tests/test_delivery.py` (deliverable của TV4 theo bảng phân công) | — | — | — | **Chưa làm** — xem mục 6 |

Quan hệ phụ thuộc: **nhận** từ TV1 (điều phối) và TV2 (item rows + shipping limit theo seller); **bàn giao** cho TV5 để Policy Agent áp `EC_POLICY_V1` (chọn giữa `late_delivery_seller` và `late_delivery_logistics`, cùng hoàn tổng freight) và Verifier Agent kiểm evidence ID.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Chấp nhận nhiều dạng task envelope (`payload`/`result`/`input`, record phẳng, `pandas.Series` qua `as_mapping`) và nhiều alias tên cột | TV1 Coordinator, TV2 Order & Seller | Agent không vỡ khi upstream đổi shape payload hoặc dùng khóa viết tắt; giảm phụ thuộc vào thứ tự hoàn thành giữa các thành viên |
| Tự tính lại `late_seller_ids` từ item rows thay vì chỉ tin cờ boolean của TV2 | TV2 | Thành cross-check hai chiều cho điều kiện `SELLER_HANDOFF_AFTER_LIMIT` — nếu hai bên lệch nhau thì phát hiện được thay vì trôi vào output |
| Phát sinh cause code và issue string đúng nguyên văn README | TV5 Policy Agent | Policy Agent dùng trực tiếp `cause_candidates` / `ranked_causes`, không phải map lại chuỗi |
| Đối chiếu `architecture.md` với code thực tế, phát hiện 3 điểm lệch | TV1 (chủ sở hữu `architecture.md`), TV5 (chủ sở hữu `metadata.json`) | Báo lại để sửa trước khi nộp — chi tiết ở mục 6 |

## 3. Kết quả theo vai trò

Bảng phân công đặt ra 3 tiêu chí nghiệm thu cho TV4. Đối chiếu từng tiêu chí:

| Tiêu chí nghiệm thu (TV4) | File/hàm liên quan | Kết quả bàn giao | Cách xác minh |
| ------------------------- | ------------------ | ---------------- | ------------- |
| Xác định đúng late / on-time | `services/delivery_analysis.py` — `is_delivered_late`, `delivery_delay_days` | So sánh **chặt** `>` và chỉ khi có đủ cả hai timestamp; trả kèm `delay_days` có dấu | `--selftest` case 1–3 và 8 PASS |
| Phân biệt trách nhiệm seller và logistics | `services/delivery_analysis.py` — `late_seller_ids`, `analyze_delivery` | `issue_candidate` + `responsible_parties`: `seller`/seller ID vi phạm, hoặc `logistics_provider`/`LOGISTICS_PROVIDER` | `--selftest` case 1, 2, 5 PASS |
| Trả root-cause candidate đúng 3 code | `services/delivery_analysis.py` — `rank_delivery_causes` | `SELLER_HANDOFF_AFTER_LIMIT`, `CARRIER_DELIVERED_AFTER_ESTIMATE`, `DELIVERY_WITHIN_ESTIMATE`, có `rank` | `--agent-card` (khóa `emits_cause_codes`) và toàn bộ self-test |
| Không chuyển múi giờ (ràng buộc riêng của TV4) | `services/delivery_analysis.py` — `parse_timestamp` + doctest | Hậu tố `Z` / `±HH:MM` bị **cắt**, không quy đổi | `python -m doctest services\delivery_analysis.py` — 2 passed, 0 failed |

Output cụ thể do phần việc của tôi tạo ra — chạy trên case thật `EC_001` (order `e2a03ccf5ea816036608b2d8c3ab8e60`). Vì TV1/TV2 chưa có code, tôi tự join `data/olist_orders_dataset.csv` và `data/olist_order_items_dataset.csv` bằng một script tạm để mô phỏng payload của TV2 (script này không commit):

```json
{
  "agent_name": "delivery_agent",
  "status": "completed",
  "result": {
    "delivery_verdict": "late",
    "late_vs_estimate": true,
    "delay_days": 3.789,
    "seller_handoff_late": true,
    "late_seller_ids": ["f7496d659ca9fdaf323c0aae84176632"],
    "handoff_delay_days": 9.08,
    "ranked_causes": [
      {"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1},
      {"cause_code": "CARRIER_DELIVERED_AFTER_ESTIMATE", "rank": 2}
    ],
    "issue_candidate": "late_delivery_seller",
    "responsible_parties": [
      {"party_type": "seller", "party_id": "f7496d659ca9fdaf323c0aae84176632"}
    ],
    "confidence": 0.93,
    "evidence_ids": [
      "order:e2a03ccf5ea816036608b2d8c3ab8e60",
      "item:e2a03ccf5ea816036608b2d8c3ab8e60:1",
      "seller:f7496d659ca9fdaf323c0aae84176632",
      "policy:SELLER_HANDOFF_AFTER_LIMIT",
      "policy:CARRIER_DELIVERED_AFTER_ESTIMATE"
    ]
  },
  "error": null
}
```

Đọc kết quả: đơn được giao lúc `2017-12-15 18:56:35` trong khi hạn cam kết là `2017-12-12 00:00:00`, tức trễ 3.79 ngày. Carrier nhận hàng lúc `2017-12-13 13:45:24`, vượt `shipping_limit_date` của seller 9.08 ngày. Cả hai điều kiện của dòng `late_delivery_seller` trong `EC_POLICY_V1` đều thỏa, nên trách nhiệm thuộc seller chứ không phải đơn vị vận chuyển.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Trong `EC_POLICY_V1`, hai dòng `late_delivery_seller` và `late_delivery_logistics` có **cùng refund (tổng freight) và cùng action (`refund_freight`)**, nhưng **khác responsible party, khác root cause và khác evidence**. Nghĩa là phân nhánh sai không làm mất điểm Financial resolution (20%) hay Resolution actions (10%), nhưng làm mất Primary issue (20%), Root cause và responsible parties (15%) và một phần Evidence IDs (15%). Đúng phần đó là việc của TV4.

Cạm bẫy thứ hai: thông điệp khiếu nại trong `input/` **luôn** nói "có dấu hiệu giao trễ". Nếu tin lời khách thì mọi case đều thành `action_required`. Nhánh `unsupported_late_claim` tồn tại để **bác bỏ** claim bằng dữ liệu, và điều kiện README ghi rõ là "đơn giao không muộn hơn estimated date **và payment khớp**" — phần payment thuộc TV3, nên tôi chỉ đề xuất candidate chứ không tự chốt.

### Cách triển khai

Thuật toán là cây quyết định tường minh trên timestamp, không dùng LLM sinh kết luận, nên tái lập 100%:

1. **Normalize.** `DeliveryTimeline.from_mapping` và `ShipmentItem.from_mapping` chuẩn hóa input qua bảng alias, nên agent đọc được cả tên cột CSV gốc (`order_delivered_customer_date`) lẫn khóa viết tắt (`delivered_customer_date`, `carrier_date`) mà TV1/TV2 có thể dùng.
2. **Parse không đổi múi giờ.** `parse_timestamp` dùng regex **cắt** hậu tố offset (`-03:00`, `Z`) thay vì quy đổi, bỏ micro-second, thử lần lượt 5 định dạng qua `strptime`. Token rỗng, `nan`, `NaT`, `-` trả `None` thay vì một ngày giả.
3. **Verdict trễ.** `is_delivered_late` chỉ trả `True` khi **cả hai** timestamp tồn tại và `delivered_customer_date > estimated_delivery_date`. So sánh chặt nên giao đúng đúng hạn không bị tính là trễ.
4. **Quy trách nhiệm.** `late_seller_ids` đánh dấu seller khi `order_delivered_carrier_date > shipping_limit_date` của ít nhất một item row thuộc seller đó — đúng nguyên văn quy ước multi-item của README. Thứ tự input được giữ nguyên để evidence tái lập được.
5. **Xếp hạng nguyên nhân.** `rank_delivery_causes` đặt `SELLER_HANDOFF_AFTER_LIMIT` ở rank 1 và `CARRIER_DELIVERED_AFTER_ESTIMATE` ở rank 2 khi seller trễ, vì bàn giao trễ là **nguyên nhân** còn giao trễ là **hệ quả**.
6. **Thiếu dữ liệu không bao giờ là tình huống có lợi.** Không có `delivered_customer_date` thì verdict `not_delivered`; không có estimate thì `unknown`. Cả hai trường hợp trả `issue_candidate = null` để **nhường** quyền kết luận cho rule canceled/unavailable (ưu tiên cao hơn, thuộc TV5) thay vì đoán.
7. **Confidence có căn cứ.** 0.93 (seller, bằng chứng đầy đủ) / 0.91 (logistics) / 0.89 (đúng hạn) / 0.4 (không đánh giá được); trừ 0.08 khi thiếu `order_delivered_carrier_date`, trừ 0.05 khi không có item row; kẹp trong `[0.30, 0.97]`. Con số diễn tả **độ đầy đủ của bằng chứng**, không phải điểm sampling của model.
8. **Evidence tự giới hạn.** `_build_evidence` chỉ sinh ID từ row thực sự nhận được, ưu tiên item row mang deadline bị vỡ, và tự chặn tối đa 3 item cộng 2 seller để TV5 còn chỗ trong ngưỡng 10 evidence khi cộng evidence của TV2/TV3.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `{case_id, order: {order_id, order_status, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date}, items: [{order_id, order_item_id, seller_id, shipping_limit_date}]}` |
| Output | Envelope `{agent_name, status, result, summary, error}`; `result` gồm `delivery_verdict`, `late_vs_estimate`, `delay_days`, `delivered`, `handed_to_carrier`, `timeline_complete`, `seller_handoff_late`, `late_seller_ids`, `handoff_delay_days`, `cause_candidates`/`ranked_causes`, `issue_candidate`, `responsible_parties`, `confidence`, `evidence_ids`, `timeline`, `notes`, `warnings` |
| Module phụ thuộc | `services/delivery_analysis.py` (thuộc tôi; zero I/O, chỉ dùng `re`, `dataclasses`, `datetime`, `typing` — không third-party import) |
| Module sử dụng output | `agents/policy_agent.py` + `services/policy_engine.py` (TV5, áp rule và hoàn freight), `agents/verifier_agent.py` (TV5, kiểm evidence ID), `shared/trace.py` (TV1, ghi `logging/trace.jsonl`) |
| Điều kiện lỗi cần xử lý | Task `None` hoặc không phải object thì `failed`; thiếu `order` hoặc thiếu timestamp thì `partial` kèm `warnings`; đơn không có item row thì không đối chiếu được `shipping_limit_date` (hạ confidence, không bịa seller); `nan`/`NaT` từ pandas thành `None`; ngoại lệ bất ngờ được bọc thành envelope `failed` để không làm chết cả mesh |

### Cách xác minh

```bash
# 1. Bộ acceptance case nội bộ (8 case: seller fault, logistics fault, on-time,
#    canceled không có timestamp, đơn nhiều seller, task rỗng, thiếu order, múi giờ)
.venv\Scripts\python.exe -m agents.delivery_agent --selftest

# 2. Doctest cho quy tắc parse timestamp (ràng buộc "không chuyển múi giờ")
.venv\Scripts\python.exe -m doctest services\delivery_analysis.py -v

# 3. Agent Card — contract công bố cho TV1/TV5
.venv\Scripts\python.exe -m agents.delivery_agent --agent-card

# 4. Chạy standalone trên một case thật qua stdin
Get-Content -Raw task.json | .venv\Scripts\python.exe -m agents.delivery_agent --task -
```

- **Kết quả mong đợi:** 8/8 self-test PASS; doctest pass; EC_001 cho `late_delivery_seller`.
- **Kết quả thực tế:** `8/8 delivery agent cases passed` (exit code 0); `2 passed and 0 failed. Test passed.`; EC_001 trả `delivery_verdict = late`, `delay_days = 3.789`, `handoff_delay_days = 9.08`, `issue_candidate = late_delivery_seller`, `confidence = 0.93`.
- **Artifact/log:** output self-test trên stdout; envelope EC_001 trích ở mục 3. Chưa có artifact trong `logging/trace.jsonl` vì tracer do TV1 sở hữu và chưa sẵn sàng. Không có secret trong output: agent không đọc `.env`, không gọi network.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Xử lý thế nào khi đơn giao trễ nhưng **thiếu** `order_delivered_carrier_date`? Không có timestamp này thì không biết seller bàn giao trước hay sau `shipping_limit_date`, mà vẫn phải chọn giữa `late_delivery_seller` và `late_delivery_logistics`.
- **Các phương án đã cân nhắc:**
  1. Suy diễn seller trễ, vì đơn trễ tổng thể thì seller "có khả năng" trễ — tức tự tạo ra một sự kiện bàn giao không có trong CSV.
  2. Trả `unknown` và bỏ case — an toàn nhưng mất gần hết điểm của case dù đã chắc chắn là trễ.
  3. Giữ kết luận "trễ" và quy trách nhiệm `logistics_provider`, kèm warning và trừ confidence.
- **Phương án đã chọn:** phương án 3.
- **Lý do:** Đúng câu chữ của `EC_POLICY_V1`: nhánh seller yêu cầu *"carrier nhận hàng sau `shipping_limit_date`"* — một điều kiện **phải được chứng minh**, không phải mặc định. Không chứng minh được thì rơi về nhánh còn lại ("không muộn hơn `shipping_limit_date`"). Phương án này cũng an toàn hơn về điểm: vì refund và action của hai nhánh giống nhau, chọn sai nhánh vẫn giữ được 30%, còn trả `unknown` thì mất cả phần chắc chắn đúng. Quan trọng hơn, nó tránh sinh evidence `seller:<id>` không có căn cứ — loại evidence bị README tính là false positive.
- **Bằng chứng quyết định phù hợp:** chạy lại đúng payload đó cho `late_delivery_logistics` với `confidence = 0.83` (0.91 trừ 0.08), `late_seller_ids = []` và warning nêu rõ lý do quy trách nhiệm. So sánh: cùng payload nhưng **có** `order_delivered_carrier_date` thì confidence là 0.91. Không seller nào bị bịa oan trong cả hai trường hợp.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `parse_timestamp("2018-10-18T00:00:00-03:00")` ban đầu trả về datetime **có tzinfo**; khi so sánh với timestamp lấy từ CSV (naive), Python ném `TypeError: can't compare offset-naive and offset-aware datetimes`.
- **Lệnh hoặc bước tái hiện:** truyền một timestamp có offset `-03:00` (đúng định dạng `opened_at` của các file trong `input/`) vào cùng một case với `order_estimated_delivery_date` lấy từ CSV (`2018-10-18 00:00:00`, không offset), rồi gọi `is_delivered_late`.
- **Nguyên nhân gốc:** input của bài lab **trộn hai hệ timestamp** — `input/EC_*.json` dùng ISO-8601 có offset, còn 9 file CSV dùng giá trị naive. Dùng `datetime.fromisoformat` "cho tiện" đã vô tình tạo ra datetime aware. Và nếu sửa bằng cách **quy đổi** về UTC thì còn tệ hơn: `2018-10-18T00:00:00-03:00` thành `2018-10-18 03:00:00`, tự nhiên trở thành "trễ 3 giờ" so với hạn `2018-10-18 00:00:00` — một false positive sinh ra từ múi giờ chứ không từ thực tế giao hàng, và sẽ làm sai chính cái nhánh mà TV4 chịu trách nhiệm.
- **Cách xử lý:** viết `parse_timestamp` riêng: regex `_TZ_SUFFIX_RE` **cắt** hậu tố `Z` hoặc `±HH:MM`, bỏ micro-second, thử 5 định dạng qua `strptime`; đầu vào đã là `datetime` thì `.replace(tzinfo=None)`. Kết quả luôn naive nên mọi phép so sánh cùng hệ, đúng yêu cầu README *"so sánh theo giá trị trong CSV; không cần chuyển múi giờ"*.
- **Cách xác minh sau khi sửa:** doctest trong `parse_timestamp` (kỳ vọng `'2018-10-18T00:00:00'`) và self-test `timezone_offset_is_not_converted` — cùng một giá trị wall-clock ở hai bên phải cho `on_time`, `delay_days = +0.00`, `unsupported_late_claim`. Cả hai pass.
- **Điều học được:** khi spec nói "so sánh theo giá trị trong CSV" thì đó là một **quy tắc nghiệp vụ**, không phải gợi ý cho tiện. Trong hệ nhiều agent, mỗi agent phải tự chuẩn hóa đầu vào ở biên của mình, vì không thể giả định upstream đã làm sạch dữ liệu.

### Việc còn thiếu trong phạm vi của tôi

`tests/test_delivery.py` là deliverable của TV4 theo bảng phân công nhưng **chưa được viết**; thư mục `tests/` chưa tồn tại và `pytest` chưa có trong `.venv` (`ModuleNotFoundError: No module named 'pytest'`). Hiện tôi thay thế bằng 8 acceptance case nhúng trong `agents/delivery_agent.py` (`run_selftest`) cộng 2 doctest — chúng chạy được và pass thật, nhưng **không** phải bộ pytest mà bảng phân công yêu cầu. Bước tiếp theo: `pip install pytest`, tạo `tests/`, port 8 case sang `tests/test_delivery.py` để `python -m pytest tests/` của TV1 gom được.

### Blocker ngoài phạm vi của tôi (đã báo nhóm)

Đối chiếu repo với `architecture.md`, tôi thấy 3 điểm lệch cần sửa trước khi nộp:

1. **Code chưa tồn tại.** `architecture.md` mô tả 6 agent và ghi lệnh `python run_all.py` cùng `python -m pytest tests/ # 43 tests`, nhưng thực tế `coordinator_agent.py`, `order_seller_agent.py`, `payment_agent.py`, `policy_agent.py`, `verifier_agent.py` đều **0 byte**; toàn bộ `services/` còn lại và `shared/` là 2 byte; `run_all.py` và `tests/` **không tồn tại**. `output/` chưa có file JSON nào, `logging/trace.jsonl` và `logging/metadata.json` đều rỗng. Vì vậy tôi **không** ghi nhận pipeline 50 case là đã chạy.
2. **Model khai báo không khớp.** `architecture.md` ghi `Qwen/Qwen2.5-1.5B-Instruct` (1.54B) khai báo tại `shared/constants.py`, nhưng `shared/constants.py` rỗng, còn `agents/delivery_agent.py` của tôi đang ghi `MODEL_NAME = "qwen2.5-7b-instruct"` / `7B`. Cả hai đều thỏa mức 10B nhưng **phải thống nhất một tên duy nhất** vì lưu ý 4 của README yêu cầu model name trong source phải khớp `metadata.json`. Tôi sẽ sửa hằng số phía mình theo con số nhóm chốt.
3. **Mô tả quyền dữ liệu của Delivery Agent chưa chính xác.** Bảng trong `architecture.md` ghi Delivery Agent đọc `orders`, và ô nhiệm vụ chỉ ghi phần so sánh với estimated date. Thực tế module của tôi **không đọc CSV** (không có `read_csv`, không import pandas) — nó nhận timestamp qua handoff — và nó **cũng** dùng item rows của TV2 để phân nhánh seller vs logistics. Nên sửa thành "không đọc CSV trực tiếp; nhận timeline từ Coordinator và shipping limit theo item từ Order & Seller Agent", đúng như dòng TV4 trong bảng phân công.

Những gì đã loại trừ: không phải lỗi môi trường. `agents.delivery_agent` và `services.delivery_analysis` import và chạy độc lập trên Python 3.9.13 trong `.venv`, self-test 8/8 pass, và đã chạy được trên dữ liệu thật của `EC_001`. Phần domain của TV4 không phải nguyên nhân của blocker.

## 7. Hiểu biết về luồng end-to-end

> Lưu ý: 5 câu hỏi in sẵn trong template (Crossref đến vector index, evaluation set, freshness monitoring, baseline/corrupted/repaired) thuộc bài lab RAG của Day 8, không áp dụng cho bài multi-agent Day 9. Tôi trả lời các câu tương ứng của bài này.

**1. Dữ liệu đi từ `input/EC_xxx.json` đến `output/EC_xxx.json` như thế nào?**
TV1 Coordinator đọc case, lấy `claimed_order_id`, rồi gọi các agent domain theo luồng trong `architecture.md`: Order & Seller (TV2) trả trạng thái order, item IDs, seller IDs, `item_total_brl`, `freight_total_brl` và danh sách seller bàn giao muộn; Payment (TV3) trả `payment_total_brl`, payment IDs, cờ split payment và kết quả đối soát với item cộng freight trong sai số 0.10 BRL; Delivery (TV4, phần tôi) trả verdict giao trễ hay đúng hạn cùng phân nhánh trách nhiệm. Mỗi agent trả cùng một envelope `{agent_name, status, result, summary, error}`. TV5 Policy Agent gom facts, áp `EC_POLICY_V1` **theo thứ tự ưu tiên** để chốt một `primary_issue` duy nhất, `case_status`, responsible party, refund và action. Verifier Agent (TV5) là hard gate cuối: kiểm schema, định dạng ID, giới hạn mảng (tối đa 5 entity, 10 evidence, 3 root cause, 3 responsible party, 5 action), làm tròn 2 chữ số, và loại evidence không dựng được từ CSV. TV1 ghi `logging/trace.jsonl`, TV5 ghi 50 JSON và `metadata.json`.

**2. Thứ tự ưu tiên của `EC_POLICY_V1` ảnh hưởng gì đến phần việc của tôi?**
`canceled_order_paid` và `unavailable_order_paid` đứng **trước** hai rule giao trễ. Đó chính là lý do agent của tôi trả `issue_candidate = null` khi thiếu `order_delivered_customer_date`: đơn canceled không bao giờ được giao, nên nếu tôi cố kết luận gì ở đó thì sẽ đẩy Policy Agent hoàn freight thay vì hoàn toàn bộ payment — sai cả `primary_issue`, responsible party (phải là `platform`/`OLIST_PLATFORM`) và số tiền. Tôi chỉ đề xuất candidate; TV5 mới là nơi quyết định.

**3. Vì sao ranh giới giữa TV2 và TV4 lại chồng lấn ở `shipping_limit_date`, và xử lý ra sao?**
Bảng phân công giao cho TV2 việc "so sánh `order_delivered_carrier_date` với từng `shipping_limit_date`" và xác định seller bàn giao muộn; nhưng TV4 cần đúng thông tin đó để chọn giữa `late_delivery_seller` và `late_delivery_logistics`. Tôi xử lý bằng cách nhận item rows thô từ TV2 và **tự tính lại** `late_seller_ids` thay vì chỉ tin một cờ boolean. Như vậy hai bên độc lập tính cùng một điều kiện, lệch nhau thì phát hiện được — còn nếu tôi phụ thuộc hoàn toàn vào cờ của TV2 thì một lỗi ở đó sẽ trôi thẳng vào output mà không ai thấy.

**4. Vì sao phải tách "giao trễ" và "ai chịu trách nhiệm" thành hai phép kiểm riêng?**
Chúng dùng hai cặp timestamp khác nhau, ở hai mức khác nhau, và có thể độc lập đúng/sai. "Trễ" là `delivered_customer_date` so với `estimated_delivery_date`, ở **mức đơn**. "Trách nhiệm" là `delivered_carrier_date` so với `shipping_limit_date`, ở **mức item**, mỗi seller một hạn riêng. Có trường hợp seller bàn giao trễ nhưng đơn vẫn đến đúng hạn — khi đó không đủ căn cứ quy trách nhiệm seller và không có khoản hoàn; agent của tôi ghi note riêng cho tình huống này thay vì gộp hai điều kiện lại.

**5. Case được coi là giải quyết thành công dựa trên artifact và metric nào?**
Artifact: đúng 50 file trong `output/` (`EC_001.json` đến `EC_050.json`, không file lạ, ZIP chỉ chứa `output/`), cộng `architecture.md`, `logging/trace.jsonl` của lượt chạy mới nhất (không append) và `metadata.json` khai báo model từ 10B tham số trở xuống. Metric: điểm có trọng số mỗi case (primary issue và confidence 20%, affected entities 20%, root cause và responsible parties 15%, evidence 15%, financial 20%, actions 10%), trung bình 50 case; case vi phạm hard gate nhận 0 điểm. Ở phạm vi TV4, tiêu chí hẹp hơn: verdict late/on-time đúng, phân nhánh seller vs logistics đúng, 3 root-cause code đúng, và không sinh evidence ID không chứng minh được.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng — self-test 8/8, doctest 2/2 và case EC_001 là kết quả thực; pipeline 50 case, `trace.jsonl` và `tests/test_delivery.py` chưa có và đã nêu rõ ở mục 6.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Mai Anh
**Ngày xác nhận:** 2026-08-05
