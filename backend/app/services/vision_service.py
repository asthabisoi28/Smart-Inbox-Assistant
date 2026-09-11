import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class VisionServiceBase(ABC):
    """Abstract interface for image description and vision analysis services."""

    @abstractmethod
    def describe_image(
        self,
        image_bytes: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates a text description for a meaningful image embedded in a document."""
        pass


class VisionService(VisionServiceBase):
    """
    Vision service implementation.
    Generates basic structural image summaries and serves as the integration
    point for multimodal LLMs (e.g. Gemini Vision).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def describe_image(
        self,
        image_bytes: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        meta = metadata or {}
        width = meta.get("width", "unknown")
        height = meta.get("height", "unknown")
        ext = meta.get("extension", "img")
        page_num = meta.get("page", 1)

        # Baseline structural description
        # Ready for multimodal LLM prompt integration in subsequent steps
        description = (
            f"[Embedded Figure on Page {page_num}: {ext.upper()} graphic, "
            f"resolution {width}x{height}px, size {len(image_bytes)} bytes]"
        )
        return description


# Default singleton instance
vision_service = VisionService()
