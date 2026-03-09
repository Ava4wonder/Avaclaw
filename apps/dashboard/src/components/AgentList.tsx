import { Link } from "react-router-dom";
import { Agent } from "../api/client";

type AgentListProps = {
  agents: Agent[];
  onDelete: (id: string) => void;
  onToggle: (id: string, enabled: boolean) => void;
};

export default function AgentList({ agents, onDelete, onToggle }: AgentListProps) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Model</th>
          <th>Tools</th>
          <th>Skill overlays</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {agents.map((agent) => (
          <tr key={agent.id}>
            <td>
              <Link to={`/agents/${agent.id}`}>{agent.name}</Link>
            </td>
            <td>{agent.model}</td>
            <td>{agent.tools.join(", ") || "-"}</td>
            <td>{agent.skills.join(", ") || "-"}</td>
            <td>
              <span className="badge">{agent.enabled ? "Enabled" : "Disabled"}</span>
            </td>
            <td>
              <button className="button ghost" onClick={() => onToggle(agent.id, !agent.enabled)}>
                {agent.enabled ? "Disable" : "Enable"}
              </button>
              <button className="button" onClick={() => onDelete(agent.id)} style={{ marginLeft: 8 }}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
