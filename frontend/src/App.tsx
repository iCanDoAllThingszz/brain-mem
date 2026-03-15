import { useState } from 'react';
import GraphVisualizer from './components/GraphVisualizer';
import ActivityStream from './components/ActivityStream';
import ControlPanel from './components/ControlPanel';
import { Brain, LayoutPanelLeft } from 'lucide-react';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="app-container">
      {/* Main Graph Area */}
      <main className="main-content">
        <GraphVisualizer />
        
        {/* Floating Header */}
        <header className="floating-header glass-panel">
          <div className="header-icon">
            <Brain size={24} />
          </div>
          <div className="header-title">
            <h1>Brain-Mem</h1>
            <p>Neural Interface</p>
          </div>
        </header>

        {/* Floating Control Panel */}
        <div className="control-panel-wrapper">
          <ControlPanel />
        </div>
        
        {/* Toggle Sidebar Button (Mobile/Tablet) */}
        {!sidebarOpen && (
          <button 
            className="sidebar-toggle glass-button"
            onClick={() => setSidebarOpen(true)}
          >
            <LayoutPanelLeft size={20} />
          </button>
        )}
      </main>

      {/* Activity Logs Sidebar */}
      <aside className={`activity-sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <ActivityStream onClose={() => setSidebarOpen(false)} />
      </aside>
    </div>
  );
}

export default App;
