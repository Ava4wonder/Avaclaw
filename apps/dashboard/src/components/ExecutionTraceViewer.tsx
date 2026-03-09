import { ExecutionSpan } from "../api/client";

type ExecutionTraceViewerProps = {
  spans: ExecutionSpan[];
};

type SpanNode = ExecutionSpan & { children: SpanNode[] };

function buildTree(spans: ExecutionSpan[]): SpanNode[] {
  const byId = new Map<string, SpanNode>();
  spans.forEach((span) => byId.set(span.id, { ...span, children: [] }));
  const roots: SpanNode[] = [];
  byId.forEach((node) => {
    if (node.parent_span_id && byId.has(node.parent_span_id)) {
      byId.get(node.parent_span_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  const sortNodes = (nodes: SpanNode[]) => {
    nodes.sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
    nodes.forEach((node) => sortNodes(node.children));
  };
  sortNodes(roots);
  return roots;
}

function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function safeJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function ExecutionTraceViewer({ spans }: ExecutionTraceViewerProps) {
  const nodes = buildTree(spans);
  const times = spans.map((span) => new Date(span.start_time).getTime());
  const endTimes = spans.map((span) => new Date(span.end_time).getTime());
  const rootStart = Math.min(...times, Date.now());
  const rootEnd = Math.max(...endTimes, rootStart + 1);
  const total = Math.max(1, rootEnd - rootStart);

  const renderNode = (node: SpanNode, depth: number) => {
    const start = new Date(node.start_time).getTime();
    const offsetPct = ((start - rootStart) / total) * 100;
    const widthPct = (node.duration_ms / total) * 100;
    return (
      <div key={node.id} className="trace-node">
        <div className="trace-row">
          <div className="trace-label" style={{ paddingLeft: depth * 16 }}>
            <div className="trace-title">
              <strong>{node.name}</strong>
              <span className="badge">{node.span_type}</span>
              <span className={`trace-status ${node.status}`}>{node.status}</span>
            </div>
            <div className="trace-meta">
              <span>Duration: {formatDuration(node.duration_ms)}</span>
              <span>Start: {new Date(node.start_time).toLocaleTimeString()}</span>
            </div>
            {node.error && <div className="trace-error">Error: {node.error}</div>}
          </div>
          <div className="trace-waterfall">
            <div
              className={`trace-bar ${node.status}`}
              style={{ left: `${offsetPct}%`, width: `${Math.max(1, widthPct)}%` }}
            />
          </div>
        </div>
        {node.span_type === "tool" && (
          <details className="trace-details">
            <summary>Tool arguments and result</summary>
            <div className="grid">
              <div>
                <div>Args</div>
                <pre className="mono">{safeJson(node.tool_args)}</pre>
              </div>
              <div>
                <div>Result</div>
                <pre className="mono">{safeJson(node.tool_result)}</pre>
              </div>
            </div>
          </details>
        )}
        {node.children.length > 0 && (
          <div className="trace-children">{node.children.map((child) => renderNode(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  return (
    <div className="trace-viewer">
      {nodes.length === 0 ? <div>No spans recorded.</div> : nodes.map((node) => renderNode(node, 0))}
    </div>
  );
}
