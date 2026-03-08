export type SkillSummary = {
  id: string;
  name: string;
  description: string;
  origin?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3003";

export async function getSkills(): Promise<SkillSummary[]> {
  const res = await fetch(`${API_BASE}/api/skills`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}
