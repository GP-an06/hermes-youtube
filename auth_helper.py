#!/usr/bin/env python3
"""Helper script to generate auth URL and exchange code for YouTube plugin."""

import json
import os
import sys
import time
import urllib.parse
from youtube_client import YouTubeClient
from setup_oauth import YOUTUBE_SCOPES, exchange_code_for_tokens

client = YouTubeClient()
cid, sec = client.get_oauth_credentials()

if not cid or not sec:
    print("ERROR: Không tìm thấy Google OAuth Client ID hoặc Client Secret.")
    sys.exit(1)

redirect_uri = "http://127.0.0.1:8089"

def get_auth_url():
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "prompt": "consent select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

def exchange_and_register(code_or_url: str, alias: str = ""):
    raw = code_or_url.strip()
    if "code=" in raw:
        parsed = urllib.parse.urlparse(raw)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [raw])[0]
    else:
        code = raw

    # Decode if needed
    code = urllib.parse.unquote(code)

    tokens = exchange_code_for_tokens(cid, sec, redirect_uri, code)
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in", 3600)

    ch_info = client.fetch_channel_details_from_token(access_token)
    channel_id = ch_info["channel_id"]
    title = ch_info["title"]
    custom_url = ch_info.get("custom_url") or ""
    subs = ch_info.get("subscriber_count", "0")
    videos = ch_info.get("video_count", "0")

    if not alias:
        alias = title.lower().replace(" ", "_").replace("-", "_")
        alias = "".join(c for c in alias if c.isalnum() or c == "_")[:20]

    existing_ch = client.registry.get("channels", {}).get(channel_id, {})
    if not refresh_token:
        refresh_token = existing_ch.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Google không cấp refresh_token mới và kênh này chưa từng lưu refresh_token.")

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

    if not client.registry.get("default_channel_id") or len(client.registry["channels"]) == 1:
        client.registry["default_channel_id"] = channel_id

    client._save_registry()

    return {
        "status": "success",
        "channel_id": channel_id,
        "title": title,
        "custom_url": custom_url,
        "alias": alias,
        "subscriber_count": subs,
        "video_count": videos,
        "is_default": (client.registry.get("default_channel_id") == channel_id),
        "total_channels": len(client.registry["channels"]),
    }

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--url":
        print(get_auth_url())
    elif len(sys.argv) > 2 and sys.argv[1] == "--exchange":
        alias_arg = sys.argv[3] if len(sys.argv) > 3 else ""
        res = exchange_and_register(sys.argv[2], alias_arg)
        print(json.dumps(res, indent=2, ensure_ascii=False))
