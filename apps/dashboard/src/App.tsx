import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import AgentsPage from "./pages/AgentsPage";
import AgentDetailPage from "./pages/AgentDetailPage";
import ExecutionLogsPage from "./pages/ExecutionLogsPage";
import TaskQueuePage from "./pages/TaskQueuePage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">Avaclaw</div>
          <nav className="nav">
            <NavLink to="/" end>
              Agents
            </NavLink>
            <NavLink to="/queue">Task Queue</NavLink>
            <NavLink to="/executions">Execution Viewer</NavLink>
          </nav>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<AgentsPage />} />
            <Route path="/agents/:id" element={<AgentDetailPage />} />
            <Route path="/queue" element={<TaskQueuePage />} />
            <Route path="/executions" element={<ExecutionLogsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
