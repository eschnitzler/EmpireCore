#!/usr/bin/env python3
"""
Automated test to explore the full game handshake and see what messages are exchanged.
"""
import socket
import ssl
import time
import base64
import hashlib
import struct

HOST = "ep-live-us1-game.goodgamestudios.com"
PORT = 443

def create_websocket_frame(data, opcode=0x01):
    """Create a WebSocket frame (text frame, MASKED for client->server)"""
    frame = bytearray()
    
    # FIN + opcode
    frame.append(0x80 | opcode)
    
    # Mask bit (1 for client) + Payload length
    length = len(data)
    if length < 126:
        frame.append(0x80 | length)  # Set mask bit
    elif length < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack('>H', length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack('>Q', length))
    
    # Generate mask key
    import os
    mask_key = os.urandom(4)
    frame.extend(mask_key)
    
    # Mask and add payload
    if isinstance(data, str):
        data = data.encode()
    
    masked_data = bytearray(len(data))
    for i in range(len(data)):
        masked_data[i] = data[i] ^ mask_key[i % 4]
    
    frame.extend(masked_data)
    
    return bytes(frame)

def parse_websocket_frame(data):
    """Parse incoming WebSocket frame"""
    if len(data) < 2:
        return None
    
    fin = (data[0] & 0x80) >> 7
    opcode = data[0] & 0x0F
    masked = (data[1] & 0x80) >> 7
    length = data[1] & 0x7F
    
    idx = 2
    
    if length == 126:
        length = struct.unpack('>H', data[idx:idx+2])[0]
        idx += 2
    elif length == 127:
        length = struct.unpack('>Q', data[idx:idx+8])[0]
        idx += 8
    
    if masked:
        mask = data[idx:idx+4]
        idx += 4
        payload = bytearray(data[idx:idx+length])
        for i in range(length):
            payload[i] ^= mask[i % 4]
        payload = bytes(payload)
    else:
        payload = data[idx:idx+length]
    
    return {'fin': fin, 'opcode': opcode, 'payload': payload}

print("=" * 70)
print("🎮 Automated GGE Protocol Test")
print("=" * 70)
print()

# Create SSL connection
context = ssl.create_default_context()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ssl_sock = context.wrap_socket(sock, server_hostname=HOST)

try:
    print(f"📡 Connecting to {HOST}:{PORT}...")
    ssl_sock.connect((HOST, PORT))
    print("✅ Connected!")
    print()
    
    # WebSocket handshake
    key = base64.b64encode(b"randomkey1234567").decode()
    handshake = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {HOST}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    
    print("📤 Sending WebSocket handshake...")
    ssl_sock.send(handshake.encode())
    
    response = ssl_sock.recv(4096)
    print("📥 Handshake response:")
    print(response.decode()[:300])
    
    if b"101 Switching Protocols" not in response:
        print("❌ Handshake failed!")
        exit(1)
    
    print("✅ WebSocket established!")
    print()
    print("="*70)
    print("Starting game protocol handshake...")
    print("="*70)
    print()
    
    # Set non-blocking with timeout
    ssl_sock.settimeout(2.0)
    
    # Message 1: Policy file request
    print("1️⃣  Sending: <policy-file-request/>")
    msg1 = "<policy-file-request/>\x00"
    ssl_sock.send(create_websocket_frame(msg1))
    
    try:
        data = ssl_sock.recv(4096)
        frame = parse_websocket_frame(data)
        if frame:
            print(f"   📥 Response ({len(frame['payload'])} bytes):")
            print(f"      {frame['payload'][:200]}")
    except socket.timeout:
        print("   ⏱️  No response (timeout)")
    print()
    
    # Message 2: Version check
    print("2️⃣  Sending: Version check (v=166)")
    msg2 = "<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>\x00"
    ssl_sock.send(create_websocket_frame(msg2))
    
    try:
        data = ssl_sock.recv(4096)
        frame = parse_websocket_frame(data)
        if frame:
            print(f"   📥 Response ({len(frame['payload'])} bytes):")
            print(f"      {frame['payload'].decode('utf-8', errors='ignore')[:300]}")
    except socket.timeout:
        print("   ⏱️  No response (timeout)")
    print()
    
    # Message 3: Login
    print("3️⃣  Sending: Login request")
    username = "Elliot Ralph"
    password = "abc123"
    zone = "EmpireEx_21"
    msg3 = f"<msg t='sys'><body action='login' r='0'><login z='{zone}'><nick><![CDATA[{username}]]></nick><pword><![CDATA[{password}]]></pword></login></body></msg>\x00"
    ssl_sock.send(create_websocket_frame(msg3))
    
    try:
        data = ssl_sock.recv(4096)
        frame = parse_websocket_frame(data)
        if frame:
            print(f"   📥 Response ({len(frame['payload'])} bytes):")
            payload = frame['payload'].decode('utf-8', errors='ignore')
            print(f"      {payload[:500]}")
            
            # Check for login success
            if 'loginOK' in payload:
                print("   ✅ Login successful!")
            elif 'loginKO' in payload:
                print("   ❌ Login failed!")
    except socket.timeout:
        print("   ⏱️  No response (timeout)")
    print()
    
    # Wait and listen for any additional messages
    print("4️⃣  Listening for additional messages (5 seconds)...")
    ssl_sock.settimeout(1.0)
    for i in range(5):
        try:
            data = ssl_sock.recv(4096)
            if data:
                frame = parse_websocket_frame(data)
                if frame:
                    payload = frame['payload'].decode('utf-8', errors='ignore')
                    print(f"   📥 Message {i+1} ({len(frame['payload'])} bytes):")
                    print(f"      {payload[:300]}")
                    print()
        except socket.timeout:
            pass
        time.sleep(1)
    
    print("="*70)
    print("Test complete!")
    print("="*70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssl_sock.close()
    print("\n🔌 Connection closed")
