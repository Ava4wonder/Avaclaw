import { Task } from "../api/client";

type TaskListProps = {
  tasks: Task[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
};

export default function TaskList({ tasks, selectedId, onSelect }: TaskListProps) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Task</th>
          <th>Status</th>
          <th>Agent</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((task) => (
          <tr
            key={task.id}
            style={{ cursor: onSelect ? "pointer" : "default" }}
            onClick={() => onSelect?.(task.id)}
          >
            <td className={selectedId === task.id ? "badge" : undefined}>{task.id.slice(0, 8)}</td>
            <td>{task.status}</td>
            <td>{task.agent_id.slice(0, 8)}</td>
            <td>{new Date(task.created_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
