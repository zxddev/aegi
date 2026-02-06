"""模型配置加载。

支持从环境变量或 YAML 文件加载模型路由配置。
包含 LiteLLM Router 多模型路由/降级/成本控制配置。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from baize_core.llm.router import (
    FallbackSpec,
    LiteLLMRouterConfig,
    ModelRouterConfig,
    ModelSpec,
    StageModelMapping,
)

# 环境变量名称
ENV_MODEL_CONFIG = "BAIZE_CORE_MODEL_CONFIG"
ENV_MODEL_CONFIG_PATH = "BAIZE_CORE_MODEL_CONFIG_PATH"
ENV_LITELLM_MODELS = "BAIZE_CORE_LITELLM_MODELS"
ENV_LITELLM_FALLBACKS = "BAIZE_CORE_LITELLM_FALLBACKS"

# 默认配置
DEFAULT_CONFIG = ModelRouterConfig(
    stage_mapping=StageModelMapping(
        outline=None,
        observe=None,
        orient=None,
        decide=None,
        act=None,
        synthesis=None,
    ),
    default_model="default",
    litellm_config=None,
)


def load_model_config() -> ModelRouterConfig:
    """从环境加载模型路由配置。

    优先级：
    1. BAIZE_CORE_MODEL_CONFIG（JSON 字符串）
    2. BAIZE_CORE_MODEL_CONFIG_PATH（YAML/JSON 文件路径）
    3. 默认配置

    Returns:
        ModelRouterConfig 实例
    """
    # 尝试从 JSON 环境变量加载
    json_config = os.getenv(ENV_MODEL_CONFIG)
    if json_config:
        try:
            data = json.loads(json_config)
            return ModelRouterConfig.from_dict(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"无法解析 {ENV_MODEL_CONFIG}: {exc}") from exc

    # 尝试从文件路径加载
    config_path = os.getenv(ENV_MODEL_CONFIG_PATH)
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"模型配置文件不存在: {config_path}")
        return _load_from_file(path)

    # 返回默认配置
    return DEFAULT_CONFIG


def _load_from_file(path: Path) -> ModelRouterConfig:
    """从文件加载配置。

    Args:
        path: 配置文件路径

    Returns:
        ModelRouterConfig 实例
    """
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix in {".json"}:
        data = json.loads(content)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml

            data = yaml.safe_load(content)
        except ImportError as exc:
            raise ImportError("加载 YAML 配置需要安装 pyyaml") from exc
    else:
        raise ValueError(f"不支持的配置文件格式: {suffix}")

    if not isinstance(data, dict):
        raise ValueError("配置文件内容必须是字典")

    return ModelRouterConfig.from_dict(data)


def create_model_config_from_env(
    stage_models: dict[str, str] | None = None,
    default_model: str = "default",
    litellm_config: LiteLLMRouterConfig | None = None,
) -> ModelRouterConfig:
    """从参数创建模型配置（用于测试或编程式配置）。

    Args:
        stage_models: 阶段到模型的映射字典
        default_model: 默认模型
        litellm_config: LiteLLM Router 配置

    Returns:
        ModelRouterConfig 实例
    """
    if stage_models is None:
        stage_models = {}

    stage_mapping = StageModelMapping(
        outline=stage_models.get("outline"),
        observe=stage_models.get("observe"),
        orient=stage_models.get("orient"),
        decide=stage_models.get("decide"),
        act=stage_models.get("act"),
        synthesis=stage_models.get("synthesis"),
    )
    return ModelRouterConfig(
        stage_mapping=stage_mapping,
        default_model=default_model,
        litellm_config=litellm_config,
    )


def create_litellm_config(
    models: list[dict[str, Any]] | None = None,
    fallbacks: list[dict[str, Any]] | None = None,
    routing_strategy: str = "simple-shuffle",
    num_retries: int = 2,
    timeout: float = 120.0,
) -> LiteLLMRouterConfig:
    """创建 LiteLLM Router 配置。

    Args:
        models: 模型配置列表，每项包含:
            - model_name: 路由器内部使用的模型别名
            - litellm_model: LiteLLM 模型标识
            - api_base: API 基地址（可选）
            - api_key: API 密钥（可选）
            - rpm: 每分钟请求数限制（可选）
            - tpm: 每分钟 token 数限制（可选）
        fallbacks: 降级配置列表，每项包含:
            - primary: 主模型名称
            - fallbacks: 降级模型列表
        routing_strategy: 路由策略
        num_retries: 重试次数
        timeout: 超时时间

    Returns:
        LiteLLMRouterConfig 实例
    """
    model_specs = []
    if models:
        for m in models:
            model_specs.append(
                ModelSpec(
                    model_name=m["model_name"],
                    litellm_model=m["litellm_model"],
                    api_base=m.get("api_base"),
                    api_key=m.get("api_key"),
                    rpm=m.get("rpm"),
                    tpm=m.get("tpm"),
                )
            )

    fallback_specs = []
    if fallbacks:
        for f in fallbacks:
            fallback_specs.append(
                FallbackSpec(
                    primary=f["primary"],
                    fallbacks=f["fallbacks"],
                )
            )

    return LiteLLMRouterConfig(
        models=model_specs,
        fallbacks=fallback_specs,
        routing_strategy=routing_strategy,
        num_retries=num_retries,
        timeout=timeout,
    )


def create_default_litellm_config() -> LiteLLMRouterConfig:
    """创建默认的 LiteLLM Router 配置。

    阶段路由：
    - planner: 规划/大纲生成（推荐 deepseek-r1 或同级推理模型）
    - extractor: 抽取/分析（推荐 qwen2.5-72b 或同级）
    - writer: 写作/合成（推荐 deepseek-v3 或同级长上下文模型）

    降级链：planner -> extractor -> writer

    Returns:
        LiteLLMRouterConfig 实例
    """
    # 从环境变量读取模型配置
    planner_model = os.getenv("LITELLM_PLANNER_MODEL", "deepseek/deepseek-r1")
    extractor_model = os.getenv("LITELLM_EXTRACTOR_MODEL", "ollama/qwen2.5:72b")
    writer_model = os.getenv("LITELLM_WRITER_MODEL", "deepseek/deepseek-v3")

    planner_api_base = os.getenv("LITELLM_PLANNER_API_BASE")
    extractor_api_base = os.getenv(
        "LITELLM_EXTRACTOR_API_BASE", "http://localhost:11434"
    )
    writer_api_base = os.getenv("LITELLM_WRITER_API_BASE")

    models = [
        ModelSpec(
            model_name="planner",
            litellm_model=planner_model,
            api_base=planner_api_base,
        ),
        ModelSpec(
            model_name="extractor",
            litellm_model=extractor_model,
            api_base=extractor_api_base,
        ),
        ModelSpec(
            model_name="writer",
            litellm_model=writer_model,
            api_base=writer_api_base,
        ),
    ]

    fallbacks = [
        FallbackSpec(primary="planner", fallbacks=["extractor", "writer"]),
        FallbackSpec(primary="extractor", fallbacks=["writer"]),
    ]

    return LiteLLMRouterConfig(
        models=models,
        fallbacks=fallbacks,
        routing_strategy="simple-shuffle",
        num_retries=2,
        timeout=120.0,
    )


def load_model_config_with_litellm() -> ModelRouterConfig:
    """加载包含 LiteLLM 配置的模型路由配置。

    优先从文件/环境变量加载，否则使用默认 LiteLLM 配置。

    Returns:
        ModelRouterConfig 实例
    """
    # 先尝试加载基础配置
    config = load_model_config()

    # 如果没有 LiteLLM 配置，尝试从环境变量创建
    if config.litellm_config is None:
        litellm_models_json = os.getenv(ENV_LITELLM_MODELS)
        if litellm_models_json:
            try:
                models_data = json.loads(litellm_models_json)
                fallbacks_json = os.getenv(ENV_LITELLM_FALLBACKS, "[]")
                fallbacks_data = json.loads(fallbacks_json)
                config = ModelRouterConfig(
                    stage_mapping=config.stage_mapping,
                    default_model=config.default_model,
                    litellm_config=create_litellm_config(
                        models=models_data,
                        fallbacks=fallbacks_data,
                    ),
                )
            except json.JSONDecodeError:
                pass

    return config
