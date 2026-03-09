import { useEffect, useState } from "react";
import { Agent } from "../api/client";
import SkillSelector from "./SkillSelector";
import ToolSelector from "./ToolSelector";

type AgentEditorProps = {
  initial?: Partial<Agent>;
  onSubmit: (payload: Omit<Agent, "id">, runPrompt?: string) => Promise<void> | void;
  submitLabel?: string;
};

export default function AgentEditor({ initial, onSubmit, submitLabel = "Save" }: AgentEditorProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt ?? "");
  const [tools, setTools] = useState<string[]>(initial?.tools ?? []);
  const [skills, setSkills] = useState<string[]>(initial?.skills ?? []);
  const [model, setModel] = useState(initial?.model ?? "qwen3-coder");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [runPrompt, setRunPrompt] = useState("");

  useEffect(() => {
    if (!initial) return;
    setName(initial.name ?? "");
    setSystemPrompt(initial.system_prompt ?? "");
    setTools(initial.tools ?? []);
    setSkills(initial.skills ?? []);
    setModel(initial.model ?? "qwen3-coder");
    setEnabled(initial.enabled ?? true);
  }, [initial]);

  return (
    <form
      className="grid"
      onSubmit={(e) => {
        e.preventDefault();
        const payload = {
          name,
          system_prompt: systemPrompt,
          tools,
          skills,
          model,
          enabled
        };
        Promise.resolve(onSubmit(payload, runPrompt.trim() ? runPrompt : undefined)).then(() =>
          setRunPrompt("")
        );
      }}
    >
      <label>
        Name
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Model
        <input className="input" value={model} onChange={(e) => setModel(e.target.value)} required />
      </label>
      <label>
        Tools
        <ToolSelector value={tools} onChange={setTools} />
      </label>
      <label>
        Skill overlays (optional)
        <SkillSelector value={skills} onChange={setSkills} />
      </label>
      <label>
        System prompt
        <textarea
          className="textarea"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          required
        />
      </label>
      <label>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled
      </label>
      <label>
        Start prompt (auto-enqueue)
        <textarea
          className="textarea"
          value={runPrompt}
          onChange={(e) => setRunPrompt(e.target.value)}
          placeholder="Run a first prompt immediately after save"
        />
      </label>
      <div>
        <button className="button primary" type="submit">
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
