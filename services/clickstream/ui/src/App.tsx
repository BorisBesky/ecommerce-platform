import SimulationControls from './components/SimulationControls';
import FraudDashboard from './components/FraudDashboard';
import RecommendationAccuracyChart from './components/RecommendationAccuracyChart';
import RayJobsPanel from './components/RayJobsPanel';

function App(): JSX.Element {
  return (
    <div className="app-shell">
      <header>
        <h1>Clickstream Intelligence Control Center</h1>
        <p>Simulate traffic, monitor fraud risk, and orchestrate recommendation jobs from a single pane.</p>
      </header>
      <main>
        <section>
          <h2>Clickstream Simulation</h2>
          <SimulationControls />
        </section>

        <div className="grid-two-columns">
          <section>
            <h2>Fraud Detection Pulse</h2>
            <FraudDashboard />
          </section>

          <section>
            <h2>Recommendation Accuracy</h2>
            <RecommendationAccuracyChart />
          </section>
        </div>

        <section>
          <h2>Ray Orchestration</h2>
          <RayJobsPanel />
        </section>
      </main>
    </div>
  );
}

export default App;

