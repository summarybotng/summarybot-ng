"""
Claude API client for AI summarization.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import anthropic
from anthropic import AsyncAnthropic

from ..exceptions import (
    ClaudeAPIError, TokenLimitExceededError, ModelUnavailableError,
    RateLimitError, AuthenticationError, NetworkError, TimeoutError
)
from ..models.base import BaseModel
from ..config.constants import DEFAULT_SUMMARIZATION_MODEL


@dataclass
class ClaudeOptions(BaseModel):
    """Options for Claude API requests."""
    model: str = DEFAULT_SUMMARIZATION_MODEL
    max_tokens: int = 4000
    temperature: float = 0.3
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: List[str] = field(default_factory=list)
    stream: bool = False


@dataclass
class ClaudeResponse(BaseModel):
    """Response from Claude API."""
    content: str
    model: str
    usage: Dict[str, int]
    stop_reason: str
    response_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    fallback_info: Dict[str, Any] = field(default_factory=dict)  # Tracks model fallback details
    
    @property
    def input_tokens(self) -> int:
        """Get input token count."""
        return self.usage.get("input_tokens", 0)
    
    @property
    def output_tokens(self) -> int:
        """Get output token count."""
        return self.usage.get("output_tokens", 0)
    
    @property
    def total_tokens(self) -> int:
        """Get total token count."""
        return self.input_tokens + self.output_tokens
    
    def is_complete(self) -> bool:
        """Check if response was completed (not truncated)."""
        return self.stop_reason != "max_tokens"


@dataclass
class UsageStats(BaseModel):
    """Claude API usage statistics."""
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    errors_count: int = 0
    rate_limit_hits: int = 0
    last_request_time: Optional[datetime] = None
    
    def add_request(self, response: ClaudeResponse, cost: float = 0.0):
        """Add a successful request to stats."""
        self.total_requests += 1
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens
        self.total_cost_usd += cost
        self.last_request_time = datetime.utcnow()
    
    def add_error(self, is_rate_limit: bool = False):
        """Add an error to stats."""
        self.errors_count += 1
        if is_rate_limit:
            self.rate_limit_hits += 1


class ClaudeClient:
    """Client for interacting with Claude API."""
    
    # Token costs per model (input, output) per 1K tokens in USD
    MODEL_COSTS = {
        "claude-3-sonnet-20240229": (0.003, 0.015),
        "claude-3-opus-20240229": (0.015, 0.075),
        "claude-3-haiku-20240307": (0.00025, 0.00125),
        "claude-3-5-sonnet-20240620": (0.003, 0.015),
        "claude-3-5-sonnet-20241022": (0.003, 0.015),  # Latest Sonnet 3.5
    }
    
    def __init__(self, api_key: str, base_url: Optional[str] = None,
                 default_timeout: int = 120, max_retries: int = 3):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key
            base_url: Optional custom base URL
            default_timeout: Default request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.api_key = api_key
        self.base_url = base_url
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.usage_stats = UsageStats()

        # Detect if using OpenRouter
        self.is_openrouter = base_url and 'openrouter' in base_url.lower()

        # Log key being used (masked)
        if api_key and len(api_key) > 10:
            masked_key = f"{api_key[:10]}...{api_key[-4:]}"
            logger.info(f"ClaudeClient initialized with API key: {masked_key}, base_url: {base_url}")

        # Initialize async client
        client_kwargs = {"api_key": api_key, "timeout": default_timeout}
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = AsyncAnthropic(**client_kwargs)

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 0.1  # Minimum seconds between requests

    # Fallback model preferences for comprehensive summaries (in priority order)
    # Updated 2026-01 to match current OpenRouter model IDs
    COMPREHENSIVE_MODEL_FALLBACKS = [
        'anthropic/claude-sonnet-4.5',   # Latest Sonnet
        'anthropic/claude-sonnet-4',     # Sonnet 4
        'anthropic/claude-3.7-sonnet',   # Sonnet 3.7
        'anthropic/claude-3.5-sonnet',   # Sonnet 3.5
        'anthropic/claude-3.5-haiku',    # Haiku 3.5 (fallback)
        'anthropic/claude-3-haiku',      # Haiku 3 (last resort)
    ]

    async def close(self):
        """Close the Claude client and cleanup resources.

        This is a cleanup method for lifecycle management.
        The AsyncAnthropic client handles its own cleanup internally.
        """
        # The AsyncAnthropic client doesn't require explicit cleanup
        # This method exists for compatibility with container lifecycle
        pass

    async def get_available_models(self) -> List[str]:
        """Query OpenRouter for available Claude models.

        Returns:
            List of available model IDs
        """
        if not self.is_openrouter:
            return list(self.MODEL_COSTS.keys())

        import httpx
        import logging
        logger = logging.getLogger(__name__)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    models = [m['id'] for m in data.get('data', []) if 'claude' in m['id'].lower()]
                    logger.info(f"OpenRouter available Claude models: {models}")
                    return models
                else:
                    logger.warning(f"Failed to fetch OpenRouter models: {response.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching OpenRouter models: {e}")

        # Return default fallback list if query fails
        return self.COMPREHENSIVE_MODEL_FALLBACKS

    async def find_available_model(self, preferred_models: List[str]) -> Optional[str]:
        """Find the first available model from a list of preferences.

        Args:
            preferred_models: List of model IDs in priority order

        Returns:
            First available model ID, or None if none available
        """
        available = await self.get_available_models()
        available_set = set(available)

        for model in preferred_models:
            if model in available_set:
                return model

        return None

    def _normalize_model_name(self, model: str) -> str:
        """Normalize model name for the current provider.

        When using OpenRouter, converts to OpenRouter format (e.g., 'anthropic/claude-3-sonnet').
        When using Claude Direct, uses dated format (e.g., 'claude-3-sonnet-20240229').

        Args:
            model: Model name (e.g., 'claude-3-sonnet-20240229' or 'anthropic/claude-3-sonnet')

        Returns:
            Normalized model name for the current provider
        """
        # Mapping from old Claude Direct model names to current OpenRouter model IDs
        # Updated 2026-01 to use current OpenRouter model IDs
        openrouter_model_map = {
            'claude-3-sonnet-20240229': 'anthropic/claude-3.5-sonnet',
            'claude-3-opus-20240229': 'anthropic/claude-opus-4',
            'claude-3-haiku-20240307': 'anthropic/claude-3-haiku',
            'claude-3-5-sonnet-20240620': 'anthropic/claude-3.5-sonnet',
            'claude-3-5-sonnet-20241022': 'anthropic/claude-3.5-sonnet',
        }

        if self.is_openrouter:
            # OpenRouter requires provider prefix and no date suffix
            # If model is already in OpenRouter format, return as-is
            if model.startswith('anthropic/') or model.startswith('openrouter/'):
                return model

            # Try to map from Claude Direct format to OpenRouter format
            if model in openrouter_model_map:
                return openrouter_model_map[model]

            # Fallback: add prefix and remove date suffix pattern
            # Remove patterns like -YYYYMMDD or -YYYYMMDD
            import re
            base_model = re.sub(r'-\d{8}$', '', model)
            return f'anthropic/{base_model}'
        else:
            # Claude Direct doesn't use provider prefix
            if model.startswith('anthropic/'):
                return model.replace('anthropic/', '', 1)
            return model

    async def create_summary(self, 
                            prompt: str,
                            system_prompt: str,
                            options: ClaudeOptions) -> ClaudeResponse:
        """Create a summary using Claude API.
        
        Args:
            prompt: User prompt with content to summarize
            system_prompt: System prompt with instructions
            options: API request options
            
        Returns:
            ClaudeResponse with generated summary
            
        Raises:
            ClaudeAPIError: If API request fails
            TokenLimitExceededError: If response exceeds token limit
            ModelUnavailableError: If requested model is unavailable
        """
        # Apply rate limiting
        await self._apply_rate_limiting()

        # Normalize model name for current provider
        normalized_model = self._normalize_model_name(options.model)

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"ClaudeClient: Original model={options.model}, Normalized model={normalized_model}, Is OpenRouter={self.is_openrouter}")

        # Validate model (check base model name without provider prefix)
        # Skip validation for openrouter/* models (they use dynamic routing)
        if not options.model.startswith('openrouter/'):
            base_model = options.model.replace('anthropic/', '')
            if base_model not in self.MODEL_COSTS:
                available_models = ", ".join(self.MODEL_COSTS.keys())
                raise ModelUnavailableError(
                    options.model,
                    context={"available_models": available_models}
                )

        # Prepare request parameters with normalized model
        request_params = self._build_request_params(prompt, system_prompt, options, normalized_model)
        
        # Execute request with retries
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._make_request(request_params, attempt)

                # Process successful response (use normalized model name)
                claude_response = self._process_response(response, normalized_model)

                # Log successful response with actual model used
                logger.info(
                    f"Summary created successfully: model={claude_response.model}, "
                    f"tokens={claude_response.input_tokens} in + {claude_response.output_tokens} out, "
                    f"cost=${self._calculate_cost(claude_response):.4f}"
                )

                # Update usage stats
                cost = self._calculate_cost(claude_response)
                self.usage_stats.add_request(claude_response, cost)

                return claude_response
                
            except anthropic.RateLimitError as e:
                self.usage_stats.add_error(is_rate_limit=True)
                
                if attempt < self.max_retries:
                    retry_after = self._extract_retry_after(e)
                    await asyncio.sleep(retry_after)
                    continue
                
                raise RateLimitError(
                    api_name="Claude",
                    retry_after=retry_after,
                    limit_type="requests"
                )
                
            except anthropic.AuthenticationError as e:
                self.usage_stats.add_error()
                raise AuthenticationError("Claude", str(e))
                
            except anthropic.APITimeoutError as e:
                self.usage_stats.add_error()
                
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                
                raise TimeoutError("Claude", self.default_timeout)
                
            except anthropic.APIConnectionError as e:
                self.usage_stats.add_error()
                
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                raise NetworkError("Claude", str(e))
                
            except anthropic.NotFoundError as e:
                self.usage_stats.add_error()
                error_message = str(e)
                logger.error(f"NotFoundError from API: {error_message}")
                logger.error(f"Request was for model: {normalized_model}, base_url: {self.base_url}")

                raise ModelUnavailableError(
                    normalized_model,
                    context={
                        "error": error_message,
                        "base_url": self.base_url,
                        "is_openrouter": self.is_openrouter
                    }
                )

            except anthropic.BadRequestError as e:
                self.usage_stats.add_error()

                # Check for specific error types
                error_message = str(e)
                if "maximum context length" in error_message.lower():
                    raise ClaudeAPIError(
                        message="Prompt exceeds maximum context length",
                        api_error_code="context_length_exceeded"
                    )

                raise ClaudeAPIError(
                    message=f"Bad request: {error_message}",
                    api_error_code="bad_request"
                )

            except Exception as e:
                self.usage_stats.add_error()
                
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                raise ClaudeAPIError(
                    message=f"Unexpected error: {str(e)}",
                    api_error_code="unexpected_error",
                    cause=e
                )
        
        # Should not reach here due to loop logic
        raise ClaudeAPIError("Max retries exceeded", "max_retries_exceeded")

    async def create_summary_with_fallback(self,
                                           prompt: str,
                                           system_prompt: str,
                                           options: ClaudeOptions,
                                           fallback_models: Optional[List[str]] = None) -> ClaudeResponse:
        """Create a summary with automatic fallback to alternative models.

        Args:
            prompt: User prompt with content to summarize
            system_prompt: System prompt with instructions
            options: API request options
            fallback_models: Optional list of fallback model IDs to try

        Returns:
            ClaudeResponse with generated summary
        """
        import logging
        logger = logging.getLogger(__name__)

        # Use default fallbacks if none provided
        if fallback_models is None:
            fallback_models = self.COMPREHENSIVE_MODEL_FALLBACKS

        # Build list of models to try (preferred first, then fallbacks)
        models_to_try = [self._normalize_model_name(options.model)]
        for fallback in fallback_models:
            normalized = self._normalize_model_name(fallback) if not fallback.startswith('anthropic/') else fallback
            if normalized not in models_to_try:
                models_to_try.append(normalized)

        last_error = None
        tried_models = []
        original_model = models_to_try[0] if models_to_try else options.model

        for model in models_to_try:
            tried_models.append(model)
            try:
                # Create new options with the current model
                current_options = ClaudeOptions(
                    model=model if model.startswith('anthropic/') else options.model,
                    max_tokens=options.max_tokens,
                    temperature=options.temperature,
                    top_p=options.top_p,
                    top_k=options.top_k,
                    stop_sequences=options.stop_sequences,
                    stream=options.stream,
                )

                # Try directly with the normalized model
                await self._apply_rate_limiting()
                request_params = self._build_request_params(prompt, system_prompt, current_options, model)
                response = await self._make_request(request_params, 0)
                claude_response = self._process_response(response, model)

                # Track fallback info in response metadata
                if len(tried_models) > 1:
                    logger.warning(f"Model fallback occurred: requested={original_model}, used={model}, tried={tried_models}")
                    claude_response.fallback_info = {
                        "occurred": True,
                        "requested_model": original_model,
                        "actual_model": model,
                        "tried_models": tried_models,
                        "failed_models": tried_models[:-1]
                    }
                else:
                    claude_response.fallback_info = {"occurred": False}

                logger.info(f"Summary created successfully with model {model}")
                cost = self._calculate_cost(claude_response)
                self.usage_stats.add_request(claude_response, cost)
                return claude_response

            except (anthropic.NotFoundError, ModelUnavailableError) as e:
                logger.warning(f"Model {model} not available, trying next fallback: {e}")
                last_error = e
                continue
            except Exception as e:
                # For other errors, don't try fallbacks - just raise
                logger.error(f"Error with model {model}: {e}")
                raise

        # All models failed
        raise ModelUnavailableError(
            options.model,
            context={
                "tried_models": tried_models,
                "last_error": str(last_error),
                "is_openrouter": self.is_openrouter
            }
        )

    async def health_check(self) -> bool:
        """Check if Claude API is accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Use fallback chain so health check passes as long as ANY model works
            options = ClaudeOptions(max_tokens=5)
            await self.create_summary_with_fallback(
                prompt="Say hello",
                system_prompt="You are a helpful assistant.",
                options=options
            )
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    def get_usage_stats(self) -> UsageStats:
        """Get current usage statistics."""
        return self.usage_stats
    
    def estimate_cost(self, input_tokens: int, output_tokens: int,
                     model: str) -> float:
        """Estimate cost for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name (with or without provider prefix)

        Returns:
            Estimated cost in USD (0.0 for openrouter/* dynamic models)
        """
        # OpenRouter dynamic models (openrouter/*) don't have fixed pricing
        if model.startswith('openrouter/'):
            return 0.0

        # Remove provider prefix for cost lookup
        base_model = model.replace('anthropic/', '')

        if base_model not in self.MODEL_COSTS:
            return 0.0

        input_cost, output_cost = self.MODEL_COSTS[base_model]

        # Costs are per 1K tokens
        total_cost = (input_tokens * input_cost + output_tokens * output_cost) / 1000
        return round(total_cost, 6)
    
    async def _apply_rate_limiting(self):
        """Apply rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - time_since_last)
        
        self._last_request_time = time.time()
    
    def _build_request_params(self, prompt: str, system_prompt: str,
                             options: ClaudeOptions, model: Optional[str] = None) -> Dict[str, Any]:
        """Build request parameters for Claude API.

        Args:
            prompt: User prompt
            system_prompt: System prompt
            options: Claude options
            model: Optional normalized model name (defaults to options.model if not provided)
        """
        params = {
            "model": model or options.model,
            "max_tokens": options.max_tokens,
            "temperature": options.temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        if options.top_p is not None:
            params["top_p"] = options.top_p
        
        if options.top_k is not None:
            params["top_k"] = options.top_k
        
        if options.stop_sequences:
            params["stop_sequences"] = options.stop_sequences
        
        if options.stream:
            params["stream"] = True
        
        return params
    
    async def _make_request(self, params: Dict[str, Any], attempt: int) -> Any:
        """Make the actual API request."""
        return await self._client.messages.create(**params)
    
    def _process_response(self, response: Any, model: str) -> ClaudeResponse:
        """Process API response into ClaudeResponse object."""
        # Extract content from response
        content = ""
        if hasattr(response, 'content') and response.content:
            if isinstance(response.content, list) and len(response.content) > 0:
                content = response.content[0].text if hasattr(response.content[0], 'text') else str(response.content[0])
            else:
                content = str(response.content)

        # Extract usage information
        usage = {}
        if hasattr(response, 'usage'):
            usage = {
                "input_tokens": getattr(response.usage, 'input_tokens', 0),
                "output_tokens": getattr(response.usage, 'output_tokens', 0)
            }

        # Get actual model used (OpenRouter returns this in response.model)
        # This is especially important for openrouter/auto which routes to different models
        actual_model = getattr(response, 'model', model)

        # Log if actual model differs from requested (e.g., with openrouter/auto)
        if actual_model != model:
            logger = logging.getLogger(__name__)
            logger.info(f"Model routing: requested={model}, actual={actual_model}")

        return ClaudeResponse(
            content=content,
            model=actual_model,  # Use actual model from response
            usage=usage,
            stop_reason=getattr(response, 'stop_reason', 'end_turn'),
            response_id=getattr(response, 'id', '')
        )
    
    def _calculate_cost(self, response: ClaudeResponse) -> float:
        """Calculate cost for a response."""
        return self.estimate_cost(
            response.input_tokens,
            response.output_tokens,
            response.model
        )
    
    def _extract_retry_after(self, error: Exception) -> int:
        """Extract retry-after value from rate limit error."""
        # Try to extract from error message or headers
        error_str = str(error)
        
        # Look for patterns like "retry after 60 seconds"
        import re
        match = re.search(r'retry.+?(\d+).+?second', error_str, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Default retry after
        return 60