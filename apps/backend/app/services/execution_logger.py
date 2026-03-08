from ..schemas import ExecutionStepOut, ExecutionSpanOut
from ..store import PostgresStore


class ExecutionLogger:
    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def log_step(self, payload: dict) -> ExecutionStepOut:
        record = self.store.add_step(payload)
        return ExecutionStepOut(**record)

    def list_steps(self, task_id: str) -> list[ExecutionStepOut]:
        return [ExecutionStepOut(**row) for row in self.store.list_steps(task_id)]

    def log_span(self, payload: dict) -> ExecutionSpanOut:
        record = self.store.add_span(payload)
        return ExecutionSpanOut(**record)

    def list_spans(self, task_id: str) -> list[ExecutionSpanOut]:
        return [ExecutionSpanOut(**row) for row in self.store.list_spans(task_id)]
