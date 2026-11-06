let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";
let latestPlan = null;

function setPrompt(text) {
    document.getElementById("userInput").value = text;
}

function setLoading(isLoading) {
    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    sendBtn.disabled = isLoading;

    if (isLoading) {
        btnText.classList.add("hidden");
        btnLoader.classList.remove("hidden");
    } else {
        btnText.classList.remove("hidden");
        btnLoader.classList.add("hidden");
    }
}

function showError(message) {
    const errorBox = document.getElementById("errorBox");

    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

function hideError() {
    const errorBox = document.getElementById("errorBox");

    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}

function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

const RP_PALETTE = ["#0b5563", "#0e7a6d", "#2a9d8f", "#8ab6b0", "#c98a1b",
    "#e0a93e", "#f2c14e", "#b8c4c9", "#7d9bb0", "#94a3b8"];

function rpBudgetBar(items, total) {
    const usable = items.filter(it => typeof it.amount === "number" && it.amount > 0);
    if (!usable.length || !total) return { bar: "", legend: "" };
    const pcts = usable.map(it => Math.round(it.amount / total * 100));
    let diff = 100 - pcts.reduce((a, b) => a + b, 0);
    if (diff !== 0) pcts[pcts.indexOf(Math.max(...pcts))] += diff;
    const bar = '<div class="rp-bar">' + pcts.map((p, i) =>
        `<div style="width:${p}%; background:${RP_PALETTE[i % RP_PALETTE.length]};"></div>`).join("") + "</div>";
    const legend = '<div class="rp-legend">' + usable.map((it, i) =>
        `<span><i style="background:${RP_PALETTE[i % RP_PALETTE.length]};"></i>${escapeHtml(it.name)} ${pcts[i]}%</span>`).join("") + "</div>";
    return { bar, legend };
}

function rpSection(number, title, tag) {
    return `<h2><span class="num">${number}</span> ${escapeHtml(title)}` +
        `<span class="tag">${escapeHtml(tag)}</span></h2>`;
}

function formatMoney(label, amount) {
    const lbl = String(label || "").trim();
    if (/\d/.test(lbl)) return lbl;
    if (typeof amount === "number" && amount > 0) {
        const val = amount < 1000 ? Math.round(amount * 1000000) : Math.round(amount);
        return val.toLocaleString("vi-VN") + "đ";
    }
    return lbl;
}

function formatCost(cost) {
    if (cost === null || cost === undefined) return "";
    const c = String(cost).trim();
    if (!c || ["null", "none"].includes(c.toLowerCase())) return "";
    const clean = c.replace(/~/g, "").replace(/VND/gi, "").replace(/VNĐ/gi, "").replace(/đ/gi, "").trim();
    const num = parseFloat(clean.replace(",", "."));
    if (!isNaN(num) && num > 0) {
        const val = num < 1000 ? Math.round(num * 1000000) : Math.round(num);
        return "~" + val.toLocaleString("vi-VN") + "đ";
    }
    return c;
}

function formatActivity(text) {
    if (!text) return "";
    return escapeHtml(text)
        .replace(/&lt;b&gt;(.*?)&lt;\/b&gt;/gi, "<b>$1</b>")
        .replace(/\*\*(.*?)\*\*/g, "<b>$1</b>");
}

// Renders the designed report (same markup as report_template.py).
// Returns "" when the plan is missing/empty so the caller can fall back
// to the markdown rendering.
function renderPlanReport(plan) {
    if (!plan || !plan.destination) return "";

    const destParts = String(plan.destination).split("•");
    const title = destParts[0].trim();
    const rest = destParts.length > 1
        ? ` <span class="gold">• ${escapeHtml(destParts.slice(1).join("•").trim())}</span>` : "";

    const chips = [];
    [["Khởi hành", plan.origin], ["Ngày đi", plan.dates], [null, plan.duration],
     [null, plan.travelers], ["Ngân sách", plan.budget_label]].forEach(([label, value]) => {
        if (value) chips.push(`<span class="rp-chip">${label ? escapeHtml(label + ": ") : ""}<b>${escapeHtml(value)}</b></span>`);
    });

    const kicker = plan.duration
        ? `Kế hoạch du lịch &nbsp;•&nbsp; ${escapeHtml(plan.duration)}`
        : "Kế hoạch du lịch";

    let html = `<div class="rp"><div class="rp-cover">` +
        `<div class="rp-kicker">${kicker}</div>` +
        `<h1>${escapeHtml(title)}${rest}</h1>` +
        `<div class="rp-sub">${escapeHtml(plan.style || "")}</div>` +
        `<div class="rp-chips">${chips.join("")}</div></div>`;

    // 1. Summary cards
    html += rpSection(1, "Tổng quan chuyến đi", "Trip Summary");
    if ((plan.summary_cards || []).length) {
        html += '<div class="rp-cards">' + plan.summary_cards.map((card, i) => {
            const label = card.label || "";
            const isGold = (i === 4) || label.toLowerCase().includes("tổng");
            return `<div class="rp-card${isGold ? " gold" : ""}">` +
                `<div class="label">${escapeHtml(label)}</div>` +
                `<div class="value">${escapeHtml(card.value)}</div>` +
                `<div class="note">${escapeHtml(card.note)}</div></div>`;
        }).join("") + "</div>";
        if (plan.summary_note) {
            html += `<p class="muted">${escapeHtml(plan.summary_note)}</p>`;
        }
    }

    // 2. Flights
    if ((plan.flights || []).length) {
        html += rpSection(2, "Thông tin chuyến bay", "Flight Information");
        html += '<table><thead><tr><th>Hãng bay</th><th>Chặng</th><th>Thời gian bay</th>' +
            '<th class="price">Giá khứ hồi / người</th><th>Ghi chú</th></tr></thead><tbody>';
        html += plan.flights.map(f => {
            const hl = f.highlight || "";
            const isTeal = ["Thoải mái nhất", "Tiện nhất", "Giờ bay đẹp"].includes(hl);
            const pill = hl ? `<span class="pill${isTeal ? " teal" : ""}">${escapeHtml(hl)}</span>` : "";
            return `<tr${hl ? ' class="best"' : ""}><td><b>${escapeHtml(f.airline)}</b>${pill}</td>` +
                `<td>${escapeHtml(f.route)}</td><td>${escapeHtml(f.duration)}</td>` +
                `<td class="price">${escapeHtml(f.price)}</td><td>${escapeHtml(f.note)}</td></tr>`;
        }).join("");
        html += "</tbody></table>";
        if (plan.flight_note) html += `<p class="muted">${escapeHtml(plan.flight_note)}</p>`;
        if (plan.visa_note) html += `<p><b>Visa:</b> ${escapeHtml(plan.visa_note)}</p>`;
    }

    // 3. Hotels
    if ((plan.hotels || []).length) {
        const hotelDuration = plan.duration ? ` (${escapeHtml(plan.duration)})` : "";
        html += rpSection(3, `Gợi ý khách sạn${hotelDuration}`, "Hotel Suggestions");
        html += '<table><thead><tr><th>Khách sạn</th><th>Khu vực</th>' +
            '<th class="price">Giá / đêm (phòng đôi)</th><th>Vì sao hợp chuyến này</th></tr></thead><tbody>';
        html += plan.hotels.map(h => {
            const hl = h.highlight || "";
            const isTeal = ["Đáng tiền", "Thoải mái nhất", "Cao cấp"].includes(hl);
            const pill = hl ? `<span class="pill${isTeal ? " teal" : ""}">${escapeHtml(hl)}</span>` : "";
            return `<tr${hl ? ' class="best"' : ""}><td><b>${escapeHtml(h.name)}</b>${pill}</td>` +
                `<td>${escapeHtml(h.area)}</td><td class="price">${escapeHtml(h.price)}</td>` +
                `<td>${escapeHtml(h.note)}</td></tr>`;
        }).join("");
        html += "</tbody></table>";
        if (plan.hotel_note) html += `<p class="muted">${escapeHtml(plan.hotel_note)}</p>`;
    }

    // 4. Day-by-day itinerary
    if ((plan.days || []).length) {
        html += rpSection(4, "Lịch trình từng ngày", "Day-by-Day Itinerary");
        const itNote = plan.itinerary_note || "Giờ địa phương tại điểm đến.";
        html += `<p class="muted">${escapeHtml(itNote)}</p>`;
        html += plan.days.map(day =>
            '<div class="rp-day"><div class="rp-day-head">' +
            `<span class="d">${escapeHtml(day.title)}</span>` +
            `<span class="t">${escapeHtml(day.subtitle)}</span>` +
            `<span class="date">${escapeHtml(day.date)}</span></div>` +
            "<table><tbody>" + (day.items || []).map(it =>
                `<tr><td>${escapeHtml(it.time)}</td><td>${formatActivity(it.activity)}</td>` +
                `<td class="cost">${escapeHtml(formatCost(it.cost))}</td></tr>`).join("") +
            "</tbody></table></div>").join("");
    }

    // 5. Budget
    const budget = plan.budget || {};
    if ((budget.items || []).length) {
        const travelersStr = plan.travelers ? ` (cho ${escapeHtml(plan.travelers)})` : "";
        html += rpSection(5, `Ngân sách ước tính${travelersStr}`, "Estimated Budget");
        html += '<table><thead><tr><th>Hạng mục</th><th>Chi tiết</th>' +
            '<th class="price">Số tiền</th></tr></thead><tbody>';
        html += budget.items.map(it =>
            `<tr><td><b>${escapeHtml(it.name)}</b></td><td>${escapeHtml(it.detail)}</td>` +
            `<td class="price">${escapeHtml(formatMoney(it.label, it.amount))}</td></tr>`).join("");
        
        const midParts = [];
        if (plan.travelers) midParts.push(plan.travelers);
        if (plan.duration) midParts.push(plan.duration);
        const midCol = midParts.join(", ") || "Tổng cộng";

        const totalLabel = formatMoney(budget.total_label, budget.total_amount);
        const limitLabel = formatMoney(budget.limit_label, budget.limit_amount);

        html += `<tr class="total"><td>TỔNG ƯỚC TÍNH</td><td>${escapeHtml(midCol)}</td>` +
            `<td class="price">${escapeHtml(totalLabel)}</td></tr></tbody></table>`;
        const { bar, legend } = rpBudgetBar(budget.items, budget.total_amount || 0);
        html += bar + legend;
        if (limitLabel && totalLabel) {
            html += '<div class="rp-budget-note">Ngân sách của bạn: ' +
                `<b>${escapeHtml(limitLabel)}</b> &nbsp;−&nbsp; Tổng ước tính: ` +
                `<b>${escapeHtml(totalLabel)}</b>` +
                (budget.remaining_label ? ` &nbsp;=&nbsp; <b>${escapeHtml(budget.remaining_label)}</b>` : "") +
                "</div>";
        }
    }

    // 6. Tips
    if ((plan.tips || []).length) {
        html += rpSection(6, "Lưu ý & khuyến nghị", "Final Recommendations");
        html += '<div class="rp-tips">' + plan.tips.map(t =>
            `<div class="rp-tip"><b>${escapeHtml(t.title)}</b> ${escapeHtml(t.text)}</div>`).join("") + "</div>";
    }

    if (plan.disclaimer) {
        html += `<div class="rp-endnote"><p class="muted">Lưu ý: ${escapeHtml(plan.disclaimer)}</p></div>`;
    }
    const destFooter = plan.destination ? `${escapeHtml(plan.destination)} ` : "";
    const durFooter = plan.duration ? `• ${escapeHtml(plan.duration)} ` : "";
    html += `<div class="rp-footer">Kế hoạch tham khảo • Giá ước tính, kiểm tra lại lúc đặt • ${destFooter}${durFooter}— TripMate AI</div></div>`;
    return html;
}

function showResult(answer, threadId, plan) {
    latestAnswerMarkdown = answer;
    latestPlan = plan || null;

    const resultSection = document.getElementById("resultSection");
    const resultBox = document.getElementById("resultBox");
    const reportBox = document.getElementById("reportBox");
    const threadInfo = document.getElementById("threadInfo");

    const reportHtml = renderPlanReport(latestPlan);
    if (reportHtml) {
        reportBox.innerHTML = reportHtml;
        reportBox.classList.remove("hidden");
        resultBox.classList.add("hidden");
        resultBox.innerHTML = "";
    } else {
        if (typeof marked !== "undefined") {
            resultBox.innerHTML = marked.parse(answer);
        } else {
            resultBox.innerText = answer;
        }
        resultBox.classList.remove("hidden");
        reportBox.classList.add("hidden");
        reportBox.innerHTML = "";
    }

    threadInfo.textContent = `Thread ID: ${threadId}`;

    resultSection.classList.remove("hidden");

    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

async function sendMessage() {
    hideError();

    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (!message) {
        showError("Please enter your travel request first.");
        return;
    }

    setLoading(true);

    try {
        const response = await fetch("/api/travel", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                thread_id: currentThreadId
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Something went wrong.");
        }

        currentThreadId = data.thread_id;
        localStorage.setItem("travel_thread_id", currentThreadId);

        showResult(data.answer, data.thread_id, data.plan || null);

    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

function copyResult() {
    const reportBox = document.getElementById("reportBox");
    const resultBox = document.getElementById("resultBox");
    const activeBox = !reportBox.classList.contains("hidden") ? reportBox : resultBox;
    const text = activeBox.innerText;

    if (!text) {
        return;
    }

    navigator.clipboard.writeText(text)
        .then(() => {
            const copyBtn = document.querySelector(".copy-btn");
            const oldText = copyBtn.textContent;

            copyBtn.textContent = "Copied!";

            setTimeout(() => {
                copyBtn.textContent = oldText;
            }, 1400);
        })
        .catch(() => {
            showError("Could not copy result.");
        });
}

async function downloadPDF() {
    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;

    // 1) Server-side PDF (the designed report) when we have a structured plan.
    //    The backend renders it with WeasyPrint -> a real text PDF, not a screenshot.
    if (latestPlan) {
        downloadBtn.textContent = "Preparing PDF...";
        downloadBtn.disabled = true;
        try {
            const response = await fetch("/api/travel/pdf", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan: latestPlan })
            });
            if (!response.ok) throw new Error("Server PDF unavailable.");
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            const safeName = (latestPlan.destination || "travel-plan")
                .split("•")[0].trim().toLowerCase()
                .replace(/[^a-z0-9\u00C0-\u024F\u1EA0-\u1EF9]/gi, "-");
            a.download = `ke-hoach-${safeName}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
            return;
        } catch (error) {
            // Fall through to the client-side screenshot PDF below
            // (e.g. WeasyPrint is not installed on the server).
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
        }
    }

    // 2) Fallback: screenshot the report area with html2pdf.js.
    downloadPDFFromPage();
}

function downloadPDFFromPage() {
    const pdfContent = document.getElementById("pdfContent");

    if (!latestAnswerMarkdown || !pdfContent) {
        showError("No travel plan available to download.");
        return;
    }

    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;

    downloadBtn.textContent = "Preparing PDF...";
    downloadBtn.disabled = true;

    const options = {
        margin: 0.5,
        filename: "ai-travel-plan.pdf",
        image: {
            type: "jpeg",
            quality: 0.98
        },
        html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff"
        },
        jsPDF: {
            unit: "in",
            format: "a4",
            orientation: "portrait"
        },
        pagebreak: {
            mode: ["avoid-all", "css", "legacy"]
        }
    };

    html2pdf()
        .set(options)
        .from(pdfContent)
        .save()
        .then(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
        })
        .catch(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
            showError("Could not download PDF.");
        });
}

document.addEventListener("keydown", function(event) {
    if (event.ctrlKey && event.key === "Enter") {
        sendMessage();
    }
});