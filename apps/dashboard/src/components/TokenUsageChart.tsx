import { ExecutionStep } from "../api/client";

type TokenUsageChartProps = {
  steps: ExecutionStep[];
};

export default function TokenUsageChart({ steps }: TokenUsageChartProps) {
  const max = Math.max(1, ...steps.map((step) => step.tokens_used));
  return (
    <div className="card">
      <div className="page-header">
        <strong>Token Usage</strong>
      </div>
      <div className="grid">
        {steps.map((step) => (
          <div key={step.id}>
            <div>Step {step.step_index}</div>
            <div className="token-bar">
              <span style={{ width: `${(step.tokens_used / max) * 100}%` }}></span>
            </div>
            <div>{step.tokens_used} tokens</div>
          </div>
        ))}
      </div>
    </div>
  );
}
