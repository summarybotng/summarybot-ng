"""
Prompts API routes - ADR-010: Prompt Repository Navigation.

Provides endpoints to view default and custom prompts.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path

router = APIRouter(prefix="/prompts", tags=["prompts"])


class DefaultPrompt(BaseModel):
    """A default prompt template."""
    name: str
    category: str
    description: str
    content: str


class DefaultPromptsResponse(BaseModel):
    """Response containing all default prompts."""
    prompts: List[DefaultPrompt]


# Descriptions for each prompt category
PROMPT_DESCRIPTIONS = {
    "default": "General-purpose summary prompt used when no specific category applies",
    "discussion": "Optimized for casual discussions and conversations",
    "meeting": "Structured for meeting notes with action items and decisions",
    "moderation": "Focused on identifying issues and moderation-relevant content",
}


@router.get("/defaults", response_model=DefaultPromptsResponse)
async def get_default_prompts() -> DefaultPromptsResponse:
    """
    Get all default prompt templates.

    Returns the built-in prompts that SummaryBot uses when no custom
    prompts are configured.
    """
    defaults_dir = Path(__file__).parent.parent.parent / "prompts" / "defaults"

    prompts = []

    if not defaults_dir.exists():
        raise HTTPException(status_code=500, detail="Default prompts directory not found")

    for prompt_file in sorted(defaults_dir.glob("*.md")):
        name = prompt_file.stem
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            prompts.append(DefaultPrompt(
                name=name,
                category=name,
                description=PROMPT_DESCRIPTIONS.get(name, f"Prompt template for {name} category"),
                content=content,
            ))
        except Exception as e:
            # Skip files that can't be read
            continue

    return DefaultPromptsResponse(prompts=prompts)


@router.get("/defaults/{category}", response_model=DefaultPrompt)
async def get_default_prompt(category: str) -> DefaultPrompt:
    """
    Get a specific default prompt by category.

    Args:
        category: The prompt category (e.g., "default", "discussion", "meeting")
    """
    defaults_dir = Path(__file__).parent.parent.parent / "prompts" / "defaults"
    prompt_file = defaults_dir / f"{category}.md"

    if not prompt_file.exists():
        raise HTTPException(status_code=404, detail=f"Prompt category '{category}' not found")

    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return DefaultPrompt(
            name=category,
            category=category,
            description=PROMPT_DESCRIPTIONS.get(category, f"Prompt template for {category} category"),
            content=content,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read prompt: {str(e)}")
