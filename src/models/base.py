"""
Base model classes for Summary Bot NG.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
import uuid
from src.utils.time import utc_now_naive


def _serialize_value(value: Any) -> Any:
    """Serialize a value, handling enums and nested objects."""
    if isinstance(value, Enum):
        return value.value
    elif isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, list):
        return [_serialize_value(item) for item in value]
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif hasattr(value, 'to_dict'):
        return value.to_dict()
    return value


@dataclass
class BaseModel:
    """Base model class with common functionality."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary, properly serializing enums."""
        result = {}
        for f in fields(self):
            value = getattr(self, f.name)
            result[f.name] = _serialize_value(value)
        return result
    
    def to_json(self) -> str:
        """Convert model to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseModel':
        """Create model instance from dictionary."""
        return cls(**data)
    
    @classmethod 
    def from_json(cls, json_str: str) -> 'BaseModel':
        """Create model instance from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class SerializableModel(ABC):
    """Abstract base class for models that need custom serialization."""
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        pass
    
    @abstractmethod
    def to_json(self) -> str:
        """Convert to JSON string."""
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SerializableModel':
        """Create instance from dictionary."""
        pass


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return utc_now_naive().replace(microsecond=0)