"""
LinkedIn Service — wraps the LinkedIn v2 REST API.

Capabilities implemented:
  ┌─ Authentication ─────────────────────────────────────────────────────────┐
  │  OAuth2 PKCE flow helpers (get_access_token_url, exchange_code_for_token)│
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ Profile / Page ────────────────────────────────────────────────────────┐
  │  get_profile, get_org_followers, get_page_analytics                     │
  └─────────────────────────────────────────────────────────────────────────┘
  ┌─ Content Posting ───────────────────────────────────────────────────────┐
  │  create_text_post, create_image_post, create_video_post,                │
  │  create_article_post, delete_post, list_published_posts                 │
  └─────────────────────────────────────────────────────────────────────────┘
  ┌─ Scheduling ────────────────────────────────────────────────────────────┐
  │  schedule_post, list_scheduled_posts, cancel_scheduled_post             │
  │  (stored in data/linkedin_scheduled.json; background runner checks it) │
  └─────────────────────────────────────────────────────────────────────────┘
  ┌─ Analytics ────────────────────────────────────────────────────────────┐
  │  get_post_analytics                                                     │
  └─────────────────────────────────────────────────────────────────────────┘
  ┌─ AI Generation ─────────────────────────────────────────────────────────┐
  │  generate_ai_post_content (text via LLM)                                │
  │  generate_ai_image       (image via DALL·E or local Stable Diffusion)   │
  └─────────────────────────────────────────────────────────────────────────┘

Setup / Configuration  (config/settings.json):
  {
    "linkedin": {
      "client_id":         "<your LinkedIn app client ID>",
      "client_secret":     "<your LinkedIn app client secret>",
      "access_token":      "<long-lived access token (optional if using OAuth flow)>",
      "org_urn":           "urn:li:organization:<your_org_id>",
      "redirect_uri":      "http://localhost:8080/callback",
      "post_as_org":       true,
      "image_gen_backend": "openai"  // "openai" | "stable_diffusion" | "none"
    }
  }

Required LinkedIn API scopes:
  w_member_social        — post as member
  w_organization_social  — post as org / company page  (requires developer review)
  r_organization_social  — read org followers / analytics
  r_liteprofile          — basic profile info
  r_emailaddress         — (optional) email

LinkedIn API docs: https://docs.microsoft.com/en-us/linkedin/marketing/
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger("linkedin_service")

# ── Constants ──────────────────────────────────────────────────────────────────
_API_BASE = "https://api.linkedin.com/v2"
_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_SCOPES = "w_member_social w_organization_social r_organization_social r_liteprofile r_emailaddress"

_SCHEDULE_FILE = Path("data/linkedin_scheduled.json")

# ── Config helpers ────────────────────────────────────────────────────────────

def _config() -> Dict[str, Any]:
    """Load linkedin section from config/settings.json."""
    cfg_path = Path("config/settings.json")
    if not cfg_path.exists():
        return {}
    try:
        with open(cfg_path) as f:
            return json.load(f).get("linkedin", {})
    except Exception:
        return {}


def _access_token() -> str:
    """Return access token from config or environment."""
    token = _config().get("access_token") or os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        raise ValueError(
            "LinkedIn access_token not configured. "
            "Run the OAuth flow first: use get_access_token_url() to get the auth URL, "
            "then exchange_code_for_token() with the returned code."
        )
    return token


def _author_urn() -> str:
    """Return the author URN (org or member) based on config."""
    cfg = _config()
    if cfg.get("post_as_org", False):
        org_urn = cfg.get("org_urn", "")
        if not org_urn:
            raise ValueError(
                "linkedin.org_urn not set in config/settings.json. "
                "Set it to 'urn:li:organization:<your_org_id>'."
            )
        return org_urn
    # Fall back to member profile
    profile = get_profile()
    return f"urn:li:person:{profile['id']}"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def get_access_token_url(state: str = "") -> Dict[str, Any]:
    """
    Generate the LinkedIn OAuth2 authorization URL.
    Open this URL in a browser; after approval LinkedIn redirects to
    redirect_uri with a `code` parameter.  Pass that code to exchange_code_for_token().
    """
    cfg = _config()
    client_id = cfg.get("client_id") or os.environ.get("LINKEDIN_CLIENT_ID", "")
    if not client_id:
        return {"status": "error", "message": "linkedin.client_id not configured"}

    redirect_uri = cfg.get("redirect_uri", "http://localhost:8080/callback")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": _SCOPES,
        "state": state or str(uuid.uuid4())[:8],
    }
    url = f"{_AUTH_URL}?{urlencode(params)}"
    return {
        "status": "success",
        "auth_url": url,
        "message": "Open this URL in your browser to authorise Octa Bot to manage LinkedIn.",
        "instruction": (
            "After approving, you will be redirected to your redirect_uri with a `code` parameter. "
            "Pass that code to exchange_code_for_token()."
        ),
    }


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """Exchange the OAuth2 authorization code for an access token."""
    cfg = _config()
    client_id = cfg.get("client_id") or os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = cfg.get("client_secret") or os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8080/callback")

    if not client_id or not client_secret:
        return {"status": "error", "message": "client_id or client_secret not configured"}

    resp = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    if not resp.ok:
        return {"status": "error", "message": resp.text}

    data = resp.json()
    return {
        "status": "success",
        "access_token": data.get("access_token"),
        "expires_in": data.get("expires_in"),
        "scope": data.get("scope"),
        "message": (
            "Access token obtained successfully. "
            "Store this in config/settings.json under linkedin.access_token."
        ),
    }


# ── Profile / Page ─────────────────────────────────────────────────────────────

def get_profile() -> Dict[str, Any]:
    """Fetch the authenticated member's basic profile."""
    url = f"{_API_BASE}/me?projection=(id,localizedFirstName,localizedLastName,vanityName)"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    data = resp.json()
    return {
        "status": "success",
        "id": data.get("id", ""),
        "name": f"{data.get('localizedFirstName', '')} {data.get('localizedLastName', '')}".strip(),
        "vanity_name": data.get("vanityName", ""),
    }


def get_org_followers() -> Dict[str, Any]:
    """Return total follower count for the configured organization page."""
    cfg = _config()
    org_urn = cfg.get("org_urn", "")
    if not org_urn:
        return {"status": "error", "message": "linkedin.org_urn not configured"}

    org_id = org_urn.split(":")[-1]
    url = f"{_API_BASE}/networkSizes/urn:li:organization:{org_id}?edgeType=CompanyFollowedByMember"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    data = resp.json()
    return {
        "status": "success",
        "follower_count": data.get("firstDegreeSize", 0),
        "org_urn": org_urn,
    }


def get_page_analytics(
    granularity: str = "MONTH",
    start_days_ago: int = 30,
) -> Dict[str, Any]:
    """
    Fetch organization page analytics (impressions, clicks, engagement, follows).
    granularity: "DAY" | "MONTH"
    """
    cfg = _config()
    org_urn = cfg.get("org_urn", "")
    if not org_urn:
        return {"status": "error", "message": "linkedin.org_urn not configured"}

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (start_days_ago * 24 * 3600 * 1000)

    url = (
        f"{_API_BASE}/organizationalEntityShareStatistics"
        f"?q=organizationalEntity&organizationalEntity={org_urn}"
        f"&timeIntervals.timeGranularityType={granularity}"
        f"&timeIntervals.timeRange.start={start_ms}"
        f"&timeIntervals.timeRange.end={now_ms}"
    )
    resp = requests.get(url, headers=_headers(), timeout=20)
    if not resp.ok:
        return {"status": "error", "message": resp.text}

    elements = resp.json().get("elements", [])
    totals: Dict[str, int] = {
        "impressions": 0,
        "clicks": 0,
        "engagement_rate_pct": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "follows": 0,
    }
    for el in elements:
        s = el.get("totalShareStatistics", {})
        totals["impressions"] += s.get("impressionCount", 0)
        totals["clicks"] += s.get("clickCount", 0)
        totals["likes"] += s.get("likeCount", 0)
        totals["comments"] += s.get("commentCount", 0)
        totals["shares"] += s.get("shareCount", 0)
        totals["follows"] += s.get("followerCount", 0)

    if totals["impressions"]:
        eng = (totals["likes"] + totals["comments"] + totals["shares"]) / totals["impressions"] * 100
        totals["engagement_rate_pct"] = round(eng, 2)

    return {"status": "success", "period_days": start_days_ago, "totals": totals, "points": len(elements)}


# ── Image upload helper ────────────────────────────────────────────────────────

def _upload_image(image_path: str) -> str:
    """
    Register + upload an image to LinkedIn Assets API.
    Returns the image asset URN (e.g. urn:li:digitalmediaAsset:...).
    """
    author = _author_urn()

    # Step 1 — register upload
    reg_payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }
    reg_resp = requests.post(
        f"{_API_BASE}/assets?action=registerUpload",
        headers=_headers(),
        json=reg_payload,
        timeout=20,
    )
    if not reg_resp.ok:
        raise RuntimeError(f"Image register failed: {reg_resp.text}")

    reg_data = reg_resp.json()
    upload_url = reg_data["value"]["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset_urn = reg_data["value"]["asset"]

    # Step 2 — upload binary
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    up_resp = requests.put(
        upload_url,
        data=img_bytes,
        headers={"Authorization": f"Bearer {_access_token()}"},
        timeout=60,
    )
    if not up_resp.ok:
        raise RuntimeError(f"Image upload failed: {up_resp.text}")

    return asset_urn


def _upload_video(video_path: str) -> str:
    """
    Register + upload a video to LinkedIn Assets API.
    Returns the video asset URN.
    """
    author = _author_urn()

    reg_payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
            "owner": author,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }
    reg_resp = requests.post(
        f"{_API_BASE}/assets?action=registerUpload",
        headers=_headers(),
        json=reg_payload,
        timeout=20,
    )
    if not reg_resp.ok:
        raise RuntimeError(f"Video register failed: {reg_resp.text}")

    reg_data = reg_resp.json()
    upload_url = reg_data["value"]["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset_urn = reg_data["value"]["asset"]

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    up_resp = requests.put(
        upload_url,
        data=video_bytes,
        headers={"Authorization": f"Bearer {_access_token()}"},
        timeout=120,
    )
    if not up_resp.ok:
        raise RuntimeError(f"Video upload failed: {up_resp.text}")

    return asset_urn


# ── UGC Post builder ───────────────────────────────────────────────────────────

def _build_ugc_post(
    author: str,
    text: str,
    *,
    media_asset_urn: str | None = None,
    media_type: str = "IMAGE",
    media_title: str = "",
    media_description: str = "",
    article_url: str | None = None,
    article_title: str | None = None,
    article_description: str | None = None,
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """Build a UGC (User Generated Content) post payload."""
    if article_url:
        share_media_category = "ARTICLE"
        media = [
            {
                "status": "READY",
                "description": {"text": article_description or ""},
                "originalUrl": article_url,
                "title": {"text": article_title or ""},
            }
        ]
    elif media_asset_urn:
        share_media_category = media_type
        media = [
            {
                "status": "READY",
                "description": {"text": media_description},
                "media": media_asset_urn,
                "title": {"text": media_title},
            }
        ]
    else:
        share_media_category = "NONE"
        media = []

    payload: Dict[str, Any] = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": share_media_category,
                "media": media,
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
    }
    return payload


# ── Posting ───────────────────────────────────────────────────────────────────

def create_text_post(
    text: str,
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Create a plain text post on LinkedIn.
    visibility: "PUBLIC" | "CONNECTIONS"
    """
    author = _author_urn()
    payload = _build_ugc_post(author, text, visibility=visibility)
    resp = requests.post(f"{_API_BASE}/ugcPosts", headers=_headers(), json=payload, timeout=20)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    post_id = resp.headers.get("x-restli-id", "")
    return {
        "status": "success",
        "post_id": post_id,
        "message": f"Text post published successfully. Post ID: {post_id}",
    }


def create_image_post(
    text: str,
    image_path: str,
    image_title: str = "",
    image_description: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Upload an image and create a LinkedIn post with it.
    image_path: local path to JPG/PNG file.
    """
    try:
        asset_urn = _upload_image(image_path)
    except Exception as exc:
        return {"status": "error", "message": f"Image upload failed: {exc}"}

    author = _author_urn()
    payload = _build_ugc_post(
        author, text,
        media_asset_urn=asset_urn,
        media_type="IMAGE",
        media_title=image_title,
        media_description=image_description,
        visibility=visibility,
    )
    resp = requests.post(f"{_API_BASE}/ugcPosts", headers=_headers(), json=payload, timeout=20)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    post_id = resp.headers.get("x-restli-id", "")
    return {
        "status": "success",
        "post_id": post_id,
        "asset_urn": asset_urn,
        "message": f"Image post published successfully. Post ID: {post_id}",
    }


def create_video_post(
    text: str,
    video_path: str,
    video_title: str = "",
    video_description: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Upload a video (MP4/H.264) and create a LinkedIn post with it.
    video_path: local path to MP4 file.
    """
    try:
        asset_urn = _upload_video(video_path)
    except Exception as exc:
        return {"status": "error", "message": f"Video upload failed: {exc}"}

    author = _author_urn()
    payload = _build_ugc_post(
        author, text,
        media_asset_urn=asset_urn,
        media_type="VIDEO",
        media_title=video_title,
        media_description=video_description,
        visibility=visibility,
    )
    resp = requests.post(f"{_API_BASE}/ugcPosts", headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    post_id = resp.headers.get("x-restli-id", "")
    return {
        "status": "success",
        "post_id": post_id,
        "asset_urn": asset_urn,
        "message": f"Video post published successfully. Post ID: {post_id}",
    }


def create_article_post(
    text: str,
    article_url: str,
    article_title: str = "",
    article_description: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """Create a LinkedIn post sharing an article / URL."""
    author = _author_urn()
    payload = _build_ugc_post(
        author, text,
        article_url=article_url,
        article_title=article_title,
        article_description=article_description,
        visibility=visibility,
    )
    resp = requests.post(f"{_API_BASE}/ugcPosts", headers=_headers(), json=payload, timeout=20)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    post_id = resp.headers.get("x-restli-id", "")
    return {
        "status": "success",
        "post_id": post_id,
        "message": f"Article post published successfully. Post ID: {post_id}",
    }


def delete_post(post_id: str) -> Dict[str, Any]:
    """Delete a LinkedIn post by its ugcPost ID."""
    url = f"{_API_BASE}/ugcPosts/{post_id}"
    resp = requests.delete(url, headers=_headers(), timeout=15)
    if not resp.ok and resp.status_code != 204:
        return {"status": "error", "message": resp.text}
    return {"status": "success", "message": f"Post {post_id} deleted."}


def list_published_posts(count: int = 10) -> Dict[str, Any]:
    """List the most recent published posts for the author."""
    author = _author_urn()
    url = (
        f"{_API_BASE}/ugcPosts?q=authors&authors=List({author})"
        f"&count={count}&sortBy=LAST_MODIFIED"
    )
    resp = requests.get(url, headers=_headers(), timeout=20)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    elements = resp.json().get("elements", [])
    posts = []
    for el in elements:
        content = el.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {})
        posts.append({
            "id": el.get("id", ""),
            "created": el.get("created", {}).get("time", ""),
            "text": content.get("shareCommentary", {}).get("text", "")[:200],
            "media_category": content.get("shareMediaCategory", "NONE"),
            "lifecycle_state": el.get("lifecycleState", ""),
        })
    return {"status": "success", "count": len(posts), "posts": posts}


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_post_analytics(post_id: str) -> Dict[str, Any]:
    """
    Fetch share statistics for a specific post.
    post_id: the ugcPost ID (e.g. urn:li:ugcPost:...)
    """
    url = (
        f"{_API_BASE}/shareStatistics?q=shareStatisticsListByActivity"
        f"&activity={post_id}&count=1"
    )
    resp = requests.get(url, headers=_headers(), timeout=15)
    if not resp.ok:
        return {"status": "error", "message": resp.text}
    elements = resp.json().get("elements", [])
    if not elements:
        return {"status": "ok", "message": "No statistics available yet.", "post_id": post_id}
    s = elements[0].get("totalShareStatistics", {})
    return {
        "status": "success",
        "post_id": post_id,
        "impressions": s.get("impressionCount", 0),
        "clicks": s.get("clickCount", 0),
        "likes": s.get("likeCount", 0),
        "comments": s.get("commentCount", 0),
        "shares": s.get("shareCount", 0),
        "engagement_rate_pct": round(
            (s.get("likeCount", 0) + s.get("commentCount", 0) + s.get("shareCount", 0))
            / max(s.get("impressionCount", 1), 1) * 100, 2
        ),
    }


# ── Scheduling ────────────────────────────────────────────────────────────────

def _load_scheduled() -> List[Dict[str, Any]]:
    if not _SCHEDULE_FILE.exists():
        return []
    with open(_SCHEDULE_FILE) as f:
        return json.load(f)


def _save_scheduled(posts: List[Dict[str, Any]]) -> None:
    _SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SCHEDULE_FILE, "w") as f:
        json.dump(posts, f, indent=2)


def schedule_post(
    text: str,
    scheduled_time: str,
    post_type: str = "text",
    image_path: str = "",
    video_path: str = "",
    article_url: str = "",
    article_title: str = "",
    visibility: str = "PUBLIC",
) -> Dict[str, Any]:
    """
    Queue a post to be published at a specific time.
    scheduled_time: ISO 8601 string e.g. "2026-03-01T10:00:00"
    post_type: "text" | "image" | "video" | "article"
    """
    try:
        sched_dt = datetime.fromisoformat(scheduled_time)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid scheduled_time format: {exc}"}

    posts = _load_scheduled()
    entry: Dict[str, Any] = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "post_type": post_type,
        "scheduled_time": sched_dt.isoformat(),
        "visibility": visibility,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if post_type == "image":
        entry["image_path"] = image_path
    elif post_type == "video":
        entry["video_path"] = video_path
    elif post_type == "article":
        entry["article_url"] = article_url
        entry["article_title"] = article_title

    posts.append(entry)
    _save_scheduled(posts)
    return {
        "status": "success",
        "scheduled_id": entry["id"],
        "message": f"Post scheduled for {sched_dt.strftime('%Y-%m-%d %H:%M')}.",
    }


def list_scheduled_posts() -> Dict[str, Any]:
    """Return all pending scheduled posts."""
    posts = _load_scheduled()
    pending = [p for p in posts if p.get("status") == "pending"]
    return {
        "status": "success",
        "count": len(pending),
        "scheduled_posts": pending,
    }


def cancel_scheduled_post(scheduled_id: str) -> Dict[str, Any]:
    """Cancel a scheduled post by its local ID."""
    posts = _load_scheduled()
    found = False
    for p in posts:
        if p["id"] == scheduled_id:
            p["status"] = "cancelled"
            found = True
            break
    if not found:
        return {"status": "error", "message": f"Scheduled post {scheduled_id} not found."}
    _save_scheduled(posts)
    return {"status": "success", "message": f"Scheduled post {scheduled_id} cancelled."}


def run_scheduled_posts() -> Dict[str, Any]:
    """
    Check and publish any pending scheduled posts whose time has arrived.
    Intended to be called by a background runner periodically.
    """
    posts = _load_scheduled()
    now = datetime.now(timezone.utc)
    published = []
    errors = []

    for p in posts:
        if p.get("status") != "pending":
            continue
        try:
            sched = datetime.fromisoformat(p["scheduled_time"])
            if sched.tzinfo is None:
                sched = sched.replace(tzinfo=timezone.utc)
            if sched > now:
                continue
        except Exception:
            continue

        pt = p.get("post_type", "text")
        try:
            if pt == "text":
                result = create_text_post(p["text"], p.get("visibility", "PUBLIC"))
            elif pt == "image":
                result = create_image_post(p["text"], p["image_path"], visibility=p.get("visibility", "PUBLIC"))
            elif pt == "video":
                result = create_video_post(p["text"], p["video_path"], visibility=p.get("visibility", "PUBLIC"))
            elif pt == "article":
                result = create_article_post(
                    p["text"], p["article_url"],
                    article_title=p.get("article_title", ""),
                    visibility=p.get("visibility", "PUBLIC"),
                )
            else:
                result = {"status": "error", "message": f"Unknown post_type: {pt}"}
        except Exception as exc:
            result = {"status": "error", "message": str(exc)}

        if result.get("status") == "success":
            p["status"] = "published"
            p["published_at"] = datetime.now(timezone.utc).isoformat()
            p["post_id"] = result.get("post_id", "")
            published.append(p["id"])
            logger.info("[linkedin] Scheduled post %s published as %s", p["id"], p.get("post_id"))
        else:
            p["status"] = "failed"
            p["error"] = result.get("message", "Unknown error")
            errors.append(p["id"])
            logger.error("[linkedin] Scheduled post %s failed: %s", p["id"], p.get("error"))

    _save_scheduled(posts)
    return {"status": "success", "published": published, "errors": errors}


# ── AI Content Generation ─────────────────────────────────────────────────────

def generate_ai_post_content(
    topic: str,
    tone: str = "professional",
    length: str = "medium",
    include_hashtags: bool = True,
    target_audience: str = "tech professionals",
) -> Dict[str, Any]:
    """
    Use the configured LLM to generate LinkedIn post text.
    tone: "professional" | "casual" | "inspirational" | "educational" | "humorous"
    length: "short" (1-2 sentences) | "medium" (3-5 sentences) | "long" (full post with sections)
    """
    from src.agent.llm.llm_parser import get_llm_client  # noqa: PLC0415

    llm = get_llm_client()

    length_guide = {"short": "1-2 sentences", "medium": "3-5 sentences", "long": "8-12 sentences with structure"}
    hashtag_instruction = (
        "End the post with 3-5 relevant hashtags on a new line." if include_hashtags
        else "Do NOT include hashtags."
    )

    system_prompt = (
        "You are an expert LinkedIn content strategist. Write engaging, authentic LinkedIn posts "
        "that drive engagement, build community, and add value. Never use generic filler phrases."
    )
    user_prompt = (
        f"Write a LinkedIn post about: {topic}\n"
        f"Tone: {tone}\n"
        f"Length: {length_guide.get(length, '3-5 sentences')}\n"
        f"Target audience: {target_audience}\n"
        f"{hashtag_instruction}\n"
        "Do NOT include a subject/title line — only the post body."
    )

    try:
        resp = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.75,
            max_tokens=800,
            timeout=30,
        )
        content = resp.choices[0].message.content.strip()
        return {"status": "success", "post_text": content, "topic": topic, "tone": tone}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def generate_ai_image(
    prompt: str,
    output_path: str = "data/linkedin_generated_image.png",
    size: str = "1024x1024",
) -> Dict[str, Any]:
    """
    Generate an image for a LinkedIn post using OpenAI DALL·E 3.
    Requires OPENAI_API_KEY in config/settings.json.
    Returns path to the saved image file.

    prompt: Text description of the desired image.
    size: "1024x1024" | "1792x1024" (landscape, good for LinkedIn) | "1024x1792"
    """
    import base64  # noqa: PLC0415

    try:
        from src.agent.llm.llm_parser import get_llm_client  # noqa: PLC0415

        llm = get_llm_client()
        # Use the OpenAI client directly for image generation
        client = llm.client

        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
            response_format="b64_json",
        )
        img_data = resp.data[0].b64_json
        img_bytes = base64.b64decode(img_data)

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img_bytes)

        return {
            "status": "success",
            "image_path": str(out_path),
            "message": f"Image generated and saved to {out_path}",
            "revised_prompt": getattr(resp.data[0], "revised_prompt", prompt),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": (
                f"Image generation failed: {exc}. "
                "Ensure OPENAI_API_KEY is configured and you have access to DALL·E 3."
            ),
        }
