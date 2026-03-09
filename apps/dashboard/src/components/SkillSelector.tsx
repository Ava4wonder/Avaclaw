import { useEffect, useMemo, useState } from "react";
import Select, { MultiValue } from "react-select";
import { getSkills, SkillSummary } from "../services/skillApi";

type SkillSelectorProps = {
  value: string[];
  onChange: (next: string[]) => void;
};

type Option = { value: string; label: string; description: string };

export default function SkillSelector({ value, onChange }: SkillSelectorProps) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);

  useEffect(() => {
    getSkills().then(setSkills).catch(() => setSkills([]));
  }, []);

  const options = useMemo<Option[]>(
    () =>
      skills.map((skill) => ({
        value: skill.id,
        label: skill.name,
        description: skill.description
      })),
    [skills]
  );

  const selected = options.filter((option) => value.includes(option.value));

  return (
    <Select
      isMulti
      classNamePrefix="skill-select"
      options={options}
      value={selected}
      onChange={(next: MultiValue<Option>) => onChange(next.map((item) => item.value))}
      placeholder="Select skill overlays"
      formatOptionLabel={(option) => (
        <div>
          <div style={{ fontWeight: 600 }}>{option.label}</div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>{option.description}</div>
        </div>
      )}
    />
  );
}
