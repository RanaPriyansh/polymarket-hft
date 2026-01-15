"""Strategy Layer Bots Package"""

from .resolution_sniper import ResolutionSniper, create_bot as create_resolution_sniper
from .semantic_sentinel import SemanticSentinel, create_bot as create_semantic_sentinel

# Try to import bots that might exist
try:
    from .correlation_scanner import CorrelationScanner
except ImportError:
    CorrelationScanner = None

__all__ = [
    "ResolutionSniper",
    "SemanticSentinel", 
    "create_resolution_sniper",
    "create_semantic_sentinel",
]
