"""
WhatsApp PII Anonymization (ADR-028).

Provides deterministic anonymization of phone numbers in WhatsApp transcripts
using HMAC-SHA256 hashing and memorable pseudonym generation.
"""

from .phone_anonymizer import (
    PhoneAnonymizer,
    hash_phone_number,
    hash_to_pseudonym,
    ADJECTIVES,
    ANIMALS,
)

__all__ = [
    "PhoneAnonymizer",
    "hash_phone_number",
    "hash_to_pseudonym",
    "ADJECTIVES",
    "ANIMALS",
]
