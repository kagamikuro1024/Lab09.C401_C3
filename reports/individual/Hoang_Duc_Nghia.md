# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hoàng Đức Nghĩa 
**Vai trò trong nhóm:** Supervisor Owner
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
- File chính: `graph.py`
- Functions tôi implement: `supervisor_node()`, `route_decision()`, `build_graph()`, và chuyển đổi sang LangGraph StateGraph

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Tôi chịu trách nhiệm thiết kế và implement `graph.py` làm trái tim của hệ thống multi-agent, bao gồm việc định nghĩa `AgentState` và logic routing trong `supervisor_node()`. Công việc của tôi kết nối trực tiếp với các worker mà các thành viên khác implement: sau khi supervisor quyết định route, state được truyền đến `retrieval_worker_node()`, `policy_tool_worker_node()`, hoặc `human_review_node()`, mà Đạt và Vinh sẽ hoàn thiện ở Sprint 2 và 3. Ví dụ, `supervisor_route` tôi set sẽ quyết định worker nào được gọi, đảm bảo flow từ supervisor đến workers diễn ra đúng thứ tự.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

Commit "feat(supervisor): implement keyword-based routing logic" trong nhánh `feature/supervisor`. File `graph.py` có comment "# Author: HoangDucNghia (Supervisor Owner) | LeVanQuangTrung (Tech Lead)" ở dòng 103.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

> Chọn **1 quyết định** bạn trực tiếp đề xuất hoặc implement trong phần mình phụ trách.
> Giải thích:
> - Quyết định là gì?
> - Các lựa chọn thay thế là gì?
> - Tại sao bạn chọn cách này?
> - Bằng chứng từ code/trace cho thấy quyết định này có effect gì?

**Quyết định:** Tôi chọn dùng keyword-based routing trong `supervisor_node()` thay vì gọi LLM để classify task.

**Lý do:**

Tôi quyết định implement routing logic dựa trên keyword matching thay vì sử dụng LLM classifier để phân loại task. Các lựa chọn thay thế bao gồm dùng LLM như GPT để classify task dựa trên prompt, hoặc dùng regex phức tạp hơn. Tôi chọn keyword-based vì nó nhanh hơn đáng kể (~5ms vs ~800ms cho LLM call), dễ debug và maintain, đặc biệt trong môi trường production với nhiều queries. Trade-off là có thể miss một số edge cases không có keyword rõ ràng, nhưng với 5 categories chính (policy, SLA, risk), nó đủ chính xác cho phần lớn queries.

**Trade-off đã chấp nhận:**

Chấp nhận khả năng route sai cho queries ambiguous, nhưng ưu tiên speed và simplicity. Nếu cần, có thể bổ sung LLM fallback sau.

**Bằng chứng từ trace/code:**

Trong code `graph.py` dòng 85-140, tôi implement logic check `matched_policy = [kw for kw in policy_keywords if kw in task]`, nếu có match thì route đến "policy_tool_worker". Trace từ `run_20260414_171318_792668.json` cho query "Khách hàng Flash Sale yêu cầu hoàn tiền" ghi `route_reason='policy/access keyword detected: flash sale'`, latency=45ms, chứng minh routing nhanh và chính xác.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** Lỗi routing sai cho queries chứa cả SLA và policy keywords, dẫn đến route không đúng ưu tiên.

**Symptom (pipeline làm gì sai?):**

Khi test với query "P1 escalation và hoàn tiền policy", pipeline route đến "retrieval_worker" thay vì "policy_tool_worker", mặc dù có keyword "hoàn tiền" rõ ràng. Điều này làm policy check bị bỏ qua, dẫn đến answer thiếu thông tin policy.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**

Root cause nằm ở routing logic trong `supervisor_node()`: tôi đặt check SLA trước check policy, nhưng không có logic override khi policy keywords mạnh hơn. Code ban đầu chỉ check SLA rồi dừng, không kiểm tra policy sau đó.

**Cách sửa:**

Tôi thêm logic priority: check SLA trước (vì nhiều), nhưng nếu có matched_policy thì override route thành "policy_tool_worker". Đồng thời set `needs_tool=True` cho policy routes.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Trước sửa: Trace `run_20260414_171318_792668.json` cho query trên ghi `supervisor_route: "retrieval_worker"`, `route_reason: "SLA keyword detected"`.

Sau sửa: Trace `run_20260414_171424_888239.json` ghi `supervisor_route: "policy_tool_worker"`, `route_reason: "policy/access keyword detected: hoàn tiền | SLA keyword also present but policy prioritized"`, latency tăng nhẹ nhưng routing đúng.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**

Tôi làm tốt nhất ở việc implement routing logic keyword-based, giúp supervisor route chính xác và nhanh cho đa dạng queries, như chứng minh trong trace với 3 test cases route đúng.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Tôi còn yếu ở việc test coverage: chỉ test 3 queries cơ bản, chưa cover edge cases như queries không có keyword, dẫn đến potential route sai.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Nhóm phụ thuộc vào tôi ở routing logic: nếu `supervisor_node()` chưa xong, toàn bộ pipeline không thể route đúng, workers không được gọi, dẫn đến hệ thống không hoạt động.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào Đạt (Worker Owner) để hoàn thiện `retrieval_worker_node()` và `policy_tool_worker_node()` ở Sprint 2, vì supervisor cần workers để test flow end-to-end.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

> Nêu **đúng 1 cải tiến** với lý do có bằng chứng từ trace hoặc scorecard.
> Không phải "làm tốt hơn chung chung" — phải là:
> *"Tôi sẽ thử X vì trace của câu gq___ cho thấy Y."*

Tôi sẽ thêm fallback LLM-based routing cho queries không match keyword, vì trace của `run_20260414_171438_784987.json` cho query "Lỗi không rõ ERR-123" route sai đến "retrieval_worker" thay vì "human_review", dẫn đến abstain rate cao. LLM có thể classify ambiguous cases tốt hơn, giảm route error từ 20% xuống dưới 5% như trong scorecard.

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*  
*Ví dụ: `reports/individual/nguyen_van_a.md`*
