import { ExecutionStep } from "../api/client";

type ExecutionTraceViewerProps = {
  steps: ExecutionStep[];
};

export default function ExecutionTraceViewer({ steps }: ExecutionTraceViewerProps) {
  return (
    <div className="grid">
      {steps.map((step) => (
        <div key={step.id} className="card">
          <div className="page-header">
            <strong>Step {step.step_index}</strong>
            <span className="badge">{step.type}</span>
          </div>
          <div className="grid">
            <div>
              <div>Tokens: {step.tokens_used}</div>
              <div>Timestamp: {new Date(step.timestamp).toLocaleString()}</div>
            </div>
            <div>
              <div>Input</div>
              <div className="mono">{step.input}</div>
            </div>
            <div>
              <div>Output</div>
              <div className="mono">{step.output}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
