import { useEffect, useState } from "react";
import { api, ExecutionSpan, ExecutionStep, Task } from "../api/client";
import TaskList from "../components/TaskList";
import ExecutionTraceViewer from "../components/ExecutionTraceViewer";
import TokenUsageChart from "../components/TokenUsageChart";

export default function ExecutionLogsPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [spans, setSpans] = useState<ExecutionSpan[]>([]);

  const loadTasks = () => api.listTasks().then(setTasks);

  useEffect(() => {
    loadTasks();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    api.getTaskSteps(selectedId).then(setSteps);
    api.getTaskTrace(selectedId).then(setSpans);
  }, [selectedId]);

  return (
    <div className="grid">
      <div className="page-header">
        <h1>Execution Viewer</h1>
        <button className="button" onClick={loadTasks}>
          Refresh
        </button>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Tasks</h2>
          <TaskList tasks={tasks} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
        <TokenUsageChart steps={steps} />
      </div>
      <div className="card">
        <h2>Execution Trace</h2>
        {selectedId ? <ExecutionTraceViewer spans={spans} /> : <div>Select a task.</div>}
      </div>
    </div>
  );
}
