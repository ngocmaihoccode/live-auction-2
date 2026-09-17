"""
=========================================================
CLIENT cho hệ thống Đấu giá Trực tuyến (Live Auction)
Môn: Công nghệ Mạng và Truyền thông
Bài tập: Exercise 08 - Live Online Auction Bidding System
=========================================================

Chức năng:
  1. Kết nối tới server qua TCP
  2. Đăng ký tên người dùng (JOIN)
  3. Nhận cập nhật real-time về giá và người dẫn đầu (thread nền)
  4. Cho phép người dùng nhập bid và gửi lên server (thread chính)

Kiến trúc đa luồng phía client:
  - Thread chính: đọc input từ bàn phím, gửi BID
  - Thread nền:   lắng nghe bản tin từ server, hiển thị lên màn hình
  
Nếu chỉ dùng 1 thread thì client sẽ bị "treo" khi chờ input,
không thể nhận update real-time từ server.
"""

import socket
import threading
import sys
import codecs

# ========== CẤU HÌNH ==========
SERVER_HOST = 'localhost'    # Đổi thành IP server nếu chạy trên máy khác
SERVER_PORT = 5000

# Cờ để dừng client
running = True


def receive_messages(sock):
    """
    Thread nền: liên tục nhận bản tin từ server và hiển thị.
    Xử lý message framing bằng cách gom vào buffer, tách theo '\n'.
    """
    global running
    buffer = ""
    # Incremental decoder: 1 ký tự tiếng Việt (2-3 byte UTF-8) có thể bị TCP cắt
    # đôi giữa 2 lần recv() liên tiếp; decode() thường sẽ raise UnicodeDecodeError
    # dù dữ liệu hợp lệ. decoder giữ lại phần byte dở dang chờ recv() tiếp theo.
    decoder = codecs.getincrementaldecoder('utf-8')()

    try:
        while running:
            data = sock.recv(1024)
            if not data:
                print("\n[CLIENT] Server đã đóng kết nối.")
                running = False
                break

            buffer += decoder.decode(data)
            printed_something = False
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue

                # Parse bản tin theo giao thức
                parts = line.split('|')
                command = parts[0]

                # In dòng trống để tách khỏi prompt nhập liệu
                print()
                printed_something = True

                if command == "WELCOME" and len(parts) >= 3:
                    item = parts[1]
                    price = parts[2]
                    print(f"🎉 Chào mừng! Món đồ: '{item}' | Giá khởi điểm: {price}")

                elif command == "UPDATE" and len(parts) >= 3:
                    price = parts[1]
                    leader = parts[2]
                    print(f"💰 GIÁ MỚI: {price} | Người dẫn đầu: {leader}")

                elif command == "ERROR" and len(parts) >= 2:
                    reason = parts[1]
                    print(f"❌ Lỗi: {reason}")

                elif command == "INFO" and len(parts) >= 2:
                    info = parts[1]
                    print(f"ℹ️  {info}")

                elif command == "WIN" and len(parts) >= 3:
                    winner = parts[1]
                    price = parts[2]
                    if winner == "none":
                        print(f"⚠️  Phiên đấu giá kết thúc mà không có ai đấu giá.")
                    else:
                        print(f"🏆 PHIÊN KẾT THÚC! Winner: {winner} với giá {price}")
                    running = False
                    # input() ở thread chính không thể bị ngắt giữa chừng, nên báo rõ
                    # để người dùng biết cần nhấn Enter thêm 1 lần để thoát hẳn.
                    print("👉 Nhấn Enter để thoát chương trình...")
                    break

                else:
                    print(f"[SERVER]: {line}")

            # In lại prompt nhập liệu 1 LẦN duy nhất sau khi đã xử lý xong toàn bộ
            # message trong buffer (tránh in lặp nhiều lần nếu nhiều message dồn
            # về trong cùng 1 lần recv()), và chỉ in nếu còn đang chạy (tránh in
            # đè lên thông báo thoát vừa in ở nhánh WIN phía trên).
            if printed_something and running:
                print("Nhập giá bid (hoặc 'quit' để thoát): ", end='', flush=True)

    except (ConnectionResetError, ConnectionAbortedError, OSError):
        if running:
            print("\n[CLIENT] Mất kết nối với server.")
        running = False

    except UnicodeDecodeError:
        # Server gửi dữ liệu không phải UTF-8 hợp lệ - không để crash thread nhận
        if running:
            print("\n[CLIENT] Nhận được dữ liệu không hợp lệ từ server.")
        running = False


def main():
    global running
    
    print("=" * 60)
    print("  CLIENT ĐẤU GIÁ TRỰC TUYẾN")
    print("=" * 60)
    
    # Nhập username
    username = input("Nhập tên của bạn: ").strip()
    if not username:
        print("Tên không được để trống. Thoát.")
        return
    
    # Kết nối tới server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)    # Timeout khi connect(), tránh treo vô hạn nếu IP/mạng sai
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
    except socket.timeout:
        print(f"❌ Kết nối tới server {SERVER_HOST}:{SERVER_PORT} quá thời gian chờ (timeout).")
        print("   Kiểm tra: IP/port đúng chưa? Mạng có chặn không?")
        sock.close()
        return
    except ConnectionRefusedError:
        print(f"❌ Không kết nối được tới server {SERVER_HOST}:{SERVER_PORT}")
        print("   Kiểm tra: Server đã chạy chưa? IP/port đúng chưa?")
        sock.close()
        return
    except OSError as e:
        print(f"❌ Lỗi kết nối tới server {SERVER_HOST}:{SERVER_PORT}: {e}")
        sock.close()
        return
    sock.settimeout(None)    # Về lại blocking mode cho các thao tác recv()/sendall() sau này

    print(f"✅ Đã kết nối tới server {SERVER_HOST}:{SERVER_PORT}")
    
    # Gửi JOIN với username
    sock.sendall(f"JOIN|{username}\n".encode('utf-8'))
    
    # Khởi động thread nền để nhận bản tin
    receive_thread = threading.Thread(target=receive_messages, args=(sock,), daemon=True)
    receive_thread.start()
    
    # Thread chính: đọc input và gửi BID
    try:
        while running:
            try:
                user_input = input("Nhập giá bid (hoặc 'quit' để thoát): ").strip()
            except EOFError:
                break
            
            if not running:
                break
            
            if user_input.lower() in ('quit', 'exit', 'q'):
                print("Đang thoát...")
                break
            
            if not user_input:
                continue
            
            # Validate là số
            try:
                amount = int(user_input)
                if amount <= 0:
                    print("❌ Giá phải là số dương.")
                    continue
            except ValueError:
                print("❌ Vui lòng nhập một số nguyên.")
                continue
            
            # Gửi BID lên server
            try:
                sock.sendall(f"BID|{amount}\n".encode('utf-8'))
            except (BrokenPipeError, OSError):
                print("[CLIENT] Không gửi được, server có thể đã tắt.")
                break
    
    except KeyboardInterrupt:
        print("\n[CLIENT] Đã nhấn Ctrl+C, thoát...")
    
    finally:
        running = False
        try:
            sock.close()
        except OSError:
            pass
        print("[CLIENT] Đã đóng kết nối. Tạm biệt! 👋")


if __name__ == "__main__":
    main()
