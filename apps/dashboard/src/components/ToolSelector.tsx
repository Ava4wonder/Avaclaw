import { useEffect, useMemo, useState } from "react";
import Select, { MultiValue } from "react-select";
import { getTools, ToolSummary } from "../services/toolApi";

type ToolSelectorProps = {
  value: string[];
  onChange: (next: string[]) => void;
};

type Option = { value: string; label: string; description: string };

export default function ToolSelector({ value, onChange }: ToolSelectorProps) {
  const [tools, setTools] = useState<ToolSummary[]>([]);

  useEffect(() => {
    getTools().then(setTools).catch(() => setTools([]));
  }, []);

  const options = useMemo<Option[]>(
    () =>
      tools.map((tool) => ({
        value: tool.id,
        label: tool.name,
        description: tool.description
      })),
    [tools]
  );

  const selected = options.filter((option) => value.includes(option.value));

  return (
    <Select
      isMulti
      classNamePrefix="tool-select"
      options={options}
      value={selected}
      onChange={(next: MultiValue<Option>) => onChange(next.map((item) => item.value))}
      placeholder="Select tools"
      formatOptionLabel={(option) => (
        <div>
          <div style={{ fontWeight: 600 }}>{option.label}</div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>{option.description}</div>
        </div>
      )}
    />
  );
}
