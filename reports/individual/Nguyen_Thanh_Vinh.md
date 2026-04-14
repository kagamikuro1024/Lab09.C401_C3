# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Thành Vinh 
**Vai trò trong nhóm:** MCP Owner
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

> Tôi phụ trách Sprint 3 - implement MCP server.

**Module/file tôi chịu trách nhiệm:**
- File chính: `mcp_server.py`
- Functions tôi implement: `search_kb(), get_ticket_info(), check_access_permission(), create_ticket()`

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Thêm MPC gọi tool cho `workers/policy_tool.py` của Đạt

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

```
PS D:\RobotvaAI\VinUni-AI20K\Day8-9-10\Lab09.C401_C3> git add mcp_server.py
PS D:\RobotvaAI\VinUni-AI20K\Day8-9-10\Lab09.C401_C3> git commit -m "feat(mcp): implement real MCP server using FastMCP library"
[feature/mcp c813593] feat(mcp): implement real MCP server using FastMCP library
 1 file changed, 57 insertions(+), 130 deletions(-)

PS D:\RobotvaAI\VinUni-AI20K\Day8-9-10\Lab09.C401_C3> git add workers/policy_tool.py
PS D:\RobotvaAI\VinUni-AI20K\Day8-9-10\Lab09.C401_C3> git commit -m "feat(mcp): integrate MCP tool calls in policy_tool worker"
[feature/mcp dfd6b1b] feat(mcp): integrate MCP tool calls in policy_tool worker
 1 file changed, 31 insertions(+), 1 deletion(-)
```

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** chọn FastMCP với stdio transport thay vì HTTP

**Lý do:** đơn giản hơn, không cần mở port, phù hợp in-process lab

**Trade-off đã chấp nhận:** không scalable qua network

**Bằng chứng từ trace/code:**

```
if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        # Chạy FastMCP server thật với stdio transport
        print("Starting MCP server (stdio transport)...", file=sys.stderr)
        mcp.run(transport="stdio")
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** Không hiện tool mà MCP call

**Symptom (pipeline làm gì sai?):**

Khi chạy test case trong `workers/policy_tool.py`, kết quả luôn chả về không có MCP call trong khi đã cho phép dùng MCP.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**

Trong hàm `run()` chạy test case, `needs_tool` luôn để mặc định là list rỗng nếu không khai báo trong các test case.

**Cách sửa:**

Khai báo thêm `"needs_tool": True` trong các test case.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Trước:
```
 ▶ Task: Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?...
  policy_applies: False
  exception: flash_sale_exception — Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách...
  MCP calls: 0

▶ Task: Khách hàng muốn hoàn tiền license key đã kích hoạt....
  policy_applies: False
  exception: digital_product_exception — Sản phẩm kỹ thuật số (license key, subscription) không được ...
  exception: activated_exception — Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn...
  MCP calls: 0

▶ Task: Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạ...
  policy_applies: True
  MCP calls: 0
```

Sau:
```
▶ Task: Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?...
  policy_applies: False
  exception: flash_sale_exception — Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách...
  MCP calls: 1

▶ Task: Khách hàng muốn hoàn tiền license key đã kích hoạt....
  policy_applies: False
  exception: digital_product_exception — Sản phẩm kỹ thuật số (license key, subscription) không được ...
  exception: activated_exception — Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn...
  MCP calls: 1

▶ Task: Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạ...
  policy_applies: True
  MCP calls: 1
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**

_________________

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

_________________

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Gọi MCP Server khi không có chunks nào được tìm thấy.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Không có

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)
Implement HTTP transport cho MCP server để test với external MCP client. Khác với giao thức STDIO (vốn bị giới hạn trong môi trường local), HTTP cho phép client và server giao tiếp qua mạng một cách độc lập. Điều này giúp bạn dễ dàng sử dụng các công cụ phổ biến như Postman, Insomnia hoặc các trình duyệt để gửi request và kiểm tra phản hồi trực tiếp mà không cần khởi động lại toàn bộ hệ thống.<br>
Bằng chứng: `latency` trong `traces/sprint3` luôn cao.

_________________

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*  
*Ví dụ: `reports/individual/nguyen_van_a.md`*
