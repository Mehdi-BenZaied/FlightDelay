import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, TrendingUp } from 'lucide-react';

export default function HistoryList({ history }) {
  return (
    <div className="glass-card p-8 h-full">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Clock className="text-indigo-400 w-5 h-5" />
          <h2 className="text-xl font-bold">Recent Activity</h2>
        </div>
        <TrendingUp className="text-slate-500 w-4 h-4" />
      </div>

      <div className="space-y-4">
        <AnimatePresence mode='popLayout'>
          {history.length > 0 ? (
            history.map((item, idx) => (
              <motion.div
                key={item.id || idx}
                layout
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="flex items-center justify-between p-4 bg-white/5 rounded-2xl border border-white/5 hover:border-white/10 transition-colors group"
              >
                <div>
                  <h4 className="font-bold text-slate-200 group-hover:text-white transition-colors">{item.airline}</h4>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span className="bg-white/10 px-1.5 py-0.5 rounded uppercase">{item.origin}</span>
                    <span>→</span>
                    <span className="bg-white/10 px-1.5 py-0.5 rounded uppercase">{item.destination}</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="block text-lg font-black text-indigo-400">{item.delay.toFixed(1)}m</span>
                  <span className="text-[10px] text-slate-600 uppercase font-bold tracking-wider">Delay</span>
                </div>
              </motion.div>
            ))
          ) : (
            <div className="py-12 text-center">
              <p className="text-slate-500 text-sm">No analysis history found.</p>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
