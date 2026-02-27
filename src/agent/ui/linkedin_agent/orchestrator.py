"""
LinkedIn skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
get_profile() – Retrieve the authenticated LinkedIn member's profile.
get_org_followers() – Get follower count for the connected organisation page.
get_page_analytics(start_date=None, end_date=None) – Get analytics for the organisation page.
create_text_post(text, visibility="PUBLIC") – Publish a plain-text LinkedIn post.
create_image_post(text, image_path, visibility="PUBLIC") – Publish a post with an image.
create_article_post(title, text, visibility="PUBLIC") – Publish a long-form article post.
delete_post(post_id) – Delete a published post.
list_published_posts(count=10) – List recently published posts and their IDs.
get_post_analytics(post_id) – Get likes, comments, shares and impressions for a post.
create_video_post(text, video_path, visibility="PUBLIC") – Publish a LinkedIn post with a video (MP4).
schedule_post(text, scheduled_time, post_type="text", image_path="", video_path="", article_url="", visibility="PUBLIC") – Queue a post for future publishing (scheduled_time: ISO 8601, e.g. "2026-03-01T10:00:00").
list_scheduled_posts() – List all pending scheduled posts.
cancel_scheduled_post(scheduled_id) – Cancel a pending scheduled post by its local ID.
get_access_token_url(state="") – Generate the LinkedIn OAuth2 authorisation URL (initial setup).
exchange_code_for_token(code) – Exchange an OAuth2 authorisation code for an access token (initial setup).
""".strip()

_SKILL_CONTEXT = """
You are the LinkedIn Skill Agent connected to the LinkedIn API.
Help the user manage their LinkedIn presence: view their profile, publish posts, analyse engagement.

Important:
- Require user confirmation before publishing any post.
- Suggest improvements to draft posts (tone, hashtags, call-to-action) if the user asks.
- LinkedIn API requires OAuth — if a tool returns an auth error, ask the user to re-authenticate.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.linkedin import linkedin_service as ls  # noqa: PLC0415

    return {
        "get_profile": lambda: ls.get_profile(),
        "get_org_followers": lambda: ls.get_org_followers(),
        "get_page_analytics": lambda start_date=None, end_date=None: ls.get_page_analytics(start_date, end_date),
        "create_text_post": lambda text, visibility="PUBLIC": ls.create_text_post(text, visibility),
        "create_image_post": lambda text, image_path, visibility="PUBLIC": ls.create_image_post(text, image_path, visibility),
        "create_article_post": lambda title, text, visibility="PUBLIC": ls.create_article_post(title, text, visibility),
        "delete_post": lambda post_id: ls.delete_post(post_id),
        "list_published_posts": lambda count=10: ls.list_published_posts(count),
        "get_post_analytics": lambda post_id: ls.get_post_analytics(post_id),
        "create_video_post": lambda text, video_path, visibility="PUBLIC": ls.create_video_post(text, video_path, visibility=visibility),
        "schedule_post": lambda text, scheduled_time, post_type="text", image_path="", video_path="", article_url="", article_title="", visibility="PUBLIC": ls.schedule_post(text, scheduled_time, post_type=post_type, image_path=image_path, video_path=video_path, article_url=article_url, article_title=article_title, visibility=visibility),
        "list_scheduled_posts": lambda: ls.list_scheduled_posts(),
        "cancel_scheduled_post": lambda scheduled_id: ls.cancel_scheduled_post(scheduled_id),
        "get_access_token_url": lambda state="": ls.get_access_token_url(state),
        "exchange_code_for_token": lambda code: ls.exchange_code_for_token(code),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="linkedin",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ LinkedIn skill error: {exc}",
            "action": "react_response",
        }
