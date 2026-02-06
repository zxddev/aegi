"""LLM 模块入口。"""

from baize_core.llm.router import ModelRouter, ModelRouterConfig, StageModelMapping
from baize_core.llm.runner import LlmConfig, LlmRunner
from baize_core.llm.structured import (
    GenerationMode,
    JsonModeAdapter,
    JsonModeConfig,
    ModelCapability,
    OutlinesAdapter,
    StructuredGenerationError,
    StructuredGenerationResult,
    StructuredGenerator,
    build_json_mode_params,
    build_outlines_prompt,
    build_schema_prompt,
    detect_model_capability,
    extract_json_from_text,
    get_recommended_mode,
    is_outlines_available,
    supports_json_mode,
    validate_and_parse,
)

__all__ = [
    "GenerationMode",
    "JsonModeAdapter",
    "JsonModeConfig",
    "LlmConfig",
    "LlmRunner",
    "ModelCapability",
    "ModelRouter",
    "ModelRouterConfig",
    "OutlinesAdapter",
    "StageModelMapping",
    "StructuredGenerationError",
    "StructuredGenerationResult",
    "StructuredGenerator",
    "build_json_mode_params",
    "build_outlines_prompt",
    "build_schema_prompt",
    "detect_model_capability",
    "extract_json_from_text",
    "get_recommended_mode",
    "is_outlines_available",
    "supports_json_mode",
    "validate_and_parse",
]
