import { useEffect, useState } from "react";
import { api, Agent } from "../api/client";
import AgentList from "../components/AgentList";
import AgentEditor from "../components/AgentEditor";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = () =>
    api
      .listAgents()
      .then(setAgents)
      .catch((err) => setError(err.message));

  useEffect(() => {
    loadAgents();
  }, []);

  return (
    <div className="grid">
      <div className="page-header">
        <h1>Agents</h1>
        <button className="button" onClick={loadAgents}>
          Refresh
        </button>
      </div>
      {error && <div className="card">{error}</div>}
      <div className="grid two">
        <div className="card">
          <h2>Create Agent</h2>
          <AgentEditor
            onSubmit={(payload) =>
              api
                .createAgent(payload)
                .then(() => loadAgents())
                .catch((err) => setError(err.message))
            }
            submitLabel="Create"
          />
        </div>
        <div className="card">
          <h2>Agent List</h2>
          <AgentList
            agents={agents}
            onDelete={(id) => api.deleteAgent(id).then(loadAgents)}
            onToggle={(id, enabled) => api.setAgentEnabled(id, enabled).then(loadAgents)}
          />
        </div>
      </div>
    </div>
  );
}
