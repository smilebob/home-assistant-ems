import React, { useState, useEffect } from 'react'
import { Save, CheckCircle2, AlertCircle, RefreshCw, Layers, ShieldCheck } from 'lucide-react'

export default function SettingsView() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await fetch('./api/config')
      if (res.ok) {
        const data = await res.json()
        setConfig(data)
      }
    } catch (e) {
      console.error('Failed to load config', e)
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (key, value) => {
    setConfig(prev => ({
      ...prev,
      [key]: value
    }))
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      const res = await fetch('./api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Configuration sauvegardée et appliquée avec succès !' })
      } else {
        setMessage({ type: 'error', text: 'Erreur lors de la sauvegarde de la configuration.' })
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Erreur réseau: ${err.message}` })
    } finally {
      setSaving(false)
      setTimeout(() => setMessage(null), 6000)
    }
  }

  if (loading || !config) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin mb-3 text-amber-400" />
        <p>Chargement des paramètres et entités...</p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-2xl border border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Layers className="w-5 h-5 text-amber-400" />
            Remapping des Entités Home Assistant & Paramètres
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Modifiez ici le nom des entités Home Assistant connectées à chaque composant. Les valeurs sont enregistrées dans <code>/data/options.json</code>.
          </p>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-semibold text-sm transition-all shadow-lg shadow-amber-500/20"
        >
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Sauvegarder & Appliquer
        </button>
      </div>

      {message && (
        <div className={`p-4 rounded-xl flex items-center gap-3 text-sm ${
          message.type === 'success' 
            ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300' 
            : 'bg-rose-500/10 border border-rose-500/30 text-rose-300'
        }`}>
          {message.type === 'success' ? <CheckCircle2 className="w-5 h-5 flex-shrink-0" /> : <AlertCircle className="w-5 h-5 flex-shrink-0" />}
          <span>{message.text}</span>
        </div>
      )}

      {/* Grid sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 1. Solaire & Batterie Felicity */}
        <div className="bg-slate-900/40 p-5 rounded-2xl border border-slate-800/80 space-y-4">
          <h3 className="text-sm font-semibold text-amber-400 flex items-center gap-2 border-b border-slate-800 pb-2">
            ☀️ Production Solaire & Batterie Résidentielle
          </h3>
          
          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Puissance Photovoltaïque (W)</label>
              <input
                type="text"
                value={config.pv_power_entity || ''}
                onChange={e => handleChange('pv_power_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Puissance Réseau Import/Export (W)</label>
              <input
                type="text"
                value={config.grid_power_entity || ''}
                onChange={e => handleChange('grid_power_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Consommation du Foyer (W)</label>
              <input
                type="text"
                value={config.house_load_entity || ''}
                onChange={e => handleChange('house_load_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1">SoC Batterie (%)</label>
                <input
                  type="text"
                  value={config.battery_soc_entity || ''}
                  onChange={e => handleChange('battery_soc_entity', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
              <div>
                <label className="block text-slate-300 font-medium mb-1">Puissance Batterie (W)</label>
                <input
                  type="text"
                  value={config.battery_power_entity || ''}
                  onChange={e => handleChange('battery_power_entity', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div>
                <label className="block text-slate-400 font-medium mb-1">Capacité Batterie (kWh)</label>
                <input
                  type="number"
                  step="0.5"
                  value={config.battery_capacity_kwh || 15}
                  onChange={e => handleChange('battery_capacity_kwh', parseFloat(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">SoC Min Réserve (%)</label>
                <input
                  type="number"
                  step="1"
                  value={config.battery_min_soc || 15}
                  onChange={e => handleChange('battery_min_soc', parseFloat(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
            </div>
          </div>
        </div>

        {/* 2. Pompe à Chaleur Mitsubishi Ecodan */}
        <div className="bg-slate-900/40 p-5 rounded-2xl border border-slate-800/80 space-y-4">
          <h3 className="text-sm font-semibold text-rose-400 flex items-center gap-2 border-b border-slate-800 pb-2">
            🔥 Pompe à Chaleur Ecodan (ECS & Chauffage)
          </h3>
          
          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Température Actuelle ECS (°C)</label>
              <input
                type="text"
                value={config.dhw_temp_entity || ''}
                onChange={e => handleChange('dhw_temp_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Thermostat Consigne ECS (climate)</label>
              <input
                type="text"
                value={config.dhw_target_entity || ''}
                onChange={e => handleChange('dhw_target_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Switch Forçage ECS (switch)</label>
              <input
                type="text"
                value={config.dhw_force_entity || ''}
                onChange={e => handleChange('dhw_force_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Température Zone 1 (°C)</label>
                <input
                  type="text"
                  value={config.z1_temp_entity || ''}
                  onChange={e => handleChange('z1_temp_entity', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
              <div>
                <label className="block text-slate-300 font-medium mb-1">Température Zone 2 (°C)</label>
                <input
                  type="text"
                  value={config.z2_temp_entity || ''}
                  onChange={e => handleChange('z2_temp_entity', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Sonde Température Extérieure (°C)</label>
              <input
                type="text"
                value={config.outdoor_temp_entity || ''}
                onChange={e => handleChange('outdoor_temp_entity', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>
          </div>
        </div>

        {/* 3. Mobilité Électrique (Tesla & Borne) */}
        <div className="bg-slate-900/40 p-5 rounded-2xl border border-slate-800/80 space-y-4">
          <h3 className="text-sm font-semibold text-sky-400 flex items-center gap-2 border-b border-slate-800 pb-2">
            🚗 Véhicule Électrique (Tesla Sally & Borne Tuya)
          </h3>
          
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Batterie Véhicule (%)</label>
                <input
                  type="text"
                  value={config.ev_soc_entity || ''}
                  onChange={e => handleChange('ev_soc_entity', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
              <div>
                <label className="block text-slate-300 font-medium mb-1">Câble Branché (binary_sensor)</label>
                <input
                  type="text"
                  value={config.ev_plugged_entity || ''}
                  onChange={e => handleChange('ev_plugged_entity', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Switch Charge Tesla (switch)</label>
              <input
                type="text"
                value={config.tesla_charge_switch || ''}
                onChange={e => handleChange('tesla_charge_switch', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Courant de Charge Tesla (number en Ampères)</label>
              <input
                type="text"
                value={config.tesla_current_number || ''}
                onChange={e => handleChange('tesla_current_number', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Interrupteur Borne Tuya (select/switch)</label>
              <input
                type="text"
                value={config.evse_power_switch || ''}
                onChange={e => handleChange('evse_power_switch', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Courant Borne Tuya (number en Ampères)</label>
              <input
                type="text"
                value={config.evse_current_number || ''}
                onChange={e => handleChange('evse_current_number', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>
          </div>
        </div>

        {/* 4. Solcast & Tarification */}
        <div className="bg-slate-900/40 p-5 rounded-2xl border border-slate-800/80 space-y-4">
          <h3 className="text-sm font-semibold text-emerald-400 flex items-center gap-2 border-b border-slate-800 pb-2">
            📊 Solcast & Paramètres Financiers
          </h3>
          
          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Prévision Solcast Puissance Instantanée (W)</label>
              <input
                type="text"
                value={config.solar_forecast_power_now || ''}
                onChange={e => handleChange('solar_forecast_power_now', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Prévision Solcast Reste Aujourd'hui (kWh)</label>
              <input
                type="text"
                value={config.solar_forecast_today_remaining || ''}
                onChange={e => handleChange('solar_forecast_today_remaining', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Prévision Solcast Demain (kWh)</label>
              <input
                type="text"
                value={config.solar_forecast_tomorrow || ''}
                onChange={e => handleChange('solar_forecast_tomorrow', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div>
                <label className="block text-slate-400 font-medium mb-1">Prix Import Réseau (€/kWh)</label>
                <input
                  type="number"
                  step="0.0001"
                  value={config.grid_import_price_fixed || 0.1689}
                  onChange={e => handleChange('grid_import_price_fixed', parseFloat(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
              <div>
                <label className="block text-slate-400 font-medium mb-1">Prix Export Rachat (€/kWh)</label>
                <input
                  type="number"
                  step="0.0001"
                  value={config.grid_export_price_fixed || 0.0400}
                  onChange={e => handleChange('grid_export_price_fixed', parseFloat(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-400 font-mono text-xs"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </form>
  )
}
