import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import SimulationControls from './components/SimulationControls';
import FraudDashboard from './components/FraudDashboard';
import RecommendationAccuracyChart from './components/RecommendationAccuracyChart';
import RayJobsPanel from './components/RayJobsPanel';
function App() {
    return (_jsxs("div", { className: "app-shell", children: [_jsxs("header", { children: [_jsx("h1", { children: "Clickstream Intelligence Control Center" }), _jsx("p", { children: "Simulate traffic, monitor fraud risk, and orchestrate recommendation jobs from a single pane." })] }), _jsxs("main", { children: [_jsxs("section", { children: [_jsx("h2", { children: "Clickstream Simulation" }), _jsx(SimulationControls, {})] }), _jsxs("div", { className: "grid-two-columns", children: [_jsxs("section", { children: [_jsx("h2", { children: "Fraud Detection Pulse" }), _jsx(FraudDashboard, {})] }), _jsxs("section", { children: [_jsx("h2", { children: "Recommendation Accuracy" }), _jsx(RecommendationAccuracyChart, {})] })] }), _jsxs("section", { children: [_jsx("h2", { children: "Ray Orchestration" }), _jsx(RayJobsPanel, {})] })] })] }));
}
export default App;
