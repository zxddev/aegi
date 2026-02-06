"""结构化输出生成器。

支持三种模式：
- json_mode: 云 API 的 JSON mode（OpenAI/Anthropic/DeepSeek）
- outlines: 本地模型的约束解码
- post_validate: 后置 Pydantic 校验（兜底）

三段式保障流程：
1. Schema 定义（Pydantic）
2. 生成时约束（云 API 用 JSON mode，本地模型用 Outlines）
3. 落地前校验（Pydantic 校验失败 → 重试 → 降级/人工介入）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

# 从统一异常模块导入，保持向后兼容性（重新导出）
from baize_core.exceptions import StructuredGenerationError

T = TypeVar("T", bound=BaseModel)

# 重新导出以保持向后兼容性
__all__ = [
    "GenerationMode",
    "ModelCapability",
    "StructuredGenerationResult",
    "StructuredGenerationError",
    "extract_json_from_text",
    "detect_model_capability",
    "is_outlines_available",
    "build_outlines_prompt",
    "StructuredGenerator",
    "OutlinesAdapter",
]


class GenerationMode(str, Enum):
    """结构化生成模式。"""

    JSON_MODE = "json_mode"
    """云 API 的 JSON mode，通过 response_format 参数约束输出。"""

    OUTLINES = "outlines"
    """本地模型的约束解码，使用 Outlines 库。"""

    POST_VALIDATE = "post_validate"
    """后置校验模式，生成文本后提取 JSON 并用 Pydantic 校验。"""


class ModelCapability(str, Enum):
    """模型结构化输出能力。"""

    JSON_MODE = "json_mode"
    """支持 JSON mode（response_format 参数）。"""

    FUNCTION_CALL = "function_call"
    """支持函数调用（tool_choice 参数）。"""

    OUTLINES = "outlines"
    """本地模型，可用 Outlines 约束解码。"""

    TEXT_ONLY = "text_only"
    """仅文本输出，需要后置校验。"""


@dataclass(frozen=True)
class StructuredGenerationResult:
    """结构化生成结果。

    Attributes:
        data: 解析后的数据对象
        raw_text: 原始输出文本
        mode_used: 使用的生成模式
        retries: 重试次数
        validation_errors: 校验错误列表（如果有）
    """

    data: BaseModel
    raw_text: str
    mode_used: GenerationMode
    retries: int
    validation_errors: list[str]


def extract_json_from_text(text: str) -> str | None:
    """从文本中提取 JSON 内容。

    支持以下格式：
    1. 纯 JSON 文本
    2. Markdown 代码块中的 JSON
    3. 文本中嵌入的 JSON 对象/数组

    Args:
        text: 原始文本

    Returns:
        提取的 JSON 字符串，未找到返回 None
    """
    stripped = text.strip()

    # 尝试直接解析
    if _is_valid_json(stripped):
        return stripped

    # 尝试从 markdown 代码块提取
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(code_block_pattern, text)
    for match in matches:
        content = match.strip()
        if _is_valid_json(content):
            return content

    # 尝试提取嵌入的 JSON 对象
    brace_pattern = r"\{[\s\S]*\}"
    brace_matches = re.findall(brace_pattern, text)
    for match in brace_matches:
        if _is_valid_json(match):
            return match

    # 尝试提取嵌入的 JSON 数组
    bracket_pattern = r"\[[\s\S]*\]"
    bracket_matches = re.findall(bracket_pattern, text)
    for match in bracket_matches:
        if _is_valid_json(match):
            return match

    return None


def _is_valid_json(text: str) -> bool:
    """检查文本是否为有效 JSON。"""
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def validate_and_parse(  # noqa: UP047
    text: str,
    schema: type[T],
) -> tuple[T | None, list[str]]:
    """校验并解析文本为 Pydantic 模型。

    Args:
        text: JSON 文本
        schema: Pydantic 模型类

    Returns:
        (解析结果, 错误列表) 元组
    """
    errors: list[str] = []

    # 提取 JSON
    json_str = extract_json_from_text(text)
    if json_str is None:
        errors.append("无法从输出中提取有效 JSON")
        return None, errors

    # 解析 JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        errors.append(f"JSON 解析失败: {exc}")
        return None, errors

    # Pydantic 校验
    try:
        result = schema.model_validate(data)
        return result, errors
    except ValidationError as exc:
        for error in exc.errors():
            loc = ".".join(str(loc_item) for loc_item in error["loc"])
            msg = error["msg"]
            errors.append(f"字段 '{loc}': {msg}")
        return None, errors


def build_schema_prompt(schema: type[BaseModel]) -> str:
    """构建 schema 提示词。

    将 Pydantic schema 转换为人类可读的 JSON Schema 描述，
    用于在 prompt 中指导 LLM 输出格式。

    Args:
        schema: Pydantic 模型类

    Returns:
        JSON Schema 字符串
    """
    json_schema = schema.model_json_schema()
    return json.dumps(json_schema, ensure_ascii=False, indent=2)


class StructuredGenerator:
    """结构化输出生成器。

    负责将 LLM 输出约束为符合 Pydantic schema 的结构化数据。
    支持三种模式：json_mode、outlines、post_validate。

    使用方式：
    1. 创建生成器实例（可选指定默认模式）
    2. 调用 generate() 方法，传入原始文本和目标 schema
    3. 获取解析后的结构化数据
    """

    def __init__(
        self,
        default_mode: GenerationMode = GenerationMode.POST_VALIDATE,
        max_retries: int = 3,
    ) -> None:
        """初始化生成器。

        Args:
            default_mode: 默认生成模式
            max_retries: 最大重试次数
        """
        self._default_mode = default_mode
        self._max_retries = max_retries

    @property
    def default_mode(self) -> GenerationMode:
        """获取默认生成模式。"""
        return self._default_mode

    @property
    def max_retries(self) -> int:
        """获取最大重试次数。"""
        return self._max_retries

    def parse_with_validation(
        self,
        text: str,
        schema: type[T],
    ) -> StructuredGenerationResult:
        """使用后置校验模式解析文本。

        Args:
            text: LLM 输出的原始文本
            schema: 目标 Pydantic schema

        Returns:
            结构化生成结果

        Raises:
            StructuredGenerationError: 校验失败
        """
        result, errors = validate_and_parse(text, schema)
        if result is not None:
            return StructuredGenerationResult(
                data=result,
                raw_text=text,
                mode_used=GenerationMode.POST_VALIDATE,
                retries=0,
                validation_errors=[],
            )

        raise StructuredGenerationError(
            message="结构化输出校验失败",
            raw_text=text,
            validation_errors=errors,
            retries=0,
        )

    def build_structured_prompt(
        self,
        user_prompt: str,
        schema: type[BaseModel],
    ) -> str:
        """构建带 schema 约束的用户提示词。

        Args:
            user_prompt: 原始用户提示词
            schema: 目标 Pydantic schema

        Returns:
            增强后的提示词
        """
        schema_str = build_schema_prompt(schema)
        return (
            f"{user_prompt}\n\n"
            "请严格按照以下 JSON Schema 格式输出，不要包含任何其他内容：\n"
            f"```json\n{schema_str}\n```\n\n"
            "输出 JSON："
        )


def get_recommended_mode(capability: ModelCapability) -> GenerationMode:
    """根据模型能力推荐生成模式。

    Args:
        capability: 模型能力

    Returns:
        推荐的生成模式
    """
    mode_map = {
        ModelCapability.JSON_MODE: GenerationMode.JSON_MODE,
        ModelCapability.FUNCTION_CALL: GenerationMode.JSON_MODE,
        ModelCapability.OUTLINES: GenerationMode.OUTLINES,
        ModelCapability.TEXT_ONLY: GenerationMode.POST_VALIDATE,
    }
    return mode_map.get(capability, GenerationMode.POST_VALIDATE)


def is_outlines_available() -> bool:
    """检查 Outlines 库是否可用。

    Returns:
        是否可用
    """
    try:
        import outlines  # noqa: F401

        return True
    except ImportError:
        return False


class OutlinesAdapter:
    """Outlines 约束解码适配器。

    封装 Outlines 库的调用，支持本地模型的结构化输出约束。
    Outlines 通过正则表达式约束解码，确保输出符合 JSON Schema。

    使用方式：
    1. 创建适配器实例（指定模型）
    2. 调用 generate() 方法生成符合 schema 的输出

    注意：
    - 需要安装 outlines 库
    - 仅适用于本地模型（transformers/vLLM/llama.cpp）
    - 云 API 应使用 JSON mode 而非 Outlines
    """

    def __init__(
        self,
        model_name: str,
        model_backend: str = "transformers",
    ) -> None:
        """初始化适配器。

        Args:
            model_name: 模型名称或路径
            model_backend: 模型后端（transformers/vllm/llamacpp）

        Raises:
            ImportError: 未安装 outlines 库
        """
        if not is_outlines_available():
            raise ImportError(
                "使用 Outlines 模式需要安装 outlines 库: pip install outlines"
            )
        self._model_name = model_name
        self._model_backend = model_backend
        self._model: Any = None
        self._generator_cache: dict[str, Any] = {}

    @property
    def model_name(self) -> str:
        """获取模型名称。"""
        return self._model_name

    @property
    def model_backend(self) -> str:
        """获取模型后端。"""
        return self._model_backend

    def _get_or_create_model(self) -> Any:
        """获取或创建模型实例。

        Returns:
            Outlines 模型实例

        Raises:
            ValueError: 不支持的模型后端
        """
        if self._model is not None:
            return self._model

        import outlines

        if self._model_backend == "transformers":
            self._model = outlines.models.transformers(self._model_name)
        elif self._model_backend == "vllm":
            self._model = outlines.models.vllm(self._model_name)
        elif self._model_backend == "llamacpp":
            self._model = outlines.models.llamacpp(self._model_name)
        else:
            raise ValueError(f"不支持的模型后端: {self._model_backend}")

        return self._model

    def generate(
        self,
        prompt: str,
        schema: type[T],
        max_tokens: int = 1024,
    ) -> StructuredGenerationResult:
        """使用 Outlines 生成结构化输出。

        Args:
            prompt: 输入提示词
            schema: 目标 Pydantic schema
            max_tokens: 最大生成 token 数

        Returns:
            结构化生成结果

        Raises:
            StructuredGenerationError: 生成或校验失败
        """
        import outlines

        model = self._get_or_create_model()

        # 为 schema 创建或获取缓存的生成器
        schema_key = schema.__name__
        if schema_key not in self._generator_cache:
            self._generator_cache[schema_key] = outlines.generate.json(model, schema)

        generator = self._generator_cache[schema_key]

        try:
            # 使用 Outlines 生成
            result = generator(prompt, max_tokens=max_tokens)

            # result 已经是 Pydantic 模型实例
            if isinstance(result, schema):
                return StructuredGenerationResult(
                    data=result,
                    raw_text=result.model_dump_json(),
                    mode_used=GenerationMode.OUTLINES,
                    retries=0,
                    validation_errors=[],
                )

            # 如果返回的不是预期类型，尝试转换
            if isinstance(result, dict):
                parsed = schema.model_validate(result)
                return StructuredGenerationResult(
                    data=parsed,
                    raw_text=json.dumps(result, ensure_ascii=False),
                    mode_used=GenerationMode.OUTLINES,
                    retries=0,
                    validation_errors=[],
                )

            raise StructuredGenerationError(
                message=f"Outlines 返回了意外的类型: {type(result)}",
                raw_text=str(result),
                validation_errors=[
                    f"预期 {schema.__name__}，实际 {type(result).__name__}"
                ],
            )

        except ValidationError as exc:
            errors = [
                f"字段 '{'.'.join(str(loc) for loc in e['loc'])}': {e['msg']}"
                for e in exc.errors()
            ]
            raise StructuredGenerationError(
                message="Outlines 输出校验失败",
                raw_text="",
                validation_errors=errors,
            ) from exc
        except Exception as exc:
            raise StructuredGenerationError(
                message=f"Outlines 生成失败: {exc}",
                raw_text="",
                validation_errors=[str(exc)],
            ) from exc

    def generate_batch(
        self,
        prompts: list[str],
        schema: type[T],
        max_tokens: int = 1024,
    ) -> list[StructuredGenerationResult]:
        """批量生成结构化输出。

        Args:
            prompts: 输入提示词列表
            schema: 目标 Pydantic schema
            max_tokens: 最大生成 token 数

        Returns:
            结构化生成结果列表
        """
        return [self.generate(prompt, schema, max_tokens) for prompt in prompts]


def build_outlines_prompt(
    system: str,
    user: str,
    schema: type[BaseModel],
) -> str:
    """构建 Outlines 使用的提示词。

    Args:
        system: 系统提示
        user: 用户输入
        schema: 目标 Pydantic schema

    Returns:
        完整的提示词
    """
    schema_str = build_schema_prompt(schema)
    return (
        f"{system}\n\n"
        f"{user}\n\n"
        f"请严格按照以下 JSON Schema 格式输出：\n{schema_str}\n\n"
        "JSON 输出："
    )


@dataclass(frozen=True)
class JsonModeConfig:
    """JSON mode 配置。

    用于配置云 API 的 JSON mode 参数。

    Attributes:
        response_format: 响应格式类型（json_object/json_schema）
        schema_name: schema 名称（用于 json_schema 模式）
        strict: 是否严格模式（OpenAI 支持）
    """

    response_format: str = "json_object"
    schema_name: str = "output"
    strict: bool = False


def build_json_mode_params(
    schema: type[BaseModel],
    config: JsonModeConfig | None = None,
) -> dict[str, Any]:
    """构建 JSON mode 请求参数。

    根据模型提供商生成对应的 response_format 参数。

    Args:
        schema: 目标 Pydantic schema
        config: JSON mode 配置

    Returns:
        response_format 参数字典
    """
    if config is None:
        config = JsonModeConfig()

    json_schema = schema.model_json_schema()

    if config.response_format == "json_schema":
        # OpenAI 的 json_schema 模式（更严格）
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": config.schema_name,
                    "schema": json_schema,
                    "strict": config.strict,
                },
            }
        }

    # 通用 json_object 模式
    return {"response_format": {"type": "json_object"}}


class JsonModeAdapter:
    """JSON mode 适配器。

    封装云 API 的 JSON mode 调用，支持 OpenAI/Anthropic/DeepSeek 等提供商。

    使用方式：
    1. 创建适配器实例
    2. 调用 build_params() 获取请求参数
    3. 调用 parse_response() 解析响应

    注意：
    - 仅适用于支持 JSON mode 的云 API
    - 本地模型应使用 Outlines 而非 JSON mode
    """

    def __init__(
        self,
        config: JsonModeConfig | None = None,
    ) -> None:
        """初始化适配器。

        Args:
            config: JSON mode 配置
        """
        self._config = config or JsonModeConfig()

    @property
    def config(self) -> JsonModeConfig:
        """获取配置。"""
        return self._config

    def build_params(
        self,
        schema: type[BaseModel],
    ) -> dict[str, Any]:
        """构建 JSON mode 请求参数。

        Args:
            schema: 目标 Pydantic schema

        Returns:
            请求参数字典
        """
        return build_json_mode_params(schema, self._config)

    def parse_response(
        self,
        response_text: str,
        schema: type[T],
    ) -> StructuredGenerationResult:
        """解析 JSON mode 响应。

        Args:
            response_text: API 响应文本
            schema: 目标 Pydantic schema

        Returns:
            结构化生成结果

        Raises:
            StructuredGenerationError: 解析或校验失败
        """
        result, errors = validate_and_parse(response_text, schema)
        if result is not None:
            return StructuredGenerationResult(
                data=result,
                raw_text=response_text,
                mode_used=GenerationMode.JSON_MODE,
                retries=0,
                validation_errors=[],
            )

        raise StructuredGenerationError(
            message="JSON mode 输出校验失败",
            raw_text=response_text,
            validation_errors=errors,
        )


# 已知支持 JSON mode 的模型前缀
JSON_MODE_SUPPORTED_PREFIXES = [
    "gpt-4",
    "gpt-3.5",
    "claude-3",
    "deepseek",
    "gemini",
    "qwen",
]


def supports_json_mode(model_name: str) -> bool:
    """检查模型是否支持 JSON mode。

    Args:
        model_name: 模型名称

    Returns:
        是否支持
    """
    model_lower = model_name.lower()
    return any(prefix in model_lower for prefix in JSON_MODE_SUPPORTED_PREFIXES)


def detect_model_capability(model_name: str) -> ModelCapability:
    """检测模型的结构化输出能力。

    检测顺序：
    1. 先检查是否为本地模型前缀（ollama/vllm/llamacpp）
    2. 再检查是否为支持 JSON mode 的云 API 模型
    3. 其他模型使用后置校验

    Args:
        model_name: 模型名称

    Returns:
        模型能力
    """
    model_lower = model_name.lower()

    # 本地模型（ollama/vllm/llamacpp）使用 Outlines，优先检测
    local_prefixes = ["ollama/", "vllm/", "llamacpp/", "local/"]
    if any(model_lower.startswith(prefix) for prefix in local_prefixes):
        return ModelCapability.OUTLINES

    # 云 API 模型通常支持 JSON mode
    if supports_json_mode(model_name):
        return ModelCapability.JSON_MODE

    # 其他模型使用后置校验
    return ModelCapability.TEXT_ONLY
