"""
Dashboard services.

ADR-042: Job execution services for retry and auto-retry functionality.
ADR-072: Coverage tracking and backfill services.
"""

from .job_executor import execute_job
from .coverage_service import get_coverage_service, CoverageService, CoverageReport

__all__ = ["execute_job", "get_coverage_service", "CoverageService", "CoverageReport"]
