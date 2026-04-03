"""
Guild Prompt Templates API routes - ADR-034: Guild Prompt Templates.

Provides endpoints to manage guild-level prompt templates that can be
reused across scheduled summaries.
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..auth import get_current_user, require_guild_admin
from ..models import ErrorResponse
from . import get_discord_bot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guilds/{guild_id}/prompt-templates", tags=["Prompt Templates"])


# ============================================================================
# Pydantic models for API
# ============================================================================

from pydantic import BaseModel, Field


class PromptTemplateCreateRequest(BaseModel):
    """Request to create a prompt template."""
    name: str = Field(..., min_length=1, max_length=100, description="Template name")
    description: Optional[str] = Field(None, max_length=500, description="Template description")
    content: str = Field(..., min_length=10, description="The prompt template content")
    based_on_default: Optional[str] = Field(None, description="Default template this was seeded from")


class PromptTemplateUpdateRequest(BaseModel):
    """Request to update a prompt template."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = Field(None, min_length=10)


class PromptTemplateResponse(BaseModel):
    """Response for a single prompt template."""
    id: str
    guild_id: str
    name: str
    description: Optional[str]
    content: str
    based_on_default: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    usage_count: int = 0  # Number of schedules using this template


class PromptTemplatesListResponse(BaseModel):
    """Response for listing prompt templates."""
    templates: List[PromptTemplateResponse]
    total: int


class PromptTemplateUsageItem(BaseModel):
    """A schedule using this template."""
    schedule_id: str
    schedule_name: str


class PromptTemplateUsageResponse(BaseModel):
    """Response showing which schedules use a template."""
    template_id: str
    schedules: List[PromptTemplateUsageItem]
    total: int


class DuplicateTemplateRequest(BaseModel):
    """Request to duplicate a template."""
    new_name: str = Field(..., min_length=1, max_length=100, description="Name for the duplicated template")


# ============================================================================
# Helper functions
# ============================================================================

def _check_guild_access(guild_id: str, user: dict):
    """Check user has access to guild."""
    if guild_id not in user.get("guilds", []):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to manage this guild"},
        )


def _get_guild_or_404(guild_id: str):
    """Get guild from bot or raise 404."""
    bot = get_discord_bot()
    if not bot or not bot.client:
        raise HTTPException(
            status_code=503,
            detail={"code": "BOT_UNAVAILABLE", "message": "Discord bot not available"},
        )

    guild = bot.client.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Guild not found"},
        )

    return guild


async def _get_prompt_template_repository():
    """Get prompt template repository instance."""
    try:
        from ...data.repositories import get_prompt_template_repository
        return await get_prompt_template_repository()
    except RuntimeError:
        return None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "",
    response_model=PromptTemplatesListResponse,
    summary="List prompt templates",
    description="Get all prompt templates for a guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
    },
)
async def list_prompt_templates(
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """List all prompt templates for a guild."""
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        return PromptTemplatesListResponse(templates=[], total=0)

    templates = await repo.get_templates_by_guild(guild_id)

    # Get usage counts for each template
    template_responses = []
    for template in templates:
        usage_count = await repo.get_usage_count(template.id)
        template_responses.append(
            PromptTemplateResponse(
                id=template.id,
                guild_id=template.guild_id,
                name=template.name,
                description=template.description,
                content=template.content,
                based_on_default=template.based_on_default,
                created_by=template.created_by,
                created_at=template.created_at,
                updated_at=template.updated_at,
                usage_count=usage_count,
            )
        )

    return PromptTemplatesListResponse(
        templates=template_responses,
        total=len(template_responses),
    )


@router.post(
    "",
    response_model=PromptTemplateResponse,
    summary="Create prompt template",
    description="Create a new prompt template for the guild.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Guild not found"},
        409: {"model": ErrorResponse, "description": "Template name already exists"},
    },
)
async def create_prompt_template(
    body: PromptTemplateCreateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    user: dict = Depends(get_current_user),
):
    """Create a new prompt template."""
    _check_guild_access(guild_id, user)
    require_guild_admin(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        raise HTTPException(
            status_code=503,
            detail={"code": "REPOSITORY_UNAVAILABLE", "message": "Template repository not available"},
        )

    # Check if name already exists
    if await repo.template_name_exists(guild_id, body.name):
        raise HTTPException(
            status_code=409,
            detail={"code": "DUPLICATE_NAME", "message": f"A template named '{body.name}' already exists"},
        )

    from ...models.prompt_template import GuildPromptTemplate

    template = GuildPromptTemplate(
        guild_id=guild_id,
        name=body.name,
        description=body.description,
        content=body.content,
        based_on_default=body.based_on_default,
        created_by=user["sub"],
    )

    await repo.save_template(template)

    return PromptTemplateResponse(
        id=template.id,
        guild_id=template.guild_id,
        name=template.name,
        description=template.description,
        content=template.content,
        based_on_default=template.based_on_default,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        usage_count=0,
    )


@router.get(
    "/{template_id}",
    response_model=PromptTemplateResponse,
    summary="Get prompt template",
    description="Get a specific prompt template by ID.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Template not found"},
    },
)
async def get_prompt_template(
    guild_id: str = Path(..., description="Discord guild ID"),
    template_id: str = Path(..., description="Template ID"),
    user: dict = Depends(get_current_user),
):
    """Get a specific prompt template."""
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    template = await repo.get_template(template_id)
    if not template or template.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    usage_count = await repo.get_usage_count(template_id)

    return PromptTemplateResponse(
        id=template.id,
        guild_id=template.guild_id,
        name=template.name,
        description=template.description,
        content=template.content,
        based_on_default=template.based_on_default,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        usage_count=usage_count,
    )


@router.patch(
    "/{template_id}",
    response_model=PromptTemplateResponse,
    summary="Update prompt template",
    description="Update an existing prompt template.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Template not found"},
        409: {"model": ErrorResponse, "description": "Template name already exists"},
    },
)
async def update_prompt_template(
    body: PromptTemplateUpdateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    template_id: str = Path(..., description="Template ID"),
    user: dict = Depends(get_current_user),
):
    """Update a prompt template."""
    _check_guild_access(guild_id, user)
    require_guild_admin(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    template = await repo.get_template(template_id)
    if not template or template.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    # Check if new name already exists (if name is being changed)
    if body.name and body.name != template.name:
        if await repo.template_name_exists(guild_id, body.name):
            raise HTTPException(
                status_code=409,
                detail={"code": "DUPLICATE_NAME", "message": f"A template named '{body.name}' already exists"},
            )

    # Update fields
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.content is not None:
        updates["content"] = body.content

    if updates:
        template.update(**updates)
        await repo.save_template(template)

    usage_count = await repo.get_usage_count(template_id)

    return PromptTemplateResponse(
        id=template.id,
        guild_id=template.guild_id,
        name=template.name,
        description=template.description,
        content=template.content,
        based_on_default=template.based_on_default,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        usage_count=usage_count,
    )


@router.delete(
    "/{template_id}",
    summary="Delete prompt template",
    description="Delete a prompt template. Will fail if schedules are using it.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Template not found"},
        409: {"model": ErrorResponse, "description": "Template is in use"},
    },
)
async def delete_prompt_template(
    guild_id: str = Path(..., description="Discord guild ID"),
    template_id: str = Path(..., description="Template ID"),
    force: bool = Query(False, description="Force delete even if in use (sets schedule template to null)"),
    user: dict = Depends(get_current_user),
):
    """Delete a prompt template."""
    _check_guild_access(guild_id, user)
    require_guild_admin(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    template = await repo.get_template(template_id)
    if not template or template.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    # Check if template is in use
    usage_count = await repo.get_usage_count(template_id)
    if usage_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TEMPLATE_IN_USE",
                "message": f"Template is used by {usage_count} schedule(s). Use force=true to delete anyway.",
            },
        )

    await repo.delete_template(template_id)
    return {"success": True}


@router.get(
    "/{template_id}/usage",
    response_model=PromptTemplateUsageResponse,
    summary="Get template usage",
    description="Get list of schedules using this template.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Template not found"},
    },
)
async def get_template_usage(
    guild_id: str = Path(..., description="Discord guild ID"),
    template_id: str = Path(..., description="Template ID"),
    user: dict = Depends(get_current_user),
):
    """Get list of schedules using this template."""
    _check_guild_access(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    template = await repo.get_template(template_id)
    if not template or template.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    usage = await repo.get_template_usage(template_id)

    schedules = [
        PromptTemplateUsageItem(
            schedule_id=item["schedule_id"],
            schedule_name=item["schedule_name"],
        )
        for item in usage
    ]

    return PromptTemplateUsageResponse(
        template_id=template_id,
        schedules=schedules,
        total=len(schedules),
    )


@router.post(
    "/{template_id}/duplicate",
    response_model=PromptTemplateResponse,
    summary="Duplicate template",
    description="Create a copy of an existing template.",
    responses={
        403: {"model": ErrorResponse, "description": "No permission"},
        404: {"model": ErrorResponse, "description": "Template not found"},
        409: {"model": ErrorResponse, "description": "New name already exists"},
    },
)
async def duplicate_prompt_template(
    body: DuplicateTemplateRequest,
    guild_id: str = Path(..., description="Discord guild ID"),
    template_id: str = Path(..., description="Template ID to duplicate"),
    user: dict = Depends(get_current_user),
):
    """Duplicate a prompt template."""
    _check_guild_access(guild_id, user)
    require_guild_admin(guild_id, user)
    _get_guild_or_404(guild_id)

    repo = await _get_prompt_template_repository()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    template = await repo.get_template(template_id)
    if not template or template.guild_id != guild_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Template not found"},
        )

    # Check if new name already exists
    if await repo.template_name_exists(guild_id, body.new_name):
        raise HTTPException(
            status_code=409,
            detail={"code": "DUPLICATE_NAME", "message": f"A template named '{body.new_name}' already exists"},
        )

    new_template = await repo.duplicate_template(template_id, body.new_name, user["sub"])

    return PromptTemplateResponse(
        id=new_template.id,
        guild_id=new_template.guild_id,
        name=new_template.name,
        description=new_template.description,
        content=new_template.content,
        based_on_default=new_template.based_on_default,
        created_by=new_template.created_by,
        created_at=new_template.created_at,
        updated_at=new_template.updated_at,
        usage_count=0,
    )
