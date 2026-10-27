"""Core YouTube Data API v3 Client for Hermes Agent.

Provides zero-bloat, robust YouTube integration using standard Python libraries:
- Multi-channel registry (multiple Brand Accounts on 1 Google account)
- Resumable video upload (supporting large files & Shorts)
- Automatic OAuth2 token refresh
- Custom thumbnail upload
- Playlist assignment
- Channel discovery and monitoring
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _get_hermes_home() -> str:
    home = os.environ.get("HERMES_HOME")
    if home and os.path.exists(home):
        return home
    profile = os.environ.get("HERMES_PROFILE") or os.environ.get("HERMES_SESSION_PROFILE")
    if profile:
        p_home = os.path.expanduser(f"~/.hermes/profiles/{profile}")
        if os.path.exists(p_home):
            return p_home
    return os.path.expanduser("~/.hermes")


class YouTubeClient:
    """Multi-channel YouTube Data API v3 client."""

    DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB (must be multiple of 256 KB)

    def __init__(self, channels_file: Optional[str] = None):
        self.hermes_home = _get_hermes_home()
        self.channels_file = channels_file or os.path.join(self.hermes_home, "youtube_channels.json")
        self._load_registry()

    def _load_registry(self) -> None:
        """Load channel registry from JSON file."""
        self.registry: Dict[str, Any] = {
            "default_channel_id": None,
            "channels": {},
            "client_id": None,
            "client_secret": None,
        }
        if os.path.exists(self.channels_file):
            try:
                with open(self.channels_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.registry.update(data)
            except Exception as e:
                print(f"[YouTubeClient] Warning: Failed to load registry from {self.channels_file}: {e}", file=sys.stderr)

    def _save_registry(self) -> None:
        """Save channel registry securely to JSON file with mode 600."""
        os.makedirs(os.path.dirname(os.path.abspath(self.channels_file)), exist_ok=True)
        tmp_file = f"{self.channels_file}.tmp.{os.getpid()}"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, self.channels_file)

    def get_oauth_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Resolve client_id and client_secret from env, google_client_secret.json, or registry."""
        # 1. Environment variables
        cid = os.environ.get("YOUTUBE_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID")
        sec = os.environ.get("YOUTUBE_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET")
        if cid and sec:
            return cid.strip(), sec.strip()

        # 2. Check profile .env
        env_path = os.path.join(self.hermes_home, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k in ("YOUTUBE_CLIENT_ID", "GOOGLE_CLIENT_ID") and not cid:
                            cid = v
                        elif k in ("YOUTUBE_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET") and not sec:
                            sec = v
                if cid and sec:
                    return cid, sec
            except Exception:
                pass

        # 3. Check google_client_secret.json in ~/.hermes or profile home
        candidate_paths = [
            os.path.join(self.hermes_home, "google_client_secret.json"),
            os.path.expanduser("~/.hermes/google_client_secret.json"),
        ]
        for p in candidate_paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cdata = json.load(f)
                    root_key = list(cdata.keys())[0] if cdata else None
                    if root_key in ("web", "installed") and isinstance(cdata[root_key], dict):
                        info = cdata[root_key]
                        c_id = info.get("client_id")
                        c_sec = info.get("client_secret")
                        if c_id and c_sec:
                            return str(c_id).strip(), str(c_sec).strip()
                except Exception:
                    pass

        # 4. Check registry
        if self.registry.get("client_id") and self.registry.get("client_secret"):
            return str(self.registry["client_id"]).strip(), str(self.registry["client_secret"]).strip()

        return None, None

    def is_configured(self) -> bool:
        """Check if client is configured with credentials and at least one channel."""
        cid, sec = self.get_oauth_credentials()
        return bool(cid and sec and self.registry.get("channels"))

    def resolve_channel(self, selector: Optional[str] = None) -> Dict[str, Any]:
        """Resolve channel data by channel_id, alias, custom_url (@handle), or title.
        If selector is None, resolves the default channel.
        """
        channels = self.registry.get("channels", {})
        if not channels:
            raise ValueError(
                "Chưa có kênh YouTube nào được kết nối trong hệ thống. "
                "Vui lòng chạy 'python3 setup_oauth.py' để kết nối kênh đầu tiên."
            )

        if not selector:
            default_id = self.registry.get("default_channel_id")
            if default_id and default_id in channels:
                return channels[default_id]
            # Fallback to the first channel
            first_id = list(channels.keys())[0]
            return channels[first_id]

        target = selector.strip()
        # Direct channel_id match
        if target in channels:
            return channels[target]

        target_lower = target.lower()
        # Match by alias, custom_url, or title
        for cid, ch in channels.items():
            if ch.get("alias") and ch["alias"].lower() == target_lower:
                return ch
            if ch.get("custom_url") and ch["custom_url"].lower().lstrip("@") == target_lower.lstrip("@"):
                return ch
            if ch.get("title") and ch["title"].lower() == target_lower:
                return ch

        # Substring title match
        for cid, ch in channels.items():
            if ch.get("title") and target_lower in ch["title"].lower():
                return ch

        avail = [f"'{c.get('alias') or c.get('title')}' (ID: {c.get('channel_id')})" for c in channels.values()]
        raise ValueError(
            f"Không tìm thấy kênh YouTube khớp với '{selector}'. "
            f"Các kênh hiện có: {', '.join(avail)}"
        )

    def get_access_token(self, channel_data: Dict[str, Any]) -> str:
        """Get or refresh valid OAuth2 access token for the channel."""
        now = time.time()
        cached_token = channel_data.get("access_token")
        expires_at = channel_data.get("expires_at", 0)

        # Buffer of 60 seconds before expiration
        if cached_token and expires_at > (now + 60):
            return cached_token

        refresh_token = channel_data.get("refresh_token")
        if not refresh_token:
            raise ValueError(
                f"Kênh '{channel_data.get('title')}' (ID: {channel_data.get('channel_id')}) "
                "không có refresh_token. Vui lòng kết nối lại kênh qua setup_oauth.py."
            )

        cid, sec = self.get_oauth_credentials()
        if not cid or not sec:
            raise ValueError("Thiếu OAuth Client ID hoặc Client Secret của Google Cloud Project.")

        token_url = "https://oauth2.googleapis.com/token"
        payload = urllib.parse.urlencode({
            "client_id": cid,
            "client_secret": sec,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        req = urllib.request.Request(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Lỗi refresh token cho kênh '{channel_data.get('title')}': {e.code} - {err_body}")

        new_access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)

        if not new_access_token:
            raise RuntimeError("Google không trả về access_token hợp lệ.")

        # Update cache in registry
        cid_key = channel_data["channel_id"]
        if cid_key in self.registry.get("channels", {}):
            self.registry["channels"][cid_key]["access_token"] = new_access_token
            self.registry["channels"][cid_key]["expires_at"] = now + expires_in
            self.registry["channels"][cid_key]["last_refreshed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._save_registry()

        return new_access_token

    def _api_request(
        self,
        method: str,
        url: str,
        access_token: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Perform an authenticated YouTube Data API v3 HTTP request."""
        req_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        if params:
            encoded_params = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{encoded_params}"

        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            req_headers["Content-Type"] = "application/json; charset=utf-8"
        elif raw_body is not None:
            data = raw_body

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_text = resp.read().decode("utf-8")
                return json.loads(resp_text) if resp_text else {}
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_text)
                err_msg = err_json.get("error", {}).get("message", err_text)
            except Exception:
                err_msg = err_text
            raise RuntimeError(f"YouTube API Error ({e.code}): {err_msg}")

    def fetch_channel_details_from_token(self, access_token: str) -> Dict[str, Any]:
        """Fetch channel info using 'mine=true' for newly authorized token."""
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "snippet,contentDetails,statistics",
            "mine": "true"
        }
        res = self._api_request("GET", url, access_token, params=params)
        items = res.get("items", [])
        if not items:
            raise RuntimeError("Không tìm thấy kênh YouTube nào liên kết với token này.")
        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        return {
            "channel_id": item.get("id"),
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "custom_url": snippet.get("customUrl"),
            "published_at": snippet.get("publishedAt"),
            "subscriber_count": stats.get("subscriberCount", "0"),
            "video_count": stats.get("videoCount", "0"),
            "view_count": stats.get("viewCount", "0"),
        }

    def list_channels(self, refresh_stats: bool = False) -> List[Dict[str, Any]]:
        """List all registered channels."""
        channels = self.registry.get("channels", {})
        default_id = self.registry.get("default_channel_id")
        result = []

        for cid, ch in channels.items():
            entry = {
                "channel_id": cid,
                "title": ch.get("title", "Unnamed"),
                "alias": ch.get("alias", ""),
                "custom_url": ch.get("custom_url", ""),
                "is_default": (cid == default_id),
                "created_at": ch.get("created_at"),
                "subscriber_count": ch.get("subscriber_count", "N/A"),
                "video_count": ch.get("video_count", "N/A"),
            }
            if refresh_stats:
                try:
                    token = self.get_access_token(ch)
                    details = self.fetch_channel_details_from_token(token)
                    entry["subscriber_count"] = details.get("subscriber_count", "N/A")
                    entry["video_count"] = details.get("video_count", "N/A")
                    ch["subscriber_count"] = entry["subscriber_count"]
                    ch["video_count"] = entry["video_count"]
                except Exception as e:
                    entry["stats_error"] = str(e)
            result.append(entry)

        if refresh_stats:
            self._save_registry()

        return result

    def get_channel(self, channel_selector: Optional[str] = None) -> Dict[str, Any]:
        """Get live channel details and statistics."""
        channel_data = self.resolve_channel(channel_selector)
        token = self.get_access_token(channel_data)
        details = self.fetch_channel_details_from_token(token)
        details["alias"] = channel_data.get("alias")
        details["is_default"] = (channel_data.get("channel_id") == self.registry.get("default_channel_id"))
        return details

    def set_default_channel(self, channel_selector: str) -> Dict[str, Any]:
        """Set a channel as default."""
        channel_data = self.resolve_channel(channel_selector)
        cid = channel_data["channel_id"]
        self.registry["default_channel_id"] = cid
        self._save_registry()
        return {
            "status": "success",
            "message": f"Đã đặt kênh '{channel_data.get('title')}' (alias: {channel_data.get('alias')}) làm kênh mặc định.",
            "default_channel_id": cid,
        }

    def upload_video(
        self,
        file_path: str,
        channel_selector: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        privacy_status: str = "public",
        publish_at: Optional[str] = None,
        made_for_kids: bool = False,
        category_id: str = "22",
        thumbnail_path: Optional[str] = None,
        playlist_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload video via YouTube Resumable Upload protocol."""
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Không tìm thấy file video: {file_path}")

        file_size = os.path.getsize(abs_path)
        if file_size == 0:
            raise ValueError(f"File video bị rỗng (0 bytes): {file_path}")

        # Guess mime type
        mime_type, _ = mimetypes.guess_type(abs_path)
        if not mime_type or not mime_type.startswith("video/"):
            mime_type = "video/mp4"

        # Resolve channel and access token
        channel_data = self.resolve_channel(channel_selector)
        access_token = self.get_access_token(channel_data)

        # Fallback title if not provided
        if not title or not title.strip():
            title = Path(abs_path).stem.replace("_", " ").replace("-", " ").title()
        title = title.strip()[:100]  # YouTube max title length 100

        # Privacy status validation
        privacy_status = (privacy_status or "public").lower()
        if privacy_status not in ("public", "unlisted", "private"):
            privacy_status = "public"

        # Prepare metadata
        body_metadata: Dict[str, Any] = {
            "snippet": {
                "title": title,
                "description": description or "",
                "categoryId": str(category_id or "22"),
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": bool(made_for_kids),
                "embeddable": True,
            }
        }
        if tags:
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            body_metadata["snippet"]["tags"] = tags

        if publish_at and privacy_status == "private":
            body_metadata["status"]["publishAt"] = publish_at

        # ------------------------------------------------------------------
        # Step 1: Initiate Resumable Upload Session
        # ------------------------------------------------------------------
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status,contentDetails"
        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": mime_type,
            "X-Upload-Content-Length": str(file_size),
        }

        init_req = urllib.request.Request(
            init_url,
            data=json.dumps(body_metadata).encode("utf-8"),
            headers=init_headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(init_req, timeout=60) as resp:
                upload_url = resp.headers.get("Location")
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Khởi tạo phiên upload YouTube thất bại ({e.code}): {err}")

        if not upload_url:
            raise RuntimeError("YouTube API không trả về upload_url (Location header).")

        # ------------------------------------------------------------------
        # Step 2: Stream Upload Chunks
        # ------------------------------------------------------------------
        chunk_size = self.DEFAULT_CHUNK_SIZE
        video_resource: Optional[Dict[str, Any]] = None

        with open(abs_path, "rb") as vf:
            start_byte = 0
            while start_byte < file_size:
                chunk_data = vf.read(chunk_size)
                if not chunk_data:
                    break
                chunk_len = len(chunk_data)
                end_byte = start_byte + chunk_len - 1

                chunk_headers = {
                    "Content-Type": mime_type,
                    "Content-Length": str(chunk_len),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
                }

                # Retry loop for chunk upload in case of transient network failure
                for attempt in range(5):
                    try:
                        chunk_req = urllib.request.Request(
                            upload_url,
                            data=chunk_data,
                            headers=chunk_headers,
                            method="PUT"
                        )
                        with urllib.request.urlopen(chunk_req, timeout=120) as c_resp:
                            resp_code = c_resp.status
                            resp_body = c_resp.read().decode("utf-8")
                            if resp_code in (200, 201):
                                video_resource = json.loads(resp_body) if resp_body else {}
                            break
                    except urllib.error.HTTPError as e:
                        if e.code == 308:
                            # 308 Resume Incomplete is expected for intermediate chunks
                            break
                        elif e.code in (500, 502, 503, 504) and attempt < 4:
                            time.sleep(2 ** attempt)
                            continue
                        else:
                            err_msg = e.read().decode("utf-8", errors="replace")
                            raise RuntimeError(f"Lỗi upload chunk ({start_byte}-{end_byte}): {e.code} - {err_msg}")
                    except (urllib.error.URLError, TimeoutError) as net_err:
                        if attempt < 4:
                            time.sleep(2 ** attempt)
                            continue
                        raise RuntimeError(f"Lỗi mạng khi upload video: {net_err}")

                start_byte += chunk_len

        if not video_resource or "id" not in video_resource:
            raise RuntimeError("Upload video hoàn thành nhưng không nhận được Video Resource ID từ YouTube.")

        video_id = video_resource["id"]
        result = {
            "status": "success",
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "watch_url": f"https://www.youtube.com/watch?v={video_id}",
            "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
            "title": title,
            "privacy_status": privacy_status,
            "publish_at": publish_at,
            "channel_id": channel_data.get("channel_id"),
            "channel_title": channel_data.get("title"),
            "channel_alias": channel_data.get("alias"),
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "thumbnail_uploaded": False,
            "playlist_added": False,
        }

        # ------------------------------------------------------------------
        # Step 3: Custom Thumbnail (optional)
        # ------------------------------------------------------------------
        if thumbnail_path:
            thumb_abs = os.path.abspath(os.path.expanduser(thumbnail_path))
            if os.path.exists(thumb_abs):
                try:
                    self.set_thumbnail(video_id, thumb_abs, channel_data=channel_data)
                    result["thumbnail_uploaded"] = True
                except Exception as th_err:
                    result["thumbnail_error"] = str(th_err)

        # ------------------------------------------------------------------
        # Step 4: Add to Playlist (optional)
        # ------------------------------------------------------------------
        if playlist_id:
            try:
                self.add_to_playlist(video_id, playlist_id, channel_data=channel_data)
                result["playlist_added"] = True
            except Exception as pl_err:
                result["playlist_error"] = str(pl_err)

        return result

    def set_thumbnail(
        self,
        video_id: str,
        image_path: str,
        channel_data: Optional[Dict[str, Any]] = None,
        channel_selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload custom thumbnail for a video."""
        abs_img = os.path.abspath(os.path.expanduser(image_path))
        if not os.path.exists(abs_img):
            raise FileNotFoundError(f"Không tìm thấy ảnh thumbnail: {image_path}")

        if not channel_data:
            channel_data = self.resolve_channel(channel_selector)
        token = self.get_access_token(channel_data)

        mime_type, _ = mimetypes.guess_type(abs_img)
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        with open(abs_img, "rb") as img_f:
            img_data = img_f.read()

        url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": mime_type,
            "Content-Length": str(len(img_data)),
        }

        req = urllib.request.Request(url, data=img_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"status": "success", "video_id": video_id, "data": data}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Lỗi set thumbnail cho video {video_id} ({e.code}): {err}")

    def add_to_playlist(
        self,
        video_id: str,
        playlist_id: str,
        channel_data: Optional[Dict[str, Any]] = None,
        channel_selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a video to a YouTube playlist."""
        if not channel_data:
            channel_data = self.resolve_channel(channel_selector)
        token = self.get_access_token(channel_data)

        url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
        return self._api_request("POST", url, token, json_body=body)

    def list_videos(self, channel_selector: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
        """List recently uploaded videos of a channel."""
        channel_data = self.resolve_channel(channel_selector)
        token = self.get_access_token(channel_data)
        cid = channel_data["channel_id"]

        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": cid,
            "maxResults": min(max(int(max_results), 1), 50),
            "order": "date",
            "type": "video",
        }
        res = self._api_request("GET", url, token, params=params)
        items = res.get("items", [])
        videos = []
        for it in items:
            vid = it.get("id", {}).get("videoId")
            snip = it.get("snippet", {})
            if vid:
                videos.append({
                    "video_id": vid,
                    "title": snip.get("title"),
                    "description": snip.get("description"),
                    "published_at": snip.get("publishedAt"),
                    "url": f"https://youtu.be/{vid}",
                    "watch_url": f"https://www.youtube.com/watch?v={vid}",
                    "studio_url": f"https://studio.youtube.com/video/{vid}/edit",
                })
        return videos

    def update_video(
        self,
        video_id: str,
        channel_selector: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        privacy_status: Optional[str] = None,
        category_id: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update existing video metadata and/or privacy."""
        channel_data = self.resolve_channel(channel_selector)
        token = self.get_access_token(channel_data)

        # Get existing video resource first
        get_url = "https://www.googleapis.com/youtube/v3/videos"
        cur = self._api_request("GET", get_url, token, params={"part": "snippet,status", "id": video_id})
        items = cur.get("items", [])
        if not items:
            raise ValueError(f"Không tìm thấy video với ID: {video_id}")

        v_res = items[0]
        snippet = v_res.get("snippet", {})
        status = v_res.get("status", {})

        if title is not None:
            snippet["title"] = title[:100]
        if description is not None:
            snippet["description"] = description
        if tags is not None:
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            snippet["tags"] = tags
        if category_id is not None:
            snippet["categoryId"] = str(category_id)
        if privacy_status is not None:
            status["privacyStatus"] = privacy_status.lower()

        body = {
            "id": video_id,
            "snippet": snippet,
            "status": status,
        }

        update_url = "https://www.googleapis.com/youtube/v3/videos?part=snippet,status"
        res = self._api_request("PUT", update_url, token, json_body=body)

        result = {
            "status": "success",
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "title": snippet.get("title"),
            "privacy_status": status.get("privacyStatus"),
        }

        if thumbnail_path:
            self.set_thumbnail(video_id, thumbnail_path, channel_data=channel_data)
            result["thumbnail_updated"] = True

        return result
