#!/usr/bin/env python3
"""
Manual interactive test to explore game protocol.
Uses raw sockets to bypass dependency issues.
"""
import socket
import ssl
import struct
import time

# Game server (from config.py)
HOST = "ep-live-us1-game.goodgamestudios.com"
PORT = 443

print("=" * 70)
print("🎮 Manual GGE Protocol Explorer")
print("=" * 70)
print(f"Server: {HOST}:{PORT}")
print()

# Create SSL socket (Python 3.13 compatible)
context = ssl.create_default_context()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ssl_sock = context.wrap_socket(sock, server_hostname=HOST)

try:
    print("📡 Connecting...")
    ssl_sock.connect((HOST, PORT))
    print("✅ Connected!")
    print()
    
    # Send HTTP upgrade to WebSocket
    handshake = f"""GET / HTTP/1.1\r
Host: {HOST}\r
Upgrade: websocket\r
Connection: Upgrade\r
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r
Sec-WebSocket-Version: 13\r
\r
"""
    
    print("📤 Sending WebSocket handshake...")
    ssl_sock.send(handshake.encode())
    
    # Receive handshake response
    response = ssl_sock.recv(4096)
    print("📥 Handshake response:")
    print(response.decode()[:200])
    print()
    
    if b"101 Switching Protocols" in response:
        print("✅ WebSocket connection established!")
        print()
        print("Now you can send game protocol messages...")
        print()
        print("Commands:")
        print("  - Type XML messages to send")
        print("  - Press Ctrl+C to exit")
        print("=" * 70)
        print()
        
        # Example first message (version check)
        version_check = "<msg t='sys'><body action='verChk' r='0'><ver v='165' /></body></msg>\x00"
        
        print("📤 Sending version check...")
        # WebSocket frame: FIN + TEXT, unmasked
        frame = b'\x81' + bytes([len(version_check)]) + version_check.encode()
        ssl_sock.send(frame)
        
        # Wait for response
        print("⏳ Waiting for response...")
        time.sleep(1)
        
        # Try to read response
        data = ssl_sock.recv(4096)
        print(f"📥 Raw response ({len(data)} bytes):")
        print(data[:200])
        print()
        
        # Interactive loop
        while True:
            try:
                # Check for incoming data
                ssl_sock.settimeout(0.5)
                try:
                    data = ssl_sock.recv(4096)
                    if data:
                        print(f"\n📥 Received ({len(data)} bytes):")
                        # Try to decode
                        try:
                            print(data.decode('utf-8', errors='ignore')[:500])
                        except:
                            print(data[:200])
                except socket.timeout:
                    pass
                
                # Prompt for input
                msg = input("Enter message (or 'q' to quit): ")
                if msg.lower() == 'q':
                    break
                    
                if msg:
                    # Send as WebSocket frame
                    frame = b'\x81' + bytes([len(msg)]) + msg.encode()
                    ssl_sock.send(frame)
                    print("📤 Sent!")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Exiting...")
                break
    else:
        print("❌ WebSocket handshake failed")
        print(response.decode())
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssl_sock.close()
    print("\n🔌 Connection closed")
