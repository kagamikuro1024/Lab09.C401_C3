# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** C401-C3  
**Ngày:** 2026-04-14

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | 0.85 (Est) | 0.511 | -0.34 | Multi-agent kiểm soát gắt gao hơn |
| Avg latency (ms) | 3500 (Est) | 7486 | +3986 | Tốn thời gian cho Supervisor/Multi-hop |
| Abstain rate (%) | 10% (Est) | 6.7% | -3.3% | Tìm được nhiều info hơn qua MCP |
| Multi-hop accuracy | Low | High | Positive | MCP Tools giúp xử lý câu hỏi sâu |
| Routing visibility | ✗ Không có | ✓ Có route_reason | N/A | Dễ debug hơn hẳn |
| Debug time (estimate) | 45 phút | 10 phút | -35 | Tiết kiệm thời gian tìm lỗi |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)
| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | 90% | 95% |
| Latency | ~3.5s | ~7.5s |

**Kết luận:** Với câu đơn giản, Multi-agent tốn latency hơn nhưng kết quả tin cậy hơn.

### 2.2 Câu hỏi multi-hop (cross-document)
| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Thấp | Cao |
| Routing visible? | ✗ | ✓ |

**Kết luận:** Multi-agent vượt trội ở khả năng kết chéo thông tin.

### 2.3 Câu hỏi cần abstain
| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | ~10% | ~6% |

**Kết luận:** Synthesis worker phân biệt được cái không biết và cái có thể suy luận qua tool.

---

## 3. Debuggability Analysis

- **Day 08**: Chạy blind, không biết lỗi ở bước nào. Ước tính 45p/bug.
- **Day 09**: Xem trace log → biết ngay lỗi ở Supervisor hay Worker. Ước tính 10p/bug.

---

## 4. Extensibility Analysis

Hệ thống Multi-agent cực kỳ dễ mở rộng. Ví dụ khi cần thêm kĩ năng "Kiểm tra ticket", chỉ cần thêm 1 MCP tool và 1 dòng logic trong Supervisor mà không phải rewrite lại toàn bộ pipeline như Day 08.

---

## 5. Cost & Latency Trade-off

- **Cost**: Tăng ~2-3 lần do gọi nhiều LLM models.
- **Latency**: Tăng ~2 lần.
- **Benefit**: Độ chính xác và khả năng quan sát (observability) là sự đánh đổi xứng đáng.

---

## 6. Kết luận

1. **Ưu điểm**: Khả năng mở rộng, khả năng debug, xử lý multi-hop cực tốt.
2. **Nhược điểm**: Delay cao, tốn token.
3. **Mở rộng**: Tích hợp thêm AI Agents xử lý multimedia như hình ảnh/giọng nói.
