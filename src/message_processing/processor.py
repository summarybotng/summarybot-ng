"""
Main message processor coordinating all message processing components.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

import discord

from .fetcher import MessageFetcher
from .filter import MessageFilter
from .cleaner import MessageCleaner
from .extractor import MessageExtractor
from .validator import MessageValidator
from ..models.message import ProcessedMessage
from ..models.summary import SummaryOptions
from ..exceptions import MessageFetchError, InsufficientContentError


class MessageProcessor:
    """Main processor for Discord messages."""
    
    def __init__(self, discord_client: discord.Client):
        """Initialize message processor with all components."""
        self.fetcher = MessageFetcher(discord_client)
        self.filter = MessageFilter()
        self.cleaner = MessageCleaner()
        self.extractor = MessageExtractor()
        self.validator = MessageValidator()
    
    async def process_channel_messages(self,
                                     channel_id: str,
                                     start_time: datetime,
                                     end_time: datetime,
                                     options: SummaryOptions,
                                     limit: Optional[int] = None,
                                     skip_min_check: bool = False) -> List[ProcessedMessage]:
        """Process messages from a channel for summarization.

        Args:
            channel_id: Discord channel ID
            start_time: Start of time range
            end_time: End of time range
            options: Summary options for filtering
            limit: Optional message limit
            skip_min_check: If True, skip min_messages validation (for multi-channel aggregation)

        Returns:
            List of processed messages ready for summarization
        """
        # Fetch raw messages
        raw_messages = await self.fetcher.fetch_messages(
            channel_id=channel_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        # Process messages through pipeline
        return await self._process_message_pipeline(raw_messages, options, skip_min_check=skip_min_check)
    
    async def process_thread_messages(self,
                                    thread_id: str,
                                    options: SummaryOptions,
                                    include_parent: bool = True,
                                    limit: Optional[int] = None) -> List[ProcessedMessage]:
        """Process messages from a thread."""
        # Fetch raw messages
        raw_messages = await self.fetcher.fetch_thread_messages(
            thread_id=thread_id,
            include_parent=include_parent,
            limit=limit
        )
        
        # Process messages through pipeline
        return await self._process_message_pipeline(raw_messages, options)
    
    async def process_messages(self,
                              raw_messages: List[discord.Message],
                              options: Optional[SummaryOptions] = None) -> List[ProcessedMessage]:
        """Process raw Discord messages through the pipeline.

        Args:
            raw_messages: List of raw Discord messages
            options: Optional summary options for filtering

        Returns:
            List of processed messages ready for summarization
        """
        if options is None:
            from ..models.summary import SummaryOptions
            options = SummaryOptions()
        return await self._process_message_pipeline(raw_messages, options)

    async def _process_message_pipeline(self,
                                      raw_messages: List[discord.Message],
                                      options: SummaryOptions,
                                      skip_min_check: bool = False) -> List[ProcessedMessage]:
        """Process messages through the complete pipeline.

        Args:
            raw_messages: Raw Discord messages to process
            options: Summary options for filtering
            skip_min_check: If True, skip min_messages validation (for multi-channel aggregation)

        Returns:
            List of processed messages
        """
        # Filter messages
        filtered_messages = self.filter.filter_messages(raw_messages, options)

        # Clean and extract information from each message
        processed_messages = []
        for message in filtered_messages:
            try:
                processed = self.cleaner.clean_message(message)
                processed = self.extractor.extract_information(processed, message)

                # Validate processed message
                if self.validator.is_valid_message(processed):
                    processed_messages.append(processed)

            except Exception as e:
                # Log error but continue processing other messages
                print(f"Error processing message {message.id}: {e}")
                continue

        # Final validation (skip for multi-channel aggregation where caller checks aggregate)
        if not skip_min_check and len(processed_messages) < options.min_messages:
            raise InsufficientContentError(
                message_count=len(processed_messages),
                min_required=options.min_messages
            )

        return processed_messages