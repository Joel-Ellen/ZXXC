"""Shared resource-generation primitives used by the official learning path.

The package owns the structured card contract, prompt construction, local
validation and rendering.  HTTP handlers and legacy compatibility endpoints
must call this package rather than carrying a second generation implementation.
"""

from .context import ResourceContext, build_resource_context
from .generator import GeneratedResourcePayload, ResourceGenerator, TEMPLATE_NOTICE
from .schemas import CARD_TYPES, CONTENT_VERSION, payload_model_for
from .validator import ValidationIssue, validate_resource_payload

__all__ = [
    "CARD_TYPES",
    "CONTENT_VERSION",
    "GeneratedResourcePayload",
    "ResourceContext",
    "ResourceGenerator",
    "TEMPLATE_NOTICE",
    "ValidationIssue",
    "build_resource_context",
    "payload_model_for",
    "validate_resource_payload",
]
