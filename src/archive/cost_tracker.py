"""
Cost tracking and attribution for summary generation.

Tracks API costs per source for billing, budgeting, and reporting.
Implements ADR-006 Section 4: Cost Attribution & Tracking.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .models import CostEntry

logger = logging.getLogger(__name__)


@dataclass
class MonthlyCost:
    """Monthly cost aggregation for a source."""
    cost_usd: float = 0.0
    summaries: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    api_key_source: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cost_usd": round(self.cost_usd, 4),
            "summaries": self.summaries,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "api_key_source": self.api_key_source,
        }


@dataclass
class SourceCost:
    """Cost tracking for a single source."""
    server_name: str
    total_cost_usd: float = 0.0
    summary_count: int = 0
    api_key_source: str = "default"
    api_key_ref: Optional[str] = None
    monthly: Dict[str, MonthlyCost] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "summary_count": self.summary_count,
            "api_key_source": self.api_key_source,
            "api_key_ref": self.api_key_ref,
            "monthly": {k: v.to_dict() for k, v in self.monthly.items()},
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class CostEstimate:
    """Estimated cost for a backfill operation."""
    periods: int
    estimated_cost_usd: float
    avg_tokens_per_summary: int
    model: str
    pricing_version: str


class PricingTable:
    """
    Versioned pricing table for OpenRouter models.

    Fetches pricing from OpenRouter API or uses static fallback.
    """

    # Static fallback pricing (updated 2026-02)
    STATIC_PRICING = {
        "2026-02-01": {
            "anthropic/claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
            "anthropic/claude-haiku-4-20250514": {"input": 0.00025, "output": 0.00125},
            "anthropic/claude-3-haiku": {"input": 0.00025, "output": 0.00125},
            "anthropic/claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
            "anthropic/claude-sonnet-4.5": {"input": 0.003, "output": 0.015},
            "anthropic/claude-opus-4": {"input": 0.015, "output": 0.075},
            "openai/gpt-4-turbo": {"input": 0.01, "output": 0.03},
        },
    }

    def __init__(self, pricing_path: Optional[Path] = None):
        """
        Initialize pricing table.

        Args:
            pricing_path: Path to pricing history JSON file
        """
        self.pricing_path = pricing_path
        self._pricing_cache: Dict[str, Dict] = {}
        self._load_pricing()

    def _load_pricing(self) -> None:
        """Load pricing from file or use static fallback."""
        if self.pricing_path and self.pricing_path.exists():
            with open(self.pricing_path, 'r') as f:
                data = json.load(f)
                for version in data.get("versions", []):
                    self._pricing_cache[version["effective_from"]] = version["models"]
        else:
            self._pricing_cache = self.STATIC_PRICING.copy()

    def get_pricing(
        self,
        model: str,
        timestamp: Optional[datetime] = None
    ) -> Tuple[float, float, str]:
        """
        Get pricing for a model at a specific time.

        Args:
            model: Model ID (e.g., "anthropic/claude-3-haiku")
            timestamp: Time for pricing lookup (default: now)

        Returns:
            Tuple of (input_cost_per_1k, output_cost_per_1k, pricing_version)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Find the applicable pricing version
        applicable_version = None
        applicable_date = None

        for version_date in sorted(self._pricing_cache.keys(), reverse=True):
            version_dt = datetime.fromisoformat(version_date)
            if version_dt <= timestamp:
                applicable_version = self._pricing_cache[version_date]
                applicable_date = version_date
                break

        if not applicable_version:
            # Use the earliest version
            earliest = min(self._pricing_cache.keys())
            applicable_version = self._pricing_cache[earliest]
            applicable_date = earliest

        # Get model pricing
        if model in applicable_version:
            pricing = applicable_version[model]
            return pricing["input"], pricing["output"], applicable_date

        # Try without date suffix
        base_model = model.rsplit("-", 1)[0] if "-2" in model else model
        if base_model in applicable_version:
            pricing = applicable_version[base_model]
            return pricing["input"], pricing["output"], applicable_date

        # Default pricing if model not found
        logger.warning(f"No pricing found for model {model}, using default")
        return 0.003, 0.015, applicable_date

    def calculate_cost(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int,
        timestamp: Optional[datetime] = None
    ) -> Tuple[float, str]:
        """
        Calculate cost for token usage.

        Args:
            model: Model ID
            tokens_input: Number of input tokens
            tokens_output: Number of output tokens
            timestamp: Time for pricing lookup

        Returns:
            Tuple of (cost_usd, pricing_version)
        """
        input_rate, output_rate, version = self.get_pricing(model, timestamp)
        cost = (tokens_input / 1000 * input_rate) + (tokens_output / 1000 * output_rate)
        return round(cost, 6), version

    async def fetch_openrouter_pricing(self, api_key: str) -> bool:
        """
        Fetch current pricing from OpenRouter API.

        Args:
            api_key: OpenRouter API key

        Returns:
            True if pricing was updated
        """
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0
                )

                if response.status_code != 200:
                    logger.warning(f"Failed to fetch OpenRouter pricing: {response.status_code}")
                    return False

                data = response.json()
                today = datetime.utcnow().strftime("%Y-%m-%d")

                # Parse model pricing
                models = {}
                for model in data.get("data", []):
                    model_id = model.get("id")
                    pricing = model.get("pricing", {})

                    if model_id and pricing:
                        # OpenRouter returns per-token prices, we store per-1k
                        input_price = float(pricing.get("prompt", 0)) * 1000
                        output_price = float(pricing.get("completion", 0)) * 1000
                        models[model_id] = {
                            "input": input_price,
                            "output": output_price,
                        }

                if models:
                    self._pricing_cache[today] = models
                    self._save_pricing()
                    logger.info(f"Updated pricing for {len(models)} models")
                    return True

                return False

        except Exception as e:
            logger.error(f"Error fetching OpenRouter pricing: {e}")
            return False

    def _save_pricing(self) -> None:
        """Save pricing to file."""
        if not self.pricing_path:
            return

        versions = []
        for date, models in sorted(self._pricing_cache.items()):
            versions.append({
                "effective_from": date,
                "models": models,
            })

        data = {
            "schema_version": "1.0.0",
            "pricing_source": "openrouter",
            "versions": versions,
        }

        self.pricing_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pricing_path, 'w') as f:
            json.dump(data, f, indent=2)


class CostTracker:
    """
    Tracks and attributes costs per source.

    Maintains a cost ledger for billing and budgeting purposes.
    """

    def __init__(
        self,
        ledger_path: Path,
        pricing_table: Optional[PricingTable] = None
    ):
        """
        Initialize cost tracker.

        Args:
            ledger_path: Path to cost ledger JSON file
            pricing_table: Optional pricing table (creates one if not provided)
        """
        self.ledger_path = ledger_path
        self.pricing = pricing_table or PricingTable()
        self._sources: Dict[str, SourceCost] = {}
        self._total_cost: float = 0.0
        self._total_summaries: int = 0
        self._load_ledger()

    def _load_ledger(self) -> None:
        """Load cost ledger from disk."""
        if not self.ledger_path.exists():
            return

        try:
            with open(self.ledger_path, 'r') as f:
                data = json.load(f)

            self._total_cost = data.get("total_cost_usd", 0.0)
            self._total_summaries = data.get("total_summaries", 0)

            for source_key, source_data in data.get("sources", {}).items():
                monthly = {}
                for month_key, month_data in source_data.get("monthly", {}).items():
                    monthly[month_key] = MonthlyCost(
                        cost_usd=month_data.get("cost_usd", 0.0),
                        summaries=month_data.get("summaries", 0),
                        tokens_input=month_data.get("tokens_input", 0),
                        tokens_output=month_data.get("tokens_output", 0),
                        api_key_source=month_data.get("api_key_source", "default"),
                    )

                self._sources[source_key] = SourceCost(
                    server_name=source_data.get("server_name", ""),
                    total_cost_usd=source_data.get("total_cost_usd", 0.0),
                    summary_count=source_data.get("summary_count", 0),
                    api_key_source=source_data.get("api_key_source", "default"),
                    api_key_ref=source_data.get("api_key_ref"),
                    monthly=monthly,
                    last_updated=datetime.fromisoformat(source_data["last_updated"]) if source_data.get("last_updated") else datetime.utcnow(),
                )

            logger.info(f"Loaded cost ledger: {len(self._sources)} sources, ${self._total_cost:.2f} total")

        except Exception as e:
            logger.error(f"Failed to load cost ledger: {e}")

    def _save_ledger(self) -> None:
        """Save cost ledger to disk."""
        data = {
            "schema_version": "1.0.0",
            "currency": "USD",
            "total_cost_usd": round(self._total_cost, 4),
            "total_summaries": self._total_summaries,
            "sources": {k: v.to_dict() for k, v in self._sources.items()},
        }

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger_path, 'w') as f:
            json.dump(data, f, indent=2)

    def record_cost(self, entry: CostEntry) -> None:
        """
        Record a cost entry to the ledger.

        Args:
            entry: Cost entry to record
        """
        source_key = entry.source_key

        # Get or create source cost record
        if source_key not in self._sources:
            self._sources[source_key] = SourceCost(
                server_name="",
                api_key_source=entry.api_key_source,
            )

        source = self._sources[source_key]
        month_key = entry.timestamp.strftime("%Y-%m")

        # Get or create monthly record
        if month_key not in source.monthly:
            source.monthly[month_key] = MonthlyCost(
                api_key_source=entry.api_key_source,
            )

        monthly = source.monthly[month_key]

        # Update totals
        source.total_cost_usd += entry.cost_usd
        source.summary_count += 1
        source.last_updated = datetime.utcnow()

        monthly.cost_usd += entry.cost_usd
        monthly.summaries += 1
        monthly.tokens_input += entry.tokens_input
        monthly.tokens_output += entry.tokens_output

        self._total_cost += entry.cost_usd
        self._total_summaries += 1

        self._save_ledger()
        logger.debug(f"Recorded cost ${entry.cost_usd:.4f} for {source_key}")

    def get_source_cost(self, source_key: str) -> Optional[SourceCost]:
        """
        Get cost information for a source.

        Args:
            source_key: Source key

        Returns:
            Source cost record if found
        """
        return self._sources.get(source_key)

    def get_monthly_cost(
        self,
        source_key: str,
        year: int,
        month: int
    ) -> Optional[MonthlyCost]:
        """
        Get monthly cost for a source.

        Args:
            source_key: Source key
            year: Year
            month: Month (1-12)

        Returns:
            Monthly cost if found
        """
        source = self._sources.get(source_key)
        if not source:
            return None

        month_key = f"{year:04d}-{month:02d}"
        return source.monthly.get(month_key)

    def get_total_cost(self) -> float:
        """Get total cost across all sources."""
        return self._total_cost

    def get_current_month_cost(self, source_key: str) -> float:
        """Get current month's cost for a source."""
        now = datetime.utcnow()
        monthly = self.get_monthly_cost(source_key, now.year, now.month)
        return monthly.cost_usd if monthly else 0.0

    def estimate_backfill_cost(
        self,
        source_key: str,
        periods: int,
        model: str = "anthropic/claude-3-haiku",
        avg_tokens_per_summary: int = 5000
    ) -> CostEstimate:
        """
        Estimate cost for a backfill operation.

        Args:
            source_key: Source key
            periods: Number of periods to backfill
            model: Model to use
            avg_tokens_per_summary: Average tokens per summary

        Returns:
            Cost estimate
        """
        # Assume 80% input, 20% output ratio
        input_tokens = int(avg_tokens_per_summary * 0.8)
        output_tokens = int(avg_tokens_per_summary * 0.2)

        per_summary_cost, pricing_version = self.pricing.calculate_cost(
            model, input_tokens, output_tokens
        )

        total_cost = per_summary_cost * periods

        return CostEstimate(
            periods=periods,
            estimated_cost_usd=round(total_cost, 4),
            avg_tokens_per_summary=avg_tokens_per_summary,
            model=model,
            pricing_version=pricing_version,
        )

    def check_budget(
        self,
        source_key: str,
        budget_monthly_usd: Optional[float]
    ) -> Tuple[bool, float, float]:
        """
        Check if a source is within budget.

        Args:
            source_key: Source key
            budget_monthly_usd: Monthly budget (None = unlimited)

        Returns:
            Tuple of (within_budget, current_cost, remaining)
        """
        if budget_monthly_usd is None:
            return True, 0.0, float('inf')

        current = self.get_current_month_cost(source_key)
        remaining = budget_monthly_usd - current
        within_budget = current < budget_monthly_usd

        return within_budget, current, max(0, remaining)

    def get_cost_report(self) -> Dict[str, Any]:
        """
        Generate a cost report for all sources.

        Returns:
            Cost report dictionary
        """
        now = datetime.utcnow()
        month_key = now.strftime("%Y-%m")

        report = {
            "period": month_key,
            "total_cost_usd": round(self._total_cost, 4),
            "total_summaries": self._total_summaries,
            "sources": [],
        }

        for source_key, source in self._sources.items():
            monthly = source.monthly.get(month_key, MonthlyCost())
            report["sources"].append({
                "source_key": source_key,
                "server_name": source.server_name,
                "total_cost_usd": round(source.total_cost_usd, 4),
                "summary_count": source.summary_count,
                "current_month": {
                    "cost_usd": round(monthly.cost_usd, 4),
                    "summaries": monthly.summaries,
                    "tokens_input": monthly.tokens_input,
                    "tokens_output": monthly.tokens_output,
                },
                "api_key_source": source.api_key_source,
            })

        return report
