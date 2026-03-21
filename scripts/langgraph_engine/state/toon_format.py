"""ToonObject - TOON Format (Tokenized Object-Oriented Notation).

Compact, semantic-preserving data format for workflow context.
- Stores data in compressed "essential" form
- Maintains reference to full data in workflow_memory
- Includes schema for smart reconstruction
- Preserves deep semantic meaning in minimal space

Example TOON object:
{
    "_toon": True,
    "_schema": "task_list",
    "_version": "1.0",
    "essential": {"count": 5, "critical": ["auth", "db"]},
    "metadata": {"original_size_kb": 45, "compressed_size_kb": 2},
    "_memory_key": "step1_output"
}
"""

from typing import Dict, Any, Optional


class ToonObject:
    """TOON Format - Tokenized Object-Oriented Notation.

    Compact, semantic-preserving data format for workflow context.
    - Stores data in compressed "essential" form
    - Maintains reference to full data in workflow_memory
    - Includes schema for smart reconstruction
    - Preserves deep semantic meaning in minimal space
    """

    @staticmethod
    def create(schema: str, essential_data: Dict, full_data: Dict = None, memory_key: str = "") -> Dict:
        """Create a TOON object.

        Args:
            schema: Type of data (e.g., "task_list", "context_status")
            essential_data: Minimal representation of data
            full_data: Full data (for size calculation)
            memory_key: Reference to where full data is stored

        Returns:
            TOON-formatted dict
        """
        full_size = len(str(full_data).encode()) / 1024 if full_data else 0
        essential_size = len(str(essential_data).encode()) / 1024

        return {
            "_toon": True,
            "_schema": schema,
            "_version": "1.0",
            "essential": essential_data,
            "metadata": {
                "original_size_kb": round(full_size, 2),
                "compressed_size_kb": round(essential_size, 2),
                "compression_ratio": round(full_size / (essential_size or 1), 1)
            },
            "_memory_key": memory_key,  # Reference to full data in workflow_memory
        }

    @staticmethod
    def is_toon(obj: Any) -> bool:
        """Check if object is TOON format."""
        return isinstance(obj, dict) and obj.get("_toon") is True

    @staticmethod
    def extract(toon_obj: Dict) -> Dict:
        """Extract essential data from TOON object."""
        if ToonObject.is_toon(toon_obj):
            return toon_obj.get("essential", {})
        return toon_obj

    @staticmethod
    def get_schema(toon_obj: Dict) -> str:
        """Get schema of TOON object."""
        if ToonObject.is_toon(toon_obj):
            return toon_obj.get("_schema", "unknown")
        return "unknown"

    @staticmethod
    def get_memory_reference(toon_obj: Dict) -> str:
        """Get reference to full data in workflow_memory."""
        if ToonObject.is_toon(toon_obj):
            return toon_obj.get("_memory_key", "")
        return ""
