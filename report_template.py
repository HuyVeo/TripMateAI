"""Report template for TripMate AI travel plans.

The LangGraph ``final_agent`` returns the plan as a structured JSON
object (see PLAN_JSON_INSTRUCTIONS). This module turns that JSON into:

* ``render_plan_html(plan)`` — the designed report (cover, summary cards,
  flight/hotel tables, day-by-day timeline, budget bar, tips), used both
  for the in-app preview and for PDF export.
* ``render_plan_pdf(plan)`` — real text PDF export rendered via
  Chromium/Edge headless (exact A4 matching ke-hoach-thai-lan-5-ngay.pdf),
  with WeasyPrint fallback.
"""

import html
import os
import re
import shutil
import subprocess
import tempfile

# ---------------------------------------------------------------------------
# JSON contract for final_agent (imported by backend.py for LLM prompt)
# Formatted to produce the exact 6 sections seen in ke-hoach-thai-lan-5-ngay.pdf
# ---------------------------------------------------------------------------
PLAN_JSON_INSTRUCTIONS = """Output ONLY a JSON object, no markdown fences, no extra text before or after.
Reply in Vietnamese (or the language of the user query).
The output must follow this exact structure:
{
  "destination": "Bangkok • Thái Lan",
  "origin": "TP.HCM (SGN)",
  "dates": "15 – 19/01/2027",
  "duration": "5 ngày 4 đêm",
  "travelers": "2 người lớn",
  "budget_label": "50.000.000đ",
  "style": "Từ TP.HCM — phố cổ, chợ nổi, di sản Ayutthaya & mua sắm. Vừa tiền nhưng thoải mái.",
  "summary_cards": [
    {"label": "ĐIỂM ĐẾN", "value": "Bangkok, Thái Lan", "note": "+ chợ nổi Damnoen Saduak & Ayutthaya"},
    {"label": "BAY", "value": "Bay thẳng ~1h45m", "note": "SGN → BKK, VietJet / Vietnam Airlines"},
    {"label": "Ở", "value": "4 đêm, khách sạn 3–4★", "note": "Khu Siam / Sukhumvit, gần BTS"},
    {"label": "ĂN & CHƠI", "value": "Chùa, chợ, sông, biển…", "note": "Grand Palace, Wat Pho, Chatuchak"},
    {"label": "TỔNG ƯỚC TÍNH", "value": "~40.700.000đ", "note": "Cho 2 người — còn dư ~9.300.000đ"},
    {"label": "THỜI ĐIỂM ĐẸP NHẤT", "value": "Tháng 11 – tháng 2", "note": "Mùa khô, 25–32°C, ít mưa"}
  ],
  "summary_note": "Ngày đi trong bản này là ví dụ (15–19/01/2027, thứ 6 – thứ 3). Đổi ngày khác vẫn dùng được lịch trình này — riêng chợ Chatuchak chỉ mở cuối tuần (thứ 7 – chủ nhật).",
  "flights": [
    {"airline": "Thai AirAsia", "route": "SGN → DMK", "duration": "~1h50m", "price": "3.500.000 – 5.000.000đ", "note": "Giá tốt nhất, nhưng xuống sân bay Don Mueang, xa trung tâm hơn BKK.", "highlight": "Rẻ nhất"},
    {"airline": "VietJet Air", "route": "SGN → BKK", "duration": "~1h45m", "price": "3.800.000 – 5.500.000đ", "note": "Bay thẳng Suvarnabhumi; hành lý xách tay 7kg, mua thêm ký gửi.", "highlight": null},
    {"airline": "Thai Vietjet", "route": "SGN → BKK", "duration": "~1h45m", "price": "4.000.000 – 5.500.000đ", "note": "Bay thẳng, giờ bay linh hoạt, hay có khuyến mãi.", "highlight": null},
    {"airline": "Vietnam Airlines", "route": "SGN → BKK", "duration": "~1h45m", "price": "5.500.000 – 7.500.000đ", "note": "Gồm 23kg ký gửi + suất ăn, giờ bay đẹp, ít delay.", "highlight": "Thoải mái nhất"}
  ],
  "flight_note": "Giá tham khảo, kiểm tra lại lúc đặt. Mẹo đặt vé: so sánh trên Skyscanner / Google Flights, đặt trước 4–6 tuần, bay sáng sớm hoặc tối muộn thường rẻ hơn. Bay thẳng xuống BKK (Suvarnabhumi) tiện hơn DMK vì có Airport Rail Link vào trung tâm.",
  "visa_note": "Hộ chiếu Việt Nam được miễn visa Thái Lan 30 ngày. Chỉ cần hộ chiếu còn hạn ít nhất 6 tháng và vé khứ hồi.",
  "hotels": [
    {"name": "ibis Styles Bangkok Ratchada", "area": "Ratchada, gần MRT Huai Khwang", "price": "~950.000đ", "note": "Hiện đại, sạch, gần chợ đêm Ratchada, tiện đi MRT.", "highlight": "Tiết kiệm"},
    {"name": "Holiday Inn Express Bangkok Siam", "area": "Siam (trung tâm)", "price": "~1.500.000đ", "note": "Bao ăn sáng, ngay BTS Siam — đi đâu cũng tiện.", "highlight": "Đáng tiền"},
    {"name": "Centara Watergate Pavillion", "area": "Pratunam (khu mua sắm)", "price": "~1.600.000đ", "note": "Ngay chợ Pratunam & Platinum Mall — tiện mua sắm ngày cuối.", "highlight": null},
    {"name": "Mercure Bangkok Sukhumvit 24", "area": "Sukhumvit, gần BTS Phrom Phong", "price": "~1.700.000đ", "note": "Hồ bơi rooftop, khu ăn uống sầm uất, yên tĩnh về đêm.", "highlight": null}
  ],
  "hotel_note": "Giá phòng đôi/đêm tham khảo trên Agoda / Booking.com. Nên chọn loại “miễn phí hủy” nếu chưa chốt ngày, và đặt sớm 3–4 tuần để giữ giá tốt.",
  "itinerary_note": "Giờ địa phương tại điểm đến. Đi lại trong thành phố: BTS/MRT + Grab, ~150.000–250.000đ/ngày.",
  "days": [
    {
      "title": "Ngày 1",
      "subtitle": "Bay sang Bangkok & phố cổ về đêm",
      "date": "Thứ 6, 15/01/2027",
      "items": [
        {"time": "06:30 – 08:00", "activity": "Ra sân bay, làm thủ tục, ăn sáng nhẹ.", "cost": null},
        {"time": "09:00 – 10:45", "activity": "Bay SGN → BKK (bay thẳng ~1h45m).", "cost": null},
        {"time": "11:00 – 12:30", "activity": "Nhập cảnh, mua SIM du lịch, đi Airport Rail Link + BTS về khách sạn.", "cost": "~150.000đ"},
        {"time": "14:00", "activity": "Check-in khách sạn, nghỉ ngơi sau chuyến bay.", "cost": null},
        {"time": "15:00 – 17:00", "activity": "<b>Wat Arun</b> (100 THB) & <b>Wat Pho</b> (200 THB) — hai ngôi chùa đẹp nhất ven sông.", "cost": "~220.000đ"},
        {"time": "17:30 – 19:00", "activity": "Dạo sông Chao Phraya, ngắm hoàng hôn từ bến tàu.", "cost": "~50.000đ"},
        {"time": "19:00 – 21:30", "activity": "Ăn tối phố Tàu <b>Yaowarat</b> — hải sản, chè, đồ ăn đường phố.", "cost": "~400.000đ"},
        {"time": "22:00", "activity": "Về khách sạn, nghỉ sớm lấy sức cho ngày mai.", "cost": null}
      ]
    }
  ],
  "budget": {
    "items": [
      {"name": "Vé máy bay khứ hồi", "detail": "VietJet, 4.500.000đ/người, gồm 20kg ký gửi", "amount": 9000000, "label": "9.000.000đ"},
      {"name": "Khách sạn 4 đêm", "detail": "~1.400.000đ/đêm, phòng đôi", "amount": 5600000, "label": "5.600.000đ"},
      {"name": "Ăn uống 5 ngày", "detail": "~1.200.000đ/ngày cho 2 người", "amount": 6000000, "label": "6.000.000đ"},
      {"name": "Đi lại nội địa", "detail": "BTS / MRT / Grab / taxi", "amount": 2500000, "label": "2.500.000đ"},
      {"name": "Vé tham quan", "detail": "Grand Palace, Wat Pho, Wat Arun, chùa Ayutthaya, thuyền", "amount": 3000000, "label": "3.000.000đ"},
      {"name": "Tour ngày", "detail": "Chợ nổi + đường ray, Ayutthaya (xe + hướng dẫn)", "amount": 3600000, "label": "3.600.000đ"},
      {"name": "Mua sắm & quà", "detail": "Chatuchak, Pratunam, Platinum Mall", "amount": 5000000, "label": "5.000.000đ"},
      {"name": "SIM + bảo hiểm du lịch", "detail": "SIM du lịch 2 cái + bảo hiểm 5 ngày", "amount": 1000000, "label": "1.000.000đ"},
      {"name": "Dự phòng", "detail": "Phát sinh, tip, đổi tiền lẻ", "amount": 5000000, "label": "5.000.000đ"}
    ],
    "total_amount": 40700000,
    "total_label": "40.700.000đ",
    "limit_amount": 50000000,
    "limit_label": "50.000.000đ",
    "remaining_label": "Còn dư ~9.300.000đ để nâng cấp khách sạn, thêm tour đảo, hoặc mua sắm thoải mái hơn."
  },
  "tips": [
    {"title": "Tiền tệ.", "text": "1 THB ≈ 730đ. Đổi tiền ở SuperRich (tỷ giá tốt) hoặc rút ATM. Chợ và xe địa phương chủ yếu dùng tiền mặt — luôn mang theo tiền lẻ."},
    {"title": "SIM & mạng.", "text": "SIM du lịch AIS / TrueMove bán ngay tại sân bay hoặc mua eSIM trước trên Klook. Nên mua 1 SIM phát wifi cho đoàn."},
    {"title": "Đi lại.", "text": "BTS/MRT + Grab là tiện và rẻ nhất. Tránh taxi không bật đồng hồ; đi tuk-tuk nhớ trả giá trước khi lên xe."},
    {"title": "Vào chùa.", "text": "Mặc kín vai và đầu gối, bỏ giày dép trước khi vào. Không chạm vào đầu tượng Phật, không chỉ chân về phía tượng."},
    {"title": "Đặt trước.", "text": "Vé Grand Palace, tour chợ nổi & điểm tham quan nên đặt online qua Klook trước 1–2 tuần để giữ giá tốt và chắc suất."},
    {"title": "Ứng dụng nên có.", "text": "Grab (đi lại), Google Maps (chỉ đường + BTS/MRT), Klook (vé/tour), Agoda / Booking.com (khách sạn)."}
  ],
  "disclaimer": "mọi giá trong bản này là ước tính tham khảo tại thời điểm lập kế hoạch (vé máy bay và khách sạn thay đổi theo ngày đặt). Kiểm tra lại giá lúc đặt vé. Cấu trúc báo cáo này theo đúng 6 mục của TripMate AI."
}

Rules:
1. Always output strictly valid JSON matching this schema. No markdown fences, no conversational text.
2. In summary_cards, include exactly 6 cards (Điểm đến, Bay, Ở, Ăn & chơi, Tổng ước tính, Thời điểm đẹp nhất).
3. The 5th card 'Tổng ước tính' must have the estimated total cost.
4. Highlight badges: use 'Rẻ nhất', 'Thoải mái nhất', 'Tiết kiệm', 'Đáng tiền' or null.
5. In days.items.activity, wrap key attractions or places in <b>...</b> for emphasis.
6. The budget amounts must be realistic integers in VND, adding up to total_amount.
"""

# ---------------------------------------------------------------------------
# Design (identical look to ke-hoach-thai-lan-5-ngay.pdf; classes prefixed rp-)
# ---------------------------------------------------------------------------
REPORT_CSS = """
  @page { size: A4; margin: 15mm 14mm 20mm 14mm; }
  * { box-sizing: border-box; }
  body {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    background: #fff;
  }
  .rp { font-family: "Noto Sans", "DejaVu Sans", "Segoe UI", sans-serif; color: #22303a;
        font-size: 10.5pt; line-height: 1.55; background: #fff; }
  .rp-cover { background: linear-gradient(135deg, #0b5563 0%, #0e7a6d 55%, #c98a1b 130%);
    color: #fff; border-radius: 14px; padding: 30px 28px 24px; margin-bottom: 18px; }
  .rp-kicker { font-size: 10pt; letter-spacing: 3px; text-transform: uppercase; opacity: .85; }
  .rp-cover h1 { font-size: 30pt; line-height: 1.15; margin: 8px 0 4px; font-weight: 700; color: #fff; }
  .rp-cover h1 .gold { color: #ffd98a; }
  .rp-sub { font-size: 12pt; opacity: .92; margin-bottom: 18px; }
  .rp-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .rp-chip { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.35);
    border-radius: 999px; padding: 6px 13px; font-size: 9.5pt; font-weight: 700; }
  .rp-chip b { color: #ffd98a; }
  .rp h2 { font-size: 15pt; color: #0b5563; margin: 22px 0 10px; padding-bottom: 6px;
    border-bottom: 2px solid #e6f2f0; display: flex; align-items: center; gap: 10px;
    break-after: avoid; page-break-after: avoid; }
  .rp h2 .num { display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; border-radius: 50%; background: #0b5563; color: #fff;
    font-size: 12pt; font-weight: 700; flex: 0 0 26px; }
  .rp h2 .tag { margin-left: auto; font-size: 8.5pt; color: #8a97a3; font-weight: 400;
    letter-spacing: 1px; text-transform: uppercase; }
  .rp p { margin: 6px 0; }
  .rp .muted { color: #6b7a86; font-size: 9.5pt; }
  .rp-cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 4px; }
  .rp-card { flex: 1 1 30%; min-width: 150px; background: #f4f8f7; border: 1px solid #dcebe8;
    border-top: 3px solid #0e7a6d; border-radius: 10px; padding: 12px 14px; break-inside: avoid; }
  .rp-card .label { font-size: 8.5pt; letter-spacing: 1.5px; text-transform: uppercase;
    color: #0e7a6d; font-weight: 700; }
  .rp-card .value { font-size: 13pt; font-weight: 700; margin-top: 3px; }
  .rp-card .note { font-size: 9pt; color: #5b6b76; margin-top: 2px; }
  .rp-card.gold { border-top-color: #c98a1b; background: #fdf8ec; border-color: #f0e2c0; }
  .rp-card.gold .label { color: #a86f0e; }
  .rp table { width: 100%; border-collapse: collapse; margin: 8px 0 4px; font-size: 10pt; }
  .rp th { background: #eaf3f1; color: #0b5563; text-align: left; padding: 8px 10px;
    font-size: 9pt; letter-spacing: .5px; text-transform: uppercase; border-bottom: 2px solid #cfe3de; }
  .rp td { padding: 8px 10px; border-bottom: 1px solid #e8eef0; vertical-align: top; }
  .rp tr:nth-child(even) td { background: #f8fbfb; }
  .rp tr.best td { background: #fdf6e3; }
  .rp .pill { display: inline-block; font-size: 8pt; font-weight: 700; color: #8a5d00;
    background: #ffe9ad; border-radius: 999px; padding: 2px 8px; margin-left: 6px;
    text-transform: uppercase; letter-spacing: .5px; white-space: nowrap; }
  .rp .pill.teal { color: #0b5563; background: #cde9e4; }
  .rp td.price, .rp th.price { text-align: right; white-space: nowrap; font-weight: 700; }
  .rp tr.total td { background: #0b5563; color: #fff; font-weight: 700; border-bottom: none; }
  .rp thead { display: table-header-group; }
  .rp tr { break-inside: avoid; page-break-inside: avoid; }
  .rp-day { margin: 14px 0 6px; break-inside: avoid; page-break-inside: avoid; }
  .rp-day-head { display: flex; align-items: baseline; gap: 10px; background: #0b5563;
    color: #fff; border-radius: 8px 8px 0 0; padding: 9px 14px; }
  .rp-day-head .d { font-size: 12pt; font-weight: 700; }
  .rp-day-head .t { font-size: 10pt; color: #ffd98a; font-weight: 700; }
  .rp-day-head .date { margin-left: auto; font-size: 9pt; opacity: .85; }
  .rp-day table { margin: 0; }
  .rp-day table td:first-child { white-space: nowrap; font-weight: 700; color: #0b5563; width: 110px; }
  .rp-day table td.cost { text-align: right; white-space: nowrap; color: #5b6b76; width: 110px; }
  .rp-bar { display: flex; height: 22px; border-radius: 999px; overflow: hidden; margin: 12px 0 8px; }
  .rp-bar div { height: 100%; }
  .rp-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 9pt; margin-bottom: 6px; }
  .rp-legend span i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; }
  .rp-budget-note { background: #fdf8ec; border: 1px solid #f0e2c0; border-radius: 10px;
    padding: 12px 16px; margin-top: 10px; font-size: 10.5pt; }
  .rp-budget-note b { color: #0b5563; }
  .rp-tips { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
  .rp-tip { flex: 1 1 45%; min-width: 220px; background: #f4f8f7; border: 1px solid #dcebe8;
    border-radius: 10px; padding: 11px 14px; break-inside: avoid; page-break-inside: avoid; }
  .rp-tip b { color: #0b5563; }
  .rp-endnote { margin-top: 18px; padding-top: 10px; border-top: 1px solid #e8eef0; break-inside: avoid; }
  .rp-footer { font-size: 8pt; color: #9aa8b2; text-align: center; margin-top: 22px; }
"""

_PALETTE = ["#0b5563", "#0e7a6d", "#2a9d8f", "#8ab6b0", "#c98a1b",
            "#e0a93e", "#f2c14e", "#b8c4c9", "#7d9bb0", "#94a3b8"]


def _esc(value) -> str:
    """HTML-escape LLM/user text; None becomes an empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _format_activity(text: str) -> str:
    """Allow safe bold tags in activity text."""
    if not text:
        return ""
    val = _esc(text)
    # Restore bold tags from safe escaped text
    val = re.sub(r"&lt;b&gt;(.*?)&lt;/b&gt;", r"<b>\1</b>", val, flags=re.IGNORECASE)
    val = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", val)
    return val


def _format_money(label, amount) -> str:
    """Format money string with dot thousands separator, falling back from amount if needed."""
    lbl = str(label or "").strip()
    if any(ch.isdigit() for ch in lbl):
        return lbl
    if isinstance(amount, (int, float)) and amount > 0:
        val = int(amount * 1_000_000) if amount < 1000 else int(amount)
        return f"{val:,}đ".replace(",", ".")
    return lbl


def _budget_bar(items, total):
    """Segmented budget bar + legend. Only numeric amounts are shown."""
    usable = []
    for it in items:
        amt = it.get("amount")
        if isinstance(amt, (int, float)) and amt > 0:
            amt_val = amt * 1_000_000 if amt < 1000 else amt
            usable.append((it, amt_val))
    if not usable:
        return "", ""
    calc_total = sum(amt for _, amt in usable) if not total else (total * 1_000_000 if total < 1000 else total)
    if not calc_total:
        return "", ""
    pcts = [round(amt / calc_total * 100) for _, amt in usable]
    diff = 100 - sum(pcts)
    if diff and pcts:
        pcts[pcts.index(max(pcts))] += diff
    segments = "".join(
        f'<div style="width:{p}%; background:{_PALETTE[i % len(_PALETTE)]};"></div>'
        for i, p in enumerate(pcts)
    )
    legend = "".join(
        f'<span><i style="background:{_PALETTE[i % len(_PALETTE)]};"></i>'
        f'{_esc(it.get("name", ""))} {p}%</span>'
        for i, (it, _) in enumerate(usable) for p in [pcts[i]]
    )
    return f'<div class="rp-bar">{segments}</div>', f'<div class="rp-legend">{legend}</div>'


def _section(number: int, title: str, tag: str) -> str:
    return (f'<h2><span class="num">{number}</span> {_esc(title)}'
            f'<span class="tag">{_esc(tag)}</span></h2>')


def _cover(plan: dict) -> str:
    dest = _esc(plan.get("destination") or "Travel Plan")
    parts = dest.split("•", 1)
    title = parts[0].strip()
    rest = f' <span class="gold">• {_esc(parts[1].strip())}</span>' if len(parts) > 1 else ""
    chips = []
    for label, key in [("Khởi hành", "origin"), ("Ngày đi", "dates"),
                       (None, "duration"), (None, "travelers"), ("Ngân sách", "budget_label")]:
        value = plan.get(key)
        if not value:
            continue
        chips.append(f'<span class="rp-chip">{_esc(label + ": ") if label else ""}'
                     f'<b>{_esc(value)}</b></span>')
    duration = _esc(plan.get("duration") or "")
    kicker = f'Kế hoạch du lịch &nbsp;•&nbsp; {duration}' if duration else 'Kế hoạch du lịch'
    return (
        '<div class="rp-cover">'
        f'<div class="rp-kicker">{kicker}</div>'
        f'<h1>{title}{rest}</h1>'
        f'<div class="rp-sub">{_esc(plan.get("style") or "")}</div>'
        f'<div class="rp-chips">{"".join(chips)}</div>'
        '</div>'
    )


def _summary_cards(plan: dict) -> str:
    cards = plan.get("summary_cards") or []
    if not cards:
        return ""
    out = []
    for i, card in enumerate(cards):
        label = card.get("label") or ""
        is_gold = (i == 4) or ("tổng" in label.lower())
        gold = " gold" if is_gold else ""
        out.append(
            f'<div class="rp-card{gold}">'
            f'<div class="label">{_esc(label)}</div>'
            f'<div class="value">{_esc(card.get("value"))}</div>'
            f'<div class="note">{_esc(card.get("note"))}</div>'
            '</div>'
        )
    note = f'<p class="muted">{_esc(plan["summary_note"])}</p>' if plan.get("summary_note") else ""
    return f'<div class="rp-cards">{"".join(out)}</div>{note}'


def _flights(plan: dict) -> str:
    flights = plan.get("flights") or []
    if not flights:
        return ""
    rows = []
    for f in flights:
        best = " class=\"best\"" if f.get("highlight") else ""
        hl = f.get("highlight") or ""
        is_teal = hl in ("Thoải mái nhất", "Tiện nhất", "Giờ bay đẹp")
        pill_class = "pill teal" if is_teal else "pill"
        pill = f'<span class="{pill_class}">{_esc(hl)}</span>' if hl else ""
        rows.append(
            f'<tr{best}><td><b>{_esc(f.get("airline"))}</b>{pill}</td>'
            f'<td>{_esc(f.get("route"))}</td>'
            f'<td>{_esc(f.get("duration"))}</td>'
            f'<td class="price">{_esc(f.get("price"))}</td>'
            f'<td>{_esc(f.get("note"))}</td></tr>'
        )
    note = f'<p class="muted">{_esc(plan["flight_note"])}</p>' if plan.get("flight_note") else ""
    visa = f'<p><b>Visa:</b> {_esc(plan["visa_note"])}</p>' if plan.get("visa_note") else ""
    return (
        _section(2, "Thông tin chuyến bay", "Flight Information")
        + '<table><thead><tr><th>Hãng bay</th><th>Chặng</th><th>Thời gian bay</th>'
          '<th class="price">Giá khứ hồi / người</th><th>Ghi chú</th></tr></thead>'
        + f'<tbody>{"".join(rows)}</tbody></table>{note}{visa}'
    )


def _hotels(plan: dict) -> str:
    hotels = plan.get("hotels") or []
    if not hotels:
        return ""
    rows = []
    for h in hotels:
        best = " class=\"best\"" if h.get("highlight") else ""
        hl = h.get("highlight") or ""
        is_teal = hl in ("Đáng tiền", "Thoải mái nhất", "Cao cấp")
        pill_class = "pill teal" if is_teal else "pill"
        pill = f'<span class="{pill_class}">{_esc(hl)}</span>' if hl else ""
        rows.append(
            f'<tr{best}><td><b>{_esc(h.get("name"))}</b>{pill}</td>'
            f'<td>{_esc(h.get("area"))}</td>'
            f'<td class="price">{_esc(h.get("price"))}</td>'
            f'<td>{_esc(h.get("note"))}</td></tr>'
        )
    note = f'<p class="muted">{_esc(plan["hotel_note"])}</p>' if plan.get("hotel_note") else ""
    duration_str = f' ({_esc(plan.get("duration"))})' if plan.get("duration") else ""
    return (
        _section(3, f"Gợi ý khách sạn{duration_str}", "Hotel Suggestions")
        + '<table><thead><tr><th>Khách sạn</th><th>Khu vực</th>'
          '<th class="price">Giá / đêm (phòng đôi)</th><th>Vì sao hợp chuyến này</th></tr></thead>'
        + f'<tbody>{"".join(rows)}</tbody></table>{note}'
    )


def _format_cost(cost) -> str:
    """Format day item cost nicely with ~ and VND currency."""
    if cost is None:
        return ""
    c = str(cost).strip()
    if not c or c.lower() in ("null", "none"):
        return ""
    try:
        clean = c.replace("~", "").replace("VND", "").replace("VNĐ", "").replace("đ", "").strip()
        num = float(clean.replace(",", "."))
        if num > 0:
            if num < 1000:
                num = num * 1_000_000
            return f"~{int(num):,}đ".replace(",", ".")
    except (ValueError, TypeError):
        pass
    return c


def _days(plan: dict) -> str:
    days = plan.get("days") or []
    if not days:
        return ""
    it_note = plan.get("itinerary_note") or "Giờ địa phương tại điểm đến."
    out = [_section(4, "Lịch trình từng ngày", "Day-by-Day Itinerary"),
           f'<p class="muted">{_esc(it_note)}</p>']
    for day in days:
        items = "".join(
            f'<tr><td>{_esc(it.get("time"))}</td>'
            f'<td>{_format_activity(it.get("activity"))}</td>'
            f'<td class="cost">{_esc(_format_cost(it.get("cost")))}</td></tr>'
            for it in (day.get("items") or [])
        )
        out.append(
            '<div class="rp-day">'
            '<div class="rp-day-head">'
            f'<span class="d">{_esc(day.get("title"))}</span>'
            f'<span class="t">{_esc(day.get("subtitle"))}</span>'
            f'<span class="date">{_esc(day.get("date"))}</span>'
            '</div>'
            f'<table><tbody>{items}</tbody></table></div>'
        )
    return "".join(out)


def _budget(plan: dict) -> str:
    budget = plan.get("budget") or {}
    items = budget.get("items") or []
    if not items:
        return ""
    rows = "".join(
        f'<tr><td><b>{_esc(it.get("name"))}</b></td>'
        f'<td>{_esc(it.get("detail"))}</td>'
        f'<td class="price">{_esc(_format_money(it.get("label"), it.get("amount")))}</td></tr>'
        for it in items
    )
    total_label = _format_money(budget.get("total_label"), budget.get("total_amount"))
    limit_label = _format_money(budget.get("limit_label"), budget.get("limit_amount"))

    travelers_duration = []
    if plan.get("travelers"):
        travelers_duration.append(str(plan.get("travelers")))
    if plan.get("duration"):
        travelers_duration.append(str(plan.get("duration")))
    mid_col = ", ".join(travelers_duration) or "Tổng cộng"

    total_row = (
        '<tr class="total"><td>TỔNG ƯỚC TÍNH</td>'
        f'<td>{_esc(mid_col)}</td>'
        f'<td class="price">{_esc(total_label)}</td></tr>'
    )
    bar, legend = _budget_bar(items, budget.get("total_amount") or 0)
    remaining = ""
    if limit_label and total_label:
        rem_label = budget.get("remaining_label") or ""
        remaining = (
            '<div class="rp-budget-note">Ngân sách của bạn: '
            f'<b>{_esc(limit_label)}</b> &nbsp;−&nbsp; Tổng ước tính: '
            f'<b>{_esc(total_label)}</b>'
            + (f' &nbsp;=&nbsp; <b>{_esc(rem_label)}</b>' if rem_label else "")
            + '</div>'
        )
    travelers_str = f' (cho {_esc(plan.get("travelers"))})' if plan.get("travelers") else ""
    return (
        _section(5, f"Ngân sách ước tính{travelers_str}", "Estimated Budget")
        + '<table><thead><tr><th>Hạng mục</th><th>Chi tiết</th>'
          '<th class="price">Số tiền</th></tr></thead>'
        + f'<tbody>{rows}{total_row}</tbody></table>{bar}{legend}{remaining}'
    )


def _tips(plan: dict) -> str:
    tips = plan.get("tips") or []
    if not tips:
        return ""
    cards = "".join(
        f'<div class="rp-tip"><b>{_esc(t.get("title"))}</b> {_esc(t.get("text"))}</div>'
        for t in tips
    )
    return _section(6, "Lưu ý & khuyến nghị", "Final Recommendations") \
        + f'<div class="rp-tips">{cards}</div>'


def render_plan_html(plan: dict) -> str:
    """Full standalone HTML document for one plan (print-ready A4)."""
    title = _esc(plan.get("destination") or "Travel Plan")
    dest_name = _esc(plan.get("destination") or "")
    duration_name = f' • {_esc(plan.get("duration"))}' if plan.get("duration") else ""
    body = (
        _cover(plan)
        + _section(1, "Tổng quan chuyến đi", "Trip Summary")
        + _summary_cards(plan)
        + _flights(plan)
        + _hotels(plan)
        + _days(plan)
        + _budget(plan)
        + _tips(plan)
    )
    if plan.get("disclaimer"):
        body += (f'<div class="rp-endnote"><p class="muted">Lưu ý: '
                 f'{_esc(plan["disclaimer"])}</p></div>')
    body += (f'<div class="rp-footer">Kế hoạch tham khảo • Giá ước tính, '
             f'kiểm tra lại lúc đặt • {dest_name}{duration_name} — TripMate AI</div>')
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8">'
        f'<title>{title} — TripMate AI</title>'
        f'<style>{REPORT_CSS}</style></head>'
        f'<body><div class="rp">{body}</div></body></html>'
    )


def find_chromium_browser():
    """Find Microsoft Edge or Google Chrome binary on Windows/Linux/macOS."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def render_plan_pdf(plan: dict) -> bytes:
    """Render the plan to a real text PDF (A4).

    First tries Chromium/Edge headless for exact pixel-perfect PDF rendering
    identical to ke-hoach-thai-lan-5-ngay.pdf.
    Falls back to WeasyPrint if available.
    """
    browser = find_chromium_browser()
    if browser:
        html_str = render_plan_html(plan)
        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = os.path.join(tmpdir, "report.html")
            pdf_file = os.path.join(tmpdir, "report.pdf")
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_str)
            cmd = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_file}",
                html_file,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            with open(pdf_file, "rb") as f:
                return f.read()

    # Fallback to WeasyPrint
    try:
        from weasyprint import HTML
        return HTML(string=render_plan_html(plan)).write_pdf()
    except Exception as exc:
        raise RuntimeError(
            "PDF export requires Microsoft Edge, Google Chrome, or WeasyPrint to be installed."
        ) from exc
