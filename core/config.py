from dataclasses import dataclass
from typing import Literal


@dataclass
class PluginConfig:
    memory_mode: Literal["global", "shared"] = "global"
    fifo_size: int = 10
    summary_mode: Literal["search_replace", "full_replace"] = "search_replace"
    inject_fifo_in_group: bool = True
    auto_summary_interval_minutes: int = 0
    max_memory_per_layer: int = 50

    # LLM Provider 配置
    summary_provider_id: str = ""           # 留空 = 使用 AstrBot 主对话模型
    summary_system_prompt: str = ""         # 总结任务的额外系统提示词

    # 注入控制
    inject_memory_in_private: bool = True
    inject_layers_in_group: Literal["important_only", "important_general", "all"] = "important_only"

    # 功能开关
    enable_auto_summary: bool = True
    enable_manual_summary: bool = True
    enable_llm_tools: bool = True
    tool_caution_in_prompt: bool = True

    @classmethod
    def from_astrbot_config(cls, config: dict) -> "PluginConfig":
        return cls(
            memory_mode=config.get("memory_mode", "global"),
            fifo_size=config.get("fifo_size", 10),
            summary_mode=config.get("summary_mode", "search_replace"),
            inject_fifo_in_group=config.get("inject_fifo_in_group", True),
            auto_summary_interval_minutes=config.get("auto_summary_interval_minutes", 0),
            max_memory_per_layer=config.get("max_memory_per_layer", 50),
            summary_provider_id=config.get("summary_provider_id", ""),
            summary_system_prompt=config.get("summary_system_prompt", ""),
            inject_memory_in_private=config.get("inject_memory_in_private", True),
            inject_layers_in_group=config.get("inject_layers_in_group", "important_only"),
            enable_auto_summary=config.get("enable_auto_summary", True),
            enable_manual_summary=config.get("enable_manual_summary", True),
            enable_llm_tools=config.get("enable_llm_tools", True),
            tool_caution_in_prompt=config.get("tool_caution_in_prompt", True),
        )
