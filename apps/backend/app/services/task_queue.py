import redis


class TaskQueue:
    def __init__(
        self,
        redis_url: str,
        queue_key: str = "avaclaw:queue",
        running_key: str = "avaclaw:running"
    ) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._queue_key = queue_key
        self._running_key = running_key

    def enqueue(self, task_id: str) -> None:
        self._redis.lpush(self._queue_key, task_id)

    def dequeue(self) -> str | None:
        return self._redis.rpop(self._queue_key)

    def depth(self) -> int:
        return int(self._redis.llen(self._queue_key))

    def mark_running(self, task_id: str) -> None:
        self._redis.sadd(self._running_key, task_id)

    def mark_complete(self, task_id: str) -> None:
        self._redis.srem(self._running_key, task_id)

    def running_tasks(self) -> list[str]:
        return list(self._redis.smembers(self._running_key))

    def close(self) -> None:
        self._redis.close()
