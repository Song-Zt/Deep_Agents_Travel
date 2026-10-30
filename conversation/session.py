
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# 单个会话最多保留多少条消息（user + assistant）
DEFAULT_MAX_TURNS = 40

# 会话 ID 只允许字母、数字、下划线和短横线，避免被拼进非法文件路径
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.match(
        session_id
    ):
        raise ValueError(f"非法的会话 ID：{session_id}")

    return session_id


@dataclass
class ConversationTurn:
    """会话中的一条消息。"""

    role: str
    content: str
    created_at: str = field(default_factory=now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.role not in ("user", "assistant"):
            raise ValueError(f"不支持的消息角色：{self.role}")

        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("消息内容不能为空")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTurn":
        if not isinstance(data, dict):
            raise ValueError("会话消息格式不正确")

        return cls(
            role=data.get("role"),
            content=data.get("content"),
            created_at=data.get("created_at") or now(),
            metadata=data.get("metadata") or {},
        )


class ConversationSession:
    """一次多轮会话。"""

    def __init__(
        self,
        session_id: str,
        max_turns: int = DEFAULT_MAX_TURNS,
    ):
        validate_session_id(session_id)

        if max_turns <= 0:
            raise ValueError("max_turns 必须大于 0")

        self.session_id = session_id
        self.max_turns = max_turns

        self.created_at = now()
        self.updated_at = self.created_at
        self.metadata: dict[str, Any] = {}

        self.turns: list[ConversationTurn] = []

    def add_user(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        return self.add_turn("user", content, metadata)

    def add_assistant(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        return self.add_turn("assistant", content, metadata)

    def add_turn(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata or {},
        )

        self.turns.append(turn)

        # 超出上限时丢弃最早的消息，保留最近上下文
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

        self.updated_at = now()

        return turn

    def history(
        self,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """返回可直接交给 LLM 的历史消息。"""

        turns = self.turns

        if limit is not None:
            if limit <= 0:
                return []
            turns = turns[-limit:]

        return [
            {
                "role": turn.role,
                "content": turn.content,
            }
            for turn in turns
        ]

    def clear(self):
        """清空对话，但保留会话本身。"""

        self.turns = []
        self.updated_at = now()

    def is_empty(self) -> bool:
        return not self.turns

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "max_turns": self.max_turns,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationSession":
        if not isinstance(data, dict):
            raise ValueError("会话数据格式不正确")

        session = cls(
            session_id=data.get("session_id"),
            max_turns=data.get("max_turns") or DEFAULT_MAX_TURNS,
        )

        session.created_at = data.get("created_at") or session.created_at
        session.updated_at = data.get("updated_at") or session.updated_at
        session.metadata = data.get("metadata") or {}
        session.turns = [
            ConversationTurn.from_dict(item)
            for item in data.get("turns") or []
        ]

        return session
