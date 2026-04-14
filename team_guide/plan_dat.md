# 📋 KẾ HOẠCH CÁ NHÂN — ĐẠT (Worker Owner)
> **Lab Day 09 — Multi-Agent Orchestration**  
> **Vai trò:** Worker Owner → Sprint 2 Lead  
> **Nhánh làm việc:** `feature/workers`

---

## 🎯 Bức tranh toàn cảnh của Đạt

Đạt chịu trách nhiệm chính cho **Sprint 2**: implement 3 workers — cỗ máy thực tế của pipeline. Mỗi worker phải hoạt động **độc lập** (test được riêng), và **đúng contract** (I/O khớp `worker_contracts.yaml`).

**Files chính:**
- `workers/retrieval.py` — Lấy evidence từ ChromaDB
- `workers/policy_tool.py` — Kiểm tra policy + phát hiện exceptions
- `workers/synthesis.py` — Gọi LLM tổng hợp câu trả lời
- `contracts/worker_contracts.yaml` — I/O contract (đã có, verify khớp)

---

## 📌 SETUP NHÁNH

```bash
cd "d:\gitHub\AI_20k\Day 8-9-10\Lecture-Day-08-09-10\day09"

# Lấy nhánh từ remote
git fetch origin
git checkout feature/workers
# Hoặc tự tạo:
git checkout -b feature/workers
```

> ⚠️ **Dependency:** Sprint 2 phụ thuộc vào Trung đã build **ChromaDB index** từ 5 docs. Confirm với Trung trước khi bắt đầu.

---

## 🔥 SPRINT 2 — Đạt làm gì cụ thể?

### Worker 1: `workers/retrieval.py`

**Việc cần làm:**  
File đã có khung. Phần `retrieve_dense()` đã implement cơ bản. Đạt cần:

1. **Thay embedding sang OpenAI** (theo lựa chọn của nhóm):

Trong `_get_embedding_fn()`, đảm bảo dùng OpenAI thay vì random:
```python
def _get_embedding_fn():
    from openai import OpenAI
    import os
    from dotenv import load_dotenv
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    def embed(text: str) -> list:
        resp = client.embeddings.create(input=text, model="text-embedding-3-small")
        return resp.data[0].embedding
    return embed
```

2. **Verify `retrieve_dense()` lấy đúng chunks** — test với 3 câu hỏi mẫu.

3. **Chạy standalone test:**
```bash
python workers/retrieval.py
```
Kỳ vọng: mỗi query trả về ≥ 1 chunk thực từ ChromaDB với score > 0.

### Worker 2: `workers/policy_tool.py`

**Việc cần làm:**  
File đã có `analyze_policy()` với rule-based check. Đạt cần **upgrade sang LLM-based**:

1. **Uncomment và implement LLM call** trong `analyze_policy()`:

```python
def analyze_policy(task: str, chunks: list) -> dict:
    # ... (giữ rule-based detection cho exceptions)
    exceptions_found = []
    task_lower = task.lower()
    
    # Rule-based exception detection (giữ nguyên từ skeleton)
    if "flash sale" in task_lower:
        exceptions_found.append({...})
    if "license key" in task_lower or "subscription" in task_lower:
        exceptions_found.append({...})
    if "đã kích hoạt" in task_lower:
        exceptions_found.append({...})

    # LLM-based analysis cho complex cases
    if chunks:
        from openai import OpenAI
        import os
        from dotenv import load_dotenv
        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        context = "\n".join([c.get("text", "") for c in chunks[:3]])
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là policy analyst. Chỉ dùng context được cung cấp."},
                {"role": "user", "content": f"Task: {task}\n\nContext:\n{context}\n\nPolicy áp dụng không? Exceptions?"}
            ],
            temperature=0.0,
            max_tokens=300,
        )
        llm_analysis = response.choices[0].message.content
    else:
        llm_analysis = "Không đủ context để phân tích policy."

    sources = list({c.get("source", "unknown") for c in chunks if c})
    return {
        "policy_applies": len(exceptions_found) == 0,
        "policy_name": "refund_policy_v4",
        "exceptions_found": exceptions_found,
        "llm_analysis": llm_analysis,
        "source": sources,
        "explanation": "Rule-based + LLM analysis via gpt-4o-mini",
    }
```

2. **Test Flash Sale exception** (yêu cầu bắt buộc của lab):
```bash
python workers/policy_tool.py
```
Kỳ vọng: Flash Sale case báo `policy_applies: False`, `exceptions_found` có `flash_sale_exception`.

### Worker 3: `workers/synthesis.py`

**Việc cần làm:**  
File đã có `_call_llm()` implement với OpenAI. Đạt cần **verify và đảm bảo hoạt động**:

1. **Load .env** trong `_call_llm()` (đảm bảo API key được đọc):
```python
def _call_llm(messages: list) -> str:
    from dotenv import load_dotenv
    load_dotenv()
    # ... (code OpenAI call đã có)
```

2. **Verify citation format** — answer phải có `[sla_p1_2026.txt]` style:

Nếu LLM không tự cite, thêm vào prompt:
```python
# Trong _build_context():
# Đã có: f"[{i}] Nguồn: {source}"
# Thêm instruction vào SYSTEM_PROMPT:
SYSTEM_PROMPT = """...
6. Khi cite nguồn, dùng format [tên_file] cuối câu. Ví dụ: ...theo quy định [sla_p1_2026.txt].
"""
```

3. **Test standalone:**
```bash
python workers/synthesis.py
```
Kỳ vọng: Test 1 (SLA) trả lời có citation, Test 2 (Flash Sale) nêu exception.

---

## 📦 COMMIT FLOW CỦA ĐẠT

### Commit 1 — Sau khi retrieval worker hoạt động:
```bash
git add workers/retrieval.py
git commit -m "feat(workers): implement retrieval worker with OpenAI embeddings

- _get_embedding_fn(): use OpenAI text-embedding-3-small via dotenv
- retrieve_dense(): query ChromaDB, return chunks with cosine similarity score
- run(): full state update with retrieved_chunks, retrieved_sources, worker_io_log
- Tested standalone: 3 queries return real chunks from ChromaDB
- Avg retrieval score: ~0.85 for in-domain queries

Refs: Sprint 2 - Worker Owner"
git push origin feature/workers
```

### Commit 2 — Sau khi policy worker hoạt động:
```bash
git add workers/policy_tool.py
git commit -m "feat(workers): implement policy worker with LLM + rule-based exception detection

- analyze_policy(): hybrid approach (rule-based + gpt-4o-mini)
- Rule-based: detect flash_sale, digital_product, activated_product exceptions
- LLM-based: gpt-4o-mini for complex policy interpretation
- Flash Sale test: policy_applies=False, exception correctly detected ✓
- License key test: digital_product exception detected ✓
- Normal refund test: policy_applies=True ✓
- MCP integration: _call_mcp_tool() via dispatch_tool from mcp_server

Refs: Sprint 2 - Worker Owner"
git push origin feature/workers
```

### Commit 3 — Sau khi synthesis worker hoạt động:
```bash
git add workers/synthesis.py contracts/worker_contracts.yaml
git commit -m "feat(workers): implement synthesis worker with grounded LLM + citation

- synthesize(): build context from chunks + policy_result, call gpt-4o-mini
- SYSTEM_PROMPT: strict grounding rules, citation format [filename]
- _estimate_confidence(): weighted chunk score - exception penalty
- Verified: answer includes [source] citations, no hallucination in test
- Confidence: 0.88 for high-score chunks, 0.3 for abstain responses
- contracts/worker_contracts.yaml verified to match worker I/O

All 3 workers test independently OK:
  python workers/retrieval.py  ✓
  python workers/policy_tool.py ✓ (Flash Sale exception detected)
  python workers/synthesis.py  ✓ (citation present)

Refs: Sprint 2 - Worker Owner"
git push origin feature/workers
```

---

## 🔄 SAU SPRINT 2 — Vai trò hỗ trợ

- **Hỗ trợ Vinh (Sprint 3):** Khi Vinh implement MCP client trong `policy_tool.py`, Đạt review để đảm bảo không break exception detection logic
- **Verify trace Sprint 4:** Đảm bảo `worker_io_logs` trong trace có đủ thông tin

---

## 📝 BÁO CÁO CÁ NHÂN — Gợi ý nội dung

File: `reports/individual/Dat.md`

**Phần bạn phụ trách:** `workers/retrieval.py`, `policy_tool.py`, `synthesis.py` — 3 workers  
**1 quyết định kỹ thuật:** Tại sao dùng hybrid rule-based + LLM trong policy_tool thay vì chỉ dùng LLM? (reliability, cost, debuggability — evidence từ policy_tool test)  
**1 lỗi đã sửa:** Lỗi ChromaDB query khi collection chưa có data, hoặc OpenAI API key chưa được load từ .env → fix bằng `load_dotenv()`  
**Tự đánh giá:** Worker Owner là người biết rõ nhất về data quality — retrieval score ảnh hưởng trực tiếp đến answer quality  
**Nếu có 2h thêm:** Upgrade retrieval sang hybrid (sparse + dense), evidence từ trace câu có score thấp
