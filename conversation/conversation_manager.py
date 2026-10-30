
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from agents.supervisor_agent import SupervisorAgent
from conversation.session import (
    DEFAULT_MAX_TURNS,
    ConversationSession,
    ConversationTurn,
)
from conversation.storage import JsonFileStorage, SQLiteStorage


# 每次交给 LLM 的历史消息条数
DEFAULT_HISTORY_MESSAGES = 10


class ConversationManager:
    """
    多轮会话管理器。

    负责：
    1. 创建、获取、删除会话
    2. 记录用户和助手消息
    3. 裁剪过长的历史
    4. 按配置选择存储后端

    存储后端：
    - database_path: SQLite（推荐，前端多会话场景）
    - storage_dir: 一个会话一个 JSON 文件
    - 都不传：仅内存，进程退出即丢失
    """

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        database_path: str | Path | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ):
        if database_path is not None:
            self._storage = SQLiteStorage(database_path)

        elif storage_dir is not None:
            self._storage = JsonFileStorage(storage_dir)

        else:
            self._storage = None

        self.max_turns = max_turns
        self._sessions: dict[str, ConversationSession] = {}

    @property
    def storage(self):
        return self._storage

    def create_session(
        self,
        session_id: str | None = None,
    ) -> ConversationSession:
        session_id = session_id or uuid.uuid4().hex[:12]

        if session_id in self._sessions:
            raise ValueError(f"会话已存在：{session_id}")

        session = ConversationSession(
            session_id=session_id,
            max_turns=self.max_turns,
        )

        self._sessions[session_id] = session

        # 先落一条空会话记录，方便前端立刻看到
        self._save_session(session)

        return session

    def get_session(
        self,
        session_id: str,
    ) -> ConversationSession | None:
        session = self._sessions.get(session_id)

        if session is not None:
            return session

        # 内存中没有时尝试从存储恢复
        session = self._load_session(session_id)

        if session is not None:
            self._sessions[session_id] = session

        return session

    def get_or_create_session(
        self,
        session_id: str | None = None,
    ) -> ConversationSession:
        if session_id is None:
            return self.create_session()

        session = self.get_session(session_id)

        if session is not None:
            return session

        return self.create_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        removed = self._sessions.pop(session_id, None) is not None

        if self._storage is not None:
            removed = self._storage.delete_session(session_id) or removed

        return removed

    def list_sessions(self) -> list[str]:
        session_ids = set(self._sessions)

        if self._storage is not None:
            session_ids.update(self._storage.list_sessions())

        return sorted(session_ids)

    def list_session_summaries(self) -> list[dict[str, Any]]:
        """返回会话列表（含标题、时间、消息数），供前端侧边栏使用。"""

        if self._storage is not None and hasattr(
            self._storage,
            "list_session_summaries",
        ):
            return self._storage.list_session_summaries()

        summaries = []

        for session_id in self.list_sessions():
            session = self.get_session(session_id)

            if session is None:
                continue

            title = next(
                (
                    turn.content
                    for turn in session.turns
                    if turn.role == "user"
                ),
                "新会话",
            )

            summaries.append({
                "session_id": session.session_id,
                "title": title[:40],
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "message_count": len(session.turns),
            })

        summaries.sort(
            key=lambda item: item["updated_at"],
            reverse=True,
        )

        return summaries

    def record_user(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        return self._record(session_id, "user", content, metadata)

    def record_assistant(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        return self._record(session_id, "assistant", content, metadata)

    def history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        session = self.get_session(session_id)

        if session is None:
            return []

        return session.history(limit=limit)

    def reset(self, session_id: str):
        """清空某个会话的对话历史。"""

        session = self.get_session(session_id)

        if session is None:
            return

        session.clear()
        self._save_session(session)

    def save(self, session_id: str):
        session = self.get_session(session_id)

        if session is not None:
            self._save_session(session)

    def _record(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None,
    ) -> ConversationTurn:
        session = self.get_or_create_session(session_id)
        turn = session.add_turn(role, content, metadata)

        self._save_session(session)

        return turn

    def _save_session(self, session: ConversationSession):
        if self._storage is None:
            return

        self._storage.save_session(session)

    def _load_session(
        self,
        session_id: str,
    ) -> ConversationSession | None:
        if self._storage is None:
            return None

        try:
            session = self._storage.load_session(session_id)

        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"会话加载失败：{session_id}，原因：{exc}")
            return None

        if session is not None:
            session.max_turns = self.max_turns

        return session


class ConversationRunner:
    """
    把会话管理和旅行助手 Agent 串起来。

    每一轮对话都会：
    1. 读取历史消息
    2. 交给 Supervisor 处理
    3. 记录用户输入和助手回复
    """

    def __init__(
        self,
        agent: SupervisorAgent | None = None,
        manager: ConversationManager | None = None,
        session_id: str | None = None,
        history_limit: int = DEFAULT_HISTORY_MESSAGES,
    ):
        self.agent = agent or SupervisorAgent()

        self.manager = manager or ConversationManager()

        self.session = self.manager.get_or_create_session(session_id)

        self.history_limit = history_limit

    @property
    def session_id(self) -> str:
        return self.session.session_id

    async def chat(self, user_input: str) -> dict[str, Any]:
        """执行一轮对话，返回 Supervisor 的完整结果。"""

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        user_input = user_input.strip()

        history = self.session.history(limit=self.history_limit)

        user_turn = self.manager.record_user(self.session_id, user_input)

        try:
            result = await self.agent.run(
                user_input,
                history=history,
            )

        except Exception:
            # 失败的一轮不留在历史里，避免污染后续上下文
            self._rollback_user_turn(user_turn)
            raise

        answer = result.get("answer") or ""

        if answer.strip():
            self.manager.record_assistant(
                self.session_id,
                answer,
                metadata={
                    "task_type": result.get("task_type"),
                },
            )

        return result

    async def chat_stream(self, user_input: str):
        """
        流式执行一轮对话，边生成边产出事件。

        事件由 SupervisorAgent.run_stream 产生，
        并在收到 done 事件后把最终回答写入会话历史。
        """

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        user_input = user_input.strip()

        history = self.session.history(limit=self.history_limit)

        user_turn = self.manager.record_user(self.session_id, user_input)

        answer_parts: list[str] = []
        task_type = None
        failed = False

        try:
            async for event in self.agent.run_stream(
                user_input,
                history=history,
            ):
                name = event.get("event")
                data = event.get("data") or {}

                if name == "delta":
                    answer_parts.append(data.get("text") or "")

                elif name == "done":
                    task_type = data.get("task_type")

                    # done 里的 answer 才是最终版，覆盖增量拼接结果
                    answer_parts = [data.get("answer") or ""]

                yield event

        except Exception:
            failed = True

            # 失败且没有任何输出时，回滚这一轮的用户消息
            if not "".join(answer_parts).strip():
                self._rollback_user_turn(user_turn)

            raise

        finally:
            # 客户端中途断开（GeneratorExit）时也会走到这里，
            # 能保存多少就先保存多少。
            answer = "".join(answer_parts).strip()

            if answer:
                self.manager.record_assistant(
                    self.session_id,
                    answer,
                    metadata={
                        "task_type": task_type,
                    },
                )

            elif not failed:
                self._rollback_user_turn(user_turn)

    def _rollback_user_turn(self, turn):
        """撤回尚未完成的用户消息，避免污染后续上下文。"""

        turns = self.session.turns

        for index, item in enumerate(turns):
            if item is turn:
                del turns[index]
                break

        self.manager.save(self.session_id)

    def reset(self):
        """清空当前会话历史。"""

        self.manager.reset(self.session_id)

    async def close(self):
        if isinstance(self.agent, SupervisorAgent):
            await self.agent.close()
