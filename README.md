# GROUP 5, TOPIC 8 - LIVE ONLINE AUCTION BIDDING SYSTEM

Project bài tập giữa kỳ môn **Công nghệ Mạng và Truyền thông** 

Giảng viên: TS. Trần Đức Minh

 **GitHub:** [https://github.com/ngocmaihoccode/Live-Online-Auction-Bidding-System](https://github.com/ngocmaihoccode/Live-Online-Auction-Bidding-System)

Hệ thống mô phỏng phiên đấu giá trực tuyến theo kiến trúc **Một Server – Nhiều Client** giao tiếp qua giao thức **TCP**.

## Yêu cầu môi trường

- **Python 3.10** trở lên
- Hệ điều hành: Windows, macOS, hoặc Linux (đã test trên Ubuntu 22.04)
- Không cần cài thư viện ngoài (chỉ dùng module chuẩn: `socket`, `threading`, `time`)
- Download và tải các file client.py, server.py, stress_test.py (nếu muốn test các hidden cases) vào folder
- Upload folder lên VSCode (hoặc phần mềm code bạn đang sử dụng)

## Cách chạy hệ thống

### 1. Chạy Server máy chủ

Mở terminal tích hợp bên trong VSCode (hoặc phần mềm code bạn đang sử dụng) và chạy lệnh sau:

```bash
python server.py
```

Server sẽ lắng nghe tại `0.0.0.0:5000`. Bạn sẽ thấy:

```
============================================================
  SERVER ĐẤU GIÁ TRỰC TUYẾN - Live Auction Server
============================================================
  Món đồ:        MacBook Pro M4
  Giá khởi điểm: 1000000
  Countdown:     15 giây
  Địa chỉ:       0.0.0.0:5000
============================================================
[SERVER] Đang lắng nghe tại 0.0.0.0:5000...
```

### 2. Chạy Server Client

Trong VSCode (hoặc phần mềm code khác), mở thêm **1 terminal mới** (giữ nguyên terminal server) và chạy:

```bash
python client.py
```

Sau đó nhập tên và bắt đầu đấu giá. Bạn có thể mở **nhiều terminal client** cùng lúc để mô phỏng nhiều người đấu giá.

### 3. Chạy Stress Test (tùy chọn — để test race condition)

Tiếp tục mở một tab terminal mới khác và chạy:

```bash
python stress_test.py
```

Script sẽ tạo 30 bot tự động, mỗi bot gửi 100 bid ngẫu nhiên gần như đồng thời (đồng bộ bằng `threading.Barrier` để tất cả bot bắt đầu cùng lúc), sau đó kiểm chứng mutex có hoạt động đúng không.

## Chạy qua Internet (thay vì localhost)

Nếu bạn muốn cho phép client từ máy tính khác kết nối vào server của mình:

**Cách 1: Kết nối trong cùng mạng LAN**
- Bật terminal trong VSCode và chạy server bình thường (`python server.py`).
- Ở phía Client: Mở file `client.py`, tìm dòng `SERVER_HOST = 'localhost'` và đổi thành **IP LAN** của máy đang chạy server (ví dụ: `SERVER_HOST = '192.168.1.100'`).

**Cách 2: Qua Internet công cộng bằng ngrok**
- Cài đặt [ngrok](https://ngrok.com/download).
- Bật terminal trong VSCode và chạy server: `python server.py`
- Mở **thêm 1 tab terminal mới** trong VSCode và chạy lệnh sau để port-forwarding: 
  ```bash
  ngrok tcp 5000
  
## Cấu trúc dự án

```
├── server.py             # Máy chủ đấu giá trung tâm (Centralized Auctioneer) - Quản lý kết nối, đếm ngược và đồng bộ Lock
├── client.py             # Giao diện người tham gia (Bidder) - Xử lý đa luồng I/O mạng và giao diện Console
├── stress_test.py        # Kịch bản kiểm thử chịu tải & Race Condition (Mô phỏng 30 bots đồng bộ qua threading.Barrier)
└── framing_test.py       # Kịch bản kiểm thử cơ chế Framing (Gửi TCP thô để mô phỏng lỗi dính và phân mảnh gói tin)
└── README.md             # Tổng quan dự án, hướng dẫn sử dụng hệ thống mô phỏng đấu giá trực tuyến, cấu trúc mã nguồn
└── report/               # Báo cáo LaTeX tổng kết dự án
```

## Trọng tâm kỹ thuật (Key Focus)

Theo yêu cầu của đề bài, hệ thống tập trung vào:

1. **Quản lý biến dùng chung** — `highest_bid`, `highest_bidder` được bảo vệ bằng `threading.Lock`
2. **Đồng bộ hóa đa luồng** — pattern check-then-act trong critical section
3. **Countdown timer** — reset khi có bid mới, xử lý race condition giữa timer và bid

## Tính năng đã cài đặt

**Đã hoàn thiện:**
- Đồng bộ hóa đa luồng (Thread-safe): Sử dụng `threading.Lock` (`price_lock`, `room_lock`)
để bảo vệ vùng găng (Critical Section) cho các biến dùng chung (`highest_bid`, danh sách `clients`), ngăn ngừa triệt để Race Condition.
- Cơ chế Đếm ngược (Smart Auto-reset Timer): Đồng hồ 15s tự động đếm ngược. Hệ thống chỉ kích hoạt Timer khi có client đầu tiên JOIN (tránh phiên tự sập khi chưa có người chơi). Đặc biệt, Timer sẽ ngay lập tức reset về 15s mỗi khi có lệnh BID hợp lệ.
- Xác thực Giá thầu (Bid Validation): Hệ thống chặn đứng các số tiền không hợp lệ (nhỏ hơn 0) và tự động từ chối (báo `ERROR`) các mức giá thấp hơn hoặc bằng giá hiện hành.
- Hệ thống Logging Chuyên sâu: Ghi log chi tiết ra Console và file server.log (chuẩn format `[HH:MM:SS] [LEVEL]`). Trace được toàn bộ quá trình Acquire/Release Lock, quá trình Reset Timer theo từng giây, và ghi nhận rõ ràng các lệnh từ chối (`WARNING`) hay lỗi (`ERROR`).
- Shutdown An toàn & Giải phóng Cổng (Graceful Shutdown): Bắt tín hiệu ngắt `SIGINT/SIGTERM`, đóng toàn bộ kết nối Client êm ái và giải phóng Port 5000 ngay lập tức (loại bỏ hoàn toàn lỗi kẹt port `TIME_WAIT`).
- Tính Chịu lỗi (Fault Tolerance): Khối `finally` xử lý ngắt kết nối an toàn. Server không bị crash (`[Errno 9]`) khi một Client bất kỳ rút cáp/tắt app đột ngột.

**Hạn chế** (nằm ngoài phạm vi của dự án, có thể học tập bổ sung sau):
- Chức năng giới hạn tần suất (Rate limiting) để chống Spam tin nhắn từ một Client.

## Các kịch bản đã kiểm tra thử

| # | Kịch bản kiểm tra thử | Mục tiêu | Cách test |
|---|---|---|---|
| 1 | Xác thực Giá thầu (Bid Validation) | Đảm bảo Server chặn các mức giá không thoả mãn điều kiện và chỉ ghi nhận giá cao nhất| 2 Client liên tiếp nhập giá thấp hơn, giá bằng và cuối cùng là giá cao hơn giá sàn|
| 2 | Cơ chế Reset Timer | Đảm bảo quá trình đếm ngược bị ngắt quãng và đếm lại 15s ngay khi có giá hợp lệ mới | Chờ Server đếm lùi xuống ở những giây cuối cùng, Client B bắn lệnh BID giá cao hơn. Theo dõi Log đếm ngược trên Server|
| 3 | Kiểm tra Chịu tải (Stress Test & Race Condition) | Chứng minh Mutex Lock hoạt động hoàn hảo trước hàng ngàn luồng truy cập đồng thời | Chạy script `stress_test.py` giả lập 30 Bot, bắn đồng loạt 3.000 requests vào Server bằng cơ chế `threading.Barrier`|
| 4 | Tính Chịu lỗi (Client Disconnect) | Server phải tiếp tục phiên đấu giá tiếp khi có Client disconnected| Đang trong lúc đếm ngược 15s, nhấn Ctrl+C để giả sử rằng Clinet A disconnected. Theo dõi phản ứng tiếp tục của Server|

## Kịch bản test đã pass

Toàn bộ 4 kịch bản đã được chạy thực tế và PASS 100%, bằng chứng lưu trong thư mục `videotestcases/`:

- [x] **Test case 1 - Xác thực giá thầu:** Server bắt lỗi và từ chối ngay lập tức các mức giá thấp hơn/bằng giá khởi điểm, trả về cảnh báo ❌ Lỗi: Giá quá thấp. Mức giá hợp lệ được chấp nhận và kích hoạt chu trình cập nhật. 
- [x] **Test Case 2 — Reset Đồng hồ:** Server log ghi nhận rõ ràng tiến trình đếm ngược đang ở mức 4 giây..., khi có lệnh BID hợp lệ, hệ thống nhảy vọt về thông báo ⏰ [TIMER] Timer đã được RESET về 15s và bắt đầu đếm lại từ 15 giây.... Không xảy ra hiện tượng chồng chéo luồng thời gian.
- [x] **Test Case 3 — Stress Test & Lock Synchronization:** Script tự động đánh giá và trả về ✅ PASS. Dữ liệu hiển thị rõ: Tổng số 3000 bids đã gửi. Mức giá cao nhất mà Server ghi nhận KHỚP TUYỆT ĐỐI với mức giá cao nhất thực tế do hệ thống Bot sinh ra. Không xuất hiện Race Condition.
- [x] **Test Case 4 — Client Disconnect (Fault Tolerance):** Tại những giây gần cuối của chu kỳ đếm ngược, một Client bị ngắt kết nối. Log Server báo khóa room_lock, dọn dẹp Client lỗi khỏi phòng và tiếp tục đếm lùi 8 giây... 7... 6... Phiên đấu giá kết thúc thành công cho các Client còn lại, Server dọn dẹp an toàn không văng lỗi `[Errno 9]`.

## Phân công thành viên

**Nhóm 5:** 

| Thành viên | MSSV | Phụ trách |
|---|---|---|
| Phạm Ngọc Mai | 11255166 | Xây dựng Server (`server.py`) & Test Cases 1,3 (`stress_test.py`) |
| Nguyễn Hà Phương | 11256961 | Xây dựng Client (`client.py`) & Test Cases 2,4|
| Nguyễn Ngọc Anh | 11250640 | Check Test Cases, Báo cáo LaTeX (`report/`) |

## License

Dự án học tập — không dùng cho mục đích thương mại.
