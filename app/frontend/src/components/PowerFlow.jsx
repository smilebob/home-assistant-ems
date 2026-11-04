import React from 'react'
import { Sun, Battery, Home, Zap, Flame, Car } from 'lucide-react'

export default function PowerFlow({ state }) {
  const pvPower = Math.round(state?.pv_power_w || 0)
  const gridPower = Math.round(state?.grid_power_w || 0)
  const houseLoad = Math.round(state?.house_load_w || 0)
  const battSoc = Math.round(state?.battery_soc || 0)
  const battPower = Math.round(state?.battery_power_w || 0)
  const dhwTemp = state?.dhw_temp != null ? Number(state.dhw_temp).toFixed(1) : '--'
  const evAmps = state?.ev_target_amps || 0
  const evSoc = state?.ev_soc != null ? Math.round(state.ev_soc) : '--'
  const evCharging = state?.ev_charging

  // Determine flow states
  const isSolarGenerating = pvPower > 40
  const isGridImporting = gridPower > 30
  const isGridExporting = gridPower < -30
  const isBatteryCharging = battPower > 50
  const isBatteryDischarging = battPower < -50
  const isDhwHeating = state?.dhw_heating_recommended

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          <Zap className="w-5 h-5 text-amber-400" /> Flux d'Énergie en Temps Réel
        </h3>
        <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
          Actif : <strong className="text-amber-400 font-mono">{state?.active_priority || 'idle'}</strong>
        </span>
      </div>

      <div className="relative w-full aspect-[16/10] max-h-[460px] flex items-center justify-center">
        {/* SVG animated flow paths */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 800 500">
          <defs>
            <linearGradient id="pvGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#eab308" />
              <stop offset="100%" stopColor="#f59e0b" />
            </linearGradient>
            <linearGradient id="battGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#22c55e" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>
            <linearGradient id="gridGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#38bdf8" />
              <stop offset="100%" stopColor="#6366f1" />
            </linearGradient>
          </defs>

          {/* Lines */}
          {/* PV (400, 70) to House (400, 250) */}
          <line
            x1="400" y1="110" x2="400" y2="210"
            stroke={isSolarGenerating ? "#eab308" : "#334155"}
            strokeWidth="4"
            strokeDasharray={isSolarGenerating ? "6 6" : "0"}
            className={isSolarGenerating ? "flow-forward" : ""}
          />

          {/* Grid (160, 250) to House (360, 250) */}
          <line
            x1="180" y1="250" x2="350" y2="250"
            stroke={isGridImporting ? "#38bdf8" : isGridExporting ? "#22c55e" : "#334155"}
            strokeWidth="4"
            strokeDasharray={isGridImporting || isGridExporting ? "6 6" : "0"}
            className={isGridImporting ? "flow-forward" : isGridExporting ? "flow-backward" : ""}
          />

          {/* House (400, 290) to Battery (250, 410) */}
          <line
            x1="365" y1="285" x2="250" y2="395"
            stroke={isBatteryCharging || isBatteryDischarging ? "#22c55e" : "#334155"}
            strokeWidth="4"
            strokeDasharray={isBatteryCharging || isBatteryDischarging ? "6 6" : "0"}
            className={isBatteryCharging ? "flow-forward" : isBatteryDischarging ? "flow-backward" : ""}
          />

          {/* House (440, 285) to PAC Ecodan (430, 400) */}
          <line
            x1="420" y1="290" x2="430" y2="390"
            stroke={isDhwHeating ? "#f97316" : "#334155"}
            strokeWidth="4"
            strokeDasharray={isDhwHeating ? "6 6" : "0"}
            className={isDhwHeating ? "flow-forward" : ""}
          />

          {/* House (450, 250) to Tesla Sally (640, 250) */}
          <line
            x1="450" y1="250" x2="620" y2="250"
            stroke={evCharging ? "#ec4899" : "#334155"}
            strokeWidth="4"
            strokeDasharray={evCharging ? "6 6" : "0"}
            className={evCharging ? "flow-forward" : ""}
          />
        </svg>

        {/* Node 1: Solaire PV (Top Center) */}
        <div className="absolute top-[3%] left-1/2 -translate-x-1/2 flex flex-col items-center">
          <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border-2 border-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
            <Sun className="w-8 h-8 text-amber-400 animate-pulse" />
          </div>
          <span className="text-xs font-semibold text-slate-300 mt-1">Solaire PV</span>
          <span className="text-sm font-bold text-amber-400 font-mono">{pvPower} W</span>
        </div>

        {/* Node 2: Réseau Enedis (Center Left) */}
        <div className="absolute top-1/2 left-[5%] -translate-y-1/2 flex flex-col items-center">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 shadow-lg ${
            isGridImporting ? 'bg-sky-500/10 border-sky-400 shadow-sky-500/20' : 'bg-slate-800 border-slate-700'
          }`}>
            <Zap className={`w-8 h-8 ${isGridImporting ? 'text-sky-400' : 'text-slate-400'}`} />
          </div>
          <span className="text-xs font-semibold text-slate-300 mt-1">Réseau Enedis</span>
          <span className={`text-sm font-bold font-mono ${gridPower > 0 ? 'text-sky-400' : gridPower < 0 ? 'text-emerald-400' : 'text-slate-400'}`}>
            {gridPower > 0 ? `+${gridPower} W` : `${gridPower} W`}
          </span>
        </div>

        {/* Node 3: Maison (Center) */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center z-10">
          <div className="w-20 h-20 rounded-3xl bg-slate-800 border-2 border-slate-600 flex items-center justify-center shadow-2xl shadow-slate-900">
            <Home className="w-10 h-10 text-slate-200" />
          </div>
          <span className="text-xs font-semibold text-slate-300 mt-1">Maison (Talon)</span>
          <span className="text-base font-bold text-slate-100 font-mono">{houseLoad} W</span>
        </div>

        {/* Node 4: Tesla Sally (Center Right) */}
        <div className="absolute top-1/2 right-[5%] -translate-y-1/2 flex flex-col items-center">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 shadow-lg ${
            evCharging ? 'bg-pink-500/10 border-pink-500 shadow-pink-500/20' : 'bg-slate-800 border-slate-700'
          }`}>
            <Car className={`w-8 h-8 ${evCharging ? 'text-pink-400' : 'text-slate-400'}`} />
          </div>
          <span className="text-xs font-semibold text-slate-300 mt-1">Tesla Sally</span>
          <span className="text-xs font-bold text-slate-400 font-mono">
            {evSoc}% • {evAmps > 0 ? `${evAmps} A` : 'Veille'}
          </span>
        </div>

        {/* Node 5: Batterie Felicity (Bottom Left) */}
        <div className="absolute bottom-[4%] left-[22%] flex flex-col items-center">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 shadow-lg ${
            battSoc > 20 ? 'bg-emerald-500/10 border-emerald-500 shadow-emerald-500/20' : 'bg-slate-800 border-slate-700'
          }`}>
            <Battery className="w-8 h-8 text-emerald-400" />
          </div>
          <span className="text-xs font-semibold text-slate-300 mt-1">Felicity (15 kWh)</span>
          <span className="text-sm font-bold text-emerald-400 font-mono">
            {battSoc}% • {battPower > 0 ? `+${battPower}W` : `${battPower}W`}
          </span>
        </div>

        {/* Node 6: PAC Ecodan (Bottom Right) */}
        <div className="absolute bottom-[4%] right-[28%] flex flex-col items-center">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 shadow-lg ${
            isDhwHeating ? 'bg-orange-500/10 border-orange-500 shadow-orange-500/20' : 'bg-slate-800 border-slate-700'
          }`}>
            <Flame className={`w-8 h-8 ${isDhwHeating ? 'text-orange-400 animate-bounce' : 'text-slate-400'}`} />
          </div>
          <span className="text-xs font-semibold text-slate-300 mt-1">PAC Ecodan (ECS)</span>
          <span className="text-sm font-bold text-orange-400 font-mono">
            {dhwTemp}°C {isDhwHeating && '• Chauffe'}
          </span>
        </div>
      </div>
    </div>
  )
}
