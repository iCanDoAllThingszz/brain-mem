import { useState } from 'react';
import { Plus, Trash2, Link as LinkIcon, AlertCircle } from 'lucide-react';
import './ControlPanel.css';

export default function ControlPanel() {
  const [activeTab, setActiveTab] = useState<'add' | 'delete' | 'rel'>('add');
  const [form, setForm] = useState({ name: '', summary: '', zone: 'episodic', node_id: '', from_id: '', to_id: '', rel_type: '' });
  const [status, setStatus] = useState<string | null>(null);

  const handleCreateNode = async () => {
    try {
      const res = await fetch('http://localhost:8100/api/graph/node', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: 'default',
          user_id: 'yugo',
          name: form.name,
          summary: form.summary,
          zone: form.zone,
          importance: 5,
        })
      });
      if (res.ok) {
        setStatus("Node Created!");
        setForm({ ...form, name: '', summary: '' });
      } else {
        setStatus("Error creating node");
      }
    } catch {
      setStatus("Network error");
    }
  };

  const handleDeleteNode = async () => {
    try {
      const res = await fetch(`http://localhost:8100/api/graph/node/${form.node_id}?tenant_id=default&user_id=yugo`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setStatus("Node Deleted!");
        setForm({ ...form, node_id: '' });
      } else {
        setStatus("Node not found");
      }
    } catch {
      setStatus("Network error");
    }
  };

  const handleCreateRel = async () => {
    try {
      const res = await fetch('http://localhost:8100/api/graph/relation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: 'default',
          user_id: 'yugo',
          from_id: form.from_id,
          to_id: form.to_id,
          rel_type: form.rel_type,
        })
      });
      if (res.ok) {
        setStatus("Relation Created!");
        setForm({ ...form, from_id: '', to_id: '', rel_type: '' });
      } else {
        setStatus("Error creating relation");
      }
    } catch {
      setStatus("Network error");
    }
  };

  return (
    <div className="control-panel glass-panel">
      {/* Header Tabs */}
      <div className="tabs-header">
        <button onClick={() => setActiveTab('add')} className={`tab-btn ${activeTab === 'add' ? 'active add' : ''}`}>
          <Plus size={16} /> Add
        </button>
        <button onClick={() => setActiveTab('delete')} className={`tab-btn border-left ${activeTab === 'delete' ? 'active delete' : ''}`}>
          <Trash2 size={16} /> Del Node
        </button>
        <button onClick={() => setActiveTab('rel')} className={`tab-btn border-left ${activeTab === 'rel' ? 'active rel' : ''}`}>
          <LinkIcon size={16} /> Rel
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'add' && (
          <div className="form-group animate-fade-in">
            <input 
              className="glass-input" placeholder="Node Name" 
              value={form.name} onChange={e => setForm({...form, name: e.target.value})}
            />
            <input 
              className="glass-input" placeholder="Summary (optional)" 
              value={form.summary} onChange={e => setForm({...form, summary: e.target.value})}
            />
            <select 
              className="glass-input select-styled"
              value={form.zone} onChange={e => setForm({...form, zone: e.target.value})}
            >
              <option value="episodic">Episodic (Event)</option>
              <option value="semantic">Semantic (Fact)</option>
              <option value="procedural">Procedural (Skill)</option>
              <option value="concept">Concept</option>
            </select>
            <button className="glass-button btn-primary" onClick={handleCreateNode}>
              <Plus size={16} /> Create Node
            </button>
          </div>
        )}

        {activeTab === 'delete' && (
          <div className="form-group animate-fade-in">
            <input 
              className="glass-input input-accent" placeholder="Node ID" 
              value={form.node_id} onChange={e => setForm({...form, node_id: e.target.value})}
            />
            <button className="glass-button btn-accent" onClick={handleDeleteNode}>
              <Trash2 size={16} /> Delete Node
            </button>
            <p className="warning-text">
              <AlertCircle size={12} className="warning-icon" />
              Deleting a node automatically removes all connected relationships.
            </p>
          </div>
        )}

        {activeTab === 'rel' && (
          <div className="form-group animate-fade-in">
            <input 
              className="glass-input input-secondary" placeholder="Source Node ID" 
              value={form.from_id} onChange={e => setForm({...form, from_id: e.target.value})}
            />
            <input 
              className="glass-input input-secondary" placeholder="Target Node ID" 
              value={form.to_id} onChange={e => setForm({...form, to_id: e.target.value})}
            />
            <input 
              className="glass-input input-secondary" placeholder="RELATION_TYPE" 
              value={form.rel_type} onChange={e => setForm({...form, rel_type: e.target.value.toUpperCase()})}
            />
            <button className="glass-button btn-secondary" onClick={handleCreateRel}>
              <LinkIcon size={16} /> Create Relation
            </button>
          </div>
        )}

        {status && (
          <div className="status-message">
            {status}
          </div>
        )}
      </div>
    </div>
  );
}
