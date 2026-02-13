"""
Main summarization engine coordinating all components.
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from .claude_client import ClaudeClient, ClaudeOptions
from .prompt_builder import PromptBuilder
from .response_parser import ResponseParser
from .cache import SummaryCache
from ..models.summary import SummaryResult, SummaryOptions, SummarizationContext
from ..models.message import ProcessedMessage
from ..exceptions import (
    SummarizationError, InsufficientContentError, PromptTooLongError,
    create_error_context
)

logger = logging.getLogger(__name__)


@dataclass
class CostEstimate:
    """Cost estimation for summarization."""
    estimated_cost_usd: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
    message_count: int
    error: Optional[str] = None


class SummarizationEngine:
    """Main engine for AI-powered summarization."""

    def __init__(self,
                 claude_client: Optional[ClaudeClient] = None,
                 cache: Optional[SummaryCache] = None,
                 max_prompt_tokens: int = 100000,
                 prompt_resolver=None):
        """Initialize summarization engine.

        Args:
            claude_client: Claude API client (None if LLM not configured)
            cache: Optional summary cache
            max_prompt_tokens: Maximum tokens allowed in prompt
            prompt_resolver: Optional PromptTemplateResolver for custom prompts
        """
        self.claude_client = claude_client
        self.cache = cache
        self.max_prompt_tokens = max_prompt_tokens
        self.prompt_resolver = prompt_resolver

        self.prompt_builder = PromptBuilder()
        self.response_parser = ResponseParser()

    def is_available(self) -> bool:
        """Check if summarization is available (LLM client configured)."""
        return self.claude_client is not None
    
    async def summarize_messages(self,
                               messages: List[ProcessedMessage],
                               options: SummaryOptions,
                               context: SummarizationContext,
                               channel_id: str = "",
                               guild_id: str = "") -> SummaryResult:
        """Summarize a list of messages.

        Args:
            messages: List of processed messages
            options: Summarization options
            context: Context information
            channel_id: Discord channel ID
            guild_id: Discord guild ID

        Returns:
            Complete summary result

        Raises:
            InsufficientContentError: Not enough content to summarize
            SummarizationError: Summarization process failed
        """
        # Check if LLM is configured
        if not self.is_available():
            raise SummarizationError(
                message="Summarization is unavailable - no LLM provider configured. "
                        "Please set OPENROUTER_API_KEY environment variable.",
                context=create_error_context(
                    channel_id=channel_id,
                    guild_id=guild_id,
                    operation="summarize_messages"
                )
            )

        # Validate input
        if len(messages) < options.min_messages:
            raise InsufficientContentError(
                message_count=len(messages),
                min_required=options.min_messages,
                context=create_error_context(
                    channel_id=channel_id,
                    guild_id=guild_id,
                    operation="summarize_messages"
                )
            )
        
        # Check cache if available
        if self.cache:
            start_time = min(msg.timestamp for msg in messages)
            end_time = max(msg.timestamp for msg in messages)
            
            cached_summary = await self.cache.get_cached_summary(
                channel_id=channel_id,
                start_time=start_time,
                end_time=end_time,
                options_hash=self._hash_options(options)
            )
            
            if cached_summary:
                return cached_summary
        
        try:
            # Get custom prompt if configured
            custom_prompt = None
            prompt_source_info = None
            if self.prompt_resolver and context:
                try:
                    from ..prompts.models import PromptContext
                    prompt_context = PromptContext(
                        guild_id=guild_id,
                        channel_name=context.channel_name if hasattr(context, 'channel_name') else None,
                        channel_id=channel_id,
                        category=getattr(options, 'category', 'discussion'),
                        summary_type=options.summary_length.value,
                        perspective=getattr(options, 'perspective', 'general'),
                        message_count=len(messages)
                    )

                    resolved = await self.prompt_resolver.resolve_prompt(
                        guild_id=guild_id,
                        context=prompt_context
                    )

                    # Use custom prompt content as system prompt
                    custom_prompt = resolved.content
                    # Capture prompt source info for transparency
                    prompt_source_info = resolved.to_source_info()
                except Exception as e:
                    # Log error but continue with default prompts
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to resolve custom prompt for guild {guild_id}, using defaults: {e}"
                    )

            # Build summarization prompt
            prompt_data = self.prompt_builder.build_summarization_prompt(
                messages=messages,
                options=options,
                context=context.to_dict() if context else None,
                custom_system_prompt=custom_prompt
            )
            
            # Check if prompt is too long
            if prompt_data.estimated_tokens > self.max_prompt_tokens:
                # Try to optimize
                optimized_user_prompt = self.prompt_builder.optimize_prompt_length(
                    prompt_data.user_prompt,
                    self.max_prompt_tokens - self.prompt_builder.estimate_token_count(prompt_data.system_prompt)
                )
                
                if self.prompt_builder.estimate_token_count(optimized_user_prompt + prompt_data.system_prompt) > self.max_prompt_tokens:
                    raise PromptTooLongError(
                        prompt_length=prompt_data.estimated_tokens,
                        max_length=self.max_prompt_tokens,
                        context=create_error_context(
                            channel_id=channel_id,
                            guild_id=guild_id,
                            operation="prompt_building",
                            message_count=len(messages)
                        )
                    )
                
                prompt_data.user_prompt = optimized_user_prompt
            
            # Configure Claude options
            claude_options = ClaudeOptions(
                model=options.get_model_for_length(),
                max_tokens=options.get_max_tokens_for_length(),
                temperature=options.temperature
            )

            logger.info(f"Summarization engine: summary_length={options.summary_length.value}, model={claude_options.model}, max_tokens={claude_options.max_tokens}")
            logger.info(f"System prompt length: {len(prompt_data.system_prompt)} chars, User prompt length: {len(prompt_data.user_prompt)} chars")

            # Call Claude API with fallback chain for all summary types
            logger.info("Using fallback-enabled API call for summary")
            response = await self.claude_client.create_summary_with_fallback(
                prompt=prompt_data.user_prompt,
                system_prompt=prompt_data.system_prompt,
                options=claude_options
            )

            logger.info(f"Claude API response: input_tokens={response.input_tokens}, output_tokens={response.output_tokens}, content_length={len(response.content)}")

            # Parse response (ADR-004: pass position_index for citation resolution)
            parsed_summary = self.response_parser.parse_summary_response(
                response_content=response.content,
                original_messages=messages,
                context=context,
                position_index=prompt_data.position_index
            )
            
            # Create final summary result
            start_time = min(msg.timestamp for msg in messages) if messages else datetime.utcnow()
            end_time = max(msg.timestamp for msg in messages) if messages else datetime.utcnow()
            
            summary_result = self.response_parser.extract_summary_result(
                parsed=parsed_summary,
                channel_id=channel_id,
                guild_id=guild_id,
                start_time=start_time,
                end_time=end_time,
                message_count=len(messages),
                context=context
            )
            
            # Add API usage metadata and summary options
            summary_result.metadata.update({
                "claude_model": response.model,  # Actual model used (may differ due to fallback)
                "requested_model": claude_options.model,  # Originally requested model
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
                "api_response_id": response.response_id,
                "processing_time": (datetime.utcnow() - summary_result.created_at).total_seconds(),
                "summary_length": options.summary_length.value,
                "perspective": options.perspective,
                # ADR-004: Citation metadata
                "citations_enabled": prompt_data.position_index is not None,
                "grounded": summary_result.has_references()
            })

            # Add prompt source info for transparency
            if prompt_source_info:
                summary_result.metadata["prompt_source"] = prompt_source_info

            # Check for model fallback and add warning
            fallback_info = getattr(response, 'fallback_info', {})
            if fallback_info.get('occurred'):
                summary_result.add_warning(
                    code="model_fallback",
                    message=f"Requested model '{fallback_info.get('requested_model')}' was not available. Used '{fallback_info.get('actual_model')}' instead.",
                    details={
                        "requested_model": fallback_info.get('requested_model'),
                        "actual_model": fallback_info.get('actual_model'),
                        "tried_models": fallback_info.get('tried_models', []),
                        "failed_models": fallback_info.get('failed_models', [])
                    }
                )
                logger.warning(f"Model fallback warning added to summary: {fallback_info}")

                # Track fallback in error log for visibility
                try:
                    from ..logging.error_tracker import initialize_error_tracker
                    from ..models.error_log import ErrorType, ErrorSeverity

                    tracker = await initialize_error_tracker()

                    # Create a simple exception to pass to capture_error
                    fallback_exception = Exception(
                        f"Model fallback: {fallback_info.get('requested_model')} -> {fallback_info.get('actual_model')}"
                    )

                    await tracker.capture_error(
                        error=fallback_exception,
                        error_type=ErrorType.MODEL_FALLBACK,
                        severity=ErrorSeverity.WARNING,
                        guild_id=context.guild_id if context else None,
                        channel_id=context.channel_ids[0] if context and context.channel_ids else None,
                        operation="summarization_model_selection",
                        details={
                            "requested_model": fallback_info.get('requested_model'),
                            "actual_model": fallback_info.get('actual_model'),
                            "tried_models": fallback_info.get('tried_models', []),
                            "failed_models": fallback_info.get('failed_models', []),
                            "summary_id": summary_result.id,
                        }
                    )
                except Exception as track_error:
                    logger.warning(f"Failed to track model fallback in error log: {track_error}")

            # Store prompt and source content for transparency
            summary_result.prompt_system = prompt_data.system_prompt
            summary_result.prompt_user = prompt_data.user_prompt
            summary_result.prompt_template_id = getattr(self.prompt_resolver, 'last_template_id', None) if self.prompt_resolver and custom_prompt else None
            summary_result.source_content = self._format_source_content(messages)
            
            # Cache result if cache is available
            if self.cache:
                await self.cache.cache_summary(summary_result)
            
            return summary_result
            
        except Exception as e:
            if isinstance(e, (InsufficientContentError, PromptTooLongError)):
                raise
            
            # Wrap other exceptions
            raise SummarizationError(
                message=f"Summarization failed: {str(e)}",
                error_code="SUMMARIZATION_FAILED",
                context=create_error_context(
                    channel_id=channel_id,
                    guild_id=guild_id,
                    operation="summarize_messages",
                    message_count=len(messages)
                ),
                retryable=True,
                cause=e
            )
    
    async def batch_summarize(self,
                            requests: List[Dict[str, Any]]) -> List[SummaryResult]:
        """Summarize multiple message sets in batch.
        
        Args:
            requests: List of summarization requests, each containing:
                - messages: List[ProcessedMessage]
                - options: SummaryOptions
                - context: SummarizationContext
                - channel_id: str
                - guild_id: str
                
        Returns:
            List of summary results in same order as requests
        """
        # Process requests concurrently with limited concurrency
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
        
        async def process_single_request(request: Dict[str, Any]) -> SummaryResult:
            async with semaphore:
                return await self.summarize_messages(
                    messages=request["messages"],
                    options=request["options"],
                    context=request["context"],
                    channel_id=request.get("channel_id", ""),
                    guild_id=request.get("guild_id", "")
                )
        
        tasks = [process_single_request(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create error summary
                error_summary = SummaryResult(
                    channel_id=requests[i].get("channel_id", ""),
                    guild_id=requests[i].get("guild_id", ""),
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                    message_count=len(requests[i]["messages"]),
                    summary_text=f"Error: {str(result)}",
                    metadata={"error": True, "error_type": type(result).__name__}
                )
                final_results.append(error_summary)
            else:
                final_results.append(result)
        
        return final_results
    
    async def estimate_cost(self,
                           messages: List[ProcessedMessage],
                           options: SummaryOptions) -> CostEstimate:
        """Estimate cost for summarizing messages.

        Args:
            messages: Messages to be summarized
            options: Summarization options

        Returns:
            Cost estimation with breakdown
        """
        # Build prompt to estimate tokens
        try:
            import inspect

            prompt_data = self.prompt_builder.build_summarization_prompt(
                messages=messages,
                options=options
            )

            input_tokens = prompt_data.estimated_tokens
            output_tokens = options.get_max_tokens_for_length()

            cost_result = self.claude_client.estimate_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=options.summarization_model
            )

            # Handle both sync and async for testing flexibility
            if inspect.iscoroutine(cost_result):
                cost = await cost_result
            else:
                cost = cost_result

            return CostEstimate(
                estimated_cost_usd=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                model=options.summarization_model,
                message_count=len(messages)
            )

        except Exception as e:
            return CostEstimate(
                estimated_cost_usd=0.0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                model=options.summarization_model,
                message_count=len(messages),
                error=str(e)
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of summarization engine.

        Returns:
            Health status information
        """
        import inspect

        # Handle case where no LLM client is configured
        if not self.is_available():
            health_info = {
                "status": "degraded",
                "claude_api": None,
                "cache": False,
                "components": {
                    "prompt_builder": True,
                    "response_parser": True
                },
                "usage_stats": None,
                "message": "No LLM provider configured - summarization unavailable"
            }
            # Check cache
            if self.cache:
                try:
                    health_info["cache"] = await self.cache.health_check()
                except Exception:
                    health_info["cache"] = False
            return health_info

        # Get usage stats (handle both sync and async for testing flexibility)
        usage_stats_result = self.claude_client.get_usage_stats()
        if inspect.iscoroutine(usage_stats_result):
            usage_stats = await usage_stats_result
        else:
            usage_stats = usage_stats_result

        health_info = {
            "status": "healthy",
            "claude_api": False,
            "cache": False,
            "components": {
                "prompt_builder": True,
                "response_parser": True
            },
            "usage_stats": usage_stats.to_dict()
        }

        # Check Claude API
        try:
            health_info["claude_api"] = await self.claude_client.health_check()
        except Exception:
            health_info["claude_api"] = False
            health_info["status"] = "degraded"
        
        # Check cache
        if self.cache:
            try:
                health_info["cache"] = await self.cache.health_check()
            except Exception:
                health_info["cache"] = False
        else:
            health_info["cache"] = None  # Cache not configured
        
        # Overall status
        if not health_info["claude_api"]:
            health_info["status"] = "unhealthy"
        elif health_info["cache"] is False:
            health_info["status"] = "degraded"
        
        return health_info
    
    def _hash_options(self, options: SummaryOptions) -> str:
        """Create hash of options for caching."""
        import hashlib

        options_str = f"{options.summary_length.value}-{options.summarization_model}-{options.temperature}-{options.max_tokens}"
        return hashlib.md5(options_str.encode()).hexdigest()[:16]

    def _format_source_content(self, messages: List[ProcessedMessage]) -> str:
        """Format source messages into readable content for storage.

        Args:
            messages: List of processed messages

        Returns:
            Formatted string of message content
        """
        lines = []
        for msg in messages:
            if not msg.has_substantial_content():
                continue

            timestamp = msg.timestamp.strftime('%Y-%m-%d %H:%M')
            content = msg.content or ""

            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."

            lines.append(f"[{timestamp}] {msg.author_name}: {content}")

            # Note attachments
            if msg.attachments:
                att_names = [att.filename for att in msg.attachments if hasattr(att, 'filename')]
                if att_names:
                    lines.append(f"  [Attachments: {', '.join(att_names)}]")

        return "\n".join(lines)