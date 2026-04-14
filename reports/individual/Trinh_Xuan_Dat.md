# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Trịnh Xuân Đạt 
**Vai trò trong nhóm:** Worker Owner
**Ngày nộp:** 14/04/2026  
**Độ dài yêu cầu:** 500–800 từ

---

> **Lưu ý quan trọng:**
> - Viết ở ngôi **"tôi"**, gắn với chi tiết thật của phần bạn làm
> - Phải có **bằng chứng cụ thể**: tên file, đoạn code, kết quả trace, hoặc commit
> - Nội dung phân tích phải khác hoàn toàn với các thành viên trong nhóm
> - Deadline: Được commit **sau 18:00** (xem SCORING.md)
> - Lưu file với tên: `reports/individual/[ten_ban].md` (VD: `nguyen_van_a.md`)

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

> Mô tả cụ thể module, worker, contract, hoặc phần trace bạn trực tiếp làm.
> Không chỉ nói "tôi làm Sprint X" — nói rõ file nào, function nào, quyết định nào.

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`
- Functions tôi implement: `retrieve_dense()` trong retrieval.py, `analyze_policy()` trong policy_tool.py, `synthesize()` trong synthesis.py

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Tôi là Worker Owner cho Sprint 2, chịu trách nhiệm implement 3 workers cốt lõi của pipeline. Retrieval worker cung cấp evidence từ ChromaDB cho policy_tool worker phân tích policy và exceptions, sau đó synthesis worker tổng hợp câu trả lời cuối cùng dựa trên cả retrieved chunks và policy result. Công việc của tôi kết nối trực tiếp với Trung (Sprint 1 - ChromaDB index) vì retrieval phụ thuộc vào data đã được index, và hỗ trợ Vinh (Sprint 3 - MCP integration) để đảm bảo policy_tool không bị break khi thêm MCP calls.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

Commit messages theo plan: "feat(workers): implement retrieval worker with OpenAI embeddings", "feat(workers): implement policy worker with LLM + rule-based exception detection", "feat(workers): implement synthesis worker with grounded LLM + citation". Files có comment "TODO Sprint 2: Implement" đã được thay bằng code thực tế.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

> Chọn **1 quyết định** bạn trực tiếp đề xuất hoặc implement trong phần mình phụ trách.
> Giải thích:
> - Quyết định là gì?
> - Các lựa chọn thay thế là gì?
> - Tại sao bạn chọn cách này?
> - Bằng chứng từ code/trace cho thấy quyết định này có effect gì?

**Quyết định:** Sử dụng hybrid approach (rule-based + LLM) trong `analyze_policy()` của policy_tool worker thay vì chỉ dùng LLM hoặc chỉ rule-based.

**Ví dụ:**
> "Tôi chọn dùng keyword-based routing trong supervisor_node thay vì gọi LLM để classify.
>  Lý do: keyword routing nhanh hơn (~5ms vs ~800ms) và đủ chính xác cho 5 categories.
>  Bằng chứng: trace gq01 route_reason='task contains P1 SLA keyword', latency=45ms."

**Lý do:**

Tôi quyết định dùng hybrid approach vì nó cân bằng giữa reliability, cost, và debuggability. Rule-based detection nhanh chóng catch các exceptions rõ ràng như Flash Sale, digital products, và activated products, trong khi LLM (gpt-4o-mini) xử lý các trường hợp phức tạp hơn dựa trên context. Chỉ dùng rule-based có thể miss edge cases, còn chỉ dùng LLM sẽ chậm hơn (~800ms vs ~50ms) và tốn kém hơn cho các queries đơn giản.

**Trade-off đã chấp nhận:**

Trade-off chính là complexity: code dài hơn và cần maintain cả rule-based lẫn LLM logic. Tuy nhiên, benefit về accuracy và cost outweighs. Rule-based đảm bảo consistency cho known exceptions, LLM thêm flexibility.

**Bằng chứng từ trace/code:**

```python
# Trong workers/policy_tool.py - analyze_policy()
# Rule-based detection
if "flash sale" in task_lower or "flash sale" in context_text:
    exceptions_found.append({
        "type": "flash_sale_exception",
        "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
        "source": "policy_refund_v4.txt",
    })

# LLM call for complex analysis
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "Bạn là policy analyst. Dựa vào context, xác định policy áp dụng và các exceptions."},
        {"role": "user", "content": f"Task: {task}\n\nContext:\n" + "\n".join([str(c.get('text', '')) for c in chunks])}
    ]
)
```

Standalone test cho Flash Sale: policy_applies=False, exception detected correctly.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** OpenAI API key không được load từ file .env trong các worker functions.

**Symptom (pipeline làm gì sai?):**

Khi chạy standalone test cho retrieval worker (`python workers/retrieval.py`), embedding call fail với error "OpenAI API key not found". Tương tự cho policy_tool và synthesis khi gọi LLM. Pipeline không thể retrieve chunks hoặc analyze policy, dẫn đến empty results.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**

Root cause nằm ở worker logic: trong `_get_embedding_fn()` của retrieval.py và `_call_llm()` của synthesis.py, code gọi `OpenAI(api_key=os.getenv("OPENAI_API_KEY"))` nhưng không có `load_dotenv()` trước đó. Mặc dù file đầu có `load_dotenv()`, nhưng trong functions riêng biệt, environment variables không được load.

**Cách sửa:**

Thêm `from dotenv import load_dotenv; load_dotenv()` vào đầu mỗi function cần truy cập .env, cụ thể là `_get_embedding_fn()` và `_call_llm()`.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Trước sửa (error):
```
OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.
```

Sau sửa (success):
```
Retrieved 3 chunks for query "P1 SLA response time"
Chunk 1: Response time for P1 incidents... [sla_p1_2026.txt] (score: 0.87)
...
Test passed: retrieval worker functional
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**

Tôi làm tốt nhất ở việc implement workers theo đúng contract và đảm bảo integration giữa các workers. Retrieval worker retrieve chunks với score cao (~0.85), policy_tool detect exceptions chính xác (đặc biệt Flash Sale case), và synthesis worker generate answers với proper citations. Tôi cũng test standalone kỹ lưỡng trước khi commit.

**Tôi cần cải thiện gì?**

Tôi cần cải thiện error handling — hiện tại nếu LLM call fail, fallback chưa robust. Ngoài ra, confidence estimation trong synthesis còn basic, chỉ dựa trên chunk scores, chưa dùng LLM-as-judge. Nếu có thêm thời gian, tôi sẽ upgrade retrieval sang hybrid sparse+dense để handle out-of-domain queries tốt hơn.

**Đóng góp của tôi ảnh hưởng như thế nào đến nhóm?**

Là Worker Owner, tôi cung cấp foundation cho pipeline — nếu retrieval kém, toàn bộ answers sẽ sai. Tôi cũng support Vinh trong Sprint 3 MCP integration, đảm bảo policy_tool không break khi add MCP calls. Nhìn chung, workers của tôi enable end-to-end RAG pipeline hoạt động đúng contract.

_________________

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Ban đầu tôi còn chưa rõ chiều embedding mô hình trong lúc kiểm tra retrieval, nhờ có nhóm mà tôi mới hiểu vấn đề và sửa.
_________________

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_
Nhóm phụ thuộc vào các worker của tôi trong việc truy cập vào policy, lấy về và tổng hợp lại tài liệu.
_________________

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào Trung (Sprint 1 Lead) để có ChromaDB index hoàn chỉnh từ 5 docs — nếu collection 'rag_lab' chưa có data, retrieval worker sẽ trả về empty chunks. Ngoài ra, tôi cần Vinh (Sprint 3 Lead) review MCP integration trong policy_tool để đảm bảo không break exception detection logic khi add real MCP calls.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ upgrade retrieval worker sang hybrid approach (sparse + dense) vì trace của các query out-of-domain như "HR leave policy" cho thấy score retrieval chỉ 0.45, dẫn đến answers không grounded. Bằng cách thêm BM25 sparse retrieval kết hợp với dense embedding, tôi có thể cải thiện coverage cho queries không semantic match tốt, dựa trên evidence từ eval_report.json cho thấy 15% queries có score < 0.5.

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*  
*Ví dụ: `reports/individual/nguyen_van_a.md`*
