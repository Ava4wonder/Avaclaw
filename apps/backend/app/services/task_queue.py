from collections import deque


class TaskQueue:
    def __init__(self) -> None:
        self._queue: deque[str] = deque()
        self._running: set[str] = set()

    def enqueue(self, task_id: str) -> None:
        self._queue.append(task_id)

    def dequeue(self) -> str | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def depth(self) -> int:
        return len(self._queue)

    def mark_running(self, task_id: str) -> None:
        self._running.add(task_id)

    def mark_complete(self, task_id: str) -> None:
        self._running.discard(task_id)

    def running_tasks(self) -> list[str]:
        return list(self._running)
