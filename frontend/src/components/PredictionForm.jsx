import React, { useState } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  Info,
  Loader2,
  Send,
} from 'lucide-react';

import AirportAutocomplete from './AirportAutocomplete';

const INITIAL_FORM_DATA = {
  airline: '',
  origin: '',
  destination: '',
  flight_duration: '',
  congestion: 5,
  aircraft_type: '',
};

export default function PredictionForm({ onNewPrediction }) {
  const [formData, setFormData] = useState(INITIAL_FORM_DATA);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const updateField = (field, value) => {
    setFormData((previous) => ({
      ...previous,
      [field]: value,
    }));
  };

  const validateForm = () => {
    const duration = Number(formData.flight_duration);
    const congestion = Number(formData.congestion);

    if (!formData.airline.trim()) {
      return 'Airline is required.';
    }

    if (!formData.aircraft_type.trim()) {
      return 'Aircraft type is required.';
    }

    if (!formData.origin.trim()) {
      return 'Origin airport is required.';
    }

    if (!formData.destination.trim()) {
      return 'Destination airport is required.';
    }

    if (
      formData.origin.trim().toUpperCase() ===
      formData.destination.trim().toUpperCase()
    ) {
      return 'Origin and destination must be different.';
    }

    if (!Number.isFinite(duration) || duration <= 0) {
      return 'Flight duration must be greater than zero.';
    }

    if (
      !Number.isInteger(congestion) ||
      congestion < 1 ||
      congestion > 10
    ) {
      return 'Congestion must be between 1 and 10.';
    }

    return null;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (loading) {
      return;
    }

    setSubmitError('');

    const validationError = validateForm();

    if (validationError) {
      setSubmitError(validationError);
      return;
    }

    const payload = {
      airline: formData.airline.trim(),
      origin: formData.origin.trim().toUpperCase(),
      destination: formData.destination.trim().toUpperCase(),
      flight_duration: Number(formData.flight_duration),
      congestion: Number(formData.congestion),
      aircraft_type: formData.aircraft_type.trim(),
    };

    setLoading(true);

    try {
      /*
       * Relative URL:
       *
       * Browser:
       *   POST http://localhost:8081/api/v1/predict/
       *
       * Frontend Nginx then proxies the request internally to:
       *   http://backend:5000/api/v1/predict/
       *
       * Do not use http://localhost:5000 here.
       */
      const response = await axios.post(
        '/api/v1/predict/',
        payload,
        {
          withCredentials: true,
          headers: {
            'Content-Type': 'application/json',
          },
          timeout: 120000,
        },
      );

      if (typeof onNewPrediction === 'function') {
        onNewPrediction(response.data);
      }
    } catch (error) {
      console.error(
        'Prediction request failed:',
        error.response?.data ?? error.message,
      );

      if (error.code === 'ECONNABORTED') {
        setSubmitError(
          'The prediction request timed out. Please try again.',
        );
        return;
      }

      if (!error.response) {
        setSubmitError(
          'The backend could not be reached. Check the Kubernetes services and Nginx proxy.',
        );
        return;
      }

      const backendMessage =
        error.response.data?.error ||
        error.response.data?.message ||
        error.response.data?.msg;

      setSubmitError(
        backendMessage ||
          `Prediction failed with status ${error.response.status}.`,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{
        opacity: 0,
        y: 20,
      }}
      animate={{
        opacity: 1,
        y: 0,
      }}
      className="glass-card p-8"
    >
      <div className="mb-8 flex items-center gap-3">
        <div className="rounded-lg bg-indigo-500/10 p-2">
          <Info className="h-5 w-5 text-indigo-400" />
        </div>

        <h2 className="text-2xl font-bold">
          New Estimation
        </h2>
      </div>

      {submitError && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />

          <span>{submitError}</span>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="space-y-6"
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <label
              htmlFor="airline"
              className="text-sm font-medium text-slate-400"
            >
              Airline
            </label>

            <input
              id="airline"
              type="text"
              required
              disabled={loading}
              autoComplete="organization"
              className="glass-input w-full"
              placeholder="e.g. American Airlines"
              value={formData.airline}
              onChange={(event) =>
                updateField('airline', event.target.value)
              }
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="aircraft-type"
              className="text-sm font-medium text-slate-400"
            >
              Aircraft Type
            </label>

            <input
              id="aircraft-type"
              type="text"
              required
              disabled={loading}
              className="glass-input w-full"
              placeholder="e.g. Boeing 737"
              value={formData.aircraft_type}
              onChange={(event) =>
                updateField(
                  'aircraft_type',
                  event.target.value,
                )
              }
            />
          </div>

          <AirportAutocomplete
            required
            disabled={loading}
            label="Origin (IATA)"
            placeholder="Search e.g. JFK or New York"
            value={formData.origin}
            onChange={(value) =>
              updateField('origin', value)
            }
          />

          <AirportAutocomplete
            required
            disabled={loading}
            label="Destination (IATA)"
            placeholder="Search e.g. LAX or Chicago"
            value={formData.destination}
            onChange={(value) =>
              updateField('destination', value)
            }
          />
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label
              htmlFor="congestion"
              className="text-sm font-medium text-slate-400"
            >
              Congestion Level
            </label>

            <span className="font-bold text-indigo-400">
              {formData.congestion}
            </span>
          </div>

          <input
            id="congestion"
            type="range"
            min="1"
            max="10"
            step="1"
            disabled={loading}
            className="w-full accent-indigo-500"
            value={formData.congestion}
            onChange={(event) =>
              updateField(
                'congestion',
                Number(event.target.value),
              )
            }
          />
        </div>

        <div className="space-y-2">
          <label
            htmlFor="flight-duration"
            className="text-sm font-medium text-slate-400"
          >
            Duration (Minutes)
          </label>

          <input
            id="flight-duration"
            type="number"
            min="1"
            step="1"
            required
            disabled={loading}
            inputMode="numeric"
            className="glass-input w-full"
            placeholder="e.g. 330"
            value={formData.flight_duration}
            onChange={(event) =>
              updateField(
                'flight_duration',
                event.target.value,
              )
            }
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-600 py-4 font-bold shadow-xl shadow-indigo-500/20 transition-all hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Send className="h-5 w-5" />
          )}

          {loading
            ? 'Analyzing Data...'
            : 'Generate Prediction'}
        </button>
      </form>
    </motion.div>
  );
}