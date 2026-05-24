"""
测试提示词组装和总结逻辑 - 独立版本
不依赖 astrbot 框架，只测试核心逻辑
"""
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

# 直接复制核心模型定义，避免导入依赖
@dataclass
class MemoryEntry:
    memory_id: str
    content: str
    layer: Literal["important", "general", "fleeting"]
    category: str = "fact"
    importance: int = 3
    subject_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    expires_at: Optional[str] = None
    source: str = "auto_summary"
    confidence: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "layer": self.layer,
            "category": self.category,
            "importance": self.importance,
            "subject_id": self.subject_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at or "",
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class MemoryState:
    important: List[MemoryEntry] = field(default_factory=list)
    general: List[MemoryEntry] = field(default_factory=list)
    fleeting: List[MemoryEntry] = field(default_factory=list)
    version: int = 1
    last_summary_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "important": [e.to_dict() for e in self.important],
            "general": [e.to_dict() for e in self.general],
            "fleeting": [e.to_dict() for e in self.fleeting],
            "version": self.version,
            "last_summary_at": self.last_summary_at or "",
        }


@dataclass
class ConversationTurn:
    turn_id: str
    user_message: str
    assistant_message: str
    timestamp: str = ""
    group_id: Optional[str] = None

    def to_prompt_text(self) -> str:
        return (
            f"[User]: {self.user_message}\n"
            f"[Assistant]: {self.assistant_message}\n"
        )


def build_default_prompt(conversation_text: str, memory_snapshot: str) -> str:
    """复制 summarizer.py 中的默认提示词逻辑"""
    # 使用 $ 占位符避免与 JSON 花括号冲突
    template = (
        "你就是这个对话中的 AI 助手（bot）。请站在你自己的视角，根据 [近期对话] 和 [你对当前用户的现有记忆]，"
        "更新你对这个用户的记忆。\n\n"
        "视角要求：\n"
        "- 使用第一人称视角，例如『用户喜欢...』『用户告诉我...』\n"
        "- 你是记忆的拥有者，这些记忆帮助你更好地与用户互动\n"
        "- 不要以第三者旁观者的口吻描述\n\n"
        "更新模式（自行选择）：\n"
        "- search_replace：精准修改。适用于大部分情况，对现有记忆进行增删改查。\n"
        "- full_replace：全量覆盖。适用于现有记忆已严重过时、需要完全重建时。\n\n"
        "各层写入标准：\n"
        "- important：仅存放核心事实。如用户身份、关键偏好、重要约定、长期目标。"
        "必须有明确证据且对用户画像/互动方式有长期影响。\n"
        "- general：存放普通事实和常规互动。如日常爱好、一般性陈述、普通事件。\n"
        "- fleeting：只允许 add，不允许 update/delete/keep。"
        "尽可能详细记录近期对话中有用的信息（如临时任务、当前话题、短期状态、用户刚提到的细节）。"
        "fleeting 记忆会在后续总结轮次中自动淘汰，因此只关注最新内容。\n\n"
        "跨用户记忆：\n"
        "- 如果对话中提及其他用户的信息，且你认为需要记录到该用户的记忆中，"
        "请使用 memory_read_user 工具先读取该用户的记忆，再决定如何更新\n"
        "- 注意：对记忆的修改是互斥的，同一时间只能有一个总结任务在修改某个用户的记忆\n\n"
        "规则：\n"
        "1. 只能返回 JSON，不要有任何额外解释\n"
        "2. search_replace 模式操作类型：add / update / delete / keep\n"
        "3. full_replace 模式需提供完整的 full_state 三层结构\n"
        "4. update 和 delete 必须引用准确的 memory_id\n"
        "5. 不要 hallucinate，没有明确证据不要添加记忆\n"
        "6. 如果某条现有记忆仍然准确且相关，使用 keep\n"
        "7. fleeting 层只允许 add 操作\n\n"
        "[近期对话]\n$conversation_text\n\n"
        "[现有记忆]\n$memory_snapshot\n\n"
        "输出格式（search_replace 模式）：\n"
        "{\n"
        '  "mode": "search_replace",\n'
        '  "summary": "总结说明",\n'
        '  "operations": [\n'
        '    {"action": "add", "layer": "general", "content": "...", "category": "fact", "importance": 3},\n'
        '    {"action": "update", "memory_id": "mem-xxx", "content": "..."},\n'
        '    {"action": "delete", "memory_id": "mem-xxx"},\n'
        '    {"action": "keep", "memory_id": "mem-xxx"}\n'
        "  ]\n"
        "}\n\n"
        "输出格式（full_replace 模式）：\n"
        "{\n"
        '  "mode": "full_replace",\n'
        '  "summary": "总结说明",\n'
        '  "full_state": {\n'
        '    "important": [{"content": "...", "category": "...", "importance": 5}],\n'
        '    "general": [{"content": "...", "category": "...", "importance": 3}],\n'
        '    "fleeting": [{"content": "...", "category": "...", "importance": 2}]\n'
        "  }\n"
        "}"
    )
    # 手动替换占位符
    template = template.replace("$conversation_text", conversation_text)
    template = template.replace("$memory_snapshot", memory_snapshot)
    return template


def test_prompt_assembly():
    """测试提示词组装是否正确"""
    print("=== 测试 1: 提示词组装 ===")

    # 模拟 FIFO 数据
    turns = [
        ConversationTurn(
            turn_id="t1",
            user_message="宝宝",
            assistant_message="诶…宝宝？这个称呼…菲说它有点不知所措，毛都炸起来了。",
            timestamp="2026-05-24T17:32:36",
        ),
        ConversationTurn(
            turn_id="t2",
            user_message="其实我是彭于晏，你认得吗",
            assistant_message="唔…彭于晏先生我当然知道，菲也知道的。它说它看过《激战》，虽然它只是一只小熊。",
            timestamp="2026-05-24T17:32:57",
        ),
    ]

    # 模拟空记忆
    state = MemoryState()

    # 构建提示词
    conversation_text = "\n".join(t.to_prompt_text() for t in turns)
    memory_snapshot = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
    prompt = build_default_prompt(conversation_text, memory_snapshot)

    print("\n--- 生成的提示词 ---")
    print(prompt)
    print("--- 提示词结束 ---\n")

    # 验证 FIFO 内容是否正确嵌入
    assert "宝宝" in prompt, "提示词应该包含用户消息'宝宝'"
    assert "彭于晏" in prompt, "提示词应该包含用户消息'彭于晏'"
    assert "菲说它有点不知所措" in prompt, "提示词应该包含助手回复"
    assert "[近期对话]" in prompt, "提示词应该包含[近期对话]标记"
    assert "[现有记忆]" in prompt, "提示词应该包含[现有记忆]标记"

    print("✅ 提示词组装测试通过")


def test_prompt_with_existing_memory():
    """测试已有记忆时的提示词组装"""
    print("\n=== 测试 2: 已有记忆时的提示词 ===")

    turns = [
        ConversationTurn(
            turn_id="t1",
            user_message="我喜欢吃火锅",
            assistant_message="好的，我记住了你喜欢吃火锅。",
            timestamp="2026-05-24T17:32:36",
        ),
    ]

    state = MemoryState(
        important=[
            MemoryEntry(
                memory_id="mem-1",
                content="用户是程序员",
                layer="important",
                category="profile",
                importance=5,
            )
        ],
        fleeting=[
            MemoryEntry(
                memory_id="mem-2",
                content="用户昨天提到想看电影",
                layer="fleeting",
                category="fact",
                importance=2,
            )
        ],
    )

    conversation_text = "\n".join(t.to_prompt_text() for t in turns)
    memory_snapshot = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
    prompt = build_default_prompt(conversation_text, memory_snapshot)

    print("\n--- 生成的提示词 ---")
    print(prompt)
    print("--- 提示词结束 ---\n")

    # 验证记忆是否正确嵌入
    assert "用户是程序员" in prompt, "提示词应该包含 important 记忆"
    assert "用户昨天提到想看电影" in prompt, "提示词应该包含 fleeting 记忆"
    assert "我喜欢吃火锅" in prompt, "提示词应该包含当前对话"

    print("✅ 已有记忆提示词测试通过")


def test_memory_state_to_dict():
    """测试 MemoryState.to_dict() 输出"""
    print("\n=== 测试 3: MemoryState.to_dict() ===")

    state = MemoryState(
        important=[
            MemoryEntry(
                memory_id="mem-1",
                content="用户是程序员",
                layer="important",
                category="profile",
                importance=5,
            )
        ],
        general=[
            MemoryEntry(
                memory_id="mem-2",
                content="用户喜欢吃火锅",
                layer="general",
                category="preference",
                importance=3,
            )
        ],
        fleeting=[],
    )

    d = state.to_dict()
    print("\n--- MemoryState JSON ---")
    print(json.dumps(d, ensure_ascii=False, indent=2))
    print("--- JSON 结束 ---\n")

    assert "important" in d
    assert "general" in d
    assert "fleeting" in d
    assert len(d["important"]) == 1
    assert len(d["general"]) == 1
    assert len(d["fleeting"]) == 0

    print("✅ MemoryState.to_dict() 测试通过")


def test_conversation_turn_to_prompt_text():
    """测试 ConversationTurn.to_prompt_text() 输出"""
    print("\n=== 测试 4: ConversationTurn.to_prompt_text() ===")

    turn = ConversationTurn(
        turn_id="t1",
        user_message="宝宝",
        assistant_message="诶…宝宝？这个称呼…",
        timestamp="2026-05-24T17:32:36",
    )

    text = turn.to_prompt_text()
    print(f"\n--- 对话文本 ---\n{text}\n--- 结束 ---\n")

    assert "[User]: 宝宝" in text
    assert "[Assistant]: 诶…宝宝？这个称呼…" in text

    print("✅ ConversationTurn.to_prompt_text() 测试通过")


def test_llm_output_parsing():
    """测试 LLM 输出解析"""
    print("\n=== 测试 5: LLM 输出解析 ===")

    # 模拟 LLM 返回的 search_replace 结果
    llm_output = {
        "mode": "search_replace",
        "summary": "用户自称彭于晏，记录此幽默互动",
        "operations": [
            {
                "action": "add",
                "layer": "general",
                "content": "用户曾开玩笑说自己是彭于晏",
                "category": "event",
                "importance": 2,
            },
            {
                "action": "add",
                "layer": "fleeting",
                "content": "用户称呼bot为'宝宝'",
                "category": "fact",
                "importance": 2,
            },
        ],
    }

    # 验证 JSON 可解析
    parsed = json.loads(json.dumps(llm_output, ensure_ascii=False))
    assert parsed["mode"] == "search_replace"
    assert len(parsed["operations"]) == 2
    assert parsed["operations"][0]["action"] == "add"
    assert parsed["operations"][0]["layer"] == "general"

    print("✅ LLM 输出解析测试通过")


def test_injection_prompt():
    """测试注入到 LLM 请求的记忆提示词格式"""
    print("\n=== 测试 6: 注入提示词格式 ===")

    state = MemoryState(
        important=[
            MemoryEntry(
                memory_id="mem-1",
                content="用户是程序员",
                layer="important",
                category="profile",
                importance=5,
            )
        ],
        general=[
            MemoryEntry(
                memory_id="mem-2",
                content="用户喜欢吃火锅",
                layer="general",
                category="preference",
                importance=3,
            )
        ],
        fleeting=[
            MemoryEntry(
                memory_id="mem-3",
                content="用户正在看视频",
                layer="fleeting",
                category="fact",
                importance=2,
            )
        ],
    )

    # 模拟 injector 的逻辑
    lines = []
    if state.important:
        lines.append("=== 重要记忆 ===")
        for e in state.important:
            lines.append(f"- {e.content}")
    if state.general:
        lines.append("=== 一般记忆 ===")
        for e in state.general:
            lines.append(f"- {e.content}")
    if state.fleeting:
        lines.append("=== 短暂记忆 ===")
        for e in state.fleeting:
            lines.append(f"- {e.content}")

    prompt = "\n".join(lines)
    print(f"\n--- 注入提示词 ---\n{prompt}\n--- 结束 ---\n")

    assert "=== 重要记忆 ===" in prompt
    assert "用户是程序员" in prompt
    assert "=== 一般记忆 ===" in prompt
    assert "用户喜欢吃火锅" in prompt
    assert "=== 短暂记忆 ===" in prompt
    assert "用户正在看视频" in prompt

    print("✅ 注入提示词格式测试通过")


def main():
    print("开始测试提示词组装和总结逻辑...\n")
    test_prompt_assembly()
    test_prompt_with_existing_memory()
    test_memory_state_to_dict()
    test_conversation_turn_to_prompt_text()
    test_llm_output_parsing()
    test_injection_prompt()
    print("\n✅ 所有测试通过！")


if __name__ == "__main__":
    main()
