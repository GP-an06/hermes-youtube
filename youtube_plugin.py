"""Hermes Plugin for YouTube Data API v3 (Multi-Channel)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from .youtube_client import YouTubeClient
except ImportError:
    from youtube_client import YouTubeClient

_client = YouTubeClient()


def _check() -> bool:
    return _client.is_configured()


def youtube_status() -> Dict[str, Any]:
    """Check configuration and health status of YouTube plugin."""
    cid, sec = _client.get_oauth_credentials()
    channels = _client.list_channels(refresh_stats=False)
    default_id = _client.registry.get("default_channel_id")

    return {
        "status": "ready" if (cid and sec and channels) else "needs_configuration",
        "has_credentials": bool(cid and sec),
        "credentials_source": "google_client_secret.json / .env / registry" if (cid and sec) else "none",
        "total_channels": len(channels),
        "default_channel_id": default_id,
        "channels": [
            {
                "title": c["title"],
                "alias": c["alias"],
                "channel_id": c["channel_id"],
                "custom_url": c["custom_url"],
                "is_default": c["is_default"],
            }
            for c in channels
        ],
        "setup_instruction": (
            "Chạy 'python3 /root/.hermes/plugins/youtube/setup_oauth.py --add' "
            "để kết nối thêm kênh mới."
        ) if not channels else "Sẵn sàng upload nội dung lên các kênh.",
    }


def youtube_list_channels(refresh_stats: bool = False) -> Dict[str, Any]:
    """List all registered YouTube channels and their aliases/metrics."""
    channels = _client.list_channels(refresh_stats=refresh_stats)
    default_id = _client.registry.get("default_channel_id")
    return {
        "total": len(channels),
        "default_channel_id": default_id,
        "channels": channels,
    }


def youtube_get_channel(channel: Optional[str] = None) -> Dict[str, Any]:
    """Get live details, metrics and subscriber count for a channel."""
    try:
        return _client.get_channel(channel)
    except Exception as e:
        return {"error": "CHANNEL_FETCH_FAILED", "message": str(e)}


def youtube_upload_video(
    file_path: str,
    channel: Optional[str] = None,
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
    try:
        return _client.upload_video(
            file_path=file_path,
            channel_selector=channel,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            publish_at=publish_at,
            made_for_kids=made_for_kids,
            category_id=category_id,
            thumbnail_path=thumbnail_path,
            playlist_id=playlist_id,
        )
    except Exception as e:
        return {
            "status": "error",
            "error": "UPLOAD_FAILED",
            "message": str(e),
            "file_path": file_path,
        }


def youtube_list_videos(channel: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """List recent videos uploaded to a specific channel."""
    try:
        videos = _client.list_videos(channel_selector=channel, max_results=limit)
        return {"channel": channel or "default", "total": len(videos), "videos": videos}
    except Exception as e:
        return {"error": "LIST_VIDEOS_FAILED", "message": str(e)}


def youtube_update_video(
    video_id: str,
    channel: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    privacy_status: Optional[str] = None,
    category_id: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Update title, description, tags, privacy status or thumbnail for a video."""
    try:
        return _client.update_video(
            video_id=video_id,
            channel_selector=channel,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            category_id=category_id,
            thumbnail_path=thumbnail_path,
        )
    except Exception as e:
        return {"error": "UPDATE_FAILED", "message": str(e)}


def youtube_set_default_channel(channel: str) -> Dict[str, Any]:
    """Set the default YouTube channel for uploads."""
    try:
        return _client.set_default_channel(channel)
    except Exception as e:
        return {"error": "SET_DEFAULT_FAILED", "message": str(e)}


SCHEMAS = {
    "youtube_status": {
        "name": "youtube_status",
        "description": "Check the health, credentials, and registered channels of the YouTube plugin.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "youtube_list_channels": {
        "name": "youtube_list_channels",
        "description": "List all configured YouTube channels (brand accounts & personal channels) linked to this Hermes agent, including aliases, channel IDs, and stats.",
        "parameters": {
            "type": "object",
            "properties": {
                "refresh_stats": {
                    "type": "boolean",
                    "description": "Whether to query live YouTube API to refresh subscriber and video counts (default false).",
                }
            },
            "required": [],
        },
    },
    "youtube_get_channel": {
        "name": "youtube_get_channel",
        "description": "Get detailed information and metrics for a specific YouTube channel.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel alias, channel ID, custom URL (@handle), or name. If omitted, uses the default channel.",
                }
            },
            "required": [],
        },
    },
    "youtube_upload_video": {
        "name": "youtube_upload_video",
        "description": "Upload a video (Shorts or Long-form) to a specified YouTube channel with SEO metadata, custom thumbnail, and playlist support. Returns the video URL and YouTube Studio link.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the video file on the system (e.g. /root/videos/promo.mp4).",
                },
                "channel": {
                    "type": "string",
                    "description": "Target channel alias, channel ID, or name. If omitted, uploads to the default channel.",
                },
                "title": {
                    "type": "string",
                    "description": "Video title (max 100 characters). If omitted, automatically derived from file name.",
                },
                "description": {
                    "type": "string",
                    "description": "Video description text with links, hashtags, and CTA.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keyword tags for YouTube SEO.",
                },
                "privacy_status": {
                    "type": "string",
                    "enum": ["public", "unlisted", "private"],
                    "description": "Visibility of the video. Default is 'public'.",
                },
                "publish_at": {
                    "type": "string",
                    "description": "Scheduled publishing time in ISO 8601 UTC format (e.g. '2026-10-25T15:00:00Z'). Requires privacy_status='private'.",
                },
                "made_for_kids": {
                    "type": "boolean",
                    "description": "COPPA compliance declaration. Default is false.",
                },
                "category_id": {
                    "type": "string",
                    "description": "YouTube category ID (default '22' for People & Blogs, '24' for Entertainment, '26' for Howto & Style).",
                },
                "thumbnail_path": {
                    "type": "string",
                    "description": "Optional path to a custom thumbnail image (.jpg or .png).",
                },
                "playlist_id": {
                    "type": "string",
                    "description": "Optional playlist ID to add this video to immediately after upload.",
                },
            },
            "required": ["file_path"],
        },
    },
    "youtube_list_videos": {
        "name": "youtube_list_videos",
        "description": "List recently published/uploaded videos on a YouTube channel.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel alias, ID, or name. Defaults to default channel.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of videos to retrieve (default 10, max 50).",
                },
            },
            "required": [],
        },
    },
    "youtube_update_video": {
        "name": "youtube_update_video",
        "description": "Update metadata (title, description, tags, privacy status, or thumbnail) of an existing video.",
        "parameters": {
            "type": "object",
            "properties": {
                "video_id": {
                    "type": "string",
                    "description": "The 11-character YouTube video ID.",
                },
                "channel": {
                    "type": "string",
                    "description": "Channel alias, ID, or name owning the video.",
                },
                "title": {
                    "type": "string",
                    "description": "New video title.",
                },
                "description": {
                    "type": "string",
                    "description": "New video description.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New SEO tags.",
                },
                "privacy_status": {
                    "type": "string",
                    "enum": ["public", "unlisted", "private"],
                    "description": "New privacy status.",
                },
                "thumbnail_path": {
                    "type": "string",
                    "description": "Path to new thumbnail image to replace current thumbnail.",
                },
            },
            "required": ["video_id"],
        },
    },
    "youtube_set_default_channel": {
        "name": "youtube_set_default_channel",
        "description": "Change the default YouTube channel used when no channel selector is provided.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel alias, channel ID, or name to set as default.",
                }
            },
            "required": ["channel"],
        },
    },
}


def register(ctx: Any) -> None:
    """Hermes plugin entrypoint."""
    handlers = {
        "youtube_status": lambda args, **_: json.dumps(youtube_status(), default=str),
        "youtube_list_channels": lambda args, **_: json.dumps(
            youtube_list_channels(args.get("refresh_stats", False)), default=str
        ),
        "youtube_get_channel": lambda args, **_: json.dumps(
            youtube_get_channel(args.get("channel")), default=str
        ),
        "youtube_upload_video": lambda args, **_: json.dumps(
            youtube_upload_video(
                file_path=args["file_path"],
                channel=args.get("channel"),
                title=args.get("title"),
                description=args.get("description"),
                tags=args.get("tags"),
                privacy_status=args.get("privacy_status", "public"),
                publish_at=args.get("publish_at"),
                made_for_kids=args.get("made_for_kids", False),
                category_id=args.get("category_id", "22"),
                thumbnail_path=args.get("thumbnail_path"),
                playlist_id=args.get("playlist_id"),
            ),
            default=str,
        ),
        "youtube_list_videos": lambda args, **_: json.dumps(
            youtube_list_videos(args.get("channel"), args.get("limit", 10)), default=str
        ),
        "youtube_update_video": lambda args, **_: json.dumps(
            youtube_update_video(
                video_id=args["video_id"],
                channel=args.get("channel"),
                title=args.get("title"),
                description=args.get("description"),
                tags=args.get("tags"),
                privacy_status=args.get("privacy_status"),
                category_id=args.get("category_id"),
                thumbnail_path=args.get("thumbnail_path"),
            ),
            default=str,
        ),
        "youtube_set_default_channel": lambda args, **_: json.dumps(
            youtube_set_default_channel(args["channel"]), default=str
        ),
    }

    emojis = {
        "youtube_status": "🩺",
        "youtube_list_channels": "📺",
        "youtube_get_channel": "📊",
        "youtube_upload_video": "🚀",
        "youtube_list_videos": "🎬",
        "youtube_update_video": "✏️",
        "youtube_set_default_channel": "⭐",
    }

    for name, schema in SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="youtube",
            schema=schema,
            handler=handlers[name],
            check_fn=_check,
            description=schema["description"],
            emoji=emojis.get(name, "▶️"),
        )
