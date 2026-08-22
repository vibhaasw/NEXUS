"""External AI dispatch: classify, route, and call provider APIs."""

from dispatch.classifier import ClassificationResult, TaskClassifier, default_classification, parse_classification_payload
from dispatch.key_pool import KeyPool, ResolvedAccount
from dispatch.orchestrator import AIOrchestrator, DispatchResult
from dispatch.provider_config import AccountSpec, ProviderSpec, load_providers
from dispatch.providers import CompletionResult, RateLimitError, build_adapter

__all__ = [
    "AccountSpec",
    "AIOrchestrator",
    "ClassificationResult",
    "CompletionResult",
    "DispatchResult",
    "KeyPool",
    "ProviderSpec",
    "RateLimitError",
    "ResolvedAccount",
    "TaskClassifier",
    "build_adapter",
    "default_classification",
    "load_providers",
    "parse_classification_payload",
]
