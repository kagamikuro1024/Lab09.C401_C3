# 📋 KẾ HOẠCH CÁ NHÂN — VINH (MCP Owner)
> **Lab Day 09 — Multi-Agent Orchestration**  
> **Vai trò:** MCP Owner → Sprint 3 Lead  
> **Nhánh làm việc:** `feature/mcp`

---

## 🎯 Bức tranh toàn cảnh của Vinh

Vinh chịu trách nhiệm chính cho **Sprint 3**: chuyển `mcp_server.py` từ mock class sang **MCP server thật** dùng `mcp` Python library (bonus +2 điểm). Đây là phần **advanced** nhóm chọn, và cũng là điểm phân biệt với nhóm chỉ làm mock.

**Files chính:**
- `mcp_server.py` — MCP server thật (FastMCP)
- `workers/policy_tool.py` — MCP client integration (coordinate với Đạt)

**Điểm bonus:** +2 điểm cho MCP server thật (không phải mock class)

---

## 📌 SETUP NHÁNH

```bash
cd "d:\gitHub\AI_20k\Day 8-9-10\Lecture-Day-08-09-10\day09"

# Lấy nhánh từ remote
git fetch origin
git checkout feature/mcp
# Hoặc tự tạo:
git checkout -b feature/mcp

# Cài thêm mcp library
pip install mcp
# Hoặc:
pip install "mcp[cli]"
```

> ⚠️ **Dependency:** Sprint 3 cần Sprint 2 đã xong (workers hoạt động, ChromaDB có data).  
> Vinh bắt đầu sau khi Đạt commit `workers/retrieval.py` hoạt động.

---

## 🔥 SPRINT 3 — Vinh làm gì cụ thể?

### Bước V3.1 — Nghiên cứu FastMCP

FastMCP là high-level wrapper của `mcp` library, rất đơn giản:
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server-name")

@mcp.tool()
def my_tool(param: str) -> dict:
    """Tool description."""
    return {"result": param}

# Chạy:
mcp.run(transport="stdio")
```

### Bước V3.2 — Rewrite `mcp_server.py` thành FastMCP

Giữ lại **toàn bộ logic** (MOCK_TICKETS, ACCESS_RULES, TOOL_SCHEMAS), chỉ thay **dispatch layer** thành `@mcp.tool()` decorator:

```python
"""
mcp_server.py — Real MCP Server using FastMCP
Sprint 3: Implement real MCP server với 4 tools.
"""

import os
import json
from datetime import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP

# ── Server instance
mcp = FastMCP("day09-internal-kb")

# ── Mock data (giữ nguyên từ skeleton)
MOCK_TICKETS = { ... }  # giữ nguyên
ACCESS_RULES = { ... }  # giữ nguyên

# ── Tool 1: search_kb
@mcp.tool()
def search_kb(query: str, top_k: int = 3) -> dict:
    """Tìm kiếm Knowledge Base nội bộ bằng semantic search. Trả về top-k chunks liên quan nhất."""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from workers.retrieval import retrieve_dense
        chunks = retrieve_dense(query, top_k=top_k)
        sources = list({c["source"] for c in chunks})
        return {
            "chunks": chunks,
            "sources": sources,
            "total_found": len(chunks),
        }
    except Exception as e:
        return {
            "chunks": [{"text": f"[ERROR] {e}", "source": "error", "score": 0}],
            "sources": [],
            "total_found": 0,
            "error": str(e),
        }

# ── Tool 2: get_ticket_info
@mcp.tool()
def get_ticket_info(ticket_id: str) -> dict:
    """Tra cứu thông tin ticket từ hệ thống Jira nội bộ."""
    ticket = MOCK_TICKETS.get(ticket_id.upper())
    if ticket:
        return ticket
    return {
        "error": f"Ticket '{ticket_id}' không tìm thấy.",
        "available_mock_ids": list(MOCK_TICKETS.keys()),
    }

# ── Tool 3: check_access_permission
@mcp.tool()
def check_access_permission(access_level: int, requester_role: str, is_emergency: bool = False) -> dict:
    """Kiểm tra điều kiện cấp quyền truy cập theo Access Control SOP."""
    rule = ACCESS_RULES.get(access_level)
    if not rule:
        return {"error": f"Access level {access_level} không hợp lệ."}
    
    notes = []
    if is_emergency and rule.get("emergency_can_bypass"):
        notes.append(rule.get("emergency_bypass_note", ""))
    elif is_emergency:
        notes.append(f"Level {access_level} KHÔNG có emergency bypass.")
    
    return {
        "access_level": access_level,
        "can_grant": True,
        "required_approvers": rule["required_approvers"],
        "approver_count": len(rule["required_approvers"]),
        "emergency_override": is_emergency and rule.get("emergency_can_bypass", False),
        "notes": notes,
        "source": "access_control_sop.txt",
    }

# ── Tool 4: create_ticket
@mcp.tool()
def create_ticket(priority: str, title: str, description: str = "") -> dict:
    """Tạo ticket mới (MOCK — không tạo thật trong lab)."""
    mock_id = f"IT-{9900 + hash(title) % 99}"
    return {
        "ticket_id": mock_id,
        "priority": priority,
        "title": title,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "url": f"https://jira.company.internal/browse/{mock_id}",
        "note": "MOCK ticket",
    }

# ── Backward compat: giữ dispatch_tool() và list_tools() cho policy_tool.py
def list_tools() -> list:
    """Backward compat: trả về tool schemas."""
    return [{"name": "search_kb"}, {"name": "get_ticket_info"},
            {"name": "check_access_permission"}, {"name": "create_ticket"}]

def dispatch_tool(tool_name: str, tool_input: dict) -> dict:
    """Backward compat: policy_tool.py vẫn dùng dispatch_tool."""
    tools = {
        "search_kb": search_kb,
        "get_ticket_info": get_ticket_info,
        "check_access_permission": check_access_permission,
        "create_ticket": create_ticket,
    }
    if tool_name not in tools:
        return {"error": f"Tool '{tool_name}' không tồn tại."}
    try:
        return tools[tool_name](**tool_input)
    except Exception as e:
        return {"error": str(e)}

# ── Entry point (MCP stdio transport)
if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        # Test mode: chạy trực tiếp không qua MCP protocol
        print("=== MCP Server Test ===")
        print(dispatch_tool("search_kb", {"query": "SLA P1", "top_k": 2}))
        print(dispatch_tool("get_ticket_info", {"ticket_id": "P1-LATEST"}))
        print(dispatch_tool("check_access_permission", {"access_level": 3, "requester_role": "contractor", "is_emergency": True}))
    else:
        # Real MCP server mode
        mcp.run(transport="stdio")
```

### Bước V3.3 — Verify `policy_tool.py` gọi MCP đúng

File `workers/policy_tool.py` đã có `_call_mcp_tool()` dùng `dispatch_tool`. Vinh cần:
1. Verify khi `needs_tool=True` và `not chunks` → MCP `search_kb` được gọi
2. Thêm `check_access_permission` call trong policy_tool khi task có "level":

```python
# Thêm vào run() trong policy_tool.py, sau Step 2:
# Step 3.5: Check access permission nếu cần
if needs_tool and any(kw in task.lower() for kw in ["level 2", "level 3", "level 1", "access level"]):
    import re
    level_match = re.search(r"level\s*(\d)", task.lower())
    if level_match:
        level = int(level_match.group(1))
        mcp_result = _call_mcp_tool("check_access_permission", {
            "access_level": level,
            "requester_role": "contractor",
            "is_emergency": "khẩn cấp" in task.lower() or "emergency" in task.lower()
        })
        state["mcp_tools_used"].append(mcp_result)
        state["history"].append(f"[{WORKER_NAME}] called MCP check_access_permission(level={level})")
```

### Bước V3.4 — Test

```bash
# Test MCP server standalone
python mcp_server.py --test

# Test policy worker với MCP calls
python workers/policy_tool.py
# Kỳ vọng: khi no chunks + needs_tool=True → MCP search_kb được gọi

# Test end-to-end
python graph.py
# Kỳ vọng: trace có mcp_tools_used không rỗng cho policy queries
```

---

## 📦 COMMIT FLOW CỦA VINH

### Commit 1 — MCP server thật:
```bash
git add mcp_server.py requirements.txt
git commit -m "feat(mcp): implement real MCP server using FastMCP library (bonus +2)

- Convert mcp_server.py to FastMCP with stdio transport
- 4 tools exposed via @mcp.tool() decorator:
  * search_kb: connects to real ChromaDB via retrieval worker
  * get_ticket_info: mock ticket database (P1-LATEST, IT-1234)
  * check_access_permission: Access Control SOP rules (level 1/2/3)
  * create_ticket: mock ticket creation with ID generation
- Backward compat: dispatch_tool() + list_tools() kept for policy_tool.py
- Test mode: python mcp_server.py --test (bypasses stdio transport)
- MCP server tested: all 4 tools return correct output

pip install: mcp[cli] added to requirements.txt

Refs: Sprint 3 - MCP Owner"
git push origin feature/mcp
```

### Commit 2 — MCP integration trong policy_tool:
```bash
git add workers/policy_tool.py
git commit -m "feat(mcp): integrate MCP tool calls in policy_tool worker

- _call_mcp_tool(): logs tool_name, input, output, timestamp to mcp_tools_used
- Step 1: call MCP search_kb when no chunks and needs_tool=True
- Step 3: call MCP get_ticket_info for ticket/P1 queries
- Step 3.5: call MCP check_access_permission for access level queries
- Trace records mcp_tool_called + mcp_result for each invocation
- supervisor_node route_reason: 'needs_tool=True → MCP enabled' when policy route

Verified: trace shows mcp_tools_used non-empty for policy queries

Refs: Sprint 3 - MCP Owner"
git push origin feature/mcp
```

---

## 🔄 SAU SPRINT 3 — Vai trò hỗ trợ

- **Hỗ trợ Minh (Sprint 4):** Cung cấp thông tin về `mcp_tools_used` format để Minh điền vào docs
- **Verify trace:** Xem trace có `mcp_tool_called` không rỗng cho câu hỏi policy

---

## 📝 BÁO CÁO CÁ NHÂN — Gợi ý nội dung

File: `reports/individual/Vinh.md`

**Phần bạn phụ trách:** `mcp_server.py` — FastMCP server + MCP integration trong `policy_tool.py`  
**1 quyết định kỹ thuật:** Tại sao chọn FastMCP với stdio transport thay vì HTTP? (đơn giản hơn, không cần mở port, phù hợp in-process lab) — trade-off: không scalable qua network  
**1 lỗi đã sửa:** Lỗi import circular khi `mcp_server.py` import từ `workers/retrieval.py` và ngược lại; hoặc lỗi FastMCP không nhận dict output → cần return plain dict  
**Tự đánh giá:** MCP Owner là bridge giữa core pipeline và external capabilities  
**Nếu có 2h thêm:** Implement HTTP transport cho MCP server để test với external MCP client (evidence từ trace: latency MCP call vs direct call)
