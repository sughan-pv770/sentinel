import { useState, useEffect } from 'react';
import { sentinelx as sxApi } from '../api/client';

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ identity_id: '', name: '', role: 'student', network_tag: '' });
  const [msg, setMsg] = useState('');

  const fetchUsers = () => {
    sxApi.users().then(d => setUsers(d.users || [])).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { fetchUsers(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setMsg('');
    try {
      await sxApi.addUser(form);
      setMsg('✅ User created successfully');
      setForm({ identity_id: '', name: '', role: 'student', network_tag: '' });
      fetchUsers();
    } catch (err) {
      setMsg(`❌ ${err.data?.detail || err.message}`);
    }
  };

  const riskColor = (score) =>
    score >= 60 ? 'var(--risk-critical)' : score >= 30 ? 'var(--risk-warning)' : 'var(--risk-safe)';

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">User Management</div>
          <div className="topbar-subtitle">{users.length} registered identities</div>
        </div>
        <div className="topbar-right">
          <button className="btn btn-primary btn-sm" onClick={() => setShowForm(!showForm)}>
            {showForm ? '✕ Cancel' : '+ Add User'}
          </button>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {/* Add User Form */}
        {showForm && (
          <div className="card mb-16 animate-slide-in">
            <div className="card-title" style={{ marginBottom: 14 }}>New User</div>
            <form onSubmit={handleAdd} className="flex gap-12 items-center" style={{ flexWrap: 'wrap' }}>
              <input className="input" style={{ flex: '1 1 160px' }} placeholder="identity_id (e.g. u_charlie)" value={form.identity_id} onChange={e => setForm({ ...form, identity_id: e.target.value })} required />
              <input className="input" style={{ flex: '1 1 160px' }} placeholder="Full name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
              <select className="input" style={{ flex: '0 0 120px' }} value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                <option value="student">student</option>
                <option value="manager">manager</option>
                <option value="admin">admin</option>
                <option value="service">service</option>
              </select>
              <input className="input" style={{ flex: '1 1 120px' }} placeholder="Network tag" value={form.network_tag} onChange={e => setForm({ ...form, network_tag: e.target.value })} />
              <button type="submit" className="btn btn-primary">Add →</button>
            </form>
            {msg && <div style={{ marginTop: 10, fontSize: 13, color: msg.startsWith('✅') ? 'var(--risk-safe)' : 'var(--risk-critical)' }}>{msg}</div>}
          </div>
        )}

        {/* Users Table */}
        <div className="card">
          {loading ? (
            <div className="loading-center"><div className="loading-spinner" /></div>
          ) : (
            <div className="scroll-x">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Identity ID</th>
                    <th>Name</th>
                    <th>Role</th>
                    <th>Supervisor</th>
                    <th>Network Tag</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.identity_id}>
                      <td className="mono" style={{ fontWeight: 600 }}>{u.identity_id}</td>
                      <td>{u.name}</td>
                      <td>
                        <span className={`tier-badge ${u.role === 'admin' ? 'revoke' : u.role === 'manager' ? 'step_up' : 'allow'}`} style={{ fontSize: 10 }}>
                          {u.role}
                        </span>
                      </td>
                      <td className="mono text-muted">{u.supervisor_id || '—'}</td>
                      <td>{u.network_tag || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
