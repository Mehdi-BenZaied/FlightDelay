import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import axios from 'axios';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Lock,
  User,
  X,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { io } from 'socket.io-client';

import Navbar from './components/Navbar';
import PredictionForm from './components/PredictionForm';
import HistoryList from './components/HistoryList';

/*
 * Use relative routes so browser requests go to the same origin as the
 * frontend:
 *
 *   Browser -> http://localhost:8081/api/...
 *   Nginx   -> http://backend:5000/api/...
 *
 * Never use http://backend:5000 from browser-side JavaScript.
 * "backend" is only resolvable inside Kubernetes.
 */
const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

const EMPTY_STATS = {
  total_predictions: 0,
  average_delay: 0,
  most_congested_airport: 'N/A',
};

function normalizeHistory(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload?.history)) {
    return payload.history;
  }

  if (Array.isArray(payload?.items)) {
    return payload.items;
  }

  return [];
}

function normalizeStats(payload) {
  const source = payload?.stats ?? payload ?? {};

  return {
    total_predictions: Number(source.total_predictions ?? 0),
    average_delay: Number(source.average_delay ?? 0),
    most_congested_airport:
      source.most_congested_airport || 'N/A',
  };
}

function normalizeUser(payload) {
  return payload?.user ?? payload ?? null;
}

export default function App() {
  const [history, setHistory] = useState([]);
  const [user, setUser] = useState(null);
  const [lastPrediction, setLastPrediction] = useState(null);
  const [stats, setStats] = useState(EMPTY_STATS);

  const [authModal, setAuthModal] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  const fetchStats = useCallback(async () => {
    try {
      const response = await api.get('/predict/stats');
      const nextStats = normalizeStats(response.data);

      setStats(nextStats);
      return nextStats;
    } catch (error) {
      console.error(
        'Failed to load prediction statistics:',
        error.response?.data ?? error.message,
      );

      return null;
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await api.get('/predict/history', {
        params: {
          limit: 6,
        },
      });

      const nextHistory = normalizeHistory(response.data);

      setHistory(nextHistory);
      return nextHistory;
    } catch (error) {
      console.error(
        'Failed to load activity history:',
        error.response?.data ?? error.message,
      );

      return [];
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const response = await api.get('/auth/me');
      const currentUser = normalizeUser(response.data);

      setUser(currentUser);
      return currentUser;
    } catch (error) {
      /*
       * A 401 response is normal when the visitor is not signed in.
       * Do not treat it as a fatal application error.
       */
      if (error.response?.status !== 401) {
        console.error(
          'Failed to check authentication:',
          error.response?.data ?? error.message,
        );
      }

      setUser(null);
      return null;
    }
  }, []);

  const refreshDashboard = useCallback(async () => {
    await Promise.allSettled([
      fetchHistory(),
      fetchStats(),
    ]);
  }, [fetchHistory, fetchStats]);

  /*
   * Load authentication, history and statistics when the application starts.
   */
  useEffect(() => {
    void Promise.allSettled([
      checkAuth(),
      fetchHistory(),
      fetchStats(),
    ]);
  }, [checkAuth, fetchHistory, fetchStats]);

  /*
   * Connect Socket.IO to the same origin as the frontend.
   *
   * Browser:
   *   http://localhost:8081/socket.io/
   *
   * Frontend Nginx proxies it internally to:
   *   http://backend:5000/socket.io/
   */
  useEffect(() => {
    const socket = io(window.location.origin, {
      path: '/socket.io',
      withCredentials: true,
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      timeout: 10000,
    });

    socket.on('connect', () => {
      console.info('Connected to the Socket.IO server:', socket.id);
    });

    socket.on('connect_error', (error) => {
      console.error('Socket.IO connection failed:', error.message);
    });

    socket.on('disconnect', (reason) => {
      console.warn('Socket.IO disconnected:', reason);
    });

    socket.on('new_prediction', (payload) => {
      const prediction = payload?.prediction ?? payload;

      if (prediction && typeof prediction === 'object') {
        setHistory((previousHistory) => {
          const alreadyExists =
            prediction.id !== undefined &&
            previousHistory.some(
              (item) => item.id === prediction.id,
            );

          if (alreadyExists) {
            return previousHistory;
          }

          return [
            prediction,
            ...previousHistory,
          ].slice(0, 6);
        });
      }

      /*
       * The WebSocket event updates the UI optimistically.
       * Refetch the backend data to make sure history and statistics match
       * what was actually persisted in the database.
       */
      void refreshDashboard();
    });

    return () => {
      socket.removeAllListeners();
      socket.disconnect();
    };
  }, [refreshDashboard]);

  const handleNewPrediction = useCallback(
    (result) => {
      setLastPrediction(result);

      /*
       * Do not depend exclusively on the WebSocket event.
       * Refresh both endpoints after every successful prediction.
       */
      void refreshDashboard();
    },
    [refreshDashboard],
  );

  const handleAuthSubmit = async (event) => {
    event.preventDefault();

    setAuthLoading(true);
    setAuthError('');

    try {
      const endpoint =
        authModal === 'login'
          ? '/auth/login'
          : '/auth/register';

      const response = await api.post(endpoint, {
        username: username.trim(),
        password,
      });

      setUser(normalizeUser(response.data));
      setAuthModal(null);
      setUsername('');
      setPassword('');

      await refreshDashboard();
    } catch (error) {
      setAuthError(
        error.response?.data?.msg ||
          error.response?.data?.message ||
          'Authentication failed. Please try again.',
      );
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout');

      setUser(null);
      setLastPrediction(null);

      await refreshDashboard();
    } catch (error) {
      console.error(
        'Logout failed:',
        error.response?.data ?? error.message,
      );
    }
  };

  const chartData = useMemo(
    () =>
      [...history]
        .reverse()
        .map((item) => {
          const delay = Number(item?.delay ?? 0);

          return {
            name: item?.airline || 'Unknown',
            delay: Number.isFinite(delay)
              ? Number(delay.toFixed(1))
              : 0,
            route: `${item?.origin || '?'}→${
              item?.destination || '?'
            }`,
          };
        }),
    [history],
  );

  const closeAuthModal = () => {
    setAuthModal(null);
    setAuthError('');
    setPassword('');
  };

  return (
    <div className="relative min-h-screen px-6 pb-20 pt-32">
      <Navbar
        user={user}
        onLogout={handleLogout}
        onLoginClick={() => {
          setAuthError('');
          setAuthModal('login');
        }}
      />

      <main className="mx-auto max-w-7xl space-y-12">
        {/* Statistical overview */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="glass-card group relative flex flex-col justify-between overflow-hidden p-6 transition-all hover:border-indigo-500/30">
            <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-500">
              Total AI Predictions
            </span>

            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-white">
                {stats.total_predictions}
              </span>

              <span className="text-xs font-bold text-indigo-400">
                queries
              </span>
            </div>

            <div className="pointer-events-none absolute -bottom-4 -right-4 select-none text-white/5 transition-all group-hover:scale-110 group-hover:text-indigo-500/5">
              <span className="text-8xl font-black leading-none">
                #
              </span>
            </div>
          </div>

          <div className="glass-card group relative flex flex-col justify-between overflow-hidden p-6 transition-all hover:border-indigo-500/30">
            <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-500">
              Average Arrival Delay
            </span>

            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black text-white">
                {stats.average_delay}
              </span>

              <span className="text-xs font-bold text-indigo-400">
                minutes
              </span>
            </div>

            <div className="pointer-events-none absolute -bottom-4 -right-4 select-none text-white/5 transition-all group-hover:scale-110 group-hover:text-indigo-500/5">
              <span className="text-8xl font-black leading-none">
                Min
              </span>
            </div>
          </div>

          <div className="glass-card group relative flex flex-col justify-between overflow-hidden p-6 transition-all hover:border-indigo-500/30">
            <span className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-500">
              Most Congested Origin
            </span>

            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-black uppercase text-white">
                {stats.most_congested_airport}
              </span>

              <span className="text-xs font-bold text-indigo-400">
                IATA
              </span>
            </div>

            <div className="pointer-events-none absolute -bottom-4 -right-4 select-none text-white/5 transition-all group-hover:scale-110 group-hover:text-indigo-500/5">
              <span className="text-8xl font-black leading-none">
                ✈
              </span>
            </div>
          </div>
        </div>

        {/* Prediction form and history */}
        <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <header className="mb-12">
              <h1 className="mb-4 text-5xl font-black leading-tight tracking-tight">
                Predict Flight Delays with
                <br />

                <span className="bg-gradient-to-r from-indigo-500 to-purple-400 bg-clip-text text-transparent">
                  AI Precision.
                </span>
              </h1>

              <p className="max-w-xl text-lg text-slate-400">
                Utilize our advanced neural forecasting engine to
                analyze congestion, weather patterns and historical
                trends in real time.
              </p>
            </header>

            <PredictionForm
              onNewPrediction={handleNewPrediction}
            />
          </div>

          <div className="h-full lg:col-span-5">
            <HistoryList history={history} />
          </div>
        </div>

        {/* Analytics chart */}
        {chartData.length > 0 && (
          <motion.div
            initial={{
              opacity: 0,
              y: 30,
            }}
            animate={{
              opacity: 1,
              y: 0,
            }}
            className="glass-card p-8"
          >
            <h2 className="mb-6 flex items-center gap-2 text-xl font-bold text-slate-100">
              <span className="inline-block h-2.5 w-2.5 animate-ping rounded-full bg-emerald-500" />
              Live Prediction Analytics Timeline
            </h2>

            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={chartData}
                  margin={{
                    top: 10,
                    right: 30,
                    left: 0,
                    bottom: 0,
                  }}
                >
                  <defs>
                    <linearGradient
                      id="colorDelay"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor="#6366f1"
                        stopOpacity={0.4}
                      />

                      <stop
                        offset="95%"
                        stopColor="#6366f1"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>

                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(255,255,255,0.05)"
                  />

                  <XAxis
                    dataKey="name"
                    stroke="#64748b"
                    fontSize={11}
                    tickLine={false}
                  />

                  <YAxis
                    stroke="#64748b"
                    fontSize={11}
                    tickLine={false}
                    unit="m"
                  />

                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: 'rgba(255,255,255,0.1)',
                      borderRadius: '12px',
                      color: '#f8fafc',
                    }}
                    formatter={(value, name, properties) => [
                      `${value} minutes`,
                      `Delay (${properties.payload.route})`,
                    ]}
                  />

                  <Area
                    type="monotone"
                    dataKey="delay"
                    stroke="#818cf8"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#colorDelay)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        )}
      </main>

      {/* Prediction result modal */}
      <AnimatePresence>
        {lastPrediction && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 p-6 backdrop-blur-sm">
            <motion.div
              initial={{
                scale: 0.9,
                opacity: 0,
              }}
              animate={{
                scale: 1,
                opacity: 1,
              }}
              exit={{
                scale: 0.9,
                opacity: 0,
              }}
              className="glass-card relative w-full max-w-md overflow-hidden p-10"
            >
              <div className="absolute left-0 top-0 h-1 w-full bg-gradient-to-r from-indigo-500 to-purple-500" />

              <button
                type="button"
                aria-label="Close prediction result"
                onClick={() => setLastPrediction(null)}
                className="absolute right-4 top-4 cursor-pointer text-slate-500 transition-colors hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>

              <div className="flex flex-col items-center text-center">
                <div className="mb-6 rounded-full bg-emerald-500/10 p-3">
                  <CheckCircle2 className="h-10 w-10 text-emerald-500" />
                </div>

                <h3 className="mb-2 text-sm font-bold uppercase tracking-widest text-slate-400">
                  Analysis Complete
                </h3>

                <h2 className="mb-8 text-2xl font-black">
                  Estimated Arrival Delay
                </h2>

                <div className="mb-8 flex items-baseline gap-2">
                  <span className="text-7xl font-black text-white">
                    {Number(
                      lastPrediction.delay ?? 0,
                    ).toFixed(1)}
                  </span>

                  <span className="text-xl font-bold text-indigo-400">
                    min
                  </span>
                </div>

                <div className="grid w-full grid-cols-2 gap-4">
                  <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                    <span className="mb-1 block text-[10px] font-bold uppercase text-slate-500">
                      Reliability
                    </span>

                    <span className="font-bold text-emerald-400">
                      High (
                      {(
                        Number(
                          lastPrediction.confidence ?? 0,
                        ) * 100
                      ).toFixed(0)}
                      %)
                    </span>
                  </div>

                  <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                    <span className="mb-1 block text-[10px] font-bold uppercase text-slate-500">
                      Weather
                    </span>

                    <span className="font-bold text-white">
                      {lastPrediction.weather?.temp ?? 'N/A'}°C
                    </span>
                  </div>
                </div>

                {lastPrediction.shap_contributions &&
                  Object.keys(
                    lastPrediction.shap_contributions,
                  ).length > 0 && (
                    <div className="mt-6 w-full space-y-3 rounded-2xl border border-white/5 bg-white/5 p-4 text-left">
                      <span className="mb-2 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        AI Feature Influence (SHAP)
                      </span>

                      {Object.entries(
                        lastPrediction.shap_contributions,
                      ).map(([feature, rawValue]) => {
                        const value = Number(rawValue ?? 0);
                        const isPositive = value >= 0;
                        const formattedValue = value.toFixed(1);
                        const absolutePercentage = Math.min(
                          100,
                          Math.abs(value) * 10,
                        );

                        const displayName = feature
                          .replace(
                            'flight_duration',
                            'Duration',
                          )
                          .replace(
                            'congestion',
                            'Congestion',
                          )
                          .replace(
                            'temperature',
                            'Temperature',
                          )
                          .replace('humidity', 'Humidity');

                        return (
                          <div
                            key={feature}
                            className="space-y-1"
                          >
                            <div className="flex justify-between text-xs font-semibold">
                              <span className="text-slate-300">
                                {displayName}
                              </span>

                              <span
                                className={
                                  isPositive
                                    ? 'text-rose-400'
                                    : 'text-emerald-400'
                                }
                              >
                                {isPositive ? '+' : ''}
                                {formattedValue}m
                              </span>
                            </div>

                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-950">
                              <div
                                className={`h-full rounded-full ${
                                  isPositive
                                    ? 'bg-gradient-to-r from-rose-500 to-red-400'
                                    : 'bg-gradient-to-r from-emerald-500 to-teal-400'
                                }`}
                                style={{
                                  width: `${absolutePercentage}%`,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                <button
                  type="button"
                  onClick={() => setLastPrediction(null)}
                  className="mt-6 w-full cursor-pointer rounded-2xl bg-white py-4 font-bold text-slate-950 transition-colors hover:bg-slate-200"
                >
                  Confirm & Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Authentication modal */}
      <AnimatePresence>
        {authModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 p-6 backdrop-blur-sm">
            <motion.div
              initial={{
                scale: 0.95,
                opacity: 0,
              }}
              animate={{
                scale: 1,
                opacity: 1,
              }}
              exit={{
                scale: 0.95,
                opacity: 0,
              }}
              className="glass-card relative w-full max-w-sm overflow-hidden p-8"
            >
              <div className="absolute left-0 top-0 h-1 w-full bg-gradient-to-r from-indigo-500 to-purple-500" />

              <button
                type="button"
                aria-label="Close authentication modal"
                onClick={closeAuthModal}
                className="absolute right-4 top-4 cursor-pointer text-slate-500 transition-colors hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>

              <div className="mb-6 text-center">
                <h2 className="mb-1 text-2xl font-bold">
                  {authModal === 'login'
                    ? 'Sign In'
                    : 'Create Account'}
                </h2>

                <p className="text-xs text-slate-400">
                  {authModal === 'login'
                    ? 'Access your flight prediction records'
                    : 'Register a new user account'}
                </p>
              </div>

              {authError && (
                <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{authError}</span>
                </div>
              )}

              <form
                onSubmit={handleAuthSubmit}
                className="space-y-4"
              >
                <div className="space-y-1">
                  <label
                    htmlFor="username"
                    className="flex items-center gap-1.5 text-xs font-semibold text-slate-400"
                  >
                    <User className="h-3 w-3" />
                    Username
                  </label>

                  <input
                    id="username"
                    type="text"
                    required
                    autoComplete="username"
                    className="glass-input w-full text-sm"
                    placeholder="e.g. ganesh"
                    value={username}
                    onChange={(event) =>
                      setUsername(event.target.value)
                    }
                  />
                </div>

                <div className="space-y-1">
                  <label
                    htmlFor="password"
                    className="flex items-center gap-1.5 text-xs font-semibold text-slate-400"
                  >
                    <Lock className="h-3 w-3" />
                    Password
                  </label>

                  <input
                    id="password"
                    type="password"
                    required
                    autoComplete={
                      authModal === 'login'
                        ? 'current-password'
                        : 'new-password'
                    }
                    className="glass-input w-full text-sm"
                    placeholder="••••••••"
                    value={password}
                    onChange={(event) =>
                      setPassword(event.target.value)
                    }
                  />
                </div>

                <button
                  type="submit"
                  disabled={authLoading}
                  className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3 text-sm font-bold shadow-lg shadow-indigo-500/10 transition-all hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {authLoading && (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}

                  {authModal === 'login'
                    ? 'Sign In'
                    : 'Sign Up'}
                </button>
              </form>

              <div className="mt-6 text-center text-xs text-slate-500">
                {authModal === 'login' ? (
                  <span>
                    New to the system?{' '}
                    <button
                      type="button"
                      onClick={() => {
                        setAuthError('');
                        setAuthModal('register');
                      }}
                      className="cursor-pointer font-semibold text-indigo-400 hover:underline"
                    >
                      Sign Up
                    </button>
                  </span>
                ) : (
                  <span>
                    Already have an account?{' '}
                    <button
                      type="button"
                      onClick={() => {
                        setAuthError('');
                        setAuthModal('login');
                      }}
                      className="cursor-pointer font-semibold text-indigo-400 hover:underline"
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