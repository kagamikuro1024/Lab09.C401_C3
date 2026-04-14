# 📋 KẾ HOẠCH CÁ NHÂN — NGHĨA (Supervisor Owner)
> **Lab Day 09 — Multi-Agent Orchestration**  
> **Vai trò:** Supervisor Owner → Sprint 1 Lead  
> **Nhánh làm việc:** `feature/supervisor`

---

## 🎯 Bức tranh toàn cảnh của Nghĩa

Nghĩa chịu trách nhiệm chính cho **Sprint 1**: thiết kế và implement `graph.py` — trái tim của toàn hệ thống multi-agent. Đây là module quan trọng nhất vì mọi routing decision đều đi qua đây.

**File chính:** `graph.py`  
**Deliverables:**  
- `AgentState` hoàn chỉnh với tất cả fields  
- `supervisor_node()` với routing logic thực (keyword-based, rõ ràng)  
- `route_decision()` conditional edge function  
- Graph kết nối đúng với LangGraph StateGraph  

---

## 📌 SETUP NHÁNH

```bash
cd "d:\gitHub\AI_20k\Day 8-9-10\Lecture-Day-08-09-10\day09"

# Lấy nhánh từ remote (Trung đã tạo)
git fetch origin
git checkout feature/supervisor

# Hoặc tự tạo nếu chưa có:
git checkout -b feature/supervisor
```

---

## 🔥 SPRINT 1 — Nghĩa làm gì cụ thể?

### Bước S1.1 — Đọc hiểu code skeleton

Đọc kỹ `graph.py` từ đầu đến cuối, đặc biệt:
- `AgentState` TypedDict (line 24-50): đã đủ fields, giữ nguyên
- `supervisor_node()` (line 80-129): phần **TODO** cần implement = routing logic
- `build_graph()` (line 236-277): hiện là Python if/else → chuyển sang LangGraph

### Bước S1.2 — Implement routing logic thực trong `supervisor_node()`

Thay phần `# --- TODO: Implement routing logic ---`:

```python
def supervisor_node(state: AgentState) -> AgentState:
    task = state["task"].lower()
    state["history"].append(f"[supervisor] received task: {state['task'][:80]}")

    # ── Nhóm 1: Policy/Access keywords
    policy_keywords = ["hoàn tiền", "refund", "flash sale", "license", 
                       "cấp quyền", "access", "level 3", "level 2",
                       "quy trình tạm thời", "emergency access", "contractor"]
    
    # ── Nhóm 2: SLA/Ticket keywords  
    sla_keywords = ["p1", "escalation", "sla", "ticket", "2am", "22:47",
                    "phản hồi", "on-call", "pagerduty", "incident"]
    
    # ── Nhóm 3: Risk keywords
    risk_keywords = ["khẩn cấp", "emergency", "err-", "không rõ", "lỗi không xác định"]

    route = "retrieval_worker"
    route_reason = "default → retrieval (no specific keyword matched)"
    needs_tool = False
    risk_high = False

    # Priority 1: Policy/Access → policy_tool_worker
    matched_policy = [kw for kw in policy_keywords if kw in task]
    if matched_policy:
        route = "policy_tool_worker"
        route_reason = f"policy/access keyword detected: {matched_policy[:2]}"
        needs_tool = True

    # Priority 2: SLA/Ticket → retrieval_worker (override nếu chưa set)
    matched_sla = [kw for kw in sla_keywords if kw in task]
    if matched_sla and route == "retrieval_worker":
        route = "retrieval_worker"
        route_reason = f"SLA/ticket keyword detected: {matched_sla[:2]}"

    # Priority 3: Risk flag
    if any(kw in task for kw in risk_keywords):
        risk_high = True
        route_reason += " | risk_high=True"

    # Priority 4: Human review override (ERR- + risk)
    if risk_high and "err-" in task:
        route = "human_review"
        route_reason = f"unknown error code (err-) + risk_high → human review"

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(f"[supervisor] route={route} | reason={route_reason}")

    return state
```

### Bước S1.3 — Chuyển sang LangGraph StateGraph

Sửa `build_graph()` thành LangGraph:

```python
# Uncomment dòng này ở đầu file:
from langgraph.graph import StateGraph, END

def build_graph():
    """Build LangGraph StateGraph với conditional edges."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("retrieval_worker", retrieval_worker_node)
    workflow.add_node("policy_tool_worker", policy_tool_worker_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("synthesis", synthesis_worker_node)

    # Entry point
    workflow.set_entry_point("supervisor")

    # Conditional edge: supervisor → route
    workflow.add_conditional_edges(
        "supervisor",
        route_decision,  # function trả về tên node
        {
            "retrieval_worker": "retrieval_worker",
            "policy_tool_worker": "policy_tool_worker",
            "human_review": "human_review",
        }
    )

    # Fixed edges
    workflow.add_edge("retrieval_worker", "synthesis")
    workflow.add_edge("policy_tool_worker", "retrieval_worker")  # policy cần retrieval context
    workflow.add_edge("human_review", "retrieval_worker")        # sau HITL tiếp tục retrieval
    workflow.add_edge("synthesis", END)

    return workflow.compile()
```

> ⚠️ **Quan trọng:** Khi dùng LangGraph, `run_graph()` phải gọi `_graph.invoke(state)` thay vì `_graph(state)`.

Sửa `run_graph()`:
```python
def run_graph(task: str) -> AgentState:
    state = make_initial_state(task)
    import time
    start = time.time()
    result = _graph.invoke(state)          # LangGraph dùng .invoke()
    result["latency_ms"] = int((time.time() - start) * 1000)
    return result
```

### Bước S1.4 — Test

```bash
# Chạy test
python graph.py
```

Kỳ vọng 3 routes đúng:
- `"SLA xử lý ticket P1 là bao lâu?"` → `retrieval_worker` (SLA keyword)
- `"Khách hàng Flash Sale yêu cầu hoàn tiền..."` → `policy_tool_worker` (flash sale)
- `"Cần cấp quyền Level 3..."` → `policy_tool_worker` (level 3 keyword)

---

## 📦 COMMIT FLOW CỦA NGHĨA

### Commit 1 — Sau khi implement routing logic:
```bash
git add graph.py
git commit -m "feat(supervisor): implement keyword-based routing logic

- supervisor_node: 3 keyword groups (policy, SLA, risk)
- policy keywords: hoàn tiền, refund, flash sale, access, level 2/3, contractor
- SLA keywords: p1, escalation, sla, ticket, on-call
- risk_high flag for ERR- error codes and emergency situations
- human_review override when ERR- + risk_high both present
- route_reason ghi đầy đủ matched keywords cho mỗi decision

Refs: Sprint 1 - Supervisor Owner"
git push origin feature/supervisor
```

### Commit 2 — Sau khi chuyển sang LangGraph:
```bash
git add graph.py
git commit -m "feat(supervisor): migrate to LangGraph StateGraph with conditional edges

- Replace Python if/else orchestrator with StateGraph
- Add nodes: supervisor, retrieval_worker, policy_tool_worker, human_review, synthesis
- Add conditional edges via route_decision() function
- Routing chain: policy_tool → retrieval → synthesis (policy cần context)
- Routing chain: human_review → retrieval → synthesis 
- run_graph() uses .invoke() instead of direct call
- All 3 test queries route correctly with clear route_reason

Tested:
  SLA P1 query → retrieval_worker ✓
  Flash Sale refund → policy_tool_worker ✓  
  Level 3 emergency → policy_tool_worker ✓

Refs: Sprint 1 - Supervisor Owner"
git push origin feature/supervisor
```

---

## 🔄 SAU SPRINT 1 — Vai trò hỗ trợ

Sau Sprint 1, Nghĩa có thể:
- **Hỗ trợ Đạt (Sprint 2):** Review routing từ perspective supervisor khi workers return state
- **Kiểm tra trace:** Đảm bảo `supervisor_route` và `route_reason` trong mỗi trace không phải "unknown"
- **Update routing:** Nếu test thấy câu hỏi không route đúng, chỉnh sửa `supervisor_node()`

---

## 📝 BÁO CÁO CÁ NHÂN — Gợi ý nội dung

File: `reports/individual/NguyenVanNghia.md`

**Phần bạn phụ trách:** `graph.py` — supervisor_node, route_decision, LangGraph StateGraph  
**1 quyết định kỹ thuật:** Dùng keyword matching thay vì LLM classifier → giải thích trade-off (speed vs accuracy, dễ debug)  
**1 lỗi đã sửa:** Lỗi LangGraph `invoke()` vs `__call__()`, hoặc routing edge sai khi policy_tool cần retrieval context  
**Tự đánh giá:** Supervisor là bottleneck — nếu route sai, toàn bộ pipeline sai  
**Nếu có 2h thêm:** Thêm LLM-based routing classifier cho câu hỏi ambiguous (evidence từ trace câu route sai)
