from ..schemas import ExecutionStepOut
from ..store import InMemoryStore


class ExecutionLogger:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def log_step(self, payload: dict) -> ExecutionStepOut:
        record = self.store.add_step(payload)
        return ExecutionStepOut(**record)

    def list_steps(self, task_id: str) -> list[ExecutionStepOut]:
        return [ExecutionStepOut(**row) for row in self.store.list_steps(task_id)]
