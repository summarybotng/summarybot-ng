"""
Performance optimization for summarization engine.
"""

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

from ..models.message import ProcessedMessage
from ..models.summary import SummaryOptions
from src.utils.time import utc_now_naive


class SummaryOptimizer:
    """Optimizes summarization requests for better performance and cost."""
    
    def __init__(self):
        # Message filtering thresholds
        self.min_content_length = 10
        self.max_message_age_days = 90
        self.duplicate_similarity_threshold = 0.8
    
    def optimize_message_list(self, 
                            messages: List[ProcessedMessage],
                            options: SummaryOptions,
                            max_messages: Optional[int] = None) -> Tuple[List[ProcessedMessage], Dict[str, Any]]:
        """Optimize message list for summarization.
        
        Args:
            messages: Original message list
            options: Summarization options
            max_messages: Optional limit on number of messages
            
        Returns:
            Tuple of (optimized_messages, optimization_stats)
        """
        stats = {
            "original_count": len(messages),
            "filtered_count": 0,
            "deduplication_removed": 0,
            "truncated_count": 0,
            "optimization_applied": []
        }
        
        optimized = messages.copy()
        
        # Filter by content quality
        optimized = self._filter_by_content_quality(optimized, options)
        stats["filtered_count"] = len(optimized)
        if stats["filtered_count"] < stats["original_count"]:
            stats["optimization_applied"].append("content_filtering")
        
        # Remove duplicates
        original_count = len(optimized)
        optimized = self._remove_duplicate_messages(optimized)
        stats["deduplication_removed"] = original_count - len(optimized)
        if stats["deduplication_removed"] > 0:
            stats["optimization_applied"].append("deduplication")
        
        # Apply message limit
        if max_messages and len(optimized) > max_messages:
            optimized = self._smart_truncate_messages(optimized, max_messages)
            stats["truncated_count"] = len(messages) - len(optimized)
            stats["optimization_applied"].append("smart_truncation")
        
        stats["final_count"] = len(optimized)
        stats["reduction_ratio"] = (stats["original_count"] - stats["final_count"]) / max(stats["original_count"], 1)
        
        return optimized, stats
    
    def estimate_optimization_benefit(self,
                                   messages: List[ProcessedMessage],
                                   options: SummaryOptions) -> Dict[str, Any]:
        """Estimate the benefit of optimization without applying it.
        
        Returns:
            Dictionary with optimization estimates
        """
        estimates = {
            "current_message_count": len(messages),
            "estimated_after_filtering": 0,
            "estimated_duplicates": 0,
            "potential_token_savings": 0,
            "potential_cost_savings_usd": 0
        }
        
        # Estimate content filtering
        substantial_messages = sum(1 for msg in messages if msg.has_substantial_content())
        estimates["estimated_after_filtering"] = substantial_messages
        
        # Estimate duplicate detection
        content_hashes = set()
        duplicate_count = 0
        for message in messages:
            content_hash = self._get_content_hash(message)
            if content_hash in content_hashes:
                duplicate_count += 1
            else:
                content_hashes.add(content_hash)
        
        estimates["estimated_duplicates"] = duplicate_count
        
        # Rough token estimation (4 chars per token)
        original_chars = sum(len(msg.content or "") for msg in messages)
        optimized_chars = sum(
            len(msg.content or "") for msg in messages 
            if msg.has_substantial_content()
        )
        optimized_chars -= duplicate_count * 100  # Rough estimate for duplicate savings
        
        estimates["potential_token_savings"] = max(0, (original_chars - optimized_chars) // 4)
        
        # Rough cost estimate (assuming $0.003 per 1K input tokens)
        token_savings = estimates["potential_token_savings"]
        estimates["potential_cost_savings_usd"] = (token_savings / 1000) * 0.003
        
        return estimates
    
    def optimize_batch_requests(self,
                              requests: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Optimize a batch of summarization requests.
        
        Args:
            requests: List of request dictionaries
            
        Returns:
            Tuple of (optimized_requests, batch_stats)
        """
        batch_stats = {
            "original_request_count": len(requests),
            "deduplication_savings": 0,
            "similar_requests_merged": 0,
            "optimization_applied": []
        }
        
        optimized_requests = []
        processed_signatures = set()
        
        for request in requests:
            # Create signature for deduplication
            signature = self._get_request_signature(request)
            
            if signature in processed_signatures:
                batch_stats["deduplication_savings"] += 1
                continue
            
            processed_signatures.add(signature)
            optimized_requests.append(request)
        
        batch_stats["final_request_count"] = len(optimized_requests)
        
        if batch_stats["deduplication_savings"] > 0:
            batch_stats["optimization_applied"].append("request_deduplication")
        
        return optimized_requests, batch_stats
    
    def _filter_by_content_quality(self,
                                 messages: List[ProcessedMessage],
                                 options: SummaryOptions) -> List[ProcessedMessage]:
        """Filter messages by content quality."""
        filtered = []
        
        for message in messages:
            # Skip messages without substantial content
            if not message.has_substantial_content():
                continue
            
            # Skip bot messages unless explicitly included
            if message.author_name.endswith(" [BOT]") and not options.include_bots:
                continue
            
            # Skip excluded users
            if message.author_id in options.excluded_users:
                continue
            
            # Skip very old messages (potential data quality issues)
            age_days = (utc_now_naive() - message.timestamp).days
            if age_days > self.max_message_age_days:
                continue
            
            filtered.append(message)
        
        return filtered
    
    def _remove_duplicate_messages(self, messages: List[ProcessedMessage]) -> List[ProcessedMessage]:
        """Remove duplicate or near-duplicate messages."""
        unique_messages = []
        seen_hashes = set()
        
        for message in messages:
            content_hash = self._get_content_hash(message)
            
            if content_hash not in seen_hashes:
                unique_messages.append(message)
                seen_hashes.add(content_hash)
        
        return unique_messages
    
    def _smart_truncate_messages(self,
                               messages: List[ProcessedMessage],
                               max_count: int) -> List[ProcessedMessage]:
        """Intelligently truncate messages to fit limits.
        
        Prioritizes:
        1. Messages with more content
        2. Messages from more active participants
        3. Messages with attachments or code blocks
        4. More recent messages
        """
        if len(messages) <= max_count:
            return messages
        
        # Score messages for importance
        scored_messages = []
        
        # Count messages per author for activity scoring
        author_counts = {}
        for msg in messages:
            author_counts[msg.author_name] = author_counts.get(msg.author_name, 0) + 1
        
        for message in messages:
            score = 0
            
            # Content length score (normalized)
            content_length = len(message.clean_content())
            score += min(content_length / 100, 10)  # Max 10 points for content
            
            # Author activity score
            author_activity = author_counts[message.author_name]
            score += min(author_activity / 5, 5)  # Max 5 points for activity
            
            # Attachment bonus
            if message.attachments:
                score += 3
            
            # Code block bonus
            if message.code_blocks:
                score += 2
            
            # Recency bonus (messages in last hour get bonus)
            age_hours = (utc_now_naive() - message.timestamp).total_seconds() / 3600
            if age_hours < 1:
                score += 2
            
            # Thread starter bonus
            if message.thread_info and message.thread_info.starter_message_id == message.id:
                score += 3
            
            scored_messages.append((score, message))
        
        # Sort by score descending and take top messages
        scored_messages.sort(key=lambda x: x[0], reverse=True)
        selected_messages = [msg for _, msg in scored_messages[:max_count]]
        
        # Re-sort by timestamp to maintain chronological order
        selected_messages.sort(key=lambda x: x.timestamp)
        
        return selected_messages
    
    def _get_content_hash(self, message: ProcessedMessage) -> str:
        """Generate hash for message content deduplication."""
        import hashlib
        
        # Use cleaned content and author for hashing
        content = message.clean_content().lower().strip()
        author = message.author_name.lower()
        
        # Remove common variations
        content = content.replace(" ", "").replace("\n", "").replace("\t", "")
        
        # Create hash
        hash_input = f"{author}:{content}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]
    
    def _get_request_signature(self, request: Dict[str, Any]) -> str:
        """Generate signature for request deduplication."""
        import hashlib
        
        # Extract key identifying information
        signature_data = {
            "channel_id": request.get("channel_id", ""),
            "guild_id": request.get("guild_id", ""),
            "message_count": len(request.get("messages", [])),
            "options": {
                "summary_length": getattr(request.get("options"), "summary_length", "").value if hasattr(request.get("options", {}), "summary_length") else "",
                "model": getattr(request.get("options"), "claude_model", "") if hasattr(request.get("options", {}), "claude_model") else ""
            }
        }
        
        # Add timestamp range if available
        messages = request.get("messages", [])
        if messages:
            signature_data["start_time"] = min(msg.timestamp for msg in messages).isoformat()
            signature_data["end_time"] = max(msg.timestamp for msg in messages).isoformat()
        
        # Create hash
        import json
        signature_str = json.dumps(signature_data, sort_keys=True)
        return hashlib.md5(signature_str.encode()).hexdigest()[:16]