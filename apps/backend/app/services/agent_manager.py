from typing import Any
from ..schemas import AgentOut
from ..store import PostgresStore


class AgentManager:
    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def list_agents(self) -> list[AgentOut]:
        return [self._map_agent(row) for row in self.store.list_agents()]

    def get_agent(self, agent_id: str) -> AgentOut | None:
        row = self.store.get_agent(agent_id)
        return self._map_agent(row) if row else None

    def create_agent(self, payload: dict[str, Any]) -> AgentOut:
        record = self.store.create_agent(payload)
        return self._map_agent(record)

    def update_agent(self, agent_id: str, payload: dict[str, Any]) -> AgentOut:
        record = self.store.update_agent(agent_id, payload)
        return self._map_agent(record)

    def delete_agent(self, agent_id: str) -> None:
        self.store.delete_agent(agent_id)

    def set_enabled(self, agent_id: str, enabled: bool) -> AgentOut:
        return self.update_agent(agent_id, {"enabled": enabled})

    @staticmethod
    def _map_agent(row: dict[str, Any]) -> AgentOut:
        return AgentOut(
            id=row["id"],
            name=row["name"],
            system_prompt=row["system_prompt"],
            tools=row["tools"],
            model=row["model"],
            enabled=bool(row["enabled"])
        )
