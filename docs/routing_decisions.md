# Routing Decisions Log — Lab Day 09

**Nhóm:** C401-C3 
**Ngày:** 2026-04-14

---

## Routing Decision #1

**Task đầu vào:**
> SLA xử lý ticket P1 là bao lâu?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `SLA/ticket keyword detected: ['p1', 'sla', 'ticket']`  
**MCP tools được gọi:** None  
**Workers called sequence:** ['retrieval_worker', 'synthesis_worker']

**Kết quả thực tế:**
- final_answer (ngắn): Phản hồi 15 phút, xử lý 4 giờ.
- confidence: 0.52
- Correct routing? Yes

**Nhận xét:** Routing chính xác nhờ keyword matching đơn giản, giúp giảm độ trễ.

---

## Routing Decision #2

**Task đầu vào:**
> Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `policy/access keyword detected: ['cấp quyền', 'level 3'] | risk_high=True (khẩn cấp)`  
**MCP tools được gọi:** `search_kb`, `get_ticket_info`, `check_access_permission`  
**Workers called sequence:** ['policy_tool_worker', 'retrieval_worker', 'synthesis_worker']

**Kết quả thực tế:**
- final_answer (ngắn): Cần sự phê duyệt của 3 bên: Line Manager, IT Admin, và IT Security.
- confidence: 0.53
- Correct routing? Yes

**Nhận xét:** Đây là case phức tạp, supervisor nhận diện tốt context rủi ro.

---

## Routing Decision #3

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý?

**Worker được chọn:** `human_review`  
**Route reason (từ trace):** `unknown error code (err-) + risk_high → human review required`  
**MCP tools được gọi:** None  
**Workers called sequence:** ['human_review', 'retrieval_worker', 'synthesis_worker']

**Kết quả thực tế:**
- final_answer (ngắn): Không tìm thấy thông tin trong tài liệu nội bộ.
- confidence: 0.30
- Correct routing? Yes

**Nhận xét:** Ngăn chặn việc AI tự bịa câu trả lời cho lỗi lạ.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 7 | 46% |
| policy_tool_worker | 7 | 46% |
| human_review | 1 | 6% |

### Routing Accuracy
- Câu route đúng: 15 / 15
- Câu trigger HITL: 1

### Lesson Learned về Routing
1. **Hybrid Logic**: Keyword kết hợp LLM là tối ưu nhất.
2. **Confidence**: synthesis_worker là chốt chặn quan trọng cuối cùng.

---

### Route Reason Quality — Cần Cải Tiến

**Vấn đề:** Decision #3 route_reason chứa "unknown" → **SCORING.md violation (-2 pts)**

**Giải pháp:** Thêm confidence score vào route_reason format
```
{category} (confidence={score:.2f}) → {worker} | {reason}
```

**Ví dụ fix:**
- `unknown error code (err-)...`  
- `error_pattern (confidence=0.88) → human_review | Unrecognized error code ERR-403-AUTH`

