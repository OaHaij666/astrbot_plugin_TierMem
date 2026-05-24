from typing import List, Optional
from core.models import MemoryState, MemoryEntry, ConversationTurn
from core.config import PluginConfig


class Injector:
    def __init__(self, config: PluginConfig):
        self.config = config

    def build_memory_prompt(
        self,
        state: MemoryState,
        subject_id: str,
        scene: str,  # "private" or "group"
        fifo_turns: Optional[List[ConversationTurn]] = None,
    ) -> str:
        parts = []
        parts.append("\n\n====================")
        parts.append("### [MEMORY SYSTEM] ###")
        parts.append(f"- Current subject_id: {subject_id}")
        parts.append(f"- Scene: {scene}")
        parts.append("")

        # 注入记忆层
        if scene == "private" and self.config.inject_memory_in_private:
            parts.append(self._format_layer("important", state.important))
            parts.append(self._format_layer("general", state.general))
            parts.append(self._format_layer("fleeting", state.fleeting))
        elif scene == "group":
            layers = self.config.inject_layers_in_group
            parts.append(self._format_layer("important", state.important))
            if layers in ("important_general", "all"):
                parts.append(self._format_layer("general", state.general))
            if layers == "all":
                parts.append(self._format_layer("fleeting", state.fleeting))

            # 群聊注入 FIFO
            if self.config.inject_fifo_in_group and fifo_turns:
                parts.append("### [RECENT CONVERSATION WITH YOU] ###")
                for turn in fifo_turns:
                    parts.append(turn.to_prompt_text())
                parts.append("")

        parts.append("### [MEMORY RULES] ###")
        parts.append("1. 只能将标记为当前 subject_id 的记忆应用到当前用户")
        parts.append("2. important 层是核心画像，general 是普通事实，fleeting 是临时内容")
        parts.append("3. 不要张冠李戴，未标记的记忆不要强行关联")
        parts.append("====================\n")

        return "\n".join(parts)

    def _format_layer(self, name: str, entries: List[MemoryEntry]) -> str:
        if not entries:
            return f"<{name}>\n(No entries)\n</{name}>\n"
        lines = [f"<{name}>"]
        for e in entries:
            lines.append(f"  - [{e.memory_id}] {e.content} (importance: {e.importance})")
        lines.append(f"</{name}>\n")
        return "\n".join(lines)
