"""
=========================================================
TEST MESSAGE FRAMING cho hệ thống Đấu giá Trực tuyến
Kiểm tra server tách đúng bản tin khi TCP:
  (1) dồn nhiều bản tin vào 1 lần gửi   (sticky packets)
  (2) chia 1 bản tin thành nhiều lần gửi (fragmented packets)
  (3) cắt đôi 1 ký tự UTF-8 nhiều byte   (tên tiếng Việt)
Cách chạy: khởi động server.py MỚI, rồi chạy: python framing_test.py
=========================================================
"""

import socket
import threading
import time

HOST = "localhost"
PORT = 5000


def now():
    return time.strftime("%H:%M:%S")


def reader(sock, name):
    """Luồng nền: in mọi bản tin server gửi về, mỗi dòng một bản tin."""
    buf = b""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                print(f"[{now()}]   <- {name} nhận: {line.decode('utf-8')}")
    except OSError:
        pass


def connect(name):
    s = socket.create_connection((HOST, PORT))
    # Tắt Nagle để mỗi lần send() được gửi đi ngay thành segment riêng
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    threading.Thread(target=reader, args=(s, name), daemon=True).start()
    return s


def send_raw(sock, data, note):
    print(f"[{now()}] -> gửi {len(data):2d} byte {data!r}   ({note})")
    sock.sendall(data)


# ---------- TEST 1: STICKY PACKETS ----------
print("\n===== TEST 1: 2 bản tin trong 1 lần send() =====")
s1 = connect("client_A")
send_raw(s1, b"JOIN|framing_test\nBID|1500000\n", "JOIN + BID dính liền")
time.sleep(1.5)

# ---------- TEST 2: FRAGMENTED PACKETS ----------
print("\n===== TEST 2: 1 bản tin chia làm 3 lần send() =====")
for part in [b"BI", b"D|160", b"0000\n"]:
    send_raw(s1, part, "mảnh của BID|1600000")
    time.sleep(0.5)
time.sleep(1.5)

# ---------- TEST 3: UTF-8 BỊ CẮT GIỮA KÝ TỰ ----------
print("\n===== TEST 3: tên tiếng Việt bị cắt giữa 1 ký tự UTF-8 =====")
msg = "JOIN|Phương\n".encode("utf-8")
cut = msg.index("ư".encode("utf-8")) + 1   # cắt ngay giữa 2 byte của chữ 'ư'
s2 = connect("client_B")
send_raw(s2, msg[:cut], "nửa đầu, dừng giữa chữ 'ư'")
time.sleep(0.5)
send_raw(s2, msg[cut:], "nửa sau")
time.sleep(1.5)

print("\n===== KẾT THÚC TEST — kiểm tra log server =====")
s1.close()
s2.close()
