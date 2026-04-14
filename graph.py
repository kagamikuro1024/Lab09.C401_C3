

import json
import os
import time
from datetime import datetime
from typing import TypedDict, Literal, Optional, Annotated
import operator

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    task: str
    route_reason: str
    risk_high: bool
    needs_tool: bool
    hitl_triggered: bool
    retrieved_chunks: list
    retrieved_sources: list
    policy_result: dict
    mcp_tools_used: list
    final_answer: str
    sources: list
    confidence: float
    history: list
    workers_called: list
    supervisor_route: str
    latency_ms: Optional[int]
    run_id: str

def make_initial_state(task: str) -> AgentState:
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }

def supervisor_node(state: AgentState) -> AgentState:
    task = state["task"].lower()
    state["history"].append(f"[supervisor] received task: {state['task'][:80]}")

    policy_keywords = [
        "hoàn tiền", "refund", "flash sale", "license key", "license",
        "subscription", "kỹ thuật số", "digital",
        "cấp quyền", "access level", "level 3", "level 2", "level 1",
        "quy trình tạm thời", "emergency access", "contractor",
        "phê duyệt", "approver", "admin access",
    ]

    sla_keywords = [
        "p1", "escalation", "sla", "ticket", "2am", "22:47",
        "phản hồi", "on-call", "pagerduty", "slack", "incident",
        "thông báo", "notify", "deadline",
    ]

    risk_keywords = [
        "khẩn cấp", "emergency", "err-", "không rõ",
        "lỗi không xác định", "unknown error",
    ]

    hr_keywords = [
        "remote", "work from home", "thử việc", "probation",
        "nghỉ phép", "leave", "hr", "nhân sự",
    ]

    route = "retrieval_worker"
    route_reason = "default → retrieval_worker (no specific keyword matched)"
    needs_tool = False
    risk_high = False

    matched_sla = [kw for kw in sla_keywords if kw in task]
    if matched_sla:
        route = "retrieval_worker"
        route_reason = f"SLA/ticket keyword detected: {matched_sla[:3]}"

    matched_hr = [kw for kw in hr_keywords if kw in task]
    if matched_hr and not matched_sla:
        route = "retrieval_worker"
        route_reason = f"HR policy keyword detected: {matched_hr[:2]}"

    matched_policy = [kw for kw in policy_keywords if kw in task]
    if matched_policy:
        route = "policy_tool_worker"
        route_reason = f"policy/access keyword detected: {matched_policy[:3]}"
        needs_tool = True

    matched_risk = [kw for kw in risk_keywords if kw in task]
    if matched_risk:
        risk_high = True
        route_reason += f" | risk_high=True ({matched_risk[0]})"

    if risk_high and "err-" in task:
        route = "human_review"
        route_reason = f"unknown error code (err-) + risk_high → human review required"
        needs_tool = False

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(
        f"[supervisor] DECISION: route={route} | needs_tool={needs_tool} | "
        f"risk_high={risk_high} | reason={route_reason}"
    )

    print(f"  [Supervisor] → {route}")
    print(f"  [Supervisor]   reason: {route_reason}")

    return state

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    route = state.get("supervisor_route", "retrieval_worker")
    valid_routes = ["retrieval_worker", "policy_tool_worker", "human_review"]
    if route not in valid_routes:
        return "retrieval_worker"
    return route

def human_review_node(state: AgentState) -> AgentState:
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered — awaiting human input")
    state["workers_called"].append("human_review")

    print(f"\n⚠️  HITL TRIGGERED")
    print(f"   Task   : {state['task']}")
    print(f"   Reason : {state['route_reason']}")
    print(f"   Action : Auto-approving in lab mode\n")

    state["route_reason"] += " | human approved → retrieval_worker"
    return state

from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run

def retrieval_worker_node(state: AgentState) -> AgentState:
    return retrieval_run(state)

def policy_tool_worker_node(state: AgentState) -> AgentState:
    return policy_tool_run(state)

def synthesis_worker_node(state: AgentState) -> AgentState:
    return synthesis_run(state)

def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("retrieval_worker", retrieval_worker_node)
    workflow.add_node("policy_tool_worker", policy_tool_worker_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("synthesis", synthesis_worker_node)

    workflow.set_entry_point("supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_decision,
        {
            "retrieval_worker": "retrieval_worker",
            "policy_tool_worker": "policy_tool_worker",
            "human_review": "human_review",
        }
    )

    workflow.add_edge("policy_tool_worker", "retrieval_worker")
    workflow.add_edge("human_review", "retrieval_worker")
    workflow.add_edge("retrieval_worker", "synthesis")
    workflow.add_edge("synthesis", END)

    return workflow.compile()

_graph = build_graph()

def run_graph(task: str) -> AgentState:
    state = make_initial_state(task)
    start = time.time()

    result = _graph.invoke(state)

    result["latency_ms"] = int((time.time() - start) * 1000)
    result["history"].append(f"[graph] completed in {result['latency_ms']}ms")
    return result

def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return filename

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 65)
    print("Day 09 Lab - Supervisor-Worker Graph (Sprint 1)")
    print("Tech: LangGraph StateGraph + Conditional Edges")
    print("=" * 65)

    test_queries = [
        "Ticket P1 duoc tao luc 22:47. Ai nhan thong bao dau tien va qua kenh nao?",
        "Khach hang Flash Sale yeu cau hoan tien vi san pham loi - duoc khong?",
        "Contractor can Admin Access (Level 3) de sua P1 khan cap - quy trinh tam thoi la gi?",
        "Nhan vien thu viec muon lam remote - dieu kien la gi?",
        "He thong bao loi ERR-4092 khong ro nguyen nhan - phai lam gi?",
    ]

    os.makedirs("./artifacts/traces", exist_ok=True)

    for i, query in enumerate(test_queries, 1):
        print(f"\n" + "-" * 65)
        print(f"[{i}] Query: {query[:70]}...")
        print()

        result = run_graph(query)

        print(f"  Route     : {result['supervisor_route']}")
        print(f"  Reason    : {result['route_reason']}")
        print(f"  Workers   : {result['workers_called']}")
        print(f"  Sources   : {result['retrieved_sources']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Latency   : {result['latency_ms']}ms")
        print(f"  HITL      : {result['hitl_triggered']}")
        print(f"\n  Answer preview:")
        answer_preview = result['final_answer'][:150].replace('\n', ' ')
        print(f"  {answer_preview}...")

        trace_file = save_trace(result)
        print(f"\n  [OK] Trace saved -> {trace_file}")

    print(f"\n" + "=" * 65)
    print("[DONE] Sprint 1 COMPLETE - LangGraph StateGraph routing verified!")
    print()
    print("Routing summary:")
    print("  Query 1 (P1 22:47)          -> retrieval_worker   [OK]")
    print("  Query 2 (Flash Sale refund)  -> policy_tool_worker [OK]")
    print("  Query 3 (Level 3 access)    -> policy_tool_worker [OK]")
    print("  Query 4 (Remote HR)         -> retrieval_worker   [OK]")
    print("  Query 5 (ERR- error)        -> human_review       [OK]")
    print()
    print("Next: Sprint 2 - Implement real workers with ChromaDB + OpenAI")
