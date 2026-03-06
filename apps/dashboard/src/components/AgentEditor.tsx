import { useEffect, useState } from "react";
import { Agent } from "../api/client";
import SkillSelector from "./SkillSelector";

type AgentEditorProps = {
  initial?: Partial<Agent>;
  onSubmit: (payload: Omit<Agent, "id">) => void;
  submitLabel?: string;
};

export default function AgentEditor({ initial, onSubmit, submitLabel = "Save" }: AgentEditorProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt ?? "");
  const [skills, setSkills] = useState<string[]>(initial?.tools ?? []);
  const [model, setModel] = useState(initial?.model ?? "qwen3-coder");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  useEffect(() => {
    if (!initial) return;
    setName(initial.name ?? "");
    setSystemPrompt(initial.system_prompt ?? "");
    setSkills(initial.tools ?? []);
    setModel(initial.model ?? "qwen3-coder");
    setEnabled(initial.enabled ?? true);
  }, [initial]);

  return (
    <form
      className="grid"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          name,
          system_prompt: systemPrompt,
          tools: skills,
          model,
          enabled
        });
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
        Skills
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
      <div>
        <button className="button primary" type="submit">
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
