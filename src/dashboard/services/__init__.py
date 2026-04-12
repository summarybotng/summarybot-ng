"""
Dashboard services.

ADR-042: Job execution services for retry and auto-retry functionality.
"""

from .job_executor import execute_job

__all__ = ["execute_job"]
