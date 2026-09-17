# GROUP 5, TOPIC 8 - LIVE ONLINE AUCTION BIDDING SYSTEM

[![GitHub](https://img.shields.io/badge/GitHub-Live--Online--Auction-blue)](https://github.com/ngocmaihoccode/Live-Online-Auction-Bidding-System)

Project bài tập giữa kỳ môn **Công nghệ Mạng và Truyền thông** 

Giảng viên: TS. Trần Đức Minh

 **GitHub:** [https://github.com/ngocmaihoccode/Live-Online-Auction-Bidding-System](https://github.com/ngocmaihoccode/Live-Online-Auction-Bidding-System)

Hệ thống mô phỏng phiên đấu giá trực tuyến theo kiến trúc **Một Server – Nhiều Client** giao tiếp qua giao thức **TCP**.

## Yêu cầu môi trường

- **Python 3.10** trở lên
- Hệ điều hành: Windows, macOS, hoặc Linux (đã test trên Ubuntu 22.04)
- Không cần cài thư viện ngoài (chỉ dùng module chuẩn: `socket`, `threading`, `time`)

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
.
├── server.py               # Máy chủ đấu giá (Thành viên 1)
├── server_no_lock.py       # Bản demo CỐ TÌNH BỎ LOCK - chỉ để chứng minh race condition, KHÔNG dùng để nộp bài
├── client.py               # Giao diện người đấu giá (Thành viên 2)
├── stress_test.py          # Test tự động chống race condition (đồng bộ bằng threading.Barrier)
├── PROTOCOL.md             # Đặc tả giao thức bản tin
├── README.md               # File này
├── report_snippets.md      # Code snippet trích sẵn cho báo cáo LaTeX (Thành viên 3)
├── server.log              # Log runtime (tự sinh khi chạy server.py, đã .gitignore)
├── screenshots/            # Toàn bộ bằng chứng test: ảnh chụp 6 kịch bản KB1-KB6,
│                           # kết quả stress test có/không lock, log so sánh, ảnh race_condition_comparison.png
└── report/                 # Báo cáo LaTeX (Thành viên 3)
```

## Trọng tâm kỹ thuật (Key Focus)

Theo yêu cầu của đề bài, hệ thống tập trung vào:

1. **Quản lý biến dùng chung** — `highest_bid`, `highest_bidder` được bảo vệ bằng `threading.Lock`
2. **Đồng bộ hóa đa luồng** — pattern check-then-act trong critical section
3. **Countdown timer** — reset khi có bid mới, xử lý race condition giữa timer và bid

Xem file `PROTOCOL.md` để biết chi tiết giao thức bản tin.

## Tính năng đã cài đặt

**Đã có:**
- Đồng bộ hóa đa luồng bằng `threading.Lock` (`price_lock`, `room_lock`) cho toàn bộ biến dùng chung
- Countdown timer 15s, reset khi có bid mới, chỉ bắt đầu khi có client đầu tiên JOIN (tránh phiên tự kết thúc lúc chưa ai tham gia)
- Validate bid: chặn số tiền không hợp lệ và số tiền ≤ 0
- Logging chi tiết ra console **và** file `server.log` (format `[YYYY-MM-DD HH:MM:SS] [LEVEL] Nội dung`), có log acquire/release lock, timer reset, bid bị từ chối (WARNING), exception (ERROR)
- Shutdown sạch: bắt tín hiệu SIGINT/SIGTERM, đóng hết client, giải phóng port ngay lập tức (không bị kẹt TIME_WAIT)
- Xử lý disconnect an toàn trong `finally` — server không crash khi 1 client mất kết nối đột ngột
- `server_no_lock.py` — bản demo cố tình bỏ lock để chứng minh race condition, phục vụ báo cáo (Task 3.1)

**Hạn chế** (nằm ngoài phạm vi đã làm tới của nhóm, có thể học tập bổ sung sau):
- Broadcast countdown timer real-time tới client (`TIMER|<giây>`)
- Broadcast + đếm số client đang online khi có người rời phòng
- Rate limiting chống spam bid

## Các kịch bản đã kiểm tra thử

| # | Kịch bản | Cách test |
|---|---|---|
| 1 | Kết nối và bid hợp lệ | Chạy 2 client, bid tăng dần |
| 2 | Từ chối bid thấp | Bid với giá ≤ giá hiện tại |
| 3 | Race condition | Chạy `stress_test.py` |
| 4 | Timer reset | Bid, chờ 10s, bid tiếp — kiểm tra timer về 15s |
| 5 | Chốt phiên khi hết giờ | Bid, chờ đủ 15s không bid tiếp |
| 6 | Client disconnect | Ctrl+C 1 client — server vẫn chạy |

## Kịch bản test đã pass

Toàn bộ 6 kịch bản đã chạy thực tế và PASS (Task 3.2), bằng chứng lưu trong `screenshots/`:

- [x] **KB1 — Bid hợp lệ:** 2 client bid tăng dần, cả 2 nhận đúng UPDATE, winner đúng người bid cao nhất → `screenshots/kb1_valid_bid.png`
- [x] **KB2 — Từ chối bid thấp:** bid thấp hơn/bằng giá hiện tại bị từ chối với WARNING, không ảnh hưởng client khác → `screenshots/kb2_reject_low_bid.png`
- [x] **KB3 — Race condition (có lock, `server.py`):** stress test 30 bot × 100 bid không phát hiện race condition → `screenshots/result_with_lock.txt`, `screenshots/log_test_with_lock.txt`
- [x] **KB4 — So sánh không lock (`server_no_lock.py`):** cùng stress test lộ rõ race condition (winner khác so với KB3: bot_27 vs bot_9) → `screenshots/result_no_lock.txt`, `screenshots/log_test_no_lock.txt`, `screenshots/race_condition_comparison.png`, `screenshots/diff_evidence.txt`
- [x] **KB5 — Timer reset:** chứng minh bằng timestamp server log (reset lúc 13:40:32 / 13:40:41 / 13:40:50, WIN xuất hiện đúng 15s sau lần reset cuối lúc 13:41:05) → `screenshots/kb5_timer_reset.png`
- [x] **KB6 — Client disconnect:** Ctrl+C 1 client giữa phiên, server không crash, 2 client còn lại vẫn bid/nhận UPDATE bình thường → `screenshots/kb6_client_disconnect.png`

## Phân công thành viên

**Nhóm 5:** 

| Thành viên | MSSV | Phụ trách |
|---|---|---|
| Ngọc Mai | 11255166 | Server & Đồng bộ hóa (`server.py`, `server_no_lock.py`, `stress_test.py`) |
| Hà Phương | 11256961 | Client & Giao diện (`client.py`) |
| Ngọc Anh | 11250640 | Báo cáo LaTeX (`report/`, `report_snippets.md`) |

## License

Dự án học tập — không dùng cho mục đích thương mại.
