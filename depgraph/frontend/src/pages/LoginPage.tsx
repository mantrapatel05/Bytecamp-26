import { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

const LoginPage = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    setError('');
    try {
      await login(username.trim(), password);
      navigate('/app');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--void-hex)' }}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm"
      >
        {/* Logo area */}
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

        {/* Login card */}
        <div className="rounded-xl p-6 border" style={{
          background: 'var(--surface-hex)',
          borderColor: 'var(--border-2-hex)',
        }}>
          <h2 className="font-syne font-semibold text-base mb-5" style={{ color: 'var(--text-1-hex)' }}>
            Sign in
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-3-hex)' }}>
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
                placeholder="admin"
                className="w-full px-3 py-2 rounded-lg border outline-none font-mono text-sm transition-all"
                style={{
                  background: 'var(--raised-hex)',
                  borderColor: 'var(--border-1-hex)',
                  color: 'var(--text-1-hex)',
                }}
                onFocus={e => (e.target.style.borderColor = 'var(--teal-hex)')}
                onBlur={e => (e.target.style.borderColor = 'var(--border-1-hex)')}
              />
            </div>

            <div>
              <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-3-hex)' }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                className="w-full px-3 py-2 rounded-lg border outline-none font-mono text-sm transition-all"
                style={{
                  background: 'var(--raised-hex)',
                  borderColor: 'var(--border-1-hex)',
                  color: 'var(--text-1-hex)',
                }}
                onFocus={e => (e.target.style.borderColor = 'var(--teal-hex)')}
                onBlur={e => (e.target.style.borderColor = 'var(--border-1-hex)')}
              />
            </div>

            {error && (
              <p className="font-mono text-xs" style={{ color: '#ff5733' }}>{error}</p>
            )}

            <motion.button
              type="submit"
              disabled={loading || !username.trim() || !password.trim()}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className="w-full py-2.5 rounded-lg font-syne font-semibold text-sm transition-all"
              style={{
                background: loading || !username.trim() || !password.trim()
                  ? 'var(--border-1-hex)' : 'var(--teal-hex)',
                color: 'var(--void-hex)',
                opacity: loading ? 0.7 : 1,
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </motion.button>
          </form>

          <p className="font-mono text-[10px] mt-4 text-center" style={{ color: 'var(--text-4-hex)' }}>
            Default: admin / depgraph123
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default LoginPage;
