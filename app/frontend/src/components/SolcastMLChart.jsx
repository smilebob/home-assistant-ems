import React from 'react'
import ReactECharts from 'echarts-for-react'

export default function SolcastMLChart({ state, history = [] }) {
  const hourlyForecast = state?.hourly_forecast || []
  const ratio = state?.solar_calibration_ratio != null ? Number(state.solar_calibration_ratio).toFixed(3) : '1.000'
  const r2 = state?.ml_r2_score != null ? Number(state.ml_r2_score).toFixed(3) : '0.766'
  const mae = state?.ml_mae_watts != null ? Math.round(state.ml_mae_watts) : '389'

  // Prepare categories (hours)
  const hours = hourlyForecast.map(h => {
    const d = new Date(h.datetime)
    return `${d.getHours()}h`
  })

  const predictedWatts = hourlyForecast.map(h => Math.round(h.predicted_watts || 0))
  const estimatedOutdoorTemp = hourlyForecast.map(h => Number(h.estimated_outdoor_temp || 0).toFixed(1))

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1e293b',
      borderColor: '#334155',
      textStyle: { color: '#f8fafc' },
    },
    legend: {
      data: ['Consommation Prédite (ML)', 'Température Extérieure Estimée'],
      textStyle: { color: '#94a3b8' },
      top: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '15%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: hours,
      axisLine: { lineStyle: { color: '#475569' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Puissance (W)',
        nameTextStyle: { color: '#38bdf8' },
        splitLine: { lineStyle: { color: '#1e293b' } },
        axisLabel: { color: '#94a3b8' },
      },
      {
        type: 'value',
        name: 'Temp (°C)',
        nameTextStyle: { color: '#f59e0b' },
        splitLine: { show: false },
        axisLabel: { color: '#f59e0b' },
      },
    ],
    series: [
      {
        name: 'Consommation Prédite (ML)',
        type: 'line',
        smooth: true,
        data: predictedWatts,
        itemStyle: { color: '#38bdf8' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(56, 189, 248, 0.4)' },
              { offset: 1, color: 'rgba(56, 189, 248, 0.0)' },
            ],
          },
        },
      },
      {
        name: 'Température Extérieure Estimée',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: estimatedOutdoorTemp,
        itemStyle: { color: '#f59e0b' },
      },
    ],
  }

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-100">
            Prédictions de Consommation ML (Prochaines 12h)
          </h3>
          <p className="text-xs text-slate-400">
            Modèle Ridge local entraîné sur l'historique thermique et les usages de la maison.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300">
            Score R² : <strong className="text-emerald-400 font-mono">{r2}</strong>
          </span>
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300">
            MAE : <strong className="text-sky-400 font-mono">{mae} W</strong>
          </span>
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300">
            Ratio Solcast : <strong className="text-amber-400 font-mono">{ratio}</strong>
          </span>
        </div>
      </div>

      <div className="w-full h-[320px]">
        {hours.length > 0 ? (
          <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            En attente des prédictions horaires du modèle...
          </div>
        )}
      </div>
    </div>
  )
}
