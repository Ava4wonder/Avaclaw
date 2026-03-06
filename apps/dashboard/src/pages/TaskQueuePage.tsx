import { useEffect, useState } from "react";
import { api, Task } from "../api/client";
import TaskList from "../components/TaskList";

export default function TaskQueuePage() {
  const [queueDepth, setQueueDepth] = useState(0);
  const [running, setRunning] = useState<string[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const loadAll = () => {
    api.getQueue().then((data) => {
      setQueueDepth(data.depth);
      setRunning(data.running);
    });
    api.listTasks().then(setTasks);
  };

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <div className="grid">
      <div className="page-header">
        <h1>Task Queue</h1>
        <button className="button" onClick={loadAll}>
          Refresh
        </button>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Queue Status</h2>
          <div>Queue depth: {queueDepth}</div>
          <div>Running tasks: {running.length}</div>
        </div>
        <div className="card">
          <h2>Running Task IDs</h2>
          <div className="mono">{running.join("\n") || "None"}</div>
        </div>
      </div>
      <div className="card">
        <h2>All Tasks</h2>
        <TaskList tasks={tasks} />
      </div>
    </div>
  );
}
