import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import apiClient from '@/api/client';
import axios from 'axios';

type Mode = 'login' | 'register' | 'setup';

const LoginPage = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [repoPath, setRepoPath] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const switchMode = (m: 'login' | 'register') => {
    setMode(m);
    setError('');
    setPassword('');
    setConfirm('');
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    if (mode === 'register') {
      if (password !== confirm) { setError('Passwords do not match'); return; }
      if (password.length < 6) { setError('Password must be at least 6 characters'); return; }
    }

    setLoading(true);
    setError('');
    try {
      if (mode === 'login') {
        await login(username.trim(), password);
        navigate('/app');
      } else {
        const res = await apiClient.register(username.trim(), password);
        localStorage.setItem('depgraph_token', res.token);
        localStorage.setItem('depgraph_username', res.username);
        // Move to repo setup step
        setMode('setup');
      }
    } catch (err: any) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail || (mode === 'login' ? 'Invalid credentials' : 'Registration failed'));
    } finally {
      setLoading(false);
    }
  };

  const handleStartAnalysis = () => {
    if (repoPath.trim()) {
      localStorage.setItem('depgraph_pending_repo', repoPath.trim());
    }
    window.location.href = '/app';
  };

  const handleSkip = () => {
    window.location.href = '/app';
  };

  const inputStyle = {
    background: 'var(--raised-hex)',
    borderColor: 'var(--border-1-hex)',
    color: 'var(--text-1-hex)',
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--void-hex)' }}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-md flex items-center justify-center font-bold text-sm"
              style={{ background: 'var(--teal-hex)', color: 'var(--void-hex)' }}>
              DG
            </div>
            <span className="font-syne font-bold text-xl" style={{ color: 'var(--text-1-hex)' }}>
              DepGraph.ai
            </span>
          </div>
          <p className="font-mono text-xs" style={{ color: 'var(--text-4-hex)' }}>
            Cross-language dependency intelligence
          </p>
        </div>

        {/* Card */}
        <AnimatePresence mode="wait">

          {/* ── Auth card (login / register) ── */}
          {mode !== 'setup' && (
            <motion.div
              key="auth"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -30 }}
              transition={{ duration: 0.22 }}
              className="rounded-xl p-6 border"
              style={{ background: 'var(--surface-hex)', borderColor: 'var(--border-2-hex)' }}
            >
              {/* Tabs */}
              <div className="flex rounded-lg overflow-hidden border mb-5" style={{ borderColor: 'var(--border-1-hex)' }}>
                {(['login', 'register'] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => switchMode(m)}
                    className="flex-1 py-2 font-syne font-semibold text-xs transition-all cursor-pointer"
                    style={{
                      background: mode === m ? 'var(--teal-hex)' : 'transparent',
                      color: mode === m ? 'var(--void-hex)' : 'var(--text-3-hex)',
                    }}
                  >
                    {m === 'login' ? 'Sign in' : 'Create account'}
                  </button>
                ))}
              </div>

              <motion.form
                key={mode}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.15 }}
                onSubmit={handleAuthSubmit}
                className="space-y-4"
              >
                <div>
                  <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-3-hex)' }}>Username</label>
                  <input
                    type="text" value={username} onChange={e => setUsername(e.target.value)}
                    autoFocus autoComplete="username"
                    placeholder={mode === 'login' ? 'admin' : 'your_username'}
                    className="w-full px-3 py-2 rounded-lg border outline-none font-mono text-sm transition-all"
                    style={inputStyle}
                    onFocus={e => (e.target.style.borderColor = 'var(--teal-hex)')}
                    onBlur={e => (e.target.style.borderColor = 'var(--border-1-hex)')}
                  />
                </div>

                <div>
                  <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-3-hex)' }}>Password</label>
                  <input
                    type="password" value={password} onChange={e => setPassword(e.target.value)}
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    placeholder="••••••••"
                    className="w-full px-3 py-2 rounded-lg border outline-none font-mono text-sm transition-all"
                    style={inputStyle}
                    onFocus={e => (e.target.style.borderColor = 'var(--teal-hex)')}
                    onBlur={e => (e.target.style.borderColor = 'var(--border-1-hex)')}
                  />
                </div>

                {mode === 'register' && (
                  <div>
                    <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-3-hex)' }}>Confirm password</label>
                    <input
                      type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
                      autoComplete="new-password" placeholder="••••••••"
                      className="w-full px-3 py-2 rounded-lg border outline-none font-mono text-sm transition-all"
                      style={inputStyle}
                      onFocus={e => (e.target.style.borderColor = 'var(--teal-hex)')}
                      onBlur={e => (e.target.style.borderColor = 'var(--border-1-hex)')}
                    />
                  </div>
                )}

                {error && <p className="font-mono text-xs" style={{ color: '#ff5733' }}>{error}</p>}

                <motion.button
                  type="submit"
                  disabled={loading || !username.trim() || !password.trim() || (mode === 'register' && !confirm.trim())}
                  whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                  className="w-full py-2.5 rounded-lg font-syne font-semibold text-sm transition-all"
                  style={{
                    background: (loading || !username.trim() || !password.trim()) ? 'var(--border-1-hex)' : 'var(--teal-hex)',
                    color: 'var(--void-hex)',
                    opacity: loading ? 0.7 : 1,
                    cursor: loading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {loading
                    ? (mode === 'login' ? 'Signing in...' : 'Creating account...')
                    : (mode === 'login' ? 'Sign in' : 'Create account')}
                </motion.button>
              </motion.form>

              {mode === 'login' && (
                <p className="font-mono text-[10px] mt-4 text-center" style={{ color: 'var(--text-4-hex)' }}>
                  Default: admin / depgraph123
                </p>
              )}
            </motion.div>
          )}

          {/* ── Setup card (post-register) ── */}
          {mode === 'setup' && (
            <motion.div
              key="setup"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="rounded-xl p-6 border"
              style={{ background: 'var(--surface-hex)', borderColor: 'var(--border-2-hex)' }}
            >
              {/* Success badge */}
              <div className="flex items-center gap-2 mb-5 p-3 rounded-lg"
                style={{ background: 'rgba(0,229,184,0.06)', border: '1px solid rgba(0,229,184,0.2)' }}>
                <span style={{ color: 'var(--teal-hex)', fontSize: 16 }}>✓</span>
                <div>
                  <div className="font-syne font-semibold text-xs" style={{ color: 'var(--teal-hex)' }}>
                    Account created!
                  </div>
                  <div className="font-mono text-[10px]" style={{ color: 'var(--text-4-hex)' }}>
                    Welcome, {username}
                  </div>
                </div>
              </div>

              <h3 className="font-syne font-semibold text-sm mb-1" style={{ color: 'var(--text-1-hex)' }}>
                Add your repository
              </h3>
              <p className="font-mono text-[11px] mb-4" style={{ color: 'var(--text-4-hex)' }}>
                Paste a local path or GitHub URL to analyze immediately.
              </p>

              <div className="space-y-3">
                <div>
                  <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-3-hex)' }}>
                    Repository path or GitHub URL
                  </label>
                  <input
                    type="text"
                    value={repoPath}
                    onChange={e => setRepoPath(e.target.value)}
                    autoFocus
                    placeholder="C:/Projects/my-app  or  https://github.com/..."
                    className="w-full px-3 py-2 rounded-lg border outline-none font-mono text-xs transition-all"
                    style={inputStyle}
                    onFocus={e => (e.target.style.borderColor = 'var(--teal-hex)')}
                    onBlur={e => (e.target.style.borderColor = 'var(--border-1-hex)')}
                    onKeyDown={e => { if (e.key === 'Enter' && repoPath.trim()) handleStartAnalysis(); }}
                  />
                </div>

                <motion.button
                  onClick={handleStartAnalysis}
                  disabled={!repoPath.trim()}
                  whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                  className="w-full py-2.5 rounded-lg font-syne font-semibold text-sm transition-all"
                  style={{
                    background: repoPath.trim() ? 'var(--teal-hex)' : 'var(--border-1-hex)',
                    color: 'var(--void-hex)',
                    cursor: repoPath.trim() ? 'pointer' : 'not-allowed',
                  }}
                >
                  Start Analysis →
                </motion.button>

                <button
                  onClick={handleSkip}
                  className="w-full py-2 font-mono text-xs cursor-pointer transition-all"
                  style={{ color: 'var(--text-4-hex)', background: 'transparent', border: 'none' }}
                >
                  Skip for now — go to dashboard
                </button>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </motion.div>
    </div>
  );
};

export default LoginPage;
