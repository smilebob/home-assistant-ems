import React, { useState, useEffect } from 'react'
import {
  Zap,
  Sun,
  Battery,
  Flame,
  Car,
  TrendingUp,
  Sliders,
  History,
  CheckCircle2,
  AlertTriangle,
  Info,
  RefreshCw,
  Power,
} from 'lucide-react'
import PowerFlow from './components/PowerFlow.jsx'
import SolcastMLChart from './components/SolcastMLChart.jsx'

export default function App() {
  const [activeTab, setActiveTab] = useState('overview')
  const [state, setState] = useState(null)
  const [history, setHistory] = useState([])
  const [decisions, setDecisions] = useState([])
  const [wsConnected, setWsConnected] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  // Determine WebSocket URL relative to current host / Ingress path
  const getWsUrl = () => {
    const loc = window.location
    const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:'
    // If running under Ingress, loc.pathname may be /api/hassio_ingress/...
    const path = loc.pathname.endsWith('/') ? loc.pathname.slice(0, -1) : loc.pathname
    return `${protocol}//${loc.host}${path}/ws`
  }

  // Poll HTTP state fallback & history
  const fetchHttpState = async () => {
    try {
      const res = await fetch('./api/state')
      if (res.ok) {
        const data = await res.json()
        setState(data)
      }
      const histRes = await fetch('./api/history?hours=24')
      if (histRes.ok) {
        const histData = await histRes.json()
        setHistory(histData)
      }
      const decRes = await fetch('./api/decisions?limit=30')
      if (decRes.ok) {
        const decData = await decRes.json()
        setDecisions(decData)
      }
    } catch (err) {
      console.error('Error fetching state:', err)
    }
  }

  // Establish WebSocket connection
  useEffect(() => {
    fetchHttpState()
    const wsUrl = getWsUrl()
    let ws = null
    let reconnectTimer = null

    const connectWs = () => {
      try {
        ws = new WebSocket(wsUrl)
        ws.onopen = () => {
          setWsConnected(true)
        }
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            setState(data)
          } catch (e) {
            console.error('WS parse error:', e)
          }
        }
        ws.onclose = () => {
          setWsConnected(false)
          reconnectTimer = setTimeout(connectWs, 4000)
        }
        ws.onerror = () => {
          ws.close()
        }
      } catch (err) {
        setWsConnected(false)
        reconnectTimer = setTimeout(connectWs, 4000)
      }
    }

    connectWs()

    const interval = setInterval(fetchHttpState, 15000)

    return () => {
      if (ws) ws.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      clearInterval(interval)
    }
  }, [])

  const handleAction = async (action, value) => {
    setActionLoading(true)
    try {
      const res = await fetch('./api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, value }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.state) setState(data.state)
      }
    } catch (err) {
      console.error('Action failed:', err)
    } finally {
      setActionLoading(false)
    }
  }

  const savings = state?.cumulative_savings_eur != null ? Number(state.cumulative_savings_eur).toFixed(2) : '0.00'
  const decisionReason = state?.decision_reason || "Initialisation de l'arbitrage énergétique..."
  const valves = state?.valve_recommendations || []

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-50 px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 flex items-center justify-center shadow-lg shadow-amber-500/20 text-slate-950 font-black text-xl">
            ⚡
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-100 flex items-center gap-2">
              Smart Residential EMS
              <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono font-medium border border-amber-500/30">
                v2.0 (Docker & Add-on)
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              Pilotage Solaire • Batterie Felicity • PAC Ecodan • Tesla Fleet
            </p>
          </div>
        </div>

        {/* Global Badges */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700 text-xs">
            <span className={`w-2.5 h-2.5 rounded-full ${wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
            <span className="text-slate-300">{wsConnected ? 'En direct' : 'Reconnexion...'}</span>
          </div>

          <div className="px-3.5 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs flex items-center gap-1.5">
            <span className="text-emerald-400 font-medium">Économies cumulées :</span>
            <strong className="text-emerald-300 font-mono text-sm">{savings} €</strong>
          </div>
        </div>
      </header>

      {/* Tabs Navigation */}
      <nav className="border-b border-slate-800/80 bg-slate-900/30 px-6 flex space-x-1">
        {[
          { id: 'overview', label: 'Pilotage & Flux', icon: Zap },
          { id: 'ml', label: 'Solcast & Machine Learning', icon: TrendingUp },
          { id: 'ecodan-ev', label: 'PAC Ecodan & Mobilité VE', icon: Flame },
          { id: 'decisions', label: 'Timeline des Décisions', icon: History },
        ].map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
                isActive
                  ? 'border-amber-400 text-amber-400 bg-amber-400/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* Decision Banner */}
        <div className="bg-slate-900/80 border border-amber-500/30 rounded-xl p-4 flex items-start gap-3 shadow-lg shadow-amber-500/5">
          <Info className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-xs uppercase tracking-wider font-bold text-amber-400">
              Explication de la décision EMS
            </div>
            <p className="text-sm text-slate-200 mt-0.5 leading-relaxed font-medium">
              {decisionReason}
            </p>
          </div>
          <button
            onClick={fetchHttpState}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
            title="Rafraîchir les données"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Tab 1: Overview & Power Flow */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <PowerFlow state={state} />
            </div>

            {/* Quick Overrides Column */}
            <div className="space-y-6">
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2 mb-4">
                  <Sliders className="w-5 h-5 text-sky-400" /> Commandes & Dérogations
                </h3>

                <div className="space-y-4">
                  {/* Auto Mode */}
                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                    <div>
                      <div className="text-sm font-medium text-slate-200">Pilote Automatique</div>
                      <div className="text-xs text-slate-400">Arbitrage solaire intelligent</div>
                    </div>
                    <button
                      disabled={actionLoading}
                      onClick={() => handleAction('auto_mode', !(state?.auto_mode ?? true))}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                        state?.auto_mode ?? true
                          ? 'bg-emerald-500 text-slate-950 hover:bg-emerald-400'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      {state?.auto_mode ?? true ? 'ACTIF' : 'MANUEL'}
                    </button>
                  </div>

                  {/* DHW Force Boost 55°C */}
                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                    <div>
                      <div className="text-sm font-medium text-slate-200">Boost ECS (55°C)</div>
                      <div className="text-xs text-slate-400">Forcer ballon d'eau chaude</div>
                    </div>
                    <button
                      disabled={actionLoading}
                      onClick={() => handleAction('force_dhw_boost', !state?.force_dhw_boost)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                        state?.force_dhw_boost
                          ? 'bg-amber-500 text-slate-950 hover:bg-amber-400'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      {state?.force_dhw_boost ? 'ON' : 'OFF'}
                    </button>
                  </div>

                  {/* Tesla Force Max Charge */}
                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                    <div>
                      <div className="text-sm font-medium text-slate-200">Charge Rapide Tesla (16A)</div>
                      <div className="text-xs text-slate-400">Ignorer le surplus solaire</div>
                    </div>
                    <button
                      disabled={actionLoading}
                      onClick={() => handleAction('force_tesla_charge', !state?.force_tesla_charge)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                        state?.force_tesla_charge
                          ? 'bg-pink-500 text-slate-950 hover:bg-pink-400'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      {state?.force_tesla_charge ? 'ON' : 'OFF'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Status Summary Card */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Mode Tarifaire</span>
                  <span className="font-semibold text-slate-200">Tarif Fixe (16.89 c€ / 4.00 c€)</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">SOC Cible Dynamique Batterie</span>
                  <span className="font-semibold text-emerald-400 font-mono">
                    {state?.dynamic_battery_target_soc || 60}%
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Seuil Réserve Thermique P4</span>
                  <span className="font-semibold text-slate-200 font-mono">
                    {state?.battery_thermal_soc_threshold || 95}%
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Fenêtre Solaire ECS</span>
                  <span className="font-semibold text-amber-400">11h00 — 16h00 (Verrouillage strict)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Machine Learning & Solcast */}
        {activeTab === 'ml' && (
          <div className="space-y-6">
            <SolcastMLChart state={state} history={history} />

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <span className="text-xs text-slate-400">Solaire Restant Aujourd'hui</span>
                <div className="text-2xl font-bold text-amber-400 font-mono mt-1">
                  {state?.solar_today_remaining_kwh || '--'} kWh
                </div>
                <span className="text-xs text-slate-500">
                  Brut Solcast : {state?.raw_solar_today_remaining_kwh || '--'} kWh
                </span>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <span className="text-xs text-slate-400">Prévision Solaire Demain</span>
                <div className="text-2xl font-bold text-amber-400 font-mono mt-1">
                  {state?.solar_tomorrow_kwh || '--'} kWh
                </div>
                <span className="text-xs text-slate-500">
                  Brut Solcast : {state?.raw_solar_tomorrow_kwh || '--'} kWh
                </span>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <span className="text-xs text-slate-400">Ratio Auto-Calibration Solcast</span>
                <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">
                  {state?.solar_calibration_ratio || '1.000'}
                </div>
                <span className="text-xs text-slate-500">
                  Sur {state?.solar_calibration_samples || 0} heures de jour comparées
                </span>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <span className="text-xs text-slate-400">Échantillons ML Consommation</span>
                <div className="text-2xl font-bold text-sky-400 font-mono mt-1">
                  {state?.ml_samples || 268}
                </div>
                <span className="text-xs text-slate-500">
                  Précision globale : {state?.ml_accuracy_pct || 70}%
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: PAC Ecodan & EV */}
        {activeTab === 'ecodan-ev' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Ecodan Card */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
              <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <Flame className="w-5 h-5 text-orange-400" /> PAC Mitsubishi Ecodan
              </h3>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-xs text-slate-400">Ballon ECS Actuel</span>
                  <div className="text-2xl font-bold text-orange-400 font-mono mt-1">
                    {state?.dhw_temp || 50.0}°C
                  </div>
                  <span className="text-xs text-slate-500">Consigne : {state?.dhw_target || 50.0}°C</span>
                </div>

                <div className="p-4 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-xs text-slate-400">Zone 2 Plancher Chauffant</span>
                  <div className="text-2xl font-bold text-slate-200 font-mono mt-1">
                    {state?.z2_temp || 20.5}°C
                  </div>
                  <span className="text-xs text-slate-500">Consigne : {state?.z2_target || 20.0}°C</span>
                </div>
              </div>

              {/* Radiator Valves Recommendations */}
              <div className="mt-4 pt-4 border-t border-slate-800">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Équilibrage Vannes Zone 1 : {state?.valve_summary || 'Toutes équilibrées'}
                </div>
                <div className="space-y-2">
                  {valves.map((v, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2 rounded-lg bg-slate-800/40 text-xs border border-slate-800"
                    >
                      <span className="text-slate-300 font-medium">{v.room}</span>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-slate-400">{v.temp}°C</span>
                        <span
                          className={`px-2 py-0.5 rounded font-medium ${
                            v.direction === 'ok'
                              ? 'bg-emerald-500/20 text-emerald-300'
                              : v.direction.includes('close')
                              ? 'bg-amber-500/20 text-amber-300'
                              : 'bg-sky-500/20 text-sky-300'
                          }`}
                        >
                          {v.action}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* EV Card */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
              <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <Car className="w-5 h-5 text-pink-400" /> Mobilité Véhicule Électrique (Sally & Borne)
              </h3>

              <div className="p-4 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-400">Statut Séquençage Véhicule</span>
                  <div className="text-base font-bold text-slate-200 mt-0.5">
                    {state?.ev_sequencing_status || 'Veille'}
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-xs text-slate-400">Batterie Sally</span>
                  <div className="text-xl font-bold text-pink-400 font-mono">
                    {state?.ev_soc || 69}%
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-800/60 border border-slate-700/60 space-y-2">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Intensité Allouée au VE</span>
                  <span className="font-bold text-pink-400 font-mono">{state?.ev_target_amps || 0} A</span>
                </div>
                <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-pink-500 h-full transition-all duration-500"
                    style={{ width: `${((state?.ev_target_amps || 0) / 16) * 100}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>0A (Veille)</span>
                  <span>6A (Min)</span>
                  <span>10A</span>
                  <span>16A (Max)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Decisions Timeline */}
        {activeTab === 'decisions' && (
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
              <History className="w-5 h-5 text-amber-400" /> Historique Chronologique des Décisions
            </h3>

            <div className="divide-y divide-slate-800">
              {decisions.length > 0 ? (
                decisions.map((d, idx) => (
                  <div key={idx} className="py-3 flex items-start gap-4 text-xs">
                    <span className="font-mono text-slate-400 shrink-0 mt-0.5">{d.time}</span>
                    <span className="px-2 py-0.5 rounded font-mono font-bold bg-slate-800 text-amber-400 shrink-0">
                      {d.priority}
                    </span>
                    <p className="text-slate-300 flex-1 leading-relaxed">{d.reason}</p>
                  </div>
                ))
              ) : (
                <div className="py-8 text-center text-slate-500 text-sm">
                  Aucune transition de priorité enregistrée récemment.
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 px-6 py-4 text-center text-xs text-slate-500">
        Smart Residential EMS Container • Exécution asynchrone découplée • DuckDB & Apache ECharts
      </footer>
    </div>
  )
}
