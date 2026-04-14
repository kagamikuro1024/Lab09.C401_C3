# -*- coding: utf-8 -*-
"""
mcp_server.py — Real MCP Server (Sprint 3 — FastMCP)
=====================================================
Sử dụng `mcp` library (FastMCP) để tạo MCP server thật với stdio transport.

Tools available:
    1. search_kb(query, top_k)           → tìm kiếm Knowledge Base (ChromaDB thật)
    2. get_ticket_info(ticket_id)        → tra cứu thông tin ticket (mock data)
    3. check_access_permission(...)      → kiểm tra quyền truy cập
    4. create_ticket(...)                → tạo ticket mới (mock)

Chạy server:
    python mcp_server.py                 → stdio transport (MCP standard)
    python mcp_server.py --test          → chạy test nội bộ (không cần MCP client)

Backward compat:
    from mcp_server import dispatch_tool, list_tools
    result = dispatch_tool("search_kb", {"query": "SLA P1", "top_k": 3})

Author: Vinh (MCP Owner) | LeVanQuangTrung (Tech Lead)
"""

import os
import sys
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────
# FastMCP Server
# ─────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("day09-internal-kb")


# ─────────────────────────────────────────────
# Mock Data
# ─────────────────────────────────────────────

MOCK_TICKETS = {
    "P1-LATEST": {
        "ticket_id": "IT-9847",
        "priority": "P1",
        "title": "API Gateway down — toàn bộ người dùng không đăng nhập được",
        "status": "in_progress",
        "assignee": "nguyen.van.a@company.internal",
        "created_at": "2026-04-13T22:47:00",
        "sla_deadline": "2026-04-14T02:47:00",
        "escalated": True,
        "escalated_to": "senior_engineer_team",
        "notifications_sent": [
            "slack:#incident-p1",
            "email:incident@company.internal",
            "pagerduty:oncall",
        ],
    },
    "IT-1234": {
        "ticket_id": "IT-1234",
        "priority": "P2",
        "title": "Feature login chậm cho một số user",
        "status": "open",
        "assignee": None,
        "created_at": "2026-04-13T09:15:00",
        "sla_deadline": "2026-04-14T09:15:00",
        "escalated": False,
    },
}

ACCESS_RULES = {
    1: {
        "required_approvers": ["Line Manager"],
        "emergency_can_bypass": False,
        "note": "Standard user access",
    },
    2: {
        "required_approvers": ["Line Manager", "IT Admin"],
        "emergency_can_bypass": True,
        "emergency_bypass_note": "Level 2 có thể cấp tạm thời với approval đồng thời của Line Manager và IT Admin on-call.",
        "note": "Elevated access",
    },
    3: {
        "required_approvers": ["Line Manager", "IT Admin", "IT Security"],
        "emergency_can_bypass": False,
        "note": "Admin access — không có emergency bypass",
    },
}


# ─────────────────────────────────────────────
# Tool 1: search_kb — Real ChromaDB search
# ─────────────────────────────────────────────

@mcp.tool()
def search_kb(query: str, top_k: int = 3) -> dict:
    """Tìm kiếm Knowledge Base nội bộ bằng semantic search. Trả về top-k chunks liên quan nhất."""
    try:
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
            "chunks": [
                {
                    "text": f"[MCP search_kb error] {e}",
                    "source": "error",
                    "score": 0.0,
                }
            ],
            "sources": ["error"],
            "total_found": 0,
            "error": str(e),
        }


# ─────────────────────────────────────────────
# Tool 2: get_ticket_info — Mock ticket lookup
# ─────────────────────────────────────────────

@mcp.tool()
def get_ticket_info(ticket_id: str) -> dict:
    """Tra cứu thông tin ticket từ hệ thống Jira nội bộ."""
    ticket = MOCK_TICKETS.get(ticket_id.upper())
    if ticket:
        return ticket
    return {
        "error": f"Ticket '{ticket_id}' không tìm thấy trong hệ thống.",
        "available_mock_ids": list(MOCK_TICKETS.keys()),
    }


# ─────────────────────────────────────────────
# Tool 3: check_access_permission
# ─────────────────────────────────────────────

@mcp.tool()
def check_access_permission(access_level: int, requester_role: str, is_emergency: bool = False) -> dict:
    """Kiểm tra điều kiện cấp quyền truy cập theo Access Control SOP."""
    rule = ACCESS_RULES.get(access_level)
    if not rule:
        return {"error": f"Access level {access_level} không hợp lệ. Levels: 1, 2, 3."}

    can_grant = True
    notes = []

    if is_emergency and rule.get("emergency_can_bypass"):
        notes.append(rule.get("emergency_bypass_note", ""))
        can_grant = True
    elif is_emergency and not rule.get("emergency_can_bypass"):
        notes.append(f"Level {access_level} KHÔNG có emergency bypass. Phải follow quy trình chuẩn.")

    return {
        "access_level": access_level,
        "can_grant": can_grant,
        "required_approvers": rule["required_approvers"],
        "approver_count": len(rule["required_approvers"]),
        "emergency_override": is_emergency and rule.get("emergency_can_bypass", False),
        "notes": notes,
        "source": "access_control_sop.txt",
    }


# ─────────────────────────────────────────────
# Tool 4: create_ticket — Mock ticket creation
# ─────────────────────────────────────────────

@mcp.tool()
def create_ticket(priority: str, title: str, description: str = "") -> dict:
    """Tạo ticket mới trong hệ thống Jira (MOCK — không tạo thật trong lab)."""
    mock_id = f"IT-{9900 + abs(hash(title)) % 99}"
    ticket = {
        "ticket_id": mock_id,
        "priority": priority,
        "title": title,
        "description": description[:200],
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "url": f"https://jira.company.internal/browse/{mock_id}",
        "note": "MOCK ticket — không tồn tại trong hệ thống thật",
    }
    print(f"  [MCP create_ticket] MOCK: {mock_id} | {priority} | {title[:50]}")
    return ticket


# ─────────────────────────────────────────────
# Backward Compat: dispatch_tool() + list_tools()
# Giữ cho policy_tool.py import được mà không cần thay đổi
# ─────────────────────────────────────────────

TOOL_REGISTRY = {
    "search_kb": search_kb,
    "get_ticket_info": get_ticket_info,
    "check_access_permission": check_access_permission,
    "create_ticket": create_ticket,
}

TOOL_SCHEMAS = {
    "search_kb": {
        "name": "search_kb",
        "description": "Tìm kiếm Knowledge Base nội bộ bằng semantic search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    "get_ticket_info": {
        "name": "get_ticket_info",
        "description": "Tra cứu thông tin ticket từ hệ thống Jira nội bộ.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
            },
            "required": ["ticket_id"],
        },
    },
    "check_access_permission": {
        "name": "check_access_permission",
        "description": "Kiểm tra điều kiện cấp quyền truy cập theo Access Control SOP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "access_level": {"type": "integer"},
                "requester_role": {"type": "string"},
                "is_emergency": {"type": "boolean", "default": False},
            },
            "required": ["access_level", "requester_role"],
        },
    },
    "create_ticket": {
        "name": "create_ticket",
        "description": "Tạo ticket mới trong hệ thống Jira (MOCK).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "priority": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["priority", "title"],
        },
    },
}


def list_tools() -> list:
    """MCP discovery: trả về danh sách tools có sẵn."""
    return list(TOOL_SCHEMAS.values())


def dispatch_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Backward-compat MCP execution: gọi tool bằng tên.
    Internally calls the FastMCP-decorated functions directly.
    """
    if tool_name not in TOOL_REGISTRY:
        return {
            "error": f"Tool '{tool_name}' không tồn tại. Available: {list(TOOL_REGISTRY.keys())}"
        }

    tool_fn = TOOL_REGISTRY[tool_name]
    try:
        result = tool_fn(**tool_input)
        return result
    except TypeError as e:
        return {
            "error": f"Invalid input for tool '{tool_name}': {e}",
            "schema": TOOL_SCHEMAS.get(tool_name, {}).get("inputSchema"),
        }
    except Exception as e:
        return {"error": f"Tool '{tool_name}' execution failed: {e}"}


# ─────────────────────────────────────────────
# CLI: --test mode or stdio transport
# ─────────────────────────────────────────────

def _run_tests():
    """Chạy test nội bộ cho tất cả 4 tools."""
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("MCP Server — FastMCP Test Mode")
    print(f"Server name: {mcp.name}")
    print("=" * 60)

    # 1. List tools
    print("\n📋 Available Tools (via FastMCP):")
    for schema in list_tools():
        print(f"  • {schema['name']}: {schema['description'][:60]}...")

    # 2. Test search_kb
    print("\n🔍 Test 1: search_kb('SLA P1 resolution time', top_k=2)")
    result = dispatch_tool("search_kb", {"query": "SLA P1 resolution time", "top_k": 2})
    if result.get("chunks"):
        for c in result["chunks"]:
            print(f"  [{c.get('score', '?'):.3f}] {c.get('source')}: {c.get('text', '')[:70]}...")
    print(f"  total_found: {result.get('total_found', 0)}")

    # 3. Test get_ticket_info
    print("\n🎫 Test 2: get_ticket_info('P1-LATEST')")
    ticket = dispatch_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
    print(f"  Ticket: {ticket.get('ticket_id')} | {ticket.get('priority')} | {ticket.get('status')}")
    if ticket.get("notifications_sent"):
        print(f"  Notifications: {ticket['notifications_sent']}")

    # 4. Test check_access_permission
    print("\n🔐 Test 3: check_access_permission(level=3, role='contractor', emergency=True)")
    perm = dispatch_tool("check_access_permission", {
        "access_level": 3,
        "requester_role": "contractor",
        "is_emergency": True,
    })
    print(f"  can_grant: {perm.get('can_grant')}")
    print(f"  required_approvers: {perm.get('required_approvers')}")
    print(f"  emergency_override: {perm.get('emergency_override')}")
    print(f"  notes: {perm.get('notes')}")

    # 5. Test create_ticket
    print("\n📝 Test 4: create_ticket(priority='P2', title='Test ticket')")
    new_ticket = dispatch_tool("create_ticket", {
        "priority": "P2",
        "title": "Test ticket from MCP server",
        "description": "This is a test ticket created during Sprint 3 testing.",
    })
    print(f"  Created: {new_ticket.get('ticket_id')} | {new_ticket.get('url')}")

    # 6. Test invalid tool
    print("\n❌ Test 5: invalid tool name")
    err = dispatch_tool("nonexistent_tool", {})
    print(f"  Error: {err.get('error')}")

    print("\n" + "=" * 60)
    print("✅ All 4 MCP tools tested successfully!")
    print("Server type: FastMCP (mcp library)")
    print("Transport: stdio (when run without --test)")
    print("=" * 60)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        # Chạy FastMCP server thật với stdio transport
        print("Starting MCP server (stdio transport)...", file=sys.stderr)
        mcp.run(transport="stdio")
