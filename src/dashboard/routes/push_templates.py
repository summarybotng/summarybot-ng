"""
Push Template API routes for ADR-014: Discord Push Templates.

Provides endpoints for managing guild-specific push templates.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..auth import get_current_user, User
from ...models.push_template import (
    PushTemplate, DEFAULT_PUSH_TEMPLATE, validate_template,
    SectionConfig,
)
from ...data.push_template_repository import get_push_template_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guilds/{guild_id}/push-template", tags=["Push Templates"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SectionConfigRequest(BaseModel):
    """Section configuration in request."""
    type: str
    enabled: bool = True
    max_items: int = Field(default=10, ge=1, le=50)
    title_override: str | None = None
    combine_with_previous: bool = False


class PushTemplateRequest(BaseModel):
    """Push template configuration request."""
    use_thread: bool = True
    thread_name_format: str = "Summary: {scope} ({date_range})"
    thread_auto_archive_minutes: int = Field(default=1440, description="60, 1440, 4320, or 10080")
    header_format: str = "📋 **Summary: {scope}**"
    show_date_range: bool = True
    show_stats: bool = True
    show_summary_text: bool = True
    sections: list[SectionConfigRequest] = Field(default_factory=list)
    include_references: bool = True
    include_jump_links: bool = True
    reference_style: str = "numbered"
    use_embeds: bool = True
    embed_color: int = Field(default=0x4A90E2, ge=0, le=0xFFFFFF)


class PushTemplateResponse(BaseModel):
    """Push template response."""
    guild_id: str
    is_custom: bool  # True if guild has custom template, False if using default
    template: Dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None


class PreviewRequest(BaseModel):
    """Preview request with sample data."""
    template: PushTemplateRequest | None = None
    # Sample data for preview
    channel_names: list[str] = Field(default=["general"])
    message_count: int = 100
    participant_count: int = 10


# ============================================================================
# Routes
# ============================================================================

@router.get("", response_model=PushTemplateResponse)
async def get_push_template(
    guild_id: str,
    user: User = Depends(get_current_user),
) -> PushTemplateResponse:
    """Get the push template for a guild.

    Returns the guild's custom template if configured, otherwise the default.
    """
    # Check user has access to guild
    if guild_id not in [g["id"] for g in user.guilds]:
        raise HTTPException(status_code=403, detail="Access denied to this guild")

    repo = await get_push_template_repository()
    guild_template = await repo.get_guild_template(guild_id)

    if guild_template:
        return PushTemplateResponse(
            guild_id=guild_id,
            is_custom=True,
            template=guild_template.template.to_dict(),
            created_at=guild_template.created_at.isoformat(),
            updated_at=guild_template.updated_at.isoformat(),
            created_by=guild_template.created_by,
        )
    else:
        return PushTemplateResponse(
            guild_id=guild_id,
            is_custom=False,
            template=DEFAULT_PUSH_TEMPLATE.to_dict(),
        )


@router.put("", response_model=PushTemplateResponse)
async def set_push_template(
    guild_id: str,
    request: PushTemplateRequest,
    user: User = Depends(get_current_user),
) -> PushTemplateResponse:
    """Set a custom push template for a guild."""
    # Check user has access to guild
    if guild_id not in [g["id"] for g in user.guilds]:
        raise HTTPException(status_code=403, detail="Access denied to this guild")

    # Convert request to PushTemplate
    sections = [
        SectionConfig(
            type=s.type,
            enabled=s.enabled,
            max_items=s.max_items,
            title_override=s.title_override,
            combine_with_previous=s.combine_with_previous,
        )
        for s in request.sections
    ] if request.sections else None

    template = PushTemplate(
        schema_version=1,
        use_thread=request.use_thread,
        thread_name_format=request.thread_name_format,
        thread_auto_archive_minutes=request.thread_auto_archive_minutes,
        header_format=request.header_format,
        show_date_range=request.show_date_range,
        show_stats=request.show_stats,
        show_summary_text=request.show_summary_text,
        sections=sections if sections else DEFAULT_PUSH_TEMPLATE.sections,
        include_references=request.include_references,
        include_jump_links=request.include_jump_links,
        reference_style=request.reference_style,
        use_embeds=request.use_embeds,
        embed_color=request.embed_color,
    )

    # Validate
    errors = validate_template(template)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Save
    repo = await get_push_template_repository()
    success = await repo.set_template(guild_id, template, user_id=user.id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save template")

    # Return updated template
    guild_template = await repo.get_guild_template(guild_id)
    return PushTemplateResponse(
        guild_id=guild_id,
        is_custom=True,
        template=guild_template.template.to_dict(),
        created_at=guild_template.created_at.isoformat(),
        updated_at=guild_template.updated_at.isoformat(),
        created_by=guild_template.created_by,
    )


@router.delete("")
async def delete_push_template(
    guild_id: str,
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete guild's custom template (reverts to default)."""
    # Check user has access to guild
    if guild_id not in [g["id"] for g in user.guilds]:
        raise HTTPException(status_code=403, detail="Access denied to this guild")

    repo = await get_push_template_repository()
    deleted = await repo.delete_template(guild_id)

    return {
        "deleted": deleted,
        "message": "Template deleted, now using default" if deleted else "No custom template found",
    }


@router.post("/preview")
async def preview_push_template(
    guild_id: str,
    request: PreviewRequest,
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Preview what a push would look like with the template.

    Returns the messages that would be sent without actually sending them.
    """
    # Check user has access to guild
    if guild_id not in [g["id"] for g in user.guilds]:
        raise HTTPException(status_code=403, detail="Access denied to this guild")

    from ...models.summary import SummaryResult, Participant
    from ...services.push_message_builder import PushMessageBuilder, PushContext
    from datetime import datetime, timedelta

    # Get template (use request template or guild's current template)
    if request.template:
        sections = [
            SectionConfig(
                type=s.type,
                enabled=s.enabled,
                max_items=s.max_items,
                title_override=s.title_override,
                combine_with_previous=s.combine_with_previous,
            )
            for s in request.template.sections
        ] if request.template.sections else None

        template = PushTemplate(
            schema_version=1,
            use_thread=request.template.use_thread,
            thread_name_format=request.template.thread_name_format,
            thread_auto_archive_minutes=request.template.thread_auto_archive_minutes,
            header_format=request.template.header_format,
            show_date_range=request.template.show_date_range,
            show_stats=request.template.show_stats,
            show_summary_text=request.template.show_summary_text,
            sections=sections if sections else DEFAULT_PUSH_TEMPLATE.sections,
            include_references=request.template.include_references,
            include_jump_links=request.template.include_jump_links,
            reference_style=request.template.reference_style,
            use_embeds=request.template.use_embeds,
            embed_color=request.template.embed_color,
        )
    else:
        repo = await get_push_template_repository()
        template = await repo.get_template(guild_id)

    # Create sample summary
    now = datetime.utcnow()
    sample_summary = SummaryResult(
        id="preview-sample",
        guild_id=guild_id,
        channel_id="123456789",
        start_time=now - timedelta(hours=24),
        end_time=now,
        message_count=request.message_count,
        summary_text="This is a sample summary preview. The team discussed project milestones, reviewed code changes, and planned upcoming features. Several decisions were made about the architecture.",
        key_points=[
            "First key point from the discussion",
            "Second important topic that was covered",
            "Third point about technical decisions",
        ],
        participants=[
            Participant(
                user_id=str(i),
                display_name=f"User{i}",
                message_count=request.message_count // request.participant_count,
            )
            for i in range(min(request.participant_count, 5))
        ],
    )

    # Build preview context
    context = PushContext(
        guild_id=guild_id,
        channel_names=request.channel_names,
        start_time=sample_summary.start_time,
        end_time=sample_summary.end_time,
        message_count=request.message_count,
        participant_count=request.participant_count,
    )

    # Build messages
    builder = PushMessageBuilder(template)
    messages = builder.build_all_messages(sample_summary, context)

    return {
        "thread_name": builder.build_thread_name(context) if template.use_thread else None,
        "message_count": len(messages),
        "messages": [
            {
                "content": msg.content,
                "is_thread_starter": msg.is_thread_starter,
            }
            for msg in messages
        ],
    }
