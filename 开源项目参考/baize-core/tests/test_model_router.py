"""模型路由测试。"""

from __future__ import annotations

from baize_core.llm.router import ModelRouter, ModelRouterConfig, StageModelMapping
from baize_core.schemas.policy import StageType


class TestModelRouter:
    """ModelRouter 单元测试。"""

    def test_按阶段选择模型(self) -> None:
        """测试按阶段选择不同模型。"""
        config = ModelRouterConfig(
            stage_mapping=StageModelMapping(
                outline="planner-model",
                observe="extractor-model",
                orient="extractor-model",
                decide="extractor-model",
                act="writer-model",
                synthesis="writer-model",
            ),
            default_model="default-model",
        )
        router = ModelRouter(config)

        assert router.get_model(StageType.OUTLINE) == "planner-model"
        assert router.get_model(StageType.OBSERVE) == "extractor-model"
        assert router.get_model(StageType.SYNTHESIS) == "writer-model"

    def test_阶段未配置时使用默认模型(self) -> None:
        """测试阶段未配置时回退到默认模型。"""
        config = ModelRouterConfig(
            stage_mapping=StageModelMapping(
                outline="planner-model",
            ),
            default_model="default-model",
        )
        router = ModelRouter(config)

        # outline 有配置
        assert router.get_model(StageType.OUTLINE) == "planner-model"
        # observe 无配置，回退到默认
        assert router.get_model(StageType.OBSERVE) == "default-model"

    def test_从字典加载配置(self) -> None:
        """测试从字典加载配置。"""
        raw = {
            "stage_mapping": {
                "outline": "model-a",
                "synthesis": "model-b",
            },
            "default_model": "model-c",
        }
        config = ModelRouterConfig.from_dict(raw)
        router = ModelRouter(config)

        assert router.get_model(StageType.OUTLINE) == "model-a"
        assert router.get_model(StageType.SYNTHESIS) == "model-b"
        assert router.get_model(StageType.OBSERVE) == "model-c"

    def test_列出所有可用模型(self) -> None:
        """测试列出所有配置的模型。"""
        config = ModelRouterConfig(
            stage_mapping=StageModelMapping(
                outline="planner",
                observe="extractor",
                synthesis="writer",
            ),
            default_model="default",
        )
        router = ModelRouter(config)

        models = router.list_models()
        assert "planner" in models
        assert "extractor" in models
        assert "writer" in models
        assert "default" in models

    def test_检查模型是否允许(self) -> None:
        """测试检查模型是否在配置范围内。"""
        config = ModelRouterConfig(
            stage_mapping=StageModelMapping(
                outline="planner",
            ),
            default_model="default",
        )
        router = ModelRouter(config)

        assert router.is_model_allowed("planner") is True
        assert router.is_model_allowed("default") is True
        assert router.is_model_allowed("unknown") is False
