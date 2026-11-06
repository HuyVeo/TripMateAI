# ✈️ TripMate AI — Multi-Agent Travel Planner

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-FF6F00?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20GPT--OSS--120B-F55036?style=flat-square)](https://groq.com/)
[![PostgreSQL](https://img.shields.io/badge/Checkpointer-PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Package Manager](https://img.shields.io/badge/Package%20Manager-uv-DE5FE9?style=flat-square)](https://github.com/astral-sh/uv)

**TripMate AI** là hệ thống lập kế hoạch du lịch thông minh đa tác tử (**Multi-Agent AI System**) được xây dựng bằng **LangGraph**, **FastAPI**, **Groq LLM** và **PostgreSQL Checkpointer**. 

Hệ thống tự động điều phối các Agent chuyên trách để tra cứu thông tin chuyến bay trực tiếp, tìm kiếm khách sạn theo ngân sách, thiết kế lịch trình từng ngày chi tiết, lập dự toán tài chính kèm thanh biểu đồ phần trăm và xuất bản báo cáo du lịch trực quan chuẩn mực theo mẫu thiết kế A4 chuyên nghiệp (xuất file PDF vector sắc nét).

---

## 🌟 Điểm nổi bật (Key Features)

- **Kiến trúc Multi-Agent phối hợp tuần tự:** Điều phối 4 Agent chuyên biệt (`flight_agent`, `hotel_agent`, `itinerary_agent`, `final_agent`) qua mô hình StateGraph của LangGraph.
- **Tra cứu chuyến bay thời gian thực:** Kết nối **AviationStack API** kết hợp bộ phân tích tuyến bay và cơ sở dữ liệu sân bay IATA toàn cầu (`airportsdata`, `pycountry`).
- **Tìm kiếm khách sạn thông minh:** Khai thác **Tavily Search API** để tìm kiếm nơi lưu trú kèm đánh giá thực tế và mức giá phù hợp.
- **Bản kế hoạch du lịch chuẩn mực 6 mục (Designed Travel Report):**
  1. **Bìa & Dải Chip (Cover & Chips):** Điểm đến, phong cách du lịch, khởi hành, ngày đi, số người, ngân sách.
  2. **Tổng quan chuyến đi (Trip Summary):** 6 thẻ tóm tắt trực quan kèm thẻ vàng hiển thị tổng chi phí ước tính.
  3. **Thông tin chuyến bay (Flight Information):** Bảng chặng bay, thời gian bay, mức giá kèm huy hiệu `Rẻ nhất`, `Thoải mái nhất`, quy định Visa và mẹo săn vé.
  4. **Gợi ý khách sạn (Hotel Suggestions):** Khách sạn tiêu biểu theo khu vực, phòng đôi, lý do lựa chọn và huy hiệu `Tiết kiệm`, `Đáng tiền`.
  5. **Lịch trình từng ngày (Day-by-Day Itinerary):** Phân chia theo ngày với mốc thời gian rõ ràng, địa danh in đậm và chi phí từng hoạt động.
  6. **Ngân sách ước tính (Estimated Budget):** Bảng phân rã chi phí chi tiết, **thanh phân bổ ngân sách theo tỷ lệ phần trăm (Segmented Budget Bar)** và hộp so sánh số dư ngân sách.
  7. **Lưu ý & khuyến nghị (Final Recommendations):** 6 thẻ chỉ dẫn thực tế (*Tiền tệ, SIM & mạng, Đi lại, Phong tục, Đặt trước vé/tour, Ứng dụng*).
- **Xuất PDF Vector Chất lượng cao:** Tích hợp engine Chromium / Microsoft Edge Headless, xuất thẳng ra file PDF vector A4 sắc nét chỉ trong 1 giây (không bị mờ hay vỡ trang như giải pháp chụp màn hình).
- **Lưu trữ phiên hội thoại (Session Memory):** Sử dụng `PostgresSaver` lưu checkpoint đa phiên theo từng `thread_id`.

---

## 🏗️ Kiến trúc luồng xử lý (Architecture & Data Flow)

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Web as FastAPI (app.py)
    participant Graph as LangGraph Engine (backend.py)
    participant Flight as Flight Agent (AviationStack)
    participant Hotel as Hotel Agent (Tavily)
    participant Itin as Itinerary Agent (Groq LLM)
    participant Final as Final Agent (Groq LLM)
    participant PDF as Export Engine (report_template.py)

    User->>Web: Nhập yêu cầu du lịch (Ví dụ: "Thái Lan 5 ngày 2 người 50tr")
    Web->>Graph: Khởi chạy run_travel_agent(user_query, thread_id)
    Graph->>Flight: Phân tích tuyến bay & tra cứu AviationStack API
    Flight-->>Graph: Cập nhật flight_results
    Graph->>Hotel: Tìm kiếm khách sạn phù hợp qua Tavily API
    Hotel-->>Graph: Cập nhật hotel_results
    Graph->>Itin: Lập khung lịch trình chi tiết theo ngày
    Itin-->>Graph: Cập nhật itinerary
    Graph->>Final: Tổng hợp thành cấu trúc JSON chuẩn 6 phần
    Final-->>Graph: Chuỗi JSON kế hoạch
    Graph->>Graph: json_repair + json.loads phân tích thành plan dict
    Graph-->>Web: Trả về { success, plan, answer, thread_id }
    Web-->>User: Hiển thị báo cáo thiết kế trực quan trên giao diện
    opt Người dùng bấm "Download PDF"
        User->>Web: POST /api/travel/pdf { plan }
        Web->>PDF: render_travel_plan_pdf(plan) qua Edge Headless
        PDF-->>Web: Trả về luồng byte PDF chuẩn A4
        Web-->>User: Tải xuống file ke-hoach-[diem-den].pdf
    end
```

---

## 📂 Cấu trúc thư mục (Project Structure)

```text
TripMateAI/
│
├── app.py                     # Máy chủ Web FastAPI & định nghĩa các Route API
├── backend.py                 # Định nghĩa StateGraph, các Agent nodes & Postgres Checkpointer
├── report_template.py         # Mẫu HTML/CSS báo cáo chuẩn và engine xuất PDF qua Edge/Chromium
├── test.py                    # Script kiểm thử độc lập qua Terminal (tự động xuất PDF)
│
├── tools/
│   ├── flight_tool.py         # Công cụ trích xuất IATA và gọi AviationStack Flight API
│   └── tavily_tool.py         # Công cụ tìm kiếm khách sạn qua Tavily Search API
│
├── templates/
│   └── index.html             # Giao diện chính của ứng dụng web
│
├── static/
│   ├── script.js              # Xử lý tương tác frontend, dựng báo cáo trực quan & tải PDF
│   ├── style.css              # Phong cách giao diện ứng dụng và bộ class .rp-* cho báo cáo
│   └── thailand-5-ngay.html   # File mẫu HTML đối sánh thiết kế
│
├── docs/
│   └── CODING_STANDARDS.md    # Tiêu chuẩn lập trình, quy ước đặt tên và thực hành code
│
├── AGENTS.md                  # Đặc tả chi tiết từng Agent và quy ước dữ liệu
├── ke-hoach-thai-lan-5-ngay.pdf # File mẫu chuẩn PDF đối sánh của hệ thống
├── requirements.txt           # Danh mục thư viện phụ thuộc
├── pyproject.toml             # Cấu hình dự án Python & package manager uv
└── README.md                  # Tài liệu hướng dẫn sử dụng
```

---

## 🚀 Hướng dẫn cài đặt & Khởi chạy (Getting Started)

### 1. Yêu cầu tiên quyết (Prerequisites)
- **Python 3.11+**
- Công cụ quản lý gói **[uv](https://github.com/astral-sh/uv)** (khuyến nghị cho tốc độ vượt trội):
  ```bash
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- Trình duyệt **Microsoft Edge** (đã có sẵn trên Windows) hoặc **Google Chrome** để xuất PDF.

### 2. Thiết lập môi trường ảo & Cài đặt thư viện
Tại thư mục gốc của dự án:
```bash
# Tạo môi trường ảo Python 3.11
uv venv --python 3.11

# Kích hoạt môi trường (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Cài đặt toàn bộ các thư viện
uv sync
```

### 3. Cấu hình biến môi trường (`.env`)
Tạo file `.env` tại thư mục gốc của dự án với nội dung:
```env
# Groq API Key (Dùng cho mô hình openai/gpt-oss-120b)
GROQ_API_KEY=your_groq_api_key_here

# Tavily API Key (Dùng để tìm kiếm thông tin khách sạn)
TAVILY_API_KEY=your_tavily_api_key_here

# AviationStack API Key (Dùng để tra cứu chuyến bay)
AVIATIONSTACK_API_KEY=your_aviationstack_api_key_here

# PostgreSQL Database URL (Có thể dùng Render PostgreSQL External URL)
DATABASE_URL=postgresql://user:password@host:port/database?sslmode=require

# Sân bay mặc định khi người dùng không nói rõ điểm khởi hành (Ví dụ: SGN hoặc HAN)
DEFAULT_ORIGIN_IATA=SGN
```

### 4. Khởi chạy ứng dụng Web
Chạy lệnh:
```bash
uv run python app.py
```
Mở trình duyệt và truy cập: **`http://127.0.0.1:8000`**

### 5. Chạy kiểm thử qua Terminal (CLI)
Bạn có thể chạy thử quy trình mà không cần mở trình duyệt:
```bash
uv run python test.py
```
Nhập câu lệnh bất kỳ (ví dụ: *"Lập kế hoạch du lịch Đà Nẵng 3 ngày 2 đêm từ Hà Nội"*). Hệ thống sẽ xử lý và tự động xuất ra file **`ke-hoach-du-lich.pdf`** ngay trong thư mục dự án.

---

## 📡 Danh sách API Endpoints

| Phương thức | Endpoint | Mô tả | Payload mẫu |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Trả về giao diện web chính | N/A |
| `POST` | `/api/travel` | Xử lý yêu cầu du lịch qua hệ thống Multi-Agent | `{"message": "Kế hoạch Thái Lan 5 ngày", "thread_id": "optional"}` |
| `POST` | `/api/travel/pdf` | Xuất luồng nhị phân PDF từ đối tượng plan | `{"plan": { ... }}` |
| `GET` | `/health` | Kiểm tra tình trạng hoạt động của API | N/A |

---

## 📚 Tài liệu kỹ thuật chuyên sâu

- [Tài liệu Kiến trúc Multi-Agent & Hợp đồng Dữ liệu](file:///E:/Project/TripMateAI/AGENTS.md)
- [Tiêu chuẩn Lập trình & Quy ước Codebase](file:///E:/Project/TripMateAI/docs/CODING_STANDARDS.md)
- [File PDF kết quả mẫu đối sánh](file:///E:/Project/TripMateAI/ke-hoach-thai-lan-5-ngay.pdf)

---

## 📄 Bản quyền (License)

Dự án được phân phối dưới giấy phép **MIT License**. Chi tiết xem tại tệp [`LICENSE`](file:///E:/Project/TripMateAI/LICENSE).
