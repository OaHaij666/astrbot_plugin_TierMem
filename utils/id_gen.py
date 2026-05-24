import uuid
from datetime import datetime, timezone


def generate_memory_id() -> str:
    return f"mem-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"


def generate_turn_id() -> str:
    return f"turn-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"
