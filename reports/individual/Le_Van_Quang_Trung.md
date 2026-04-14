# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Lê Văn Quang Trung  
**Vai trò trong nhóm:** Supervisor Owner / Orchestrator Lead / MCP Provider  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Trong dự án lab Day 09, tôi đảm nhận vai trò **Tech Lead** và **Orchestrator Owner**. Nhiệm vụ chính của tôi là thiết kế và triển khai kiến trúc điều phối Agent theo mô hình **Supervisor-Worker** bằng LangGraph.

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py` (Supervisor điều hướng), `mcp_server.py` (Triển khai MCP server chuyên dụng), và `workers/policy_tool.py` (Worker phân tích chính sách).
- Functions tôi implement: `supervisor_node` (logic định tuyến), `run_graph` (quản lý trạng thái AgentState), và các `@mcp.tool()` định nghĩa trong MCP server.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Công việc của tôi là "xương sống" kết nối các module lại với nhau. Tôi thiết kế `AgentState` để làm hợp đồng dữ liệu giữa các worker. Khi các thành viên khác hoàn thiện `retrieval_worker` hoặc `synthesis_worker`, hệ thống của tôi sẽ tự động gọi chúng dựa trên quyết định của Supervisor. Tôi cũng cung cấp các công cụ tra cứu thông qua MCP server để hỗ trợ cho việc phân tích chính sách phức tạp.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Sử dụng **Hybrid Routing Logic** (kết hợp Keyword matching và LLM Classification) cho Supervisor.

Thay vì gọi LLM để phân loại 100% mọi câu hỏi đầu vào, tôi đã đề xuất và triển khai một lớp tiền xử lý dựa trên từ khóa và biểu thức chính quy (Regex). 

**Lý do:**
1. **Tối ưu Latency:** Các câu hỏi đơn giản về SLA (pattern: "SLA", "P1") hoặc tra cứu Ticket (pattern: "ticket", "INC-") có thể được định tuyến ngay lập tức tới `retrieval_worker` trong < 10ms. 
2. **Tiết kiệm chi phí:** Giảm được khoảng 40-50% số lượng token gọi tới LLM cho nhiệm vụ phân loại (classification).
3. **Độ tin cậy:** Keyword matching cho kết quả chính xác tuyệt đối với các tên quy trình nội bộ cố định, tránh việc LLM "sáng tạo" quá mức dẫn đến việc route sai.

**Trade-off đã chấp nhận:**
Hệ thống phức tạp hơn một chút ở phần code supervisor và cần bảo trì danh sách từ khóa khi có quy trình mới. Tuy nhiên, lợi ích về tốc độ phản hồi cho người dùng là vượt trội.

**Bằng chứng từ trace/code:**
Trong trace `run_20260414_160319.json`, câu hỏi "SLA xử lý ticket P1 là bao lâu?" được route ngay lập tức:
```json
"supervisor_route": "retrieval_worker",
"route_reason": "SLA/ticket keyword detected: ['p1', 'sla', 'ticket']",
"latency_ms": 6847
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** **Collection Name Mismatch** dẫn đến việc Retrieval không tìm thấy dữ liệu.

**Symptom:**
Khi chạy Sprint 2, hệ thống luôn trả về câu trả lời "Không tìm thấy thông tin" (Abstain) mặc dù các file dữ liệu đã được nạp và build index thành công.

**Root cause:**
Sau khi debug trace và kiểm tra `chroma_db`, tôi phát hiện `build_index.py` tạo collection với tên `rag_lab`, trong khi file `workers/retrieval.py` cũ đang hard-code tìm kiếm trên collection `day09_docs`. Do tên không khớp, ChromaDB khởi tạo một collection trống mới và trả về kết quả rỗng (empty result).

**Cách sửa:**
Tôi đã chỉnh sửa `workers/retrieval.py` để đồng bộ hóa tên collection:
```python
# Before
collection = client.get_or_create_collection(name="day09_docs")

# After
collection = client.get_or_create_collection(name="rag_lab")
```

**Bằng chứng trước/sau:**
- **Trước khi sửa:** Trace log ghi nhận `retrieved_chunks` là mảng rỗng `[]`, confidence của synthesis là 0.1.
- **Sau khi sửa:** Trace log ghi nhận 5 chunks từ file `sla-p1-2026.pdf`, confidence tăng lên 0.58.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
Tôi làm tốt nhất ở việc thiết kế cấu trúc hệ thống (architecture) và triển khai MCP server. MCP server của tôi hoạt động ổn định và cung cấp 4 tool đầy đủ cho việc truy vấn hạ tầng nội bộ.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Tôi cảm thấy latency của hệ thống vẫn còn hơi cao khi xử lý các câu hỏi "multi-hop" cần gọi tuần tự nhiều worker.

**Nhóm phụ thuộc vào tôi ở đâu?**
Nếu file `graph.py` của tôi không hoạt động, toàn bộ pipeline sẽ bị block vì đây là nơi khởi tạo và vận hành luồng LangGraph.

**Phần tôi phụ thuộc vào thành viên khác:**
Tôi phụ thuộc vào Synthesis Owner để đảm bảo kết quả cuối cùng được diễn đạt trôi chảy và có trích dẫn đúng định dạng yêu cầu của lab.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Nếu có thêm 2 giờ, tôi sẽ triển khai cơ chế **Parallel Node Execution** trong LangGraph. Dựa trên trace của câu Q15 (cần cả SLA và Access Control context), hiện tại hệ thống gọi tuần tự tốn ~18s. Nếu chạy song song Retrieval Worker và Policy Tool Worker, tôi tin rằng có thể giảm latency xuống còn ~10-12s, cải thiện đáng kể trải nghiệm người dùng.

---
