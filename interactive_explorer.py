#!/usr/bin/env python3
"""
Interactive game command explorer - login and try commands!
"""
import socket
import ssl
import time
import base64
import struct
import os
import json

HOST = "ep-live-us1-game.goodgamestudios.com"
PORT = 443

def create_websocket_frame(data, opcode=0x01):
    """Create masked WebSocket frame"""
    frame = bytearray()
    frame.append(0x80 | opcode)
    
    length = len(data)
    if length < 126:
        frame.append(0x80 | length)
    elif length < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack('>H', length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack('>Q', length))
    
    mask_key = os.urandom(4)
    frame.extend(mask_key)
    
    if isinstance(data, str):
        data = data.encode()
    
    masked_data = bytearray(len(data))
    for i in range(len(data)):
        masked_data[i] = data[i] ^ mask_key[i % 4]
    
    frame.extend(masked_data)
    return bytes(frame)

def parse_websocket_frame(data):
    """Parse WebSocket frame"""
    if len(data) < 2:
        return None
    
    opcode = data[0] & 0x0F
    length = data[1] & 0x7F
    
    idx = 2
    if length == 126:
        length = struct.unpack('>H', data[idx:idx+2])[0]
        idx += 2
    elif length == 127:
        length = struct.unpack('>Q', data[idx:idx+8])[0]
        idx += 8
    
    payload = data[idx:idx+length]
    return {'opcode': opcode, 'payload': payload}

def send_command(sock, cmd):
    """Send a command and wait for response"""
    sock.send(create_websocket_frame(cmd))
    time.sleep(0.3)
    
    try:
        data = sock.recv(8192)
        if data:
            frame = parse_websocket_frame(data)
            if frame:
                return frame['payload'].decode('utf-8', errors='ignore')
    except socket.timeout:
        pass
    return None

print("=" * 70)
print("🎮 Interactive Game Command Explorer")
print("=" * 70)
print()

# Connect
context = ssl.create_default_context()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ssl_sock = context.wrap_socket(sock, server_hostname=HOST)

try:
    print(f"📡 Connecting...")
    ssl_sock.connect((HOST, PORT))
    
    # WebSocket handshake
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {HOST}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    
    ssl_sock.send(handshake.encode())
    response = ssl_sock.recv(4096)
    
    if b"101 Switching Protocols" not in response:
        print("❌ WebSocket handshake failed")
        exit(1)
    
    print("✅ WebSocket connected")
    ssl_sock.settimeout(1.0)
    
    # Game handshake
    print("🎮 Performing game handshake...")
    
    # Policy
    send_command(ssl_sock, "<policy-file-request/>\x00")
    
    # Version
    resp = send_command(ssl_sock, "<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>\x00")
    if resp and 'apiOK' in resp:
        print("   ✅ Version check OK")
    
    # Login (XML)
    username = "Elliot Ralph"
    password = "abc123"
    zone = "EmpireEx_21"
    login_msg = f"<msg t='sys'><body action='login' r='0'><login z='{zone}'><nick><![CDATA[{username}]]></nick><pword><![CDATA[{password}]]></pword></login></body></msg>\x00"
    
    resp = send_command(ssl_sock, login_msg)
    print(f"   ✅ XML Login response: {resp[:80] if resp else 'None'}...")
    
    # Wait for additional login messages
    print("   ⏳ Waiting for all login messages...")
    time.sleep(1)
    for i in range(5):
        try:
            data = ssl_sock.recv(8192)
            if data:
                frame = parse_websocket_frame(data)
                if frame:
                    msg = frame['payload'].decode('utf-8', errors='ignore')
                    print(f"   📥 {msg[:100]}...")
        except socket.timeout:
            break
    
    # XT Login (Real auth)
    print("   🔐 Sending XT login (lli)...")
    xt_login_payload = {
        "CONM": 175,
        "RTM": 24,
        "ID": 0,
        "PL": 1,
        "NOM": username,
        "PW": password,
        "LT": None,
        "LANG": "en",
        "DID": "0",
        "AID": "1745592024940879420",
        "KID": "",
        "REF": "https://empire.goodgamestudios.com",
        "GCI": "",
        "SID": 9,
        "PLFID": 1,
    }
    
    xt_packet = f"%xt%{zone}%lli%1%{json.dumps(xt_login_payload)}%"
    resp = send_command(ssl_sock, xt_packet)
    print(f"   ✅ XT Login response: {resp[:80] if resp else 'None'}...")
    
    # Wait for more messages
    time.sleep(2)
    for i in range(10):
        try:
            data = ssl_sock.recv(8192)
            if data:
                frame = parse_websocket_frame(data)
                if frame:
                    msg = frame['payload'].decode('utf-8', errors='ignore')
                    print(f"   📥 {msg[:100] if len(msg) < 100 else msg[:80] + '...'}...")
        except socket.timeout:
            break
    
    print()
    print("=" * 70)
    print("✅ Logged in! Now trying game commands...")
    print("=" * 70)
    print()
    
    # Try different commands
    zone = "EmpireEx_21"
    seq = 1
    commands = [
        ("gbd", f"%xt%{zone}%gbd%{seq}%{{}}%"),  # Get big data (player info)
        ("dcl", f"%xt%{zone}%dcl%{seq}%{{}}%"),  # Detailed castle list
        ("gaa", f"%xt%{zone}%gaa%{seq}%{{}}%"),  # Get all areas
        ("gfi", f"%xt%{zone}%gfi%{seq}%{{}}%"),  # Get full info?
    ]
    
    for cmd_name, cmd in commands:
        print(f"📤 Sending: {cmd_name} - {cmd}")
        resp = send_command(ssl_sock, cmd)
        seq += 1
        
        if resp:
            print(f"   📥 Response ({len(resp)} chars):")
            
            # Try to pretty print if JSON
            if resp.startswith('%xt%'):
                parts = resp.split('%')
                print(f"      Command: {parts[1] if len(parts) > 1 else 'unknown'}")
                # Check if last part is JSON
                try:
                    data_part = parts[-2] if len(parts) > 2 else ""
                    if data_part.startswith('{') or data_part.startswith('['):
                        data = json.loads(data_part)
                        print(f"      Data: {json.dumps(data, indent=8)[:500]}")
                    else:
                        print(f"      Data: {data_part[:200]}")
                except:
                    print(f"      Raw: {resp[:300]}")
            else:
                print(f"      {resp[:300]}")
        else:
            print(f"   ⏱️  No response")
        
        print()
        time.sleep(0.5)
    
    print("=" * 70)
    print("Experiment complete! Check responses above.")
    print("=" * 70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssl_sock.close()
    print("\n🔌 Connection closed")
