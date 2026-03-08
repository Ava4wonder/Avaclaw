export type Agent = {
  id: string;
  name: string;
  system_prompt: string;
  tools: string[];
  model: string;
  enabled: boolean;
};

export type TaskStatus = "queued" | "running" | "completed" | "failed";

export type Task = {
  id: string;
  agent_id: string;
  input: string;
  status: TaskStatus;
  result: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type ExecutionStep = {
  id: string;
  task_id: string;
  step_index: number;
  type: "llm" | "tool";
  input: string;
  output: string;
  tokens_used: number;
  timestamp: string;
};

export type ExecutionSpan = {
  id: string;
  task_id: string;
  trace_id: string;
  parent_span_id: string | null;
  name: string;
  span_type: "task" | "llm" | "tool";
  start_time: string;
  end_time: string;
  duration_ms: number;
  status: "ok" | "error";
  error?: string | null;
  model?: string | null;
  tokens_total?: number | null;
  tool_args?: unknown;
  tool_result?: unknown;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3003";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listAgents: () => request<Agent[]>("/api/agents"),
  getAgent: (id: string) => request<Agent>(`/api/agents/${id}`),
  createAgent: (payload: Omit<Agent, "id">) =>
    request<Agent>("/api/agents", { method: "POST", body: JSON.stringify(payload) }),
  updateAgent: (id: string, payload: Partial<Omit<Agent, "id">>) =>
    request<Agent>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteAgent: (id: string) => request<void>(`/api/agents/${id}`, { method: "DELETE" }),
  setAgentEnabled: (id: string, enabled: boolean) =>
    request<Agent>(`/api/agents/${id}/enable`, {
      method: "POST",
      body: JSON.stringify({ enabled })
    }),
  listTasks: () => request<Task[]>("/api/tasks"),
  createTask: (agentId: string, input: string) =>
    request<Task>("/api/tasks", { method: "POST", body: JSON.stringify({ agent_id: agentId, input }) }),
  getTaskSteps: (taskId: string) => request<ExecutionStep[]>(`/api/tasks/${taskId}/steps`),
  getTaskTrace: (taskId: string) => request<ExecutionSpan[]>(`/api/tasks/${taskId}/trace`),
  getQueue: () => request<{ depth: number; running: string[] }>("/api/queue")
};
