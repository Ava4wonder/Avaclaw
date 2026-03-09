import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Agent, Task } from "../api/client";
import AgentEditor from "../components/AgentEditor";
import TaskList from "../components/TaskList";

export default function AgentDetailPage() {
  const { id } = useParams();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [queueDepth, setQueueDepth] = useState<number>(0);
  const [taskInput, setTaskInput] = useState("");

  const runningTasks = useMemo(() => tasks.filter((task) => task.status === "running"), [tasks]);

  const loadAll = () => {
    if (!id) return;
    api.getAgent(id).then(setAgent);
    api.listTasks().then(setTasks);
    api.getQueue().then((data) => setQueueDepth(data.depth));
  };

  useEffect(() => {
    loadAll();
  }, [id]);

  if (!agent) {
    return <div className="card">Loading...</div>;
  }

  return (
    <div className="grid">
      <div className="page-header">
        <h1>{agent.name}</h1>
        <button className="button" onClick={loadAll}>
          Refresh
        </button>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Configuration</h2>
          <AgentEditor
            initial={agent}
            submitLabel="Update"
            onSubmit={(payload, runPrompt) =>
              api
                .updateAgent(agent.id, payload)
                .then((updated) =>
                  runPrompt ? api.createTask(updated.id, runPrompt).then(() => updated) : updated
                )
                .then((updated) => {
                  setAgent(updated);
                  loadAll();
                })
            }
          />
        </div>
        <div className="card">
          <h2>Status</h2>
          <div>Enabled: {agent.enabled ? "Yes" : "No"}</div>
          <div>Queue depth: {queueDepth}</div>
          <div>Running tasks: {runningTasks.length}</div>
        </div>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Run Task</h2>
          <form
            className="grid"
            onSubmit={(e) => {
              e.preventDefault();
              if (!taskInput.trim()) return;
              api.createTask(agent.id, taskInput).then(() => {
                setTaskInput("");
                loadAll();
              });
            }}
          >
            <textarea
              className="textarea"
              value={taskInput}
              onChange={(e) => setTaskInput(e.target.value)}
              placeholder="Describe the task to run"
            />
            <button className="button primary" type="submit">
              Enqueue
            </button>
          </form>
        </div>
        <div className="card">
          <h2>Running Tasks</h2>
          <TaskList tasks={runningTasks} />
        </div>
      </div>
    </div>
  );
}
