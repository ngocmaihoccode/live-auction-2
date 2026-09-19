"""
=========================================================
SERVER cho hệ thống Đấu giá Trực tuyến (Live Auction)
Môn: Công nghệ Mạng và Truyền thông
Bài tập: Exercise 08 - Live Online Auction Bidding System
=========================================================

"""

import socket
import threading
import time
import sys
import signal
import logging
import codecs

# ========== CẤU HÌNH ==========
HOST = '0.0.0.0'         # Lắng nghe từ mọi network interface
PORT = 5000              # Port TCP của server
COUNTDOWN_SECONDS = 15   # Thời gian đếm ngược
ITEM_NAME = "MacBook Pro M4"    # Món đồ đấu giá
STARTING_PRICE = 1000000    # Giá khởi điểm 

# ========== CẤU HÌNH LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server.log", mode="a", encoding="utf-8"),
    ],
)

# ========== BIẾN TOÀN CỤC ==========
highest_bid = STARTING_PRICE     # Giá cao nhất hiện tại
highest_bidder = None            # Tên người đang dẫn đầu
auction_active = True            # Cờ: phiên đấu giá còn diễn ra hay không
auction_started = False          # Cờ: countdown đã bắt đầu chưa

clients = {}                     # Dict {socket: username}
timer_version = 0                # Kỹ thuật đánh dấu phiên bản timer để reset an toàn

# ========== CÁC LOCK ĐỂ ĐỒNG BỘ HÓA ==========
price_lock = threading.Lock()
room_lock = threading.Lock()


# ========== HÀM GỬI BẢN TIN ==========
def send_message(sock, message):
    try:
        sock.sendall((message + '\n').encode('utf-8'))
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False

def send_to_all(message, exclude=None):
    disconnected = []
    logging.info("🔒 [LOCK] Acquire room_lock (send_to_all)")
    with room_lock:
        for sock, username in clients.items():
            if sock == exclude:
                continue
            if not send_message(sock, message):
                disconnected.append(sock)

        for sock in disconnected:
            username = clients.pop(sock, "unknown")
            logging.warning(f"[SERVER] Client '{username}' đã ngắt kết nối trong lúc broadcast")
            try:
                sock.close()
            except OSError:
                pass
    logging.info("🔓 [LOCK] Release room_lock (send_to_all)")


# ========== LOGIC ĐẾM NGƯỢC (COUNTDOWN TIMER) ==========
def countdown_display(version, seconds_left):
    """
    Luồng phụ chạy ngầm in thời gian đếm ngược ra màn hình.
    Chỉ tiếp tục đếm nếu phiên bản timer hiện tại trùng khớp (chưa bị reset).
    """
    global timer_version, auction_active
    
    while auction_active and timer_version == version and seconds_left > 0:
        logging.info(f"[COUNTDOWN] Thời gian còn lại: {seconds_left} giây...")
        time.sleep(1)
        seconds_left -= 1
        
    # Nếu đếm về 0 và timer này vẫn là bản mới nhất -> chốt đơn
    if auction_active and timer_version == version and seconds_left == 0:
        end_auction()

def end_auction():
    global auction_active

    logging.info("🔒 [LOCK] Acquire price_lock (end_auction)")
    with price_lock:
        if not auction_active:
            logging.info("🔓 [LOCK] Release price_lock (end_auction) - phiên đã kết thúc")
            return

        auction_active = False
        winner = highest_bidder
        final_price = highest_bid
    logging.info("🔓 [LOCK] Release price_lock (end_auction)")

    if winner:
        send_to_all(f"WIN|{winner}|{final_price}")
        logging.info(f"[SERVER] 🏆 PHIÊN ĐẤU GIÁ KẾT THÚC")
        logging.info(f"[SERVER] 🏆 Người thắng: {winner} với giá {final_price}")
    else:
        send_to_all(f"WIN|none|0")
        logging.info(f"[SERVER] Phiên kết thúc không có người đấu giá.")

def reset_timer():
    """
    Reset countdown timer về 15 giây. PHẢI được gọi TRONG price_lock.
    Tạo một timer_version mới để các luồng đếm ngược cũ tự động hủy bỏ.
    """
    global timer_version
    timer_version += 1  # Đánh dấu phiên bản mới, giết chết luồng cũ
    
    logging.info(f"⏰ [TIMER] Timer đã được RESET về {COUNTDOWN_SECONDS}s")
    
    # Khởi động luồng in thời gian mới
    t = threading.Thread(
        target=countdown_display, 
        args=(timer_version, COUNTDOWN_SECONDS), 
        daemon=True
    )
    t.start()


# ========== XỬ LÝ TỪNG CLIENT ==========
def handle_client(client_socket, client_address):
    global highest_bid, highest_bidder, auction_started

    username = None
    buffer = ""
    decoder = codecs.getincrementaldecoder('utf-8')()

    logging.info(f"[SERVER] Client mới kết nối từ {client_address}")
    
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            
            buffer += decoder.decode(data)
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('|')
                command = parts[0]
                
                # ---------- Xử lý JOIN ----------
                if command == "JOIN" and len(parts) >= 2:
                    if username is not None:
                        send_message(client_socket, "ERROR|Bạn đã JOIN rồi")
                        continue

                    new_username = parts[1].strip()
                    if not new_username:
                        send_message(client_socket, "ERROR|Tên không được để trống")
                        continue

                    logging.info("🔒 [LOCK] Acquire price_lock (JOIN - check active)")
                    with price_lock:
                        session_ended = not auction_active
                    logging.info("🔓 [LOCK] Release price_lock (JOIN)")
                    if session_ended:
                        send_message(client_socket, "ERROR|Phiên đấu giá đã kết thúc")
                        continue

                    logging.info("🔒 [LOCK] Acquire room_lock (JOIN)")
                    with room_lock:
                        duplicate_name = new_username in clients.values()
                        if not duplicate_name:
                            clients[client_socket] = new_username
                    logging.info("🔓 [LOCK] Release room_lock (JOIN)")

                    if duplicate_name:
                        send_message(client_socket, f"ERROR|Tên '{new_username}' đã tồn tại")
                        continue

                    username = new_username
                    send_message(client_socket, f"WELCOME|{ITEM_NAME}|{STARTING_PRICE}")
                    send_to_all(f"INFO|{username} đã tham gia phòng", exclude=client_socket)

                    logging.info("🔒 [LOCK] Acquire price_lock (JOIN init timer)")
                    with price_lock:
                        current_price = highest_bid
                        current_leader = highest_bidder if highest_bidder else "chưa có ai"
                        if not auction_started:
                            auction_started = True
                            logging.info(f"[SERVER] ⏰ Client đầu tiên đã JOIN. Bắt đầu countdown!")
                            reset_timer()
                    logging.info("🔓 [LOCK] Release price_lock (JOIN init timer)")
                    
                    send_message(client_socket, f"UPDATE|{current_price}|{current_leader}")
                    logging.info(f"[SERVER] '{username}' đã tham gia. Tổng số: {len(clients)}")
                
                # ---------- Xử lý BID ----------
                elif command == "BID" and len(parts) >= 2:
                    if username is None:
                        send_message(client_socket, "ERROR|Bạn phải JOIN trước")
                        continue
                    
                    try:
                        amount = int(parts[1])
                    except ValueError:
                        send_message(client_socket, "ERROR|Số tiền không hợp lệ")
                        continue

                    if amount <= 0:
                        send_message(client_socket, "ERROR|Số tiền phải là số dương")
                        continue

                    accepted = False
                    reason = ""

                    logging.info("🔒 [LOCK] Acquire price_lock (BID)")
                    with price_lock:
                        if not auction_active:
                            reason = "Phiên đấu giá đã kết thúc"
                        elif amount > highest_bid:
                            highest_bid = amount
                            highest_bidder = username
                            accepted = True
                            reset_timer()  # Gọi reset timer NGAY TRONG lock
                        else:
                            reason = f"Giá quá thấp (hiện tại: {highest_bid})"
                    logging.info("🔓 [LOCK] Release price_lock (BID)")

                    if accepted:
                        logging.info(f"[SERVER] ✅ Chấp nhận BID {amount} từ '{username}'")
                        send_to_all(f"UPDATE|{amount}|{username}")
                    else:
                        logging.warning(f"[SERVER] ❌ Từ chối BID {amount} từ '{username}': {reason}")
                        send_message(client_socket, f"ERROR|{reason}")

                else:
                    send_message(client_socket, f"ERROR|Cú pháp không hợp lệ")

    except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
        logging.error(f"[SERVER] Client '{username or client_address}' mất kết nối")
    except UnicodeDecodeError as e:
        logging.error(f"[SERVER] Client '{username}' lỗi UTF-8: {e}")
    finally:
        logging.info("🔒 [LOCK] Acquire room_lock (disconnect cleanup)")
        with room_lock:
            if client_socket in clients:
                username = clients.pop(client_socket)
                logging.info(f"[SERVER] '{username}' rời phòng. Còn lại: {len(clients)} client")
        logging.info("🔓 [LOCK] Release room_lock (disconnect cleanup)")
        try:
            client_socket.close()
        except OSError:
            pass


# ========== XỬ LÝ TÍN HIỆU DỪNG ==========
def signal_handler(signum, frame):
    logging.info(f"[SERVER] Nhận tín hiệu dừng. Đang dọn dẹp...")
    raise KeyboardInterrupt()


# ========== KHỞI ĐỘNG SERVER ==========
def main():
    global auction_active, timer_version

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.info("=" * 60)
    logging.info("  SERVER ĐẤU GIÁ TRỰC TUYẾN - Môn: Mạng và Truyền thông")
    logging.info("=" * 60)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(10)
        logging.info(f"[SERVER] Đang lắng nghe tại {HOST}:{PORT}...")
        logging.info(f"[SERVER] ⏳ Đang chờ client đầu tiên JOIN...")

        while auction_active:
            try:
                server_socket.settimeout(1.0)
                try:
                    client_sock, client_addr = server_socket.accept()
                except socket.timeout:
                    continue
                
                if not auction_active:
                    send_message(client_sock, "ERROR|Phiên đấu giá đã kết thúc")
                    client_sock.close()
                    break
                
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_sock, client_addr),
                    daemon=True
                )
                client_thread.start()
            except OSError:
                break
        
        logging.info("[SERVER] Chờ 5 giây để client kịp nhận thông báo WIN...")
        time.sleep(5)  # Tăng lên 5 giây để tránh lỗi Errno 9

    except KeyboardInterrupt:
        logging.info("[SERVER] Nhận tín hiệu dừng (Ctrl+C)")
    
    finally:
        auction_active = False
        timer_version += 1 # Ép luồng timer cũ chết đi
        
        logging.info("🔒 [LOCK] Acquire room_lock (server shutdown)")
        with room_lock:
            for sock in list(clients.keys()):
                try:
                    sock.close()
                except OSError:
                    pass
            clients.clear()
        logging.info("🔓 [LOCK] Release room_lock (server shutdown)")

        try:
            server_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

        server_socket.close()
        logging.info("[SERVER] Đã tắt server. Tạm biệt! 👋")
        logging.info(f"[SERVER] Port {PORT} đã được giải phóng.")


if __name__ == "__main__":
    main()
    
