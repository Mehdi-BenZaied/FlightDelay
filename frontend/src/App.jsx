import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Navbar from './components/Navbar';
import PredictionForm from './components/PredictionForm';
import HistoryList from './components/HistoryList';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle2, Lock, User, AlertCircle, Loader2 } from 'lucide-react';
import { io } from 'socket.io-client';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

axios.defaults.withCredentials = true;

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || window.location.origin;

export default function App() {
  const [history, setHistory] = useState([]);
  const [user, setUser] = useState(null);
  const [lastPrediction, setLastPrediction] = useState(null);
  
  // Stats states
  const [stats, setStats] = useState({
    total_predictions: 0,
    average_delay: 0.0,
    most_congested_airport: 'N/A'
  });
  
  // Auth Modal states
  const [authModal, setAuthModal] = useState(null); // 'login' | 'register' | null
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  useEffect(() => {
    checkAuth();
    fetchHistory();
    fetchStats();
  }, []);

  useEffect(() => {
    // Connect to Flask WebSockets
    const socket = io(API_BASE_URL, {
  path: '/socket.io',
  withCredentials: true,
});

    socket.on('connect', () => {
      console.log('Connected to WebSockets server');
    });

    socket.on('new_prediction', (data) => {
      console.log('Live prediction event received:', data);
      // Prepend to history
      setHistory((prev) => {
        if (prev.some((item) => item.id === data.id)) return prev;
        return [data, ...prev.slice(0, 5)];
      });
      // Increment live statistics counters
      fetchStats();
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  const fetchStats = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/v1/predict/stats`);
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load stats', err);
    }
  };

  const checkAuth = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/v1/auth/me`);
      setUser(res.data);
    } catch (err) {
      setUser(null);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/v1/predict/history?limit=6`);
      setHistory(res.data);
    } catch (err) {
      console.error('Failed to load activity history', err);
    }
  };

  const handleNewPrediction = (result) => {
    setLastPrediction(result);
    // History list is updated in real-time via WebSockets, but we also refresh just in case
    fetchHistory();
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthError('');
    try {
      const endpoint = authModal === 'login' ? 'login' : 'register';
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/${endpoint}`, {
        username,
        password
      });
      setUser(res.data.user);
      setAuthModal(null);
      setUsername('');
      setPassword('');
      // Refresh history for the user's specific items
      fetchHistory();
    } catch (err) {
      setAuthError(err.response?.data?.msg || 'Authentication failed. Please try again.');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post(`${API_BASE_URL}/api/v1/auth/logout`);
      setUser(null);
      // Refresh history to show recent public predictions
      fetchHistory();
    } catch (err) {
      console.error('Logout failed', err);
    }
  };

  // Process data for Recharts
  const getChartData = () => {
    return [...history].reverse().map((item) => ({
      name: item.airline,
      delay: parseFloat(item.delay.toFixed(1)),
      route: `${item.origin}→${item.destination}`
    }));
  };

  return (
    <div className="relative pt-32 pb-20 px-6 min-h-screen">
      <Navbar 
        user={user} 
        onLogout={handleLogout} 
        onLoginClick={() => {
          setAuthError('');
          setAuthModal('login');
        }} 
      />
      
      <main className="max-w-7xl mx-auto space-y-12">
        {/* Statistical Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="glass-card p-6 flex flex-col justify-between relative overflow-hidden group hover:border-indigo-500/30 transition-all">
            <span className="block text-xs text-slate-500 uppercase font-bold tracking-wider mb-2">Total AI Predictions</span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-white">{stats.total_predictions}</span>
              <span className="text-xs text-indigo-400 font-bold">queries</span>
            </div>
            <div className="absolute -bottom-4 -right-4 text-white/5 group-hover:text-indigo-500/5 group-hover:scale-110 transition-all select-none pointer-events-none">
              <span className="text-8xl font-black leading-none">#</span>
            </div>
          </div>

          <div className="glass-card p-6 flex flex-col justify-between relative overflow-hidden group hover:border-indigo-500/30 transition-all">
            <span className="block text-xs text-slate-500 uppercase font-bold tracking-wider mb-2">Average Arrival Delay</span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-white">{stats.average_delay}</span>
              <span className="text-xs text-indigo-400 font-bold">minutes</span>
            </div>
            <div className="absolute -bottom-4 -right-4 text-white/5 group-hover:text-indigo-500/5 group-hover:scale-110 transition-all select-none pointer-events-none">
              <span className="text-8xl font-black leading-none">Min</span>
            </div>
          </div>

          <div className="glass-card p-6 flex flex-col justify-between relative overflow-hidden group hover:border-indigo-500/30 transition-all">
            <span className="block text-xs text-slate-500 uppercase font-bold tracking-wider mb-2">Most Congested Origin</span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-white uppercase">{stats.most_congested_airport}</span>
              <span className="text-xs text-indigo-400 font-bold">IATA</span>
            </div>
            <div className="absolute -bottom-4 -right-4 text-white/5 group-hover:text-indigo-500/5 group-hover:scale-110 transition-all select-none pointer-events-none">
              <span className="text-8xl font-black leading-none">✈</span>
            </div>
          </div>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Side: Form */}
          <div className="lg:col-span-7">
            <header className="mb-12">
              <h1 className="text-5xl font-black mb-4 tracking-tight leading-tight">
                Predict Flight Delays with <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-purple-400">
                  AI Precision.
                </span>
              </h1>
              <p className="text-slate-400 text-lg max-w-xl">
                Utilize our advanced neural forecasting engine to analyze congestion, 
                weather patterns, and historical trends in real-time.
              </p>
            </header>
            
            <PredictionForm onNewPrediction={handleNewPrediction} />
          </div>

          {/* Right Side: History */}
          <div className="lg:col-span-5 h-full">
            <HistoryList history={history} />
          </div>
        </div>

        {/* Real-time Analytics Visualisation */}
        {history.length > 0 && (
          <motion.div 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card p-8"
          >
            <h2 className="text-xl font-bold mb-6 text-slate-100 flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 bg-emerald-500 rounded-full animate-ping" />
              Live Prediction Analytics Timeline
            </h2>
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={getChartData()} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorDelay" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={11} tickLine={false} unit="m" />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#0f172a', 
                      borderColor: 'rgba(255,255,255,0.1)', 
                      borderRadius: '12px',
                      color: '#f8fafc'
                    }}
                    formatter={(value, name, props) => [`${value} minutes`, `Delay (${props.payload.route})`]}
                  />
                  <Area type="monotone" dataKey="delay" stroke="#818cf8" strokeWidth={2.5} fillOpacity={1} fill="url(#colorDelay)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        )}
      </main>

      {/* Result Modal */}
      <AnimatePresence>
        {lastPrediction && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-sm">
            <motion.div 
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass-card max-w-md w-full p-10 relative overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-purple-500" />
              <button 
                onClick={() => setLastPrediction(null)}
                className="absolute top-4 right-4 text-slate-500 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex flex-col items-center text-center">
                <div className="bg-emerald-500/10 p-3 rounded-full mb-6">
                  <CheckCircle2 className="text-emerald-500 w-10 h-10" />
                </div>
                <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-2">Analysis Complete</h3>
                <h2 className="text-2xl font-black mb-8">Estimated Arrival Delay</h2>
                
                <div className="flex items-baseline gap-2 mb-8">
                  <span className="text-7xl font-black text-white">{lastPrediction.delay.toFixed(1)}</span>
                  <span className="text-xl font-bold text-indigo-400">min</span>
                </div>

                <div className="grid grid-cols-2 gap-4 w-full">
                  <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
                    <span className="block text-[10px] text-slate-500 uppercase font-bold mb-1">Reliability</span>
                    <span className="text-emerald-400 font-bold">High ({(lastPrediction.confidence * 100).toFixed(0)}%)</span>
                  </div>
                  <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
                    <span className="block text-[10px] text-slate-500 uppercase font-bold mb-1">Weather</span>
                    <span className="text-white font-bold">{lastPrediction.weather.temp}°C</span>
                  </div>
                </div>

                {/* Explainable AI (SHAP) Contribution Bars */}
                {lastPrediction.shap_contributions && Object.keys(lastPrediction.shap_contributions).length > 0 && (
                  <div className="w-full mt-6 text-left space-y-3 bg-white/5 p-4 rounded-2xl border border-white/5">
                    <span className="block text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-2">AI Feature Influence (SHAP)</span>
                    {Object.entries(lastPrediction.shap_contributions).map(([feature, val]) => {
                      const isPositive = val >= 0;
                      const formattedVal = val.toFixed(1);
                      const absPercent = Math.min(100, Math.abs(val) * 10);
                      const displayName = feature
                        .replace('flight_duration', 'Duration')
                        .replace('congestion', 'Congestion')
                        .replace('temperature', 'Temperature')
                        .replace('humidity', 'Humidity');
                      return (
                        <div key={feature} className="space-y-1">
                          <div className="flex justify-between text-xs font-semibold">
                            <span className="text-slate-300">{displayName}</span>
                            <span className={isPositive ? 'text-rose-400' : 'text-emerald-400'}>
                              {isPositive ? '+' : ''}{formattedVal}m
                            </span>
                          </div>
                          <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden">
                            <div 
                              className={`h-full rounded-full ${isPositive ? 'bg-gradient-to-r from-rose-500 to-red-400' : 'bg-gradient-to-r from-emerald-500 to-teal-400'}`}
                              style={{ width: `${absPercent}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <button 
                  onClick={() => setLastPrediction(null)}
                  className="w-full bg-white text-slate-950 font-bold py-4 rounded-2xl mt-6 hover:bg-slate-200 transition-colors cursor-pointer"
                >
                  Confirm & Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Authentication Modal */}
      <AnimatePresence>
        {authModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-sm">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card max-w-sm w-full p-8 relative overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-purple-500" />
              <button 
                onClick={() => setAuthModal(null)}
                className="absolute top-4 right-4 text-slate-500 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="text-center mb-6">
                <h2 className="text-2xl font-bold mb-1">
                  {authModal === 'login' ? 'Sign In' : 'Create Account'}
                </h2>
                <p className="text-xs text-slate-400">
                  {authModal === 'login' ? 'Access your flight prediction records' : 'Register a new user account'}
                </p>
              </div>

              {authError && (
                <div className="mb-4 bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-xl flex items-center gap-2 text-xs">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{authError}</span>
                </div>
              )}

              <form onSubmit={handleAuthSubmit} className="space-y-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                    <User className="w-3 h-3" /> Username
                  </label>
                  <input 
                    type="text" required
                    className="glass-input w-full text-sm"
                    placeholder="e.g. ganesh"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                    <Lock className="w-3 h-3" /> Password
                  </label>
                  <input 
                    type="password" required
                    className="glass-input w-full text-sm"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>

                <button
                  type="submit"
                  disabled={authLoading}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 py-3 rounded-xl font-bold flex items-center justify-center gap-2 transition-all cursor-pointer text-sm shadow-lg shadow-indigo-500/10"
                >
                  {authLoading ? <Loader2 className="animate-spin w-4 h-4" /> : null}
                  {authModal === 'login' ? 'Sign In' : 'Sign Up'}
                </button>
              </form>

              <div className="mt-6 text-center text-xs text-slate-500">
                {authModal === 'login' ? (
                  <span>
                    New to the system?{' '}
                    <button 
                      onClick={() => {
                        setAuthError('');
                        setAuthModal('register');
                      }}
                      className="text-indigo-400 hover:underline font-semibold cursor-pointer"
                    >
                      Sign Up
                    </button>
                  </span>
                ) : (
                  <span>
                    Already have an account?{' '}
                    <button 
                      onClick={() => {
                        setAuthError('');
                        setAuthModal('login');
                      }}
                      className="text-indigo-400 hover:underline font-semibold cursor-pointer"
                    >
                      Sign In
                    </button>
                  </span>
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

