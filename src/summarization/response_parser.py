"""
Claude response parsing and processing.

Includes ADR-004 support for parsing message-level citations.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..models.summary import (
    SummaryResult, ActionItem, TechnicalTerm, Participant,
    SummarizationContext, Priority
)
from ..models.message import ProcessedMessage
from ..models.base import BaseModel, generate_id
from ..models.reference import (
    SummaryReference, ReferencedClaim, PositionIndex,
    build_deduped_reference_index
)
from ..exceptions import SummarizationError

logger = logging.getLogger(__name__)


@dataclass
class ParsedSummary(BaseModel):
    """Parsed and structured summary from Claude response."""
    summary_text: str
    key_points: List[str]
    action_items: List[ActionItem]
    technical_terms: List[TechnicalTerm]
    participants: List[Participant]
    raw_response: str
    parsing_metadata: Dict[str, Any]
    # ADR-004: Referenced claims (populated when citations are parsed)
    referenced_key_points: List[ReferencedClaim] = field(default_factory=list)
    referenced_action_items: List[ReferencedClaim] = field(default_factory=list)
    referenced_decisions: List[ReferencedClaim] = field(default_factory=list)
    referenced_topics: List[ReferencedClaim] = field(default_factory=list)
    reference_index: List[SummaryReference] = field(default_factory=list)


class ResponseParser:
    """Parses and processes Claude API responses into structured summaries."""
    
    def __init__(self):
        self.fallback_parsers = [
            self._parse_json_response,
            self._parse_markdown_response,
            self._parse_freeform_response
        ]
    
    def parse_summary_response(self,
                             response_content: str,
                             original_messages: List[ProcessedMessage],
                             context: Optional[SummarizationContext] = None,
                             position_index: Optional[PositionIndex] = None) -> ParsedSummary:
        """Parse Claude response into structured summary.

        Args:
            response_content: Raw response from Claude
            original_messages: Original messages that were summarized
            context: Additional context information
            position_index: Optional PositionIndex for resolving citations (ADR-004)

        Returns:
            Parsed and structured summary

        Raises:
            SummarizationError: If parsing fails completely
        """
        parsing_metadata = {
            "response_length": len(response_content),
            "parsing_method": None,
            "extraction_stats": {},
            "warnings": [],
            "citations_enabled": position_index is not None  # ADR-004
        }

        # Log response preview for debugging
        logger.debug(f"Parsing Claude response (length={len(response_content)})")
        logger.debug(f"Response preview: {response_content[:500]}...")

        # Try each parser in order
        for parser_method in self.fallback_parsers:
            try:
                logger.debug(f"Trying parser: {parser_method.__name__}")
                # ADR-004: Pass position_index to JSON parser for citation resolution
                if parser_method == self._parse_json_response and position_index:
                    parsed = parser_method(response_content, parsing_metadata, position_index)
                else:
                    parsed = parser_method(response_content, parsing_metadata)
                if parsed:
                    logger.debug(f"Parser {parser_method.__name__} succeeded")
                    # Enhance with message analysis
                    enhanced = self._enhance_with_message_analysis(
                        parsed, original_messages, context
                    )

                    # Validate and clean up
                    validated = self._validate_and_clean(enhanced, parsing_metadata)

                    return validated
                else:
                    logger.debug(f"Parser {parser_method.__name__} returned None")

            except Exception as e:
                error_msg = f"{parser_method.__name__}: {str(e)}"
                parsing_metadata["warnings"].append(error_msg)
                logger.warning(f"Parser {parser_method.__name__} failed: {str(e)}")
                continue

        # All parsers failed - log full details
        logger.error(f"All parsers failed for response. Warnings: {parsing_metadata['warnings']}")
        logger.error(f"Full response content: {response_content}")

        raise SummarizationError(
            message="Failed to parse Claude response with any available parser",
            error_code="RESPONSE_PARSE_FAILED",
            context={
                "response_preview": response_content[:200],
                "parsing_metadata": parsing_metadata
            }
        )
    
    def extract_summary_result(self,
                             parsed: ParsedSummary,
                             channel_id: str,
                             guild_id: str,
                             start_time: datetime,
                             end_time: datetime,
                             message_count: int,
                             context: Optional[SummarizationContext] = None) -> SummaryResult:
        """Convert parsed summary to SummaryResult object."""
        return SummaryResult(
            id=generate_id(),
            channel_id=channel_id,
            guild_id=guild_id,
            start_time=start_time,
            end_time=end_time,
            message_count=message_count,
            key_points=parsed.key_points,
            action_items=parsed.action_items,
            technical_terms=parsed.technical_terms,
            participants=parsed.participants,
            summary_text=parsed.summary_text,
            metadata=parsed.parsing_metadata,
            created_at=datetime.utcnow(),
            context=context,
            # ADR-004: Include referenced claims
            referenced_key_points=parsed.referenced_key_points,
            referenced_action_items=parsed.referenced_action_items,
            referenced_decisions=parsed.referenced_decisions,
            reference_index=parsed.reference_index
        )
    
    def _parse_json_response(self, content: str, metadata: Dict[str, Any],
                            position_index: Optional[PositionIndex] = None) -> Optional[ParsedSummary]:
        """Parse JSON-formatted response.

        Args:
            content: Raw response content
            metadata: Parsing metadata dict to update
            position_index: Optional PositionIndex for resolving citations (ADR-004)
        """
        metadata["parsing_method"] = "json"

        # Extract JSON from response (handle code blocks)
        # First try to find JSON within code blocks
        json_str = self._extract_json_from_codeblock(content)

        if not json_str:
            # Try to find JSON without code blocks using brace counting
            json_str = self._extract_json_with_brace_counting(content)

        if not json_str:
            logger.debug("No JSON found in response")
            return None

        logger.debug(f"Extracted JSON string (length={len(json_str)})")

        try:
            data = json.loads(json_str)
            logger.debug(f"Successfully parsed JSON with {len(data)} top-level keys")

            # Extract components - support multiple format variations
            summary_text = (
                data.get("summary_text", "") or
                data.get("summary", "") or
                data.get("overview", "") or  # camelCase format
                data.get("🎯 Overview", "") or
                data.get("Overview", "")
            )

            # ADR-004: Track referenced claims
            referenced_key_points: List[ReferencedClaim] = []
            referenced_action_items: List[ReferencedClaim] = []
            referenced_decisions: List[ReferencedClaim] = []

            # Extract key points from various formats
            key_points_raw = (
                data.get("key_points", []) or
                data.get("mainTopics", []) or  # camelCase format
                data.get("💡 Key Technical Points", []) or
                data.get("Key Technical Points", []) or
                []
            )

            # Flatten key points if they're in dict format
            key_points = []
            if isinstance(key_points_raw, list):
                for item in key_points_raw:
                    if isinstance(item, dict):
                        # ADR-004: Handle referenced format {"text": "...", "references": [1,2]}
                        if "text" in item and "references" in item and position_index:
                            refs = position_index.resolve_many(item.get("references", []))
                            confidence = item.get("confidence", 1.0)
                            referenced_key_points.append(ReferencedClaim(
                                text=item["text"],
                                references=refs,
                                confidence=confidence
                            ))
                            key_points.append(item["text"])  # Also add flat version
                        # Handle nested topic/points format: {"topic": "...", "points": [...]}
                        elif "topic" in item and "points" in item:
                            # Extract all points from this topic
                            if isinstance(item["points"], list):
                                key_points.extend(item["points"])
                        else:
                            # Extract values from simple dict (e.g., {"Point 1": "...", "Point 2": "..."})
                            for key, value in item.items():
                                if isinstance(value, str) and not key.startswith('_'):
                                    key_points.append(value)
                    elif isinstance(item, str):
                        key_points.append(item)
            elif isinstance(key_points_raw, str):
                key_points = [key_points_raw]

            # ADR-004: Parse decisions (new field)
            decisions_raw = data.get("decisions", [])
            for item in decisions_raw:
                if isinstance(item, dict) and "text" in item and position_index:
                    refs = position_index.resolve_many(item.get("references", []))
                    confidence = item.get("confidence", 1.0)
                    referenced_decisions.append(ReferencedClaim(
                        text=item["text"],
                        references=refs,
                        confidence=confidence
                    ))

            # Parse action items - support custom emoji format
            action_items_raw = (
                data.get("action_items", []) or
                data.get("🔧 Action Items", []) or
                data.get("Action Items", []) or
                []
            )
            action_items = []
            for item_data in action_items_raw:
                if isinstance(item_data, dict):
                    priority = Priority.MEDIUM  # default
                    if "priority" in item_data:
                        try:
                            priority = Priority(item_data["priority"].lower())
                        except ValueError:
                            pass

                    # ADR-004: Handle referenced action items
                    description = item_data.get("description", "") or item_data.get("text", "")
                    action_items.append(ActionItem(
                        description=description,
                        assignee=item_data.get("assignee"),
                        priority=priority
                    ))

                    # Create referenced version if references present
                    if "references" in item_data and position_index:
                        refs = position_index.resolve_many(item_data.get("references", []))
                        referenced_action_items.append(ReferencedClaim(
                            text=description,
                            references=refs,
                            confidence=item_data.get("confidence", 1.0)
                        ))
                elif isinstance(item_data, str):
                    action_items.append(ActionItem(description=item_data))

            # Parse technical terms
            technical_terms = []
            for term_data in data.get("technical_terms", []):
                if isinstance(term_data, dict):
                    technical_terms.append(TechnicalTerm(
                        term=term_data.get("term", ""),
                        definition=term_data.get("definition", ""),
                        context=term_data.get("context", ""),
                        source_message_id=""  # Will be filled later if possible
                    ))

            # Parse participants (with ADR-004 support for referenced contributions)
            participants = []
            for participant_data in data.get("participants", []):
                if isinstance(participant_data, dict):
                    # Handle referenced contributions
                    referenced_contributions = []
                    key_contributions_raw = participant_data.get("key_contributions", [])

                    flat_contributions = []
                    if isinstance(key_contributions_raw, list):
                        for contrib in key_contributions_raw:
                            if isinstance(contrib, dict) and "text" in contrib and position_index:
                                # Referenced contribution
                                refs = position_index.resolve_many(contrib.get("references", []))
                                referenced_contributions.append(ReferencedClaim(
                                    text=contrib["text"],
                                    references=refs,
                                    confidence=contrib.get("confidence", 1.0)
                                ))
                                flat_contributions.append(contrib["text"])
                            elif isinstance(contrib, str):
                                flat_contributions.append(contrib)
                    elif isinstance(key_contributions_raw, str):
                        flat_contributions = [key_contributions_raw]

                    # Also check old format field
                    if not flat_contributions:
                        flat_contributions = self._ensure_list(participant_data.get("key_contribution", []))

                    participants.append(Participant(
                        user_id="",  # Will be filled from message analysis
                        display_name=participant_data.get("name", ""),
                        message_count=participant_data.get("message_count", 0),
                        key_contributions=flat_contributions,
                        referenced_contributions=referenced_contributions
                    ))

            # ADR-004: Build deduped reference index
            reference_index = []
            if position_index:
                reference_index = build_deduped_reference_index(
                    referenced_key_points,
                    referenced_action_items,
                    referenced_decisions
                )

            metadata["extraction_stats"] = {
                "key_points": len(key_points),
                "action_items": len(action_items),
                "technical_terms": len(technical_terms),
                "participants": len(participants),
                "referenced_key_points": len(referenced_key_points),
                "referenced_decisions": len(referenced_decisions),
                "reference_count": len(reference_index)
            }

            return ParsedSummary(
                summary_text=summary_text,
                key_points=key_points,
                action_items=action_items,
                technical_terms=technical_terms,
                participants=participants,
                raw_response=content,
                parsing_metadata=metadata.copy(),
                referenced_key_points=referenced_key_points,
                referenced_action_items=referenced_action_items,
                referenced_decisions=referenced_decisions,
                reference_index=reference_index
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {str(e)}")
            logger.error(f"Failed JSON string (first 500 chars): {json_str[:500]}")
            logger.error(f"Failed JSON string (last 500 chars): {json_str[-500:]}")
            metadata["warnings"].append(f"JSON parse error: {str(e)}")
            metadata["json_extract_length"] = len(json_str)
            metadata["json_preview"] = json_str[:200]
            return None
    
    def _parse_markdown_response(self, content: str, metadata: Dict[str, Any]) -> Optional[ParsedSummary]:
        """Parse markdown-formatted response."""
        metadata["parsing_method"] = "markdown"
        
        # Extract sections using regex
        summary_text = self._extract_markdown_section(content, r"(?:## )?Summary", r"(?=##|$)")
        key_points = self._extract_markdown_list(content, r"(?:## )?Key Points?")
        action_items_text = self._extract_markdown_list(content, r"(?:## )?Action Items?")
        technical_terms_text = self._extract_markdown_list(content, r"(?:## )?Technical Terms?")
        participants_text = self._extract_markdown_list(content, r"(?:## )?Participants?")

        # If we didn't extract ANY meaningful content, return None to let freeform parser try
        if not summary_text and not key_points and not action_items_text and not technical_terms_text:
            logger.debug("Markdown parser found no structured content, falling back to next parser")
            return None

        # Convert to objects
        action_items = [ActionItem(description=item) for item in action_items_text]
        
        technical_terms = []
        for term_text in technical_terms_text:
            # Parse "term: definition" format
            if ':' in term_text:
                term, definition = term_text.split(':', 1)
                technical_terms.append(TechnicalTerm(
                    term=term.strip(),
                    definition=definition.strip(),
                    context="",
                    source_message_id=""
                ))
        
        participants = []
        for participant_text in participants_text:
            # Parse "Name (X messages): contribution" format
            match = re.match(r'([^(]+)(?:\((\d+)\s+messages?\))?\s*:?\s*(.*)', participant_text)
            if match:
                name, msg_count, contribution = match.groups()
                participants.append(Participant(
                    user_id="",
                    display_name=name.strip(),
                    message_count=int(msg_count) if msg_count else 0,
                    key_contributions=[contribution.strip()] if contribution.strip() else []
                ))
        
        return ParsedSummary(
            summary_text=summary_text,
            key_points=key_points,
            action_items=action_items,
            technical_terms=technical_terms,
            participants=participants,
            raw_response=content,
            parsing_metadata=metadata.copy()
        )
    
    def _parse_freeform_response(self, content: str, metadata: Dict[str, Any]) -> Optional[ParsedSummary]:
        """Parse freeform text response as fallback."""
        metadata["parsing_method"] = "freeform"
        logger.warning("Falling back to freeform parser - JSON/Markdown parsing failed")

        # Strip code blocks to avoid embedding raw JSON/code
        # Remove ```json ... ``` or ``` ... ``` blocks (complete blocks)
        cleaned_content = re.sub(r'```(?:json)?\s*.*?\s*```', '', content, flags=re.DOTALL)

        # Also remove incomplete code blocks (```json at start without closing ```)
        cleaned_content = re.sub(r'```(?:json)?\s*\{.*', '', cleaned_content, flags=re.DOTALL)

        # Remove any standalone JSON objects that weren't in code blocks
        # Match { ... } that looks like JSON (contains "key": patterns)
        cleaned_content = re.sub(r'\{\s*"[^"]+"\s*:.*?\}(?=\s*$|\s*\n\s*\n)', '', cleaned_content, flags=re.DOTALL)

        # Remove incomplete JSON at the end (starts with { but doesn't close)
        cleaned_content = re.sub(r'\{\s*"[^"]+"\s*:.*$', '', cleaned_content, flags=re.DOTALL)

        # Remove any lines that look like JSON properties
        lines = cleaned_content.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip lines that look like JSON (start with ", {, }, or contain ": )
            if stripped.startswith('"') and '":' in stripped:
                continue
            if stripped in ['{', '}', '[', ']', '},', '],']:
                continue
            if re.match(r'^\s*"[^"]+"\s*:\s*[\[\{"\d]', stripped):
                continue
            cleaned_lines.append(line)

        cleaned_content = '\n'.join(cleaned_lines).strip()

        # Use the cleaned content as summary text
        summary_text = cleaned_content.strip()

        # If nothing left after stripping, extract text before any JSON
        if not summary_text:
            logger.warning("Content was entirely code/JSON, extracting text before JSON")
            # Try to get any text before the first { or ```
            match = re.match(r'^(.*?)(?:```|\{)', content, flags=re.DOTALL)
            if match and match.group(1).strip():
                summary_text = match.group(1).strip()
            else:
                # Last resort: use a generic message
                summary_text = "[Summary content was in an unrecognized format]"

        # Try to extract some structure with simple heuristics
        lines = summary_text.split('\n')
        key_points = []

        for line in lines:
            line = line.strip()
            # Look for bullet points or numbered lists
            if re.match(r'^[-*•]\s+|^\d+\.\s+', line):
                key_points.append(re.sub(r'^[-*•]\s+|^\d+\.\s+', '', line))

        # If no bullet points found, split summary into sentences as key points
        if not key_points and summary_text:
            sentences = re.split(r'[.!?]+', summary_text)
            key_points = [s.strip() for s in sentences if len(s.strip()) > 10][:5]

        return ParsedSummary(
            summary_text=summary_text,
            key_points=key_points,
            action_items=[],  # Can't reliably extract from freeform
            technical_terms=[],  # Can't reliably extract from freeform
            participants=[],  # Will be filled from message analysis
            raw_response=content,
            parsing_metadata=metadata.copy()
        )
    
    def _enhance_with_message_analysis(self,
                                     parsed: ParsedSummary,
                                     messages: List[ProcessedMessage],
                                     context: Optional[SummarizationContext]) -> ParsedSummary:
        """Enhance parsed summary with analysis of original messages."""
        # Count actual participants from messages
        participant_counts = {}
        participant_contributions = {}
        
        for message in messages:
            author = message.author_name
            participant_counts[author] = participant_counts.get(author, 0) + 1
            
            if message.has_substantial_content():
                if author not in participant_contributions:
                    participant_contributions[author] = []
                
                # Add substantial messages as contributions
                content_summary = message.get_content_summary(50)
                if content_summary and content_summary != "[Empty message]":
                    participant_contributions[author].append(content_summary)
        
        # Update or create participant objects
        updated_participants = []
        existing_names = {p.display_name.lower(): p for p in parsed.participants}
        
        for author, count in participant_counts.items():
            if author.lower() in existing_names:
                # Update existing participant
                participant = existing_names[author.lower()]
                participant.message_count = count
                if author in participant_contributions:
                    participant.key_contributions = participant_contributions[author][:3]  # Top 3
                updated_participants.append(participant)
            else:
                # Create new participant
                updated_participants.append(Participant(
                    user_id="",  # Would need Discord API to resolve
                    display_name=author,
                    message_count=count,
                    key_contributions=participant_contributions.get(author, [])[:3]
                ))
        
        # Sort by message count
        updated_participants.sort(key=lambda p: p.message_count, reverse=True)
        
        parsed.participants = updated_participants
        return parsed
    
    def _validate_and_clean(self, parsed: ParsedSummary, metadata: Dict[str, Any]) -> ParsedSummary:
        """Validate and clean up parsed summary."""
        # Ensure summary text exists
        if not parsed.summary_text.strip():
            logger.warning(f"Parsed summary has empty text. Parsing metadata: {metadata}")
            logger.warning(f"Raw response: {parsed.raw_response[:1000]}")
            parsed.summary_text = "Summary could not be extracted from response."
        
        # Limit lengths to prevent excessive content
        parsed.summary_text = parsed.summary_text[:2000]  # Discord embed limit
        parsed.key_points = parsed.key_points[:10]  # Max 10 points
        parsed.action_items = parsed.action_items[:20]  # Max 20 actions
        parsed.technical_terms = parsed.technical_terms[:15]  # Max 15 terms
        
        # Clean up empty or too-short items
        parsed.key_points = [point for point in parsed.key_points if len(point.strip()) > 5]
        
        metadata["final_stats"] = {
            "summary_length": len(parsed.summary_text),
            "key_points": len(parsed.key_points),
            "action_items": len(parsed.action_items),
            "technical_terms": len(parsed.technical_terms),
            "participants": len(parsed.participants)
        }
        
        return parsed
    
    def _extract_markdown_section(self, content: str, header_pattern: str, 
                                 end_pattern: str = r"(?=##|$)") -> str:
        """Extract a markdown section by header."""
        pattern = f"{header_pattern}[:\n]+(.*?){end_pattern}"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    def _extract_markdown_list(self, content: str, header_pattern: str) -> List[str]:
        """Extract items from a markdown list section."""
        section = self._extract_markdown_section(content, header_pattern)
        if not section:
            return []
        
        items = []
        for line in section.split('\n'):
            line = line.strip()
            if re.match(r'^[-*•]\s+|^\d+\.\s+', line):
                item = re.sub(r'^[-*•]\s+|^\d+\.\s+', '', line).strip()
                if item:
                    items.append(item)
        
        return items
    
    def _ensure_list(self, value) -> List[str]:
        """Ensure value is a list of strings."""
        if isinstance(value, list):
            return [str(item) for item in value]
        elif isinstance(value, str):
            return [value] if value else []
        else:
            return [str(value)] if value else []

    def _extract_json_from_codeblock(self, content: str) -> Optional[str]:
        """Extract JSON from markdown code blocks using brace counting.

        Args:
            content: Content that may contain JSON in code blocks

        Returns:
            Extracted JSON string or None
        """
        # Look for ```json or ``` followed by {
        code_block_pattern = r'```(?:json)?\s*'
        match = re.search(code_block_pattern + r'(\{)', content, re.DOTALL)

        if not match:
            return None

        # Start position is where the { is found
        start_pos = match.start(1)

        # Use brace counting to find the matching closing brace
        json_str = self._extract_balanced_braces(content, start_pos)

        if json_str:
            # Verify it ends before the closing ``` if present
            end_pos = start_pos + len(json_str)
            remaining = content[end_pos:end_pos + 20]
            if '```' in remaining:
                return json_str

        return json_str

    def _extract_json_with_brace_counting(self, content: str) -> Optional[str]:
        """Extract JSON using brace counting without code blocks.

        Args:
            content: Content that may contain JSON

        Returns:
            Extracted JSON string or None
        """
        json_start = content.find('{')
        if json_start == -1:
            return None

        return self._extract_balanced_braces(content, json_start)

    def _extract_balanced_braces(self, content: str, start_pos: int) -> Optional[str]:
        """Extract JSON object using balanced brace counting.

        Args:
            content: Full content string
            start_pos: Position of opening brace

        Returns:
            JSON string with balanced braces or None
        """
        if start_pos >= len(content) or content[start_pos] != '{':
            return None

        brace_count = 0
        in_string = False
        escape_next = False
        end_pos = start_pos

        for i in range(start_pos, len(content)):
            char = content[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i
                        return content[start_pos:end_pos + 1]

        return None