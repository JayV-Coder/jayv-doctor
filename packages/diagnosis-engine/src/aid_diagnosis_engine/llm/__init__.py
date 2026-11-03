"""Acesso ao LLM do motor de diagnóstico (ticket #22, ADR-0007): o diagnóstico usa `GuardedLLM`
sobre o provedor da Organização (`provider_for`)."""

from aid_diagnosis_engine.llm.base import (
    LLMError,
    LLMInvalidOutputError,
    LLMProvider,
    LLMTransientError,
    LLMUnavailableError,
    Msg,
    StructuredResult,
    Usage,
)
from aid_diagnosis_engine.llm.client import GuardedLLM
from aid_diagnosis_engine.llm.guards import Untrusted
from aid_diagnosis_engine.llm.registry import PROVIDERS, provider_for

__all__ = [
    "PROVIDERS",
    "GuardedLLM",
    "LLMError",
    "LLMInvalidOutputError",
    "LLMProvider",
    "LLMTransientError",
    "LLMUnavailableError",
    "Msg",
    "StructuredResult",
    "Untrusted",
    "Usage",
    "provider_for",
]
