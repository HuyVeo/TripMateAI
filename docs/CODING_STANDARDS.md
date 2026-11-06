# TripMate AI — Coding Standards & Guidelines

Tài liệu này định nghĩa các tiêu chuẩn lập trình, quy ước kiến trúc, quản lý mã nguồn và thực hành tốt nhất được áp dụng trong toàn bộ dự án **TripMate AI**. Mọi thành viên và công cụ AI tham gia phát triển codebase cần tuân thủ nghiêm ngặt các quy tắc dưới đây.

---

## 1. Nguyên tắc cốt lõi (Core Principles)

1. **Modularity & Separation of Concerns (SoC):**
   - Tách biệt rõ ràng giữa các tầng: Routing/API ([`app.py`](file:///E:/Project/TripMateAI/app.py)), Multi-Agent Graph & Checkpointing ([`backend.py`](file:///E:/Project/TripMateAI/backend.py)), Công cụ ngoài ([`tools/`](file:///E:/Project/TripMateAI/tools)), Trình diễn & xuất PDF ([`report_template.py`](file:///E:/Project/TripMateAI/report_template.py)), Giao diện người dùng ([`static/`](file:///E:/Project/TripMateAI/static), [`templates/`](file:///E:/Project/TripMateAI/templates)).
2. **Defensive LLM Integration (Phòng vệ dữ liệu từ LLM):**
   - Không bao giờ giả định đầu ra của LLM luôn là chuỗi JSON hợp lệ 100%. Luôn bọc qua cơ chế parse linh hoạt ([`json_repair`](https://github.com/mangiucugna/json_repair) + `json.loads`) kèm xử lý ngoại lệ và fallback an toàn.
3. **Type Safety & Schema Clarity:**
   - Sử dụng Type Hints (`typing.TypedDict`, `typing.Annotated`, `typing.Optional`) cho trạng thái graph và Pydantic `BaseModel` cho dữ liệu truyền nhận qua HTTP API.
4. **Deterministic & Resilient PDF Generation:**
   - Ưu tiên công cụ render headless gốc hệ thống (Chromium / Microsoft Edge Headless) thay vì phụ thuộc vào thư viện bên thứ ba dễ lỗi tương thích OS như WeasyPrint hay thư viện chụp màn hình canvas phía client.

---

## 2. Tiêu chuẩn mã nguồn Python (Python Standards)

Dự án sử dụng **Python 3.11+** và quản lý phụ thuộc bằng **`uv`**.

### 2.1. Quy ước đặt tên (Naming Conventions)
- **Biến và Hàm:** `snake_case` (ví dụ: `run_travel_agent`, `parse_plan_json`, `user_query`).
- **Lớp & TypedDict:** `PascalCase` (ví dụ: `TravelState`, `TravelRequest`, `PdfRequest`).
- **Hằng số & Cấu hình:** `UPPER_SNAKE_CASE` (ví dụ: `BASE_URL`, `COUNTRY_ALIASES`, `PLAN_JSON_INSTRUCTIONS`).
- **Hàm hoặc biến nội bộ:** Thêm tiền tố dấu gạch dưới `_` (ví dụ: `_truncate_text`, `_format_money`, `_budget_bar`).

### 2.2. Type Hinting & State Definitions
Mọi hàm trong luồng xử lý chính cần có chú thích kiểu dữ liệu đầy đủ.

```python
from typing import TypedDict, Annotated, Optional
import operator
from langchain_core.messages import AnyMessage

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int
```

> [!IMPORTANT]
> Khi định nghĩa các trường tin nhắn tích lũy trong LangGraph, luôn sử dụng `Annotated[list[AnyMessage], operator.add]` để trạng thái tin nhắn được thêm mới tuần tự thay vì bị ghi đè.

### 2.3. Xử lý ngoại lệ & Token Budgeting
Do mô hình Groq (`openai/gpt-oss-120b`) có giới hạn số lượng token mỗi phút (TPM) trên gói miễn phí, việc quản lý prompt là bắt buộc:
1. **Cắt tỉa văn bản trước khi đưa vào Prompt:**
   - Dùng hàm `_truncate_text(content, max_chars)` để kiểm soát độ dài kết quả trả về từ công cụ tìm kiếm và chuyến bay.
2. **Cấu hình `max_tokens` đầy đủ cho LLM:**
   - Luôn khởi tạo `ChatGroq(..., max_tokens=8192)` để tránh việc câu trả lời bị cắt cụt giữa chừng.
3. **Cơ chế Retry có suy giảm (Gradual Prompt Reduction):**
   - Khi gặp mã lỗi `413 Request Too Large`, hệ thống phải chủ động hạ cấp độ chi tiết của prompt (ví dụ: chuyển từ schema JSON chi tiết sang prompt tối giản) thay vì thử lại cùng một prompt nhiều lần.

---

## 3. Kiến trúc LangGraph & Multi-Agent

### 3.1. Cấu trúc một Node Agent chuẩn
Mỗi agent trong hệ thống nhận vào `TravelState` và trả về một `dict` cập nhật các trường liên quan trong State:

```python
def example_agent(state: TravelState) -> dict:
    query = state["user_query"]
    data = fetch_external_data(query)
    
    return {
        "flight_results": data,
        "messages": [AIMessage(content="Data fetched successfully.")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
```

### 3.2. Quản lý Phiên & Checkpointer
- Sử dụng `PostgresSaver` kết nối qua chuỗi `DATABASE_URL` (hỗ trợ SSL bắt buộc với `sslmode=require`).
- Mỗi yêu cầu từ người dùng phải đi kèm một `thread_id` duy nhất (nếu không có thì tự sinh UUID) để cách ly trạng thái giữa các người dùng và duy trì lịch sử hội thoại.

---

## 4. Tiêu chuẩn API & FastAPI

1. **Validation dữ liệu đầu vào:**
   Mọi endpoint nhận payload JSON đều phải định nghĩa `pydantic.BaseModel`.
   ```python
   class TravelRequest(BaseModel):
       message: str
       thread_id: Optional[str] = None
   ```
2. **Cấu trúc phản hồi API (`/api/travel`):**
   Phản hồi JSON trả về client cần đảm bảo cấu trúc nhất quán:
   ```json
   {
     "success": true,
     "thread_id": "user_...",
     "answer": "Nội dung trả lời...",
     "plan": { ... },
     "flight_results": "...",
     "hotel_results": "...",
     "itinerary": "...",
     "llm_calls": 3
   }
   ```
3. **Mã lỗi HTTP:**
   - `400 Bad Request`: Tin nhắn rỗng hoặc tham số không hợp lệ.
   - `500 Internal Server Error`: Lỗi hệ thống ngoài tầm kiểm soát (kèm in traceback ra log server).
   - `501 Not Implemented`: Không tìm thấy engine xuất PDF tương thích trên máy chủ.

---

## 5. Tiêu chuẩn Báo cáo & Xuất bản PDF ([`report_template.py`](file:///E:/Project/TripMateAI/report_template.py))

### 5.1. Cấu trúc mẫu 6 phần đồng nhất
Bản kế hoạch du lịch luôn phải tuân thủ chuẩn 6 mục nội dung tương đồng với [`ke-hoach-thai-lan-5-ngay.pdf`](file:///E:/Project/TripMateAI/ke-hoach-thai-lan-5-ngay.pdf):
1. **Cover & Chips:** Tên kế hoạch, phong cách, các chip tóm tắt (*Khởi hành, Ngày đi, Thời gian, Số người, Ngân sách*).
2. **Tổng quan chuyến đi:** 6 thẻ chỉ số chuẩn (*Điểm đến, Bay, Ở, Ăn & chơi, Tổng ước tính thẻ vàng, Thời điểm đẹp nhất*).
3. **Thông tin chuyến bay:** Bảng chặng, hãng bay, giá, ghi chú, visa và huy hiệu (`Rẻ nhất`, `Thoải mái nhất`).
4. **Gợi ý khách sạn:** Bảng khách sạn, khu vực, giá/đêm, điểm nổi bật và huy hiệu (`Tiết kiệm`, `Đáng tiền`).
5. **Lịch trình từng ngày:** Bảng 3 cột (*Thời gian, Hoạt động in đậm địa danh, Chi phí ước tính*).
6. **Ngân sách ước tính:** Bảng chi phí, thanh biểu đồ phần trăm màu sắc, chú giải và ghi chú so sánh ngân sách dư/thiếu.
7. **Lưu ý & khuyến nghị:** 6 thẻ chỉ dẫn thực tế (*Tiền tệ, SIM & mạng, Đi lại, Trang phục, Đặt trước, Ứng dụng*).

### 5.2. Nguyên tắc xuất PDF
- Sử dụng Chromium / Microsoft Edge Headless binary có sẵn:
  `[browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path]`
- Các phần tử HTML trong file in phải có chỉ thị tránh ngắt trang giữa chừng:
  ```css
  .rp-day, .rp-tip, .rp table tr { break-inside: avoid; page-break-inside: avoid; }
  h2 { break-after: avoid; page-break-after: avoid; }
  ```

---

## 6. Tiêu chuẩn Frontend & JavaScript ([`static/script.js`](file:///E:/Project/TripMateAI/static/script.js))

1. **Không rò rỉ biến toàn cục:** Giữ các biến trạng thái (`currentThreadId`, `latestPlan`, `latestAnswerMarkdown`) có phạm vi rõ ràng.
2. **Đồng bộ Logic Render:** Hàm `renderPlanReport(plan)` trên JavaScript phải sinh ra cấu trúc HTML và CSS class `.rp-*` giống hệt hàm `render_plan_html(plan)` trên Python.
3. **Phòng chống XSS:** Mọi chuỗi lấy từ người dùng hoặc mô hình LLM khi nhúng vào DOM qua template literals bắt buộc phải chạy qua hàm `escapeHtml(value)` trước khi gán `innerHTML`.
4. **Tải PDF mượt mà:** Khi người dùng nhấn nút Tải PDF, frontend gọi `/api/travel/pdf` lấy luồng Blob nhị phân và kích hoạt tự động tải xuống kèm tên file chuẩn định dạng `ke-hoach-[diem-den].pdf`.

---

## 7. Quy ước Quản lý Mã nguồn (Git & Workflow)

### 7.1. File không được phép commit (`.gitignore`)
- Các file chứa API key và chuỗi kết nối: `.env`, `.env.local`.
- Thư mục ảo: `.venv/`, `__pycache__/`, `*.pyc`.
- Các file tạm thời khi sinh PDF hoặc debug: `*.tmp`, `debug_*.txt`, `test_*.html`.

### 7.2. Chuẩn viết Commit Message (Conventional Commits)
Sử dụng format chuẩn:
- `feat: <nội dung>`: Thêm tính năng hoặc agent mới.
- `fix: <nội dung>`: Sửa lỗi logic, lỗi parse JSON hoặc lỗi ngắt trang PDF.
- `docs: <nội dung>`: Cập nhật tài liệu kỹ thuật, tiêu chuẩn coding, README.
- `refactor: <nội dung>`: Tối ưu code mà không thay đổi chức năng.
- `chore: <nội dung>`: Cập nhật dependency, cấu hình môi trường.
