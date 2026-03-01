"""
Configuration constants for the summarization bot.
Single source of truth for all default values.
"""

# Model Configuration
# Note: Using Haiku as default since it's reliably available on OpenRouter
# Users can configure other models via SUMMARIZATION_MODEL env var or /config command
# Updated 2026-01 to use current OpenRouter model IDs
DEFAULT_SUMMARIZATION_MODEL = "anthropic/claude-3-haiku"
DEFAULT_BRIEF_MODEL = "anthropic/claude-3-haiku"
DEFAULT_COMPREHENSIVE_MODEL = "anthropic/claude-sonnet-4.5"  # Best model for comprehensive summaries

# Valid model choices (current OpenRouter model IDs as of 2026-01)
# Also includes legacy names for backward compatibility
VALID_MODELS = [
    # Current OpenRouter format
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-3.7-sonnet",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3-haiku",
    "anthropic/claude-opus-4.5",
    "anthropic/claude-opus-4",
    # Legacy format (for backward compatibility)
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
]

# Model aliases for backward compatibility (old format -> new format)
MODEL_ALIASES = {
    "claude-3-haiku-20240307": "anthropic/claude-3-haiku",
    "claude-3-5-sonnet-20240620": "anthropic/claude-3.5-sonnet",
    "claude-3-5-sonnet-20241022": "anthropic/claude-3.5-sonnet",
    "claude-3-opus-20240229": "anthropic/claude-opus-4",
    "claude-3-sonnet-20240229": "anthropic/claude-3.5-sonnet",
}

# ADR-024: Model escalation chain for resilient summary generation
# Ordered from cheapest/fastest to most capable
MODEL_ESCALATION_CHAIN = [
    "anthropic/claude-3-haiku",      # Tier 1: Fast/cheap
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3.5-sonnet",   # Tier 2: Balanced
    "anthropic/claude-3.7-sonnet",
    "anthropic/claude-sonnet-4",     # Tier 3: Advanced
    "anthropic/claude-sonnet-4.5",   # Tier 4: Best available
]

# Starting model index by summary type
STARTING_MODEL_INDEX = {
    "brief": 0,       # Start with haiku
    "detailed": 2,    # Start with sonnet 3.5
    "comprehensive": 4,  # Start with sonnet 4
}

# Default retry configuration
DEFAULT_MAX_RETRY_ATTEMPTS = 7
DEFAULT_RETRY_COST_CAP_USD = 0.50
DEFAULT_MAX_TOKENS_CAP = 16000
