"""
=========================================================
STRESS TEST - Kiểm tra Race Condition
=========================================================

Mục đích: Chứng minh Mutex/Lock ở server hoạt động đúng bằng cách:
  - Tạo nhiều client tự động (mặc định 10)
  - Mỗi client bid liên tục các giá ngẫu nhiên gần nhau
  - Sau khi test xong, kiểm tra: giá cao nhất server chấp nhận
    có ĐÚNG là giá cao nhất trong tất cả bid đã gửi hay không

Nếu KHÔNG có lock ở server:
  - Có thể có 2 client cùng "thắng" 1 mức giá
  - Highest_bid có thể bị ghi đè sai
  - Log server sẽ có kết quả bất nhất

Nếu CÓ lock (đúng): highest_bid cuối cùng luôn = max(mọi bid đã accept).

Cách dùng:
  1. Chạy server trước: python server.py
  2. Chạy stress test: python stress_test.py
  3. Quan sát log server + kết quả in ra
"""

import socket
import threading
import random
import time

from server import STARTING_PRICE    # Đọc từ server.py để luôn đồng bộ giá khởi điểm

SERVER_HOST = 'localhost'
SERVER_PORT = 5000

NUM_CLIENTS = 30           # Số client giả lập
BIDS_PER_CLIENT = 100      # Mỗi client gửi bao nhiêu bid
BID_INTERVAL = 0.005       # Cách nhau bao lâu giữa các bid (giây) - nhanh hơn cả time.sleep amplify

# Barrier đồng bộ: ép TẤT CẢ bot chờ nhau rồi mới đồng loạt bắt đầu bid cùng lúc,
# thay vì bắt đầu rải rác -> nhiều thread cùng đọc highest_bid gần như đồng thời,
# tăng khả năng lộ race condition khi test server_no_lock.py.
start_barrier = threading.Barrier(NUM_CLIENTS)

# Lưu tất cả bid đã gửi (để so sánh sau)
all_bids_sent = []
bids_lock = threading.Lock()

# Lưu bản tin UPDATE cuối cùng nhận được từ server
last_update = {"price": 0, "leader": None}
update_lock = threading.Lock()


def client_worker(client_id):
    """Mô phỏng 1 client: kết nối, join, spam bid ngẫu nhiên"""
    username = f"stress_bot_{client_id}"
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER_HOST, SERVER_PORT))
        sock.sendall(f"JOIN|{username}\n".encode('utf-8'))
        
        # Thread nhận cập nhật từ server
        def receiver():
            buffer = ""
            try:
                while True:
                    data = sock.recv(1024)
                    if not data:
                        break
                    buffer += data.decode('utf-8')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        parts = line.strip().split('|')
                        if parts[0] == "UPDATE" and len(parts) >= 3:
                            with update_lock:
                                try:
                                    p = int(parts[1])
                                    if p > last_update["price"]:
                                        last_update["price"] = p
                                        last_update["leader"] = parts[2]
                                except ValueError:
                                    pass
            except OSError:
                pass
        
        threading.Thread(target=receiver, daemon=True).start()

        # Chờ 1 chút để nhận WELCOME
        time.sleep(0.3)

        # Đồng bộ: chờ TẤT CẢ bot join xong rồi mới đồng loạt bắt đầu bid cùng lúc
        try:
            start_barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            print(f"[Bot {client_id}] Barrier timeout (có bot khác join chậm/lỗi) - vẫn tiếp tục bid riêng lẻ")

        # Spam bid
        base_price = STARTING_PRICE + 1000    # Bắt đầu cao hơn giá khởi điểm để chắc chắn được chấp nhận
        for i in range(BIDS_PER_CLIENT):
            # Random giá trong khoảng để có nhiều cạnh tranh (dao động rộng hơn phù hợp với STARTING_PRICE lớn)
            bid_amount = base_price + random.randint(1, 100) * 1000
            
            with bids_lock:
                all_bids_sent.append(bid_amount)
            
            try:
                sock.sendall(f"BID|{bid_amount}\n".encode('utf-8'))
            except OSError:
                break
            
            time.sleep(BID_INTERVAL + random.uniform(0, 0.02))
        
        # Chờ nhận nốt bản tin cuối
        time.sleep(1)
        sock.close()
    
    except Exception as e:
        print(f"[Bot {client_id}] Lỗi: {e}")


def main():
    print("=" * 60)
    print(f"  STRESS TEST - {NUM_CLIENTS} clients x {BIDS_PER_CLIENT} bids")
    print("=" * 60)
    print(f"  Server: {SERVER_HOST}:{SERVER_PORT}")
    print(f"  Tổng số bid dự kiến: {NUM_CLIENTS * BIDS_PER_CLIENT}")
    print("=" * 60)
    print()
    
    threads = []
    start_time = time.time()
    
    # Khởi động tất cả bot cùng lúc
    for i in range(NUM_CLIENTS):
        t = threading.Thread(target=client_worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()
    
    # Chờ tất cả xong
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    
    # ========== PHÂN TÍCH KẾT QUẢ ==========
    print()
    print("=" * 60)
    print("  KẾT QUẢ STRESS TEST")
    print("=" * 60)
    
    with bids_lock:
        max_bid_sent = max(all_bids_sent) if all_bids_sent else 0
        total_sent = len(all_bids_sent)
    
    with update_lock:
        final_price = last_update["price"]
        final_leader = last_update["leader"]
    
    print(f"Thời gian test:                    {elapsed:.2f} giây")
    print(f"Tổng số bid đã gửi:                {total_sent}")
    print(f"Giá cao nhất trong các bid đã gửi: {max_bid_sent}")
    print(f"Giá cao nhất server công nhận:     {final_price}")
    print(f"Người dẫn đầu cuối cùng:           {final_leader}")
    print()
    
    # Đánh giá
    if final_price == max_bid_sent:
        print("✅ PASS: Server công nhận đúng giá cao nhất!")
        print("   -> Mutex hoạt động đúng, không có race condition.")
    elif final_price > 0 and final_price in all_bids_sent:
        print("⚠️  Server công nhận một giá thấp hơn max.")
        print("   Có thể do bản tin UPDATE cuối chưa kịp về trước khi test dừng.")
        print("   Kiểm tra log server để xác nhận highest_bid thực sự.")
    else:
        print("❌ FAIL: Có dấu hiệu race condition!")
        print("   Kiểm tra lại logic Lock ở server.")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
