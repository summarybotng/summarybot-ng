"""
Issue Tracker API Routes (ADR-070)

Public issue submission for users to report bugs, features, and questions.
Integrated with audit logging (ADR-045).
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query

from ..models import (
    CreateIssueRequest,
    CreateIssueResponse,
    IssueResponse,
    IssueListResponse,
    IssueConfigResponse,
)

logger = logging.getLogger(__name__)


async def _audit_issue_event(
    event_type: str,
    request: Request,
    issue_id: Optional[str] = None,
    issue_type: Optional[str] = None,
    guild_id: Optional[str] = None,
    user_id: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    details: Optional[dict] = None,
):
    """Log an issue tracker event to the audit log."""
    try:
        from ...logging import get_audit_service
        service = await get_audit_service()

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

        await service.log(
            event_type,
            user_id=user_id,
            guild_id=guild_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            details={
                "issue_id": issue_id,
                "issue_type": issue_type,
                **(details or {}),
            },
        )
    except Exception as e:
        logger.warning(f"Failed to log audit event: {e}")

router = APIRouter(prefix="/issues", tags=["issues"])

# Configuration
ISSUE_TRACKER_URL = "https://github.com/summarybotng/summarybot-ng/issues"
ISSUE_TRACKER_ENABLED = True


async def get_issue_repository():
    """Get the issue repository instance."""
    try:
        from ...data.repositories import get_issue_repository as _get_repo
        return await _get_repo()
    except RuntimeError:
        return None


@router.get("/config", response_model=IssueConfigResponse)
async def get_issue_config():
    """Get issue tracker configuration."""
    return IssueConfigResponse(
        enabled=ISSUE_TRACKER_ENABLED,
        github_url=ISSUE_TRACKER_URL,
        allow_local=True,
    )


@router.post("", response_model=CreateIssueResponse)
async def create_issue(
    request: Request,
    body: CreateIssueRequest,
    guild_id: Optional[str] = Query(None, description="Guild context for the issue"),
):
    """
    Submit a local issue.

    For users without GitHub accounts who want to report bugs or request features.
    Issues are stored locally and can be replicated to GitHub by admins.
    """
    if not ISSUE_TRACKER_ENABLED:
        raise HTTPException(status_code=503, detail="Issue tracker is disabled")

    # Get reporter Discord ID if authenticated
    reporter_discord_id = None
    if hasattr(request.state, "user") and request.state.user:
        reporter_discord_id = request.state.user.id

    repo = await get_issue_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Issue tracker unavailable")

    try:
        issue = await repo.create_issue(
            title=body.title,
            description=body.description,
            issue_type=body.issue_type.value,
            guild_id=guild_id,
            reporter_email=body.email,
            reporter_discord_id=reporter_discord_id,
            page_url=body.page_url,
            browser_info=body.browser_info,
            app_version=body.app_version,
        )

        logger.info(f"Issue {issue.id} created: {body.issue_type.value} - {body.title[:50]}")

        # Audit log the issue creation (ADR-045)
        await _audit_issue_event(
            "issue.created",
            request,
            issue_id=issue.id,
            issue_type=body.issue_type.value,
            guild_id=guild_id,
            user_id=reporter_discord_id,
            success=True,
            details={
                "title": body.title[:100],
                "page_url": body.page_url,
            },
        )

        return CreateIssueResponse(
            success=True,
            id=issue.id,
            message="Issue submitted successfully. Thank you for your feedback!",
            github_url=None,
        )
    except Exception as e:
        logger.error(f"Failed to create issue: {e}")
        # Audit log the failure
        await _audit_issue_event(
            "issue.create_failed",
            request,
            issue_type=body.issue_type.value,
            guild_id=guild_id,
            user_id=reporter_discord_id,
            success=False,
            error_message=str(e)[:200],
        )
        raise HTTPException(status_code=500, detail="Failed to submit issue")


@router.get("", response_model=IssueListResponse)
async def list_issues(
    request: Request,
    guild_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    issue_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List local issues (admin only in future).

    For now, returns issues for the specified guild or all issues if no guild specified.
    """
    repo = await get_issue_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Issue tracker unavailable")

    try:
        issues, total = await repo.list_issues(
            guild_id=guild_id,
            status=status,
            issue_type=issue_type,
            limit=limit,
            offset=offset,
        )

        return IssueListResponse(
            issues=[
                IssueResponse(
                    id=issue.id,
                    guild_id=issue.guild_id,
                    title=issue.title,
                    description=issue.description,
                    issue_type=issue.issue_type,
                    reporter_email=None,  # Hide email in list
                    page_url=issue.page_url,
                    browser_info=issue.browser_info,
                    app_version=issue.app_version,
                    status=issue.status,
                    github_issue_url=issue.github_issue_url,
                    created_at=issue.created_at,
                )
                for issue in issues
            ],
            total=total,
        )
    except Exception as e:
        logger.error(f"Failed to list issues: {e}")
        raise HTTPException(status_code=500, detail="Failed to list issues")


@router.get("/github-url")
async def get_github_issue_url(
    issue_type: str = Query("bug", description="Issue type: bug, feature, question"),
    title: Optional[str] = Query(None, description="Pre-filled title"),
    page_url: Optional[str] = Query(None, description="Page URL for context"),
    app_version: Optional[str] = Query(None, description="App version"),
):
    """
    Generate a GitHub issue URL with pre-filled template.

    Returns a URL that opens GitHub's new issue page with context filled in.
    """
    # Map issue type to template
    template_map = {
        "bug": "bug_report.md",
        "feature": "feature_request.md",
        "question": "question.md",
    }
    template = template_map.get(issue_type, "bug_report.md")

    # Build body with context
    body_parts = []
    if page_url:
        body_parts.append(f"**Page:** {page_url}")
    if app_version:
        body_parts.append(f"**App Version:** {app_version}")
    if body_parts:
        body_parts.append("")
        body_parts.append("---")
        body_parts.append("")

    body = "\n".join(body_parts)

    # Build URL
    from urllib.parse import urlencode
    params = {"template": template}
    if title:
        params["title"] = title
    if body:
        params["body"] = body

    github_url = f"{ISSUE_TRACKER_URL}/new?{urlencode(params)}"

    return {"url": github_url}
