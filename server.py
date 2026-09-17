"""
=========================================================
SERVER cho hệ thống Đấu giá Trực tuyến (Live Auction)
Môn: Công nghệ Mạng và Truyền thông
Bài tập: Exercise 08 - Live Online Auction Bidding System
=========================================================

Tác giả: Mai
MSSV: 11
Ngày tạo: 12/09/2026

Kiến trúc: 1 Server (Auctioneer) - Nhiều Client (Bidders), giao tiếp qua TCP

Trọng tâm kỹ thuật (Key Focus của đề bài):
  1. Quản lý biến dùng chung (highest_bid, highest_bidder) an toàn giữa nhiều thread
  2. Đồng bộ hóa đa luồng bằng Mutex/Lock để tránh Race Condition
  3. Countdown timer 15s có cơ chế reset khi có bid mới hợp lệ
"""

import socket
import threading
import time
import sys
import signal
import logging
import codecs

# ========== CẤU HÌNH ==========
HOST = '0.0.0.0'          # Lắng nghe từ mọi network interface (cho phép client từ máy khác kết nối)
PORT = 5000               # Port TCP của server
COUNTDOWN_SECONDS = 15    # Thời gian đếm ngược, theo đề bài là 15 giây
ITEM_NAME = "MacBook Pro M4"    # Món đồ đấu giá (có thể đổi)
STARTING_PRICE = 1000000    # Giá khởi điểm (đơn vị: VND, hoặc bất kỳ)

# ========== CẤU HÌNH LOGGING ==========
# Ghi log ra 2 nơi: console (xem trực tiếp lúc chạy) và file server.log
# (append mode, UTF-8) để làm minh chứng cho báo cáo + debug về sau.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server.log", mode="a", encoding="utf-8"),
    ],
)

# ========== BIẾN TOÀN CỤC (DÙNG CHUNG GIỮA CÁC THREAD) ==========
# CẢNH BÁO: Các biến này bị truy cập bởi NHIỀU thread cùng lúc.
# Bắt buộc phải bảo vệ bằng Lock để tránh Race Condition.

highest_bid = STARTING_PRICE     # Giá cao nhất hiện tại
highest_bidder = None            # Tên người đang dẫn đầu
auction_active = True            # Cờ: phiên đấu giá còn diễn ra hay không
auction_started = False          # Cờ: countdown đã bắt đầu chưa (chỉ bắt đầu khi client đầu tiên JOIN)

clients = {}                     # Dict {socket: username} - danh sách client đang kết nối

# current_timer được bảo vệ NGẦM ĐỊNH bởi price_lock: biến này chỉ được đọc/ghi
# bên trong reset_timer(), và reset_timer() luôn được gọi trong "with price_lock:"
# (xem end_auction, xử lý BID, và JOIN của client đầu tiên) nên không cần lock riêng.
current_timer = None             # Đối tượng Timer đang chạy

# ========== CÁC LOCK ĐỂ ĐỒNG BỘ HÓA ==========
# Đây là phần TRỌNG TÂM của bài - Key Focus của đề

# Lock 1: Bảo vệ highest_bid, highest_bidder, auction_active
# Dùng khi: kiểm tra + cập nhật giá, reset timer, chốt phiên
price_lock = threading.Lock()

# Lock 2: Bảo vệ dict clients (danh sách kết nối)
# Dùng khi: thêm client mới, xóa client rời đi, duyệt để broadcast
room_lock = threading.Lock()

# QUY TẮC THỨ TỰ LOCK (Lock Ordering) - để tránh deadlock:
# Codebase này CHỦ ĐÍCH không bao giờ giữ 2 lock cùng lúc (không nested lock).
# Mỗi khối "with price_lock" hoặc "with room_lock" luôn được acquire/release
# độc lập, tách rời nhau (vd: trong JOIN, price_lock chỉ được lấy SAU KHI
# room_lock đã release). Nếu sau này cần sửa code và bắt buộc phải giữ cả 2
# lock cùng lúc, PHẢI tuân thủ thứ tự cố định: price_lock trước, room_lock sau
# (không bao giờ theo chiều ngược lại), để tránh deadlock giữa các thread.


# ========== HÀM GỬI BẢN TIN AN TOÀN ==========
def send_message(sock, message):
    """
    Gửi 1 bản tin tới 1 client cụ thể.
    Bản tin luôn kết thúc bằng '\n' để làm ranh giới message (message framing).
    Vì TCP là byte-stream, nếu không có ranh giới thì các bản tin có thể bị dính vào nhau.
    """
    try:
        # encode() chuyển str thành bytes để gửi qua socket
        sock.sendall((message + '\n').encode('utf-8'))
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        # Client đã disconnect - không thể gửi
        return False


def send_to_all(message, exclude=None):
    """
    Gửi 1 bản tin tới TẤT CẢ các client trong phòng.
    exclude: socket muốn loại trừ (ví dụ: không gửi lại cho người vừa bid)
    
    QUAN TRỌNG: Phải giữ room_lock khi duyệt dict để tránh RuntimeError
    trong trường hợp có client khác đang join/leave giữa lúc broadcast.
    """
    disconnected = []

    logging.info("🔒 [LOCK] Acquire room_lock (send_to_all)")
    with room_lock:
        # Duyệt qua tất cả client đang kết nối
        for sock, username in clients.items():
            if sock == exclude:
                continue
            if not send_message(sock, message):
                # Không gửi được -> client đã disconnect
                disconnected.append(sock)

        # Xóa các client đã disconnect ngay trong lock (an toàn)
        for sock in disconnected:
            username = clients.pop(sock, "unknown")
            logging.warning(f"[SERVER] Client '{username}' đã ngắt kết nối trong lúc broadcast")
            try:
                sock.close()
            except OSError:
                pass
    logging.info("🔓 [LOCK] Release room_lock (send_to_all)")


# ========== LOGIC ĐẾM NGƯỢC (COUNTDOWN TIMER) ==========
def end_auction():
    """
    Hàm được gọi khi timer đếm ngược về 0 - chốt phiên đấu giá.
    
    LƯU Ý QUAN TRỌNG VỀ RACE CONDITION:
    - Có thể có trường hợp Timer sắp chạy end_auction() cùng lúc có bid mới đến.
    - Nếu không bảo vệ bằng lock + cờ auction_active, có thể xảy ra:
      * Bid được ghi nhận SAU khi đã chốt phiên (sai logic)
      * Hoặc chốt phiên 2 lần (gửi 2 lần bản tin WIN)
    - Cờ auction_active + price_lock giải quyết vấn đề này.
    """
    global auction_active

    logging.info("🔒 [LOCK] Acquire price_lock (end_auction)")
    with price_lock:
        # Kiểm tra kép: nếu phiên đã kết thúc rồi (do lý do khác) thì không làm gì
        if not auction_active:
            logging.info("🔓 [LOCK] Release price_lock (end_auction) - phiên đã kết thúc từ trước")
            return

        # Đánh dấu phiên đã kết thúc - các bid đến sau sẽ bị từ chối
        auction_active = False

        # Lấy thông tin winner trong lúc vẫn giữ lock
        winner = highest_bidder
        final_price = highest_bid
    logging.info("🔓 [LOCK] Release price_lock (end_auction)")

    # Broadcast WIN sau khi đã ra khỏi price_lock (tránh giữ lock quá lâu)
    if winner:
        send_to_all(f"WIN|{winner}|{final_price}")
        logging.info(f"[SERVER] 🏆 PHIÊN ĐẤU GIÁ KẾT THÚC")
        logging.info(f"[SERVER] 🏆 Người thắng: {winner} với giá {final_price}")
    else:
        send_to_all(f"WIN|none|0")
        logging.info(f"[SERVER] Phiên kết thúc không có người đấu giá.")


def reset_timer():
    """
    Reset countdown timer về 15 giây - gọi mỗi khi có bid hợp lệ mới.
    
    LƯU Ý: threading.Timer không có API "reset" - phải cancel() cái cũ rồi tạo mới.
    Hàm này PHẢI được gọi TRONG price_lock để tránh 2 thread cùng reset gây rối.
    """
    global current_timer
    
    # Hủy timer cũ nếu đang chạy
    if current_timer is not None:
        current_timer.cancel()
    
    # Tạo timer mới, đếm ngược COUNTDOWN_SECONDS giây rồi tự động gọi end_auction()
    current_timer = threading.Timer(COUNTDOWN_SECONDS, end_auction)
    current_timer.daemon = True    # Thread nền, tự tắt khi main thread tắt
    current_timer.start()

    # Log timer reset tại đây (thay vì ở từng nơi gọi reset_timer()) để đảm bảo
    # ghi nhận đầy đủ mọi lần reset dù gọi từ BID hay từ JOIN của client đầu tiên
    logging.info(f"⏰ [TIMER] Timer đã được reset về {COUNTDOWN_SECONDS}s")


# ========== XỬ LÝ TỪNG CLIENT (mỗi client 1 thread) ==========
def handle_client(client_socket, client_address):
    """
    Hàm chạy trong 1 thread riêng cho MỖI client kết nối.
    Nhận bản tin từ client, xử lý theo giao thức, phản hồi hoặc broadcast.
    
    Giao thức bản tin (đã thống nhất với thành viên 2 - xem PROTOCOL.md):
      Client -> Server:
        JOIN|<username>         - Đăng ký tên khi mới kết nối
        BID|<amount>            - Đặt giá
      Server -> Client:
        WELCOME|<item>|<price>  - Chào mừng, thông báo món đồ + giá khởi điểm
        UPDATE|<price>|<user>   - Broadcast giá mới
        ERROR|<lý do>           - Từ chối bid không hợp lệ
        WIN|<user>|<price>      - Thông báo winner khi hết phiên
    """
    global highest_bid, highest_bidder, auction_started

    username = None
    buffer = ""    # Buffer để gom bytes nhận được, xử lý message framing
    # Incremental decoder: 1 ký tự tiếng Việt (2-3 byte UTF-8) có thể bị TCP cắt
    # đôi giữa 2 lần recv() liên tiếp; decode() thường sẽ raise UnicodeDecodeError
    # dù dữ liệu hợp lệ. decoder giữ lại phần byte dở dang chờ recv() tiếp theo.
    decoder = codecs.getincrementaldecoder('utf-8')()

    logging.info(f"[SERVER] Client mới kết nối từ {client_address}")
    
    try:
        while True:
            # Nhận dữ liệu từ client (tối đa 1024 bytes/lần)
            data = client_socket.recv(1024)
            if not data:
                # data rỗng => client đã đóng kết nối
                break
            
            # Gom vào buffer, tách message theo '\n'
            # (Đây là cách xử lý TCP byte-stream đúng chuẩn)
            buffer += decoder.decode(data)
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue
                
                # Parse bản tin theo giao thức
                parts = line.split('|')
                command = parts[0]
                
                # ---------- Xử lý JOIN ----------
                if command == "JOIN" and len(parts) >= 2:
                    # Chặn JOIN nhiều lần trên cùng 1 kết nối (đã có username rồi)
                    if username is not None:
                        send_message(client_socket, "ERROR|Bạn đã JOIN rồi, không thể JOIN lại")
                        continue

                    new_username = parts[1].strip()
                    if not new_username:
                        send_message(client_socket, "ERROR|Tên không được để trống")
                        continue

                    # Chặn JOIN sau khi phiên đấu giá đã kết thúc
                    logging.info("🔒 [LOCK] Acquire price_lock (JOIN - check auction_active)")
                    with price_lock:
                        session_ended = not auction_active
                    logging.info("🔓 [LOCK] Release price_lock (JOIN - check auction_active)")
                    if session_ended:
                        send_message(client_socket, "ERROR|Phiên đấu giá đã kết thúc, không thể tham gia")
                        continue

                    # Thêm client vào dict, đồng thời kiểm tra trùng username (bảo vệ bằng room_lock)
                    logging.info("🔒 [LOCK] Acquire room_lock (JOIN)")
                    with room_lock:
                        duplicate_name = new_username in clients.values()
                        if not duplicate_name:
                            clients[client_socket] = new_username
                    logging.info("🔓 [LOCK] Release room_lock (JOIN)")

                    if duplicate_name:
                        send_message(client_socket, f"ERROR|Tên '{new_username}' đã có người dùng, vui lòng chọn tên khác")
                        continue

                    username = new_username

                    # Gửi WELCOME cho client vừa join
                    send_message(client_socket, f"WELCOME|{ITEM_NAME}|{STARTING_PRICE}")

                    # Thông báo cho các client khác biết có người mới vào
                    send_to_all(f"INFO|{username} đã tham gia phòng đấu giá", exclude=client_socket)

                    # Gửi luôn giá hiện tại cho client mới (để họ biết đang ở mức nào)
                    # Đồng thời: nếu đây là client đầu tiên JOIN thành công, bắt đầu countdown
                    # timer tại đây (KHÔNG start timer lúc server vừa mở, tránh phiên tự kết
                    # thúc trong lúc chưa có ai tham gia).
                    logging.info("🔒 [LOCK] Acquire price_lock (JOIN)")
                    with price_lock:
                        current_price = highest_bid
                        current_leader = highest_bidder if highest_bidder else "chưa có ai"
                        if not auction_started:
                            auction_started = True
                            reset_timer()
                            logging.info(f"[SERVER] ⏰ Client đầu tiên đã JOIN. Countdown {COUNTDOWN_SECONDS}s bắt đầu")
                    logging.info("🔓 [LOCK] Release price_lock (JOIN)")
                    send_message(client_socket, f"UPDATE|{current_price}|{current_leader}")

                    logging.info(f"[SERVER] '{username}' đã tham gia. Tổng số client: {len(clients)}")
                
                # ---------- Xử lý BID ----------
                elif command == "BID" and len(parts) >= 2:
                    if username is None:
                        send_message(client_socket, "ERROR|Bạn phải JOIN trước khi bid")
                        continue
                    
                    # Parse số tiền
                    try:
                        amount = int(parts[1])
                    except ValueError:
                        send_message(client_socket, "ERROR|Số tiền không hợp lệ")
                        continue

                    # Chặn số tiền không dương (0 hoặc âm) trước khi vào critical section
                    if amount <= 0:
                        send_message(client_socket, "ERROR|Số tiền phải là số dương")
                        continue


                    # ============================================================
                    # ĐÂY LÀ PHẦN QUAN TRỌNG NHẤT CỦA CẢ BÀI - CRITICAL SECTION
                    # ============================================================
                    # Kiểm tra + cập nhật phải nằm TRONG CÙNG 1 LOCK.
                    # Đây gọi là pattern "check-then-act".
                    # 
                    # Nếu KHÔNG có lock, khi 2 client cùng bid 20k đồng thời:
                    #   Thread A: đọc highest_bid = 15k, thấy 20k > 15k, chuẩn bị ghi
                    #   Thread B: đọc highest_bid = 15k, thấy 20k > 15k, chuẩn bị ghi
                    #   -> Cả 2 cùng "thắng", ghi đè lung tung, có thể sai bidder.
                    # 
                    # Có lock: 2 thread xếp hàng, người đến trước ghi thành công,
                    # người sau thấy 20k KHÔNG > 20k -> bị từ chối. ĐÚNG LOGIC.
                    
                    accepted = False
                    reason = ""

                    logging.info("🔒 [LOCK] Acquire price_lock (BID)")
                    with price_lock:
                        # Kiểm tra phiên còn hoạt động
                        if not auction_active:
                            reason = "Phiên đấu giá đã kết thúc"
                        # Kiểm tra bid CAO HƠN giá hiện tại (strict >, không phải >=)
                        elif amount > highest_bid:
                            # Cập nhật giá cao nhất
                            highest_bid = amount
                            highest_bidder = username
                            accepted = True

                            # Reset timer NGAY TRONG lock để tránh race giữa timer và bid
                            reset_timer()
                        else:
                            reason = f"Giá quá thấp (hiện tại: {highest_bid})"
                    logging.info("🔓 [LOCK] Release price_lock (BID)")
                    # ============================================================
                    # KẾT THÚC CRITICAL SECTION
                    # ============================================================

                    # Xử lý sau khi ra khỏi lock (để không giữ lock quá lâu)
                    if accepted:
                        logging.info(f"[SERVER] ✅ Chấp nhận BID {amount} từ '{username}'")
                        # Broadcast giá mới cho toàn phòng
                        send_to_all(f"UPDATE|{amount}|{username}")
                    else:
                        logging.warning(f"[SERVER] ❌ Từ chối BID {amount} từ '{username}': {reason}")
                        send_message(client_socket, f"ERROR|{reason}")

                # ---------- Bản tin không hợp lệ ----------
                else:
                    send_message(client_socket, f"ERROR|Cú pháp không hợp lệ: {line}")

    except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
        # Client bị ngắt kết nối đột ngột (ví dụ: đóng cửa sổ, mất mạng)
        # KHÔNG được để lỗi này làm crash server
        logging.error(f"[SERVER] Client '{username or client_address}' mất kết nối: {e}")

    except UnicodeDecodeError as e:
        # Client gửi dữ liệu không phải UTF-8 hợp lệ (vd: byte rác, sai giao thức)
        # KHÔNG được để lỗi này làm crash thread xử lý client
        logging.error(f"[SERVER] Client '{username or client_address}' gửi dữ liệu không hợp lệ (không phải UTF-8): {e}")

    finally:
        # Dù có lỗi hay không, luôn dọn dẹp: xóa khỏi danh sách + đóng socket
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


# ========== XỬ LÝ TÍN HIỆU DỪNG (SIGINT / SIGTERM) ==========
def signal_handler(signum, frame):
    """
    Bắt tín hiệu SIGINT (Ctrl+C) và SIGTERM (lệnh `kill <pid>`) để server luôn
    thoát sạch qua CÙNG MỘT đường dọn dẹp với Ctrl+C hiện có (khối except/finally
    trong main()), tránh viết 2 đoạn code dọn dẹp trùng lặp dễ lệch nhau.

    Cách hoạt động: raise KeyboardInterrupt ngay trong handler. Theo PEP 475,
    nếu handler raise exception thì lời gọi hệ thống đang bị chặn (vd. accept())
    sẽ nhận exception đó thay vì tự động retry -> except KeyboardInterrupt trong
    main() bắt được, rồi finally sẽ đóng toàn bộ client + server socket.
    """
    sig_name = signal.Signals(signum).name
    logging.info(f"[SERVER] Nhận tín hiệu dừng ({sig_name}). Đang dọn dẹp...")
    raise KeyboardInterrupt()


# ========== KHỞI ĐỘNG SERVER ==========
def main():
    global current_timer

    # Đăng ký handler cho cả Ctrl+C (SIGINT) và lệnh kill thông thường (SIGTERM)
    # để đảm bảo port luôn được giải phóng dù server bị dừng bằng cách nào.
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.info("=" * 60)
    logging.info("  SERVER ĐẤU GIÁ TRỰC TUYẾN - Live Auction Server")
    logging.info("=" * 60)
    logging.info(f"  Món đồ:       {ITEM_NAME}")
    logging.info(f"  Giá khởi điểm: {STARTING_PRICE}")
    logging.info(f"  Countdown:    {COUNTDOWN_SECONDS} giây")
    logging.info(f"  Địa chỉ:      {HOST}:{PORT}")
    logging.info("=" * 60)
    
    # Tạo TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # SO_REUSEADDR: cho phép dùng lại port ngay nếu server vừa tắt
    # (Nếu không có, phải chờ khoảng 30s-2min mới chạy lại được)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(10)    # backlog = 10 client chờ accept
        logging.info(f"[SERVER] Đang lắng nghe tại {HOST}:{PORT}...")
        logging.info(f"[SERVER] Nhấn Ctrl+C để dừng server")

        # Chưa khởi động timer ngay - đợi client đầu tiên JOIN mới bắt đầu
        # (Xem xử lý JOIN trong handle_client: auction_started + reset_timer())
        logging.info(f"[SERVER] ⏳ Đang chờ client đầu tiên JOIN để bắt đầu countdown {COUNTDOWN_SECONDS}s...")

        # Vòng lặp chính: accept client mới
        while auction_active:
            try:
                # accept() sẽ chặn cho tới khi có client kết nối
                # Đặt timeout để có thể kiểm tra auction_active định kỳ
                server_socket.settimeout(1.0)
                try:
                    client_sock, client_addr = server_socket.accept()
                except socket.timeout:
                    continue
                
                if not auction_active:
                    # Phiên đã kết thúc trong lúc chờ accept - từ chối client mới
                    send_message(client_sock, "ERROR|Phiên đấu giá đã kết thúc")
                    client_sock.close()
                    break
                
                # Tạo thread mới xử lý client này (mô hình thread-per-client)
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_sock, client_addr),
                    daemon=True    # Thread nền
                )
                client_thread.start()
            
            except OSError:
                break
        
        # Sau khi phiên kết thúc, chờ thêm vài giây để client kịp nhận WIN
        logging.info("[SERVER] Chờ 3 giây để client nhận thông báo WIN...")
        time.sleep(3)

    except KeyboardInterrupt:
        # Người dùng nhấn Ctrl+C (hoặc signal_handler raise lại từ SIGINT/SIGTERM)
        logging.info("[SERVER] Nhận tín hiệu dừng từ bàn phím (Ctrl+C)")
    
    finally:
        # Dọn dẹp
        if current_timer:
            current_timer.cancel()
        
        # Đóng tất cả client
        logging.info("🔒 [LOCK] Acquire room_lock (server shutdown)")
        with room_lock:
            for sock in list(clients.keys()):
                try:
                    sock.close()
                except OSError:
                    pass
            clients.clear()
        logging.info("🔓 [LOCK] Release room_lock (server shutdown)")

        # shutdown(SHUT_RDWR) trước close() để force OS giải phóng port ngay lập tức,
        # tránh trường hợp port bị kẹt ở trạng thái TIME_WAIT khi chạy lại server.
        try:
            server_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Socket đang ở trạng thái listen (chưa từng accept/connect) có thể
            # không hỗ trợ shutdown() trên một số hệ điều hành -> bỏ qua an toàn.
            pass

        server_socket.close()
        logging.info("[SERVER] Đã tắt server. Tạm biệt! 👋")
        logging.info(f"[SERVER] Port {PORT} đã được giải phóng, có thể chạy lại ngay")


if __name__ == "__main__":
    main()
