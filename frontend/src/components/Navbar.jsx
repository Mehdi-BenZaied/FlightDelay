import React from 'react';
import { Plane, BarChart3, ShieldCheck, LogOut } from 'lucide-react';

export default function Navbar({ user, onLogout, onLoginClick }) {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 px-6 py-4">
      <div className="max-w-7xl mx-auto flex justify-between items-center bg-slate-900/50 backdrop-blur-md border border-white/5 rounded-2xl px-6 py-3">
        <div className="flex items-center gap-2">
          <div className="bg-indigo-600 p-2 rounded-lg">
            <Plane className="text-white w-5 h-5" />
          </div>
          <span className="text-xl font-extrabold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
            Flight Delay AI
          </span>
        </div>
        
        <div className="flex items-center gap-8">
          <a href="/" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">Predictions</a>
          <a href="http://localhost:8050" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">Analytics</a>
          
          <div className="h-4 w-px bg-white/10" />
          
          {user ? (
            <div className="flex items-center gap-4">
              <span className="text-sm text-slate-400">Welcome, <span className="text-indigo-400 font-bold">{user.username}</span></span>
              <button onClick={onLogout} className="p-2 hover:bg-white/5 rounded-lg transition-colors group cursor-pointer" title="Log Out">
                <LogOut className="w-4 h-4 text-slate-400 group-hover:text-red-400" />
              </button>
            </div>
          ) : (
            <button 
              onClick={onLoginClick}
              className="text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 px-5 py-2 rounded-xl transition-all shadow-lg shadow-indigo-500/20 text-white cursor-pointer"
            >
              Sign In
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}
