#!/usr/bin/env python3
"""Interactive OAuth & Multi-Channel Setup Wizard for Hermes YouTube Plugin.

Allows connecting multiple YouTube channels (Brand Accounts & personal channels)
managed under the SAME or DIFFERENT Google accounts to Hermes Agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple

try:
    from .youtube_client import YouTubeClient, _get_hermes_home
except ImportError:
    from youtube_client import YouTubeClient, _get_hermes_home


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/userinfo.email",
]


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP server to catch OAuth redirect callback."""
    code: Optional[str] = None
    error: Optional[str] = None

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Quiet logging

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <html>
            <body style="font-family: system-ui, sans-serif; text-align: center; padding: 50px; background: #0f172a; color: #f8fafc;">
                <h1 style="color: #22c55e;">&#10004; Xác thực YouTube thành công!</h1>
                <p>Mã ủy quyền đã được chuyển về Hermes Agent.</p>
                <p style="color: #94a3b8;">Bạn có thể đóng tab trình duyệt này và quay lại terminal/chat.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        elif "error" in params:
            OAuthCallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h1>Lỗi xác thực: {OAuthCallbackHandler.error}</h1>".encode("utf-8"))


def exchange_code_for_tokens(client_id: str, client_secret: str, redirect_uri: str, code: str) -> Dict[str, Any]:
    """Exchange authorization code for refresh_token and access_token."""
    token_url = "https://oauth2.googleapis.com/token"
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Lỗi trao đổi OAuth code lấy token: {e.code} - {err_msg}")


def print_gcp_guide():
    print("\n" + "=" * 76)
    print("📋 HƯỚNG DẪN CẤU HÌNH GOOGLE CLOUD PROJECT CHO YOUTUBE DATA API")
    print("=" * 76)
    print("1. Truy cập Google Cloud Console: https://console.cloud.google.com")
    print("2. Chọn hoặc Tạo Project mới (ví dụ: 'Hermes YouTube Agent')")
    print("3. Bật YouTube Data API v3:")
    print("   -> Vào 'APIs & Services' > 'Library'")
    print("   -> Tìm 'YouTube Data API v3' và nhấn 'ENABLE'")
    print("4. Cấu hình OAuth Consent Screen:")
    print("   -> Vào 'APIs & Services' > 'OAuth consent screen'")
    print("   -> User Type: Chọn 'External' (BẮT BUỘC chọn External để hỗ trợ Brand Accounts)")
    print("   -> Điền Tên App & Email liên hệ")
    print("   -> Tại tab 'Test users': Nhấn '+ ADD USERS' và thêm Email Google quản lý các kênh YouTube")
    print("5. Tạo OAuth Client ID:")
    print("   -> Vào 'APIs & Services' > 'Credentials' > '+ CREATE CREDENTIALS' > 'OAuth client ID'")
    print("   -> Application type: Chọn 'Web application'")
    print("   -> Authorized redirect URIs: Thêm:")
    print("         http://127.0.0.1:8089")
    print("         http://localhost:8089")
    print("   -> Lưu lại và copy Client ID & Client Secret.")
    print("=" * 76 + "\n")


def add_channel_interactive(client: YouTubeClient, port: int = 8089):
    cid, sec = client.get_oauth_credentials()

    if not cid or not sec:
        print("⚠️ Chưa tìm thấy Google OAuth Client ID & Secret.")
        choice = input("Bạn có muốn xem hướng dẫn tạo trên GCP không? (y/n) [y]: ").strip().lower()
        if choice in ("", "y", "yes"):
            print_gcp_guide()

        cid = input("Nhập Client ID: ").strip()
        sec = input("Nhập Client Secret: ").strip()
        if not cid or not sec:
            print("❌ Client ID và Client Secret không được để trống!")
            return

        # Save to registry
        client.registry["client_id"] = cid
        client.registry["client_secret"] = sec
        client._save_registry()
        print("✓ Đã lưu Client ID và Secret vào registry.")

    redirect_uri = f"http://127.0.0.1:{port}"

    # Build Auth URL
    auth_params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent select_account",  # Force account & channel selector
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"

    print("\n" + "-" * 76)
    print("🔗 BƯỚC ỦY QUYỀN KÊNH YOUTUBE (OAUTH CONSENT):")
    print("-" * 76)
    print("Mẹo: Nếu cùng 1 email quản lý nhiều kênh (Brand Accounts), màn hình Google")
    print("sẽ hiển thị danh sách các Kênh. Vui lòng CHỌN ĐÚNG KÊNH bạn muốn kết nối!")
    print("\n👉 Mở đường link sau trên trình duyệt để cấp quyền:")
    print(f"\n{auth_url}\n")
    print("-" * 76)
    print(f"Đang chờ callback tại {redirect_uri} ...")
    print("(Nếu chạy trên VPS từ xa, bạn có thể tạo SSH tunnel: ssh -N -L 8089:127.0.0.1:8089 user@vps)")
    print("Hoặc nếu trình duyệt không redirect về được, bạn có thể copy mã 'code=...' dán trực tiếp bên dưới.\n")

    # Start local HTTP server in background thread
    server = HTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.daemon = True
    server_thread.start()

    code = None
    # Wait for either HTTP callback or user manual paste
    print("Nhấn Enter nếu đã duyệt xong trên web hoặc dán Authorization Code / URL vào đây:")
    user_input = input("> ").strip()

    if OAuthCallbackHandler.code:
        code = OAuthCallbackHandler.code
    elif user_input:
        if "code=" in user_input:
            parsed = urllib.parse.urlparse(user_input)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [user_input])[0]
        else:
            code = user_input

    server.server_close()

    if not code:
        print("❌ Không nhận được mã ủy quyền. Vui lòng thử lại!")
        return

    print("\n⏳ Đang trao đổi mã lấy token từ Google...")
    try:
        tokens = exchange_code_for_tokens(cid, sec, redirect_uri, code)
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        return

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in", 3600)

    if not refresh_token:
        print("⚠️ Cảnh báo: Google không trả về refresh_token mới (do tài khoản đã được cấp quyền trước đó).")
        print("Nếu muốn lấy lại refresh_token, hãy hủy quyền app tại https://myaccount.google.com/permissions và thử lại.")

    print("🔍 Đang lấy thông tin kênh YouTube từ token vừa cấp...")
    try:
        ch_info = client.fetch_channel_details_from_token(access_token)
    except Exception as e:
        print(f"❌ Không thể lấy thông tin kênh: {e}")
        return

    channel_id = ch_info["channel_id"]
    title = ch_info["title"]
    custom_url = ch_info.get("custom_url") or ""
    subs = ch_info.get("subscriber_count", "0")
    videos = ch_info.get("video_count", "0")

    print("\n" + "=" * 76)
    print(f"🎉 KẾT NỐI KÊNH THÀNH CÔNG:")
    print(f"   • Tên kênh: {title}")
    print(f"   • Channel ID: {channel_id}")
    print(f"   • Custom URL: {custom_url}")
    print(f"   • Người đăng ký: {subs} | Video: {videos}")
    print("=" * 76)

    # Suggest alias
    default_alias = title.lower().replace(" ", "_").replace("-", "_")
    default_alias = "".join(c for c in default_alias if c.isalnum() or c == "_")[:20]
    alias_input = input(f"\nNhập tên gợi nhớ (alias) cho kênh này [Mặc định: {default_alias}]: ").strip()
    alias = alias_input or default_alias

    # If channel already exists and no new refresh token returned, keep old refresh_token
    existing_ch = client.registry.get("channels", {}).get(channel_id, {})
    if not refresh_token:
        refresh_token = existing_ch.get("refresh_token")
        if not refresh_token:
            print("❌ Lỗi nghiêm trọng: Kênh này chưa từng có refresh_token. Vui lòng cấp quyền lại với prompt=consent.")
            return

    client.registry.setdefault("channels", {})[channel_id] = {
        "channel_id": channel_id,
        "title": title,
        "custom_url": custom_url,
        "alias": alias,
        "refresh_token": refresh_token,
        "access_token": access_token,
        "expires_at": time.time() + expires_in,
        "subscriber_count": subs,
        "video_count": videos,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Set as default if first channel
    if not client.registry.get("default_channel_id") or len(client.registry["channels"]) == 1:
        client.registry["default_channel_id"] = channel_id
        print(f"✓ Đã đặt '{title}' làm kênh mặc định.")

    client._save_registry()
    print(f"✓ Đã lưu cấu hình an toàn vào {client.channels_file} (mode 600).")
    print(f"👉 Bây giờ bạn có thể upload video lên kênh này bằng lệnh: 'youtube_upload_video'")
    print(f"   hoặc chỉ định kênh qua alias: channel='{alias}'.\n")


def list_channels_cli(client: YouTubeClient):
    channels = client.registry.get("channels", {})
    if not channels:
        print("\n📭 Chưa có kênh YouTube nào được kết nối trong hệ thống.")
        print("Chạy 'python3 setup_oauth.py --add' để kết nối kênh đầu tiên.\n")
        return

    default_id = client.registry.get("default_channel_id")
    print("\n" + "=" * 76)
    print(f"📺 DANH SÁCH CÁC KÊNH YOUTUBE ĐÃ KẾT NỐI ({len(channels)} kênh)")
    print("=" * 76)
    for idx, (cid, ch) in enumerate(channels.items(), 1):
        is_def = " (MẶC ĐỊNH ⭐)" if cid == default_id else ""
        alias = ch.get("alias") or "N/A"
        print(f"{idx}. {ch.get('title')} [{alias}]{is_def}")
        print(f"   - Channel ID: {cid}")
        print(f"   - Handle: {ch.get('custom_url') or 'N/A'}")
        print(f"   - Subs: {ch.get('subscriber_count', 'N/A')} | Videos: {ch.get('video_count', 'N/A')}")
        print(f"   - Ngày kết nối: {ch.get('created_at', 'N/A')}")
        print("-" * 76)
    print()


def set_default_cli(client: YouTubeClient, target: str):
    try:
        res = client.set_default_channel(target)
        print(f"✓ {res['message']}")
    except Exception as e:
        print(f"❌ {e}")


def remove_channel_cli(client: YouTubeClient, target: str):
    channels = client.registry.get("channels", {})
    try:
        ch = client.resolve_channel(target)
        cid = ch["channel_id"]
        title = ch.get("title")
        del channels[cid]
        if client.registry.get("default_channel_id") == cid:
            client.registry["default_channel_id"] = list(channels.keys())[0] if channels else None
        client._save_registry()
        print(f"✓ Đã gỡ kênh '{title}' (ID: {cid}) khỏi hệ thống.")
    except Exception as e:
        print(f"❌ {e}")


def main():
    parser = argparse.ArgumentParser(description="Hermes YouTube Multi-Channel Setup Wizard")
    parser.add_argument("--add", action="store_true", help="Kết nối thêm kênh YouTube mới")
    parser.add_argument("--list", action="store_true", help="Liệt kê các kênh đã kết nối")
    parser.add_argument("--set-default", metavar="CHANNEL", help="Đặt kênh mặc định theo alias hoặc Channel ID")
    parser.add_argument("--remove", metavar="CHANNEL", help="Gỡ một kênh khỏi hệ thống")
    parser.add_argument("--port", type=int, default=8089, help="Local port for OAuth callback (mặc định 8089)")
    args = parser.parse_args()

    client = YouTubeClient()

    if args.list:
        list_channels_cli(client)
    elif args.set_default:
        set_default_cli(client, args.set_default)
    elif args.remove:
        remove_channel_cli(client, args.remove)
    elif args.add:
        add_channel_interactive(client, port=args.port)
    else:
        # Default interactive menu
        print("=" * 76)
        print("   HERMES AGENT - YOUTUBE MULTI-CHANNEL MANAGEMENT WIZARD")
        print("=" * 76)
        print("1. Kết nối thêm kênh YouTube mới (Add Channel)")
        print("2. Xem danh sách các kênh đã kết nối (List Channels)")
        print("3. Đặt kênh mặc định (Set Default Channel)")
        print("4. Gỡ kênh khỏi hệ thống (Remove Channel)")
        print("5. Xem hướng dẫn Google Cloud Project (GCP Guide)")
        print("6. Thoát")
        print("-" * 76)
        choice = input("Chọn chức năng [1-6]: ").strip()
        if choice == "1":
            add_channel_interactive(client, port=args.port)
        elif choice == "2":
            list_channels_cli(client)
        elif choice == "3":
            t = input("Nhập alias hoặc Channel ID cần đặt làm mặc định: ").strip()
            if t:
                set_default_cli(client, t)
        elif choice == "4":
            t = input("Nhập alias hoặc Channel ID cần gỡ: ").strip()
            if t:
                remove_channel_cli(client, t)
        elif choice == "5":
            print_gcp_guide()
        else:
            print("Tạm biệt!")


if __name__ == "__main__":
    main()
