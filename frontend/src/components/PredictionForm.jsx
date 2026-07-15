import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Send, Loader2, Info } from 'lucide-react';
import axios from 'axios';
import AirportAutocomplete from './AirportAutocomplete';

export default function PredictionForm({ onNewPrediction }) {
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    airline: '',
    origin: '',
    destination: '',
    flight_duration: '',
    congestion: 5,
    aircraft_type: ''
  });

  const handleSubmit = async (e) => {
  e.preventDefault();
  setLoading(true);

  try {
    const payload = {
      ...formData,
      flight_duration: Number(formData.flight_duration),
      congestion: Number(formData.congestion),
    };

   const response = await axios.post(
  '/api/v1/predict/',
  {
    ...formData,
    flight_duration: Number(formData.flight_duration),
    congestion: Number(formData.congestion),
  },
  {
    withCredentials: true,
    headers: {
      'Content-Type': 'application/json',
    },
  }
);

    onNewPrediction(response.data);
  } catch (error) {
    console.error('Prediction error:', error);

    const status = error.response?.status;
    const backendMessage =
      error.response?.data?.error ||
      error.response?.data?.message ||
      error.response?.data?.msg;

    alert(
      backendMessage ||
      `Prediction failed${status ? ` (${status})` : ''}. Check the backend terminal.`
    );
  } finally {
    setLoading(false);
  }
};

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-8"
    >
      <div className="flex items-center gap-3 mb-8">
        <div className="bg-indigo-500/10 p-2 rounded-lg">
          <Info className="text-indigo-400 w-5 h-5" />
        </div>
        <h2 className="text-2xl font-bold">New Estimation</h2>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-400">Airline</label>
            <input 
              required
              className="glass-input w-full"
              placeholder="e.g. American Airlines"
              value={formData.airline}
              onChange={(e) => setFormData({...formData, airline: e.target.value})}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-400">Aircraft Type</label>
            <input 
              required
              className="glass-input w-full"
              placeholder="e.g. Boeing 737"
              value={formData.aircraft_type}
              onChange={(e) => setFormData({...formData, aircraft_type: e.target.value})}
            />
          </div>
          
          <AirportAutocomplete
            required
            label="Origin (IATA)"
            placeholder="Search e.g. JFK or New York"
            value={formData.origin}
            onChange={(val) => setFormData({...formData, origin: val})}
          />
          <AirportAutocomplete
            required
            label="Destination (IATA)"
            placeholder="Search e.g. LAX or Chicago"
            value={formData.destination}
            onChange={(val) => setFormData({...formData, destination: val})}
          />
        </div>

        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <label className="text-sm font-medium text-slate-400">Congestion Level</label>
            <span className="text-indigo-400 font-bold">{formData.congestion}</span>
          </div>
          <input 
            type="range" min="1" max="10" 
            className="w-full accent-indigo-500"
            value={formData.congestion}
            onChange={(e) => setFormData({...formData, congestion: parseInt(e.target.value)})}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-400">Duration (Minutes)</label>
          <input 
            type="number" required
            className="glass-input w-full"
            placeholder="e.g. 330"
            value={formData.flight_duration}
            onChange={(e) => setFormData({...formData, flight_duration: e.target.value})}
          />
        </div>

        <button 
          disabled={loading}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 py-4 rounded-2xl font-bold flex items-center justify-center gap-2 transition-all shadow-xl shadow-indigo-500/20 mt-4"
        >
          {loading ? <Loader2 className="animate-spin w-5 h-5" /> : <Send className="w-5 h-5" />}
          {loading ? 'Analyzing Data...' : 'Generate Prediction'}
        </button>
      </form>
    </motion.div>
  );
}
