import aiosqlite
from pathlib import Path
from datetime import datetime, timezone
from astrbot.api import logger
from core.exceptions import MigrationError
from .database import SQLiteDB
from .memory_repo import MemoryRepository
from .fifo_repo import FifoRepository


class ModeMigration:
    def __init__(self, db: SQLiteDB):
        self.db = db

    async def check_and_run(self, current_mode: str) -> None:
        """检查并执行模式迁移"""
        stored_mode = await self._get_stored_mode()
        if stored_mode == current_mode:
            return

        if stored_mode is None:
            # 首次运行，记录当前模式
            await self._set_mode(current_mode)
            return

        logger.info(f"检测到模式切换: {stored_mode} -> {current_mode}，准备迁移")

        backup_dir = self.db.db_path.parent / "migration"
        backup_path = backup_dir / f"memory_pre_migration_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db"
        await self.db.vacuum_backup(backup_path)
        logger.info(f"迁移前备份已创建: {backup_path}")

        try:
            if stored_mode == "global" and current_mode == "shared":
                await self._global_to_shared()
            elif stored_mode == "shared" and current_mode == "global":
                await self._shared_to_global()
            await self._set_mode(current_mode)
            logger.info("模式迁移完成")
        except Exception as e:
            logger.error(f"模式迁移失败: {e}")
            raise MigrationError(f"模式迁移失败: {e}")

    async def _get_stored_mode(self) -> str:
        async with self.db.conn.execute(
            "SELECT value FROM meta WHERE key = 'memory_mode'"
        ) as cursor:
            row = await cursor.fetchone()
        return row["value"] if row else None

    async def _set_mode(self, mode: str) -> None:
        await self.db.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('memory_mode', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (mode,),
        )
        await self.db.conn.commit()

    async def _global_to_shared(self) -> None:
        """global -> shared: 合并同一用户在所有群/私聊中的记忆"""
        mem_repo = MemoryRepository(self.db.conn)
        fifo_repo = FifoRepository(self.db.conn)

        # 获取所有 subject_id
        subjects = await mem_repo.list_all_subjects()
        user_map: dict = {}

        for subject_id in subjects:
            user_id = subject_id.split("#")[0]
            if user_id not in user_map:
                user_map[user_id] = []
            user_map[user_id].append(subject_id)

        for user_id, subject_ids in user_map.items():
            shared_subject = f"{user_id}#shared"
            all_entries = []
            for sid in subject_ids:
                entries = await mem_repo.get_by_subject(sid)
                all_entries.extend(entries)

            # 按 content 去重，保留 importance 更高的
            seen = {}
            for e in all_entries:
                key = e.content.strip()
                if key not in seen or e.importance > seen[key].importance:
                    seen[key] = e

            for entry in seen.values():
                entry.subject_id = shared_subject
                entry.memory_id = f"mem-migrated-{entry.memory_id}"
                await mem_repo.upsert(entry)

            # FIFO: 取最近的一个
            latest_turns = []
            for sid in subject_ids:
                turns = await fifo_repo.get_turns(sid, 1)
                if turns:
                    latest_turns.append(turns[0])
            if latest_turns:
                latest_turns.sort(key=lambda t: t.timestamp, reverse=True)
                turn = latest_turns[0]
                turn.turn_id = f"turn-migrated-{turn.turn_id}"
                await fifo_repo.append_turn(shared_subject, turn)

            # 清理旧数据
            for sid in subject_ids:
                await mem_repo.delete_by_subject(sid)
                await fifo_repo.clear(sid)

            logger.info(f"用户 {user_id} 已合并到 shared 模式")

    async def _shared_to_global(self) -> None:
        """shared -> global: 将 shared 记忆复制到该用户所有历史上下文"""
        mem_repo = MemoryRepository(self.db.conn)
        fifo_repo = FifoRepository(self.db.conn)

        # 获取所有 shared subject_id
        async with self.db.conn.execute(
            "SELECT DISTINCT subject_id FROM memories WHERE subject_id LIKE '%#shared'"
        ) as cursor:
            rows = await cursor.fetchall()
        shared_subjects = [row["subject_id"] for row in rows]

        for shared_subject in shared_subjects:
            user_id = shared_subject.split("#")[0]

            # 查找该用户所有历史上下文（从 memories 和 fifo_buffer 中）
            async with self.db.conn.execute(
                "SELECT DISTINCT subject_id FROM memories WHERE subject_id LIKE ?",
                (f"{user_id}#%",),
            ) as cursor:
                rows = await cursor.fetchall()
            all_subjects = {row["subject_id"] for row in rows}

            async with self.db.conn.execute(
                "SELECT DISTINCT subject_id FROM fifo_buffer WHERE subject_id LIKE ?",
                (f"{user_id}#%",),
            ) as cursor:
                rows = await cursor.fetchall()
            all_subjects.update(row["subject_id"] for row in rows)

            # 排除 shared 本身
            all_subjects.discard(shared_subject)

            entries = await mem_repo.get_by_subject(shared_subject)
            turns = await fifo_repo.get_turns(shared_subject, 9999)

            for target_subject in all_subjects:
                for entry in entries:
                    entry.subject_id = target_subject
                    entry.memory_id = f"mem-copied-{entry.memory_id}"
                    await mem_repo.upsert(entry)
                for turn in turns:
                    turn.turn_id = f"turn-copied-{turn.turn_id}"
                    await fifo_repo.append_turn(target_subject, turn)

            # 清理 shared 数据
            await mem_repo.delete_by_subject(shared_subject)
            await fifo_repo.clear(shared_subject)

            logger.info(f"用户 {user_id} 已从 shared 复制到 global 模式")
