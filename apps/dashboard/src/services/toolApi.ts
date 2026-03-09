export type ToolSummary = {
  id: string;
  name: string;
  description: string;
  origin?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3003";

export async function getTools(): Promise<ToolSummary[]> {
  const res = await fetch(`${API_BASE}/api/tools`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}
