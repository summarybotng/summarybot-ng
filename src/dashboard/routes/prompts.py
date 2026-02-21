"""
Prompts API routes - ADR-010: Prompt Repository Navigation.

Provides endpoints to view default and custom prompts.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from pathlib import Path

router = APIRouter(prefix="/prompts", tags=["prompts"])


class DefaultPrompt(BaseModel):
    """A default prompt template."""
    name: str
    category: str
    description: str
    content: str
    file_path: Optional[str] = None


class PerspectiveLength(BaseModel):
    """A prompt for a specific perspective and length."""
    name: str
    file_path: str
    content: str
    description: str


class Perspective(BaseModel):
    """A perspective with its available lengths."""
    description: str
    lengths: Dict[str, PerspectiveLength]


class DefaultPromptsResponse(BaseModel):
    """Response containing all default prompts."""
    prompts: List[DefaultPrompt]
    perspectives: Dict[str, Perspective]


# Descriptions for each prompt category
PROMPT_DESCRIPTIONS = {
    "default": "General-purpose summary prompt used when no specific category applies",
    "discussion": "Optimized for casual discussions and conversations",
    "meeting": "Structured for meeting notes with action items and decisions",
    "moderation": "Focused on identifying issues and moderation-relevant content",
}

PERSPECTIVE_DESCRIPTIONS = {
    "general": "Balanced summaries for general audiences",
    "developer": "Technical focus on code, architecture, and engineering",
    "marketing": "Customer insights, sentiment, and market opportunities",
    "executive": "Strategic decisions, risks, and business impact",
    "support": "Issue tracking, troubleshooting, and customer support",
}

LENGTH_DESCRIPTIONS = {
    "brief": "Concise 2-3 paragraph summary of key points only",
    "detailed": "Thorough coverage of topics, decisions, and context",
    "comprehensive": "Complete documentation with full analysis",
}


@router.get("/defaults", response_model=DefaultPromptsResponse)
async def get_default_prompts() -> DefaultPromptsResponse:
    """
    Get all default prompt templates.

    Returns the built-in prompts that SummaryBot uses when no custom
    prompts are configured, organized by:
    - Category prompts (discussion, meeting, moderation)
    - Perspective/length prompts (developer/brief, marketing/detailed, etc.)
    """
    defaults_dir = Path(__file__).parent.parent.parent / "prompts" / "defaults"

    prompts = []
    perspectives = {}

    if not defaults_dir.exists():
        raise HTTPException(status_code=500, detail="Default prompts directory not found")

    # Load flat category prompts
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
                file_path=f"defaults/{name}.md",
            ))
        except Exception:
            continue

    # Load hierarchical perspective/length prompts
    for perspective_dir in sorted(defaults_dir.iterdir()):
        if perspective_dir.is_dir():
            perspective_name = perspective_dir.name
            lengths = {}

            for prompt_file in sorted(perspective_dir.glob("*.md")):
                length_name = prompt_file.stem
                try:
                    with open(prompt_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    lengths[length_name] = PerspectiveLength(
                        name=length_name,
                        file_path=f"defaults/{perspective_name}/{length_name}.md",
                        content=content,
                        description=LENGTH_DESCRIPTIONS.get(length_name, f"{length_name.capitalize()} summary"),
                    )
                except Exception:
                    continue

            if lengths:
                perspectives[perspective_name] = Perspective(
                    description=PERSPECTIVE_DESCRIPTIONS.get(
                        perspective_name, f"Summaries from {perspective_name} perspective"
                    ),
                    lengths=lengths,
                )

    return DefaultPromptsResponse(prompts=prompts, perspectives=perspectives)


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
