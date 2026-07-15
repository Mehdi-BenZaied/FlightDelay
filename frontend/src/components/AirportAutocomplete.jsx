import React, { useState, useRef, useEffect } from 'react';

const AIRPORTS = [
  { code: 'JFK', name: 'John F. Kennedy International', city: 'New York', country: 'USA' },
  { code: 'LAX', name: 'Los Angeles International', city: 'Los Angeles', country: 'USA' },
  { code: 'ORD', name: 'O\'Hare International', city: 'Chicago', country: 'USA' },
  { code: 'LHR', name: 'Heathrow Airport', city: 'London', country: 'UK' },
  { code: 'DXB', name: 'Dubai International', city: 'Dubai', country: 'UAE' },
  { code: 'DEL', name: 'Indira Gandhi International', city: 'Delhi', country: 'India' },
  { code: 'BOM', name: 'Chhatrapati Shivaji International', city: 'Mumbai', country: 'India' },
  { code: 'BLR', name: 'Kempegowda International', city: 'Bengaluru', country: 'India' },
  { code: 'HYD', name: 'Rajiv Gandhi International', city: 'Hyderabad', country: 'India' },
  { code: 'MAA', name: 'Chennai International', city: 'Chennai', country: 'India' },
  { code: 'CCU', name: 'Netaji Subhash Chandra Bose International', city: 'Kolkata', country: 'India' },
];

export default function AirportAutocomplete({ label, value, onChange, placeholder, required }) {
  const [query, setQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const wrapperRef = useRef(null);

  // Sync initial query state with standard IATA code value when value changes
  useEffect(() => {
    if (!isFocused) {
      setQuery(value || '');
    }
  }, [value, isFocused]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsFocused(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleInputChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    setIsFocused(true);
    // Bubble up the change on every keystroke
    onChange(val.toUpperCase().trim());
  };

  const handleSelect = (airport) => {
    onChange(airport.code);
    setQuery(airport.code);
    setIsFocused(false);
  };

  const handleFocus = () => {
    setIsFocused(true);
    // Show the actual value on focus so they can edit it
    setQuery(value || '');
  };

  const filteredAirports = AIRPORTS.filter((a) => {
    const searchTerm = query.toLowerCase().trim();
    if (!searchTerm) return true;
    return (
      a.code.toLowerCase().includes(searchTerm) ||
      a.name.toLowerCase().includes(searchTerm) ||
      a.city.toLowerCase().includes(searchTerm)
    );
  });

  const getDisplayValue = () => {
    if (isFocused) {
      return query;
    }
    const selected = AIRPORTS.find((a) => a.code === value);
    if (selected) {
      return `${selected.code} - ${selected.city} (${selected.name})`;
    }
    return value || query || '';
  };

  return (
    <div ref={wrapperRef} className="space-y-2 relative">
      <label className="text-sm font-medium text-slate-400 block">{label}</label>
      <input
        required={required}
        className="glass-input w-full uppercase"
        placeholder={placeholder}
        value={getDisplayValue()}
        onChange={handleInputChange}
        onFocus={handleFocus}
      />
      {isFocused && filteredAirports.length > 0 && (
        <ul className="absolute top-[84px] left-0 w-full bg-slate-900/95 backdrop-blur-xl border border-white/10 rounded-2xl max-h-56 overflow-y-auto z-50 p-2 shadow-2xl divide-y divide-white/5">
          {filteredAirports.map((airport) => (
            <li
              key={airport.code}
              onClick={() => handleSelect(airport)}
              className="px-4 py-2.5 hover:bg-indigo-600/20 text-slate-200 hover:text-white rounded-xl transition-all cursor-pointer text-xs flex justify-between items-center"
            >
              <div>
                <span className="font-bold text-sm text-indigo-400 block uppercase">{airport.code}</span>
                <span className="text-slate-400 font-semibold">{airport.city}, {airport.country}</span>
              </div>
              <span className="text-[10px] text-slate-500 italic truncate max-w-[150px]">{airport.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
