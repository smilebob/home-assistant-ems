/**
 * Smart Residential EMS - Custom Lovelace Card (ems-card.js) v1.1.0
 * Displays live PV/Battery/Grid/Ecodan/Tesla energy flows, 4-Priority state,
 * Explainable EMS Decision Banner, Strict EV Sequencing Status,
 * Solcast Brut vs EMS Auto-Calibrated ML Forecasts (D+0/D+1/D+2 + Instant W),
 * Consumption ML Accuracy (%, MAE W, R²), Thermostatic Valve Balancing Advice,
 * and one-click override switches.
 */

class SmartResidentialEMSCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: config.title || "Smart Residential EMS",
      entity: config.entity || "sensor.smart_residential_ems_ems_active_priority_state",
      auto_switch: config.auto_switch || "switch.smart_residential_ems_ems_autonomous_optimization",
      dhw_switch: config.dhw_switch || "switch.smart_residential_ems_ems_force_ecodan_dhw_boost_55degc",
      tesla_switch: config.tesla_switch || "switch.smart_residential_ems_ems_force_tesla_max_charge",
      thermal_switch: config.thermal_switch || "switch.smart_residential_ems_ems_allow_zone_2_underfloor_thermal_storage",
      ...config,
    };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _toggleEntity(entityId) {
    if (!this._hass || !entityId) return;
    this._hass.callService("homeassistant", "toggle", { entity_id: entityId });
  }

  _retrainML() {
    if (!this._hass) return;
    this._hass.callService("ems", "retrain_ml_model", {});
  }

  _formatPriorityLabel(state) {
    const labels = {
      idle: "Veille / Autoconsommation Standard",
      priority_1_comfort_dhw: "Priorité 1 : Confort & Chauffe ECS Solaire",
      priority_2_battery: "Priorité 2 : Charge Batterie 15 kWh (Autonomie Nuit)",
      priority_3_tesla: "Priorité 3 : Charge Solaire Tesla (Modulation Douce)",
      priority_4_thermal_boost: "Priorité 4 : Stockage Thermique (Plancher Salon + ECS 55°C)",
      priority_dynamic_grid_charge: "Opportunité Tarif Bas : Charge Réseau Forcée",
    };
    return labels[state] || state || "Initialisation...";
  }

  _formatSeqLabel(status) {
    const map = {
      synchronized: "Synchronisé (Véhicule ✓ → Borne ✓)",
      vehicle_confirmed_borne_synced: "Confirmé Véhicule ✓ → Borne appliquée ✓",
      vehicle_timeout_fallback: "Timeout confirmation véhicule (15s) → Borne pilotée",
      awaiting_vehicle_confirmation: "Attente confirmation consigne véhicule...",
      idle: "Repos",
    };
    return map[status] || status || "Prêt";
  }

  _render() {
    if (!this._hass || !this.shadowRoot) return;

    const mainState = this._hass.states[this._config.entity];
    const attrs = mainState ? mainState.attributes : {};
    const priorityState = mainState ? mainState.state : "idle";

    const decisionReason = attrs.decision_reason || "Analyse des flux énergétiques en cours...";
    const pvW = attrs.pv_power_w ?? 0;
    const gridW = attrs.grid_power_w ?? 0;
    const loadW = attrs.house_load_w ?? 0;
    const surplusW = attrs.smoothed_surplus_w ?? 0;
    const battSoc = attrs.battery_soc ?? 0;
    const battTargetSoc = attrs.dynamic_battery_target_soc ?? 80;
    const battThermalSoc = attrs.battery_thermal_soc_threshold ?? 95;
    const dhwTemp = attrs.dhw_temp ?? "--";
    const dhwTarget = attrs.dhw_target ?? 48;
    const z1Temp = attrs.z1_temp ?? "--";
    const z2Temp = attrs.z2_temp ?? "--";
    const z2Target = attrs.z2_target ?? "--";
    const evPlugged = attrs.ev_plugged ?? false;
    const evSoc = attrs.ev_soc ?? "--";
    const evCharging = attrs.ev_charging ?? false;
    const evAmps = attrs.ev_target_amps ?? 0;
    const evSeqStatus = attrs.ev_sequencing_status || "idle";

    // Raw vs Calibrated Solar
    const rawSolPowerW = attrs.raw_solar_forecast_power_w ?? 0;
    const calSolPowerW = attrs.calibrated_solar_power_w ?? 0;
    const solRatioPct = attrs.solar_calibration_ratio ? Math.round(attrs.solar_calibration_ratio * 100) : 100;
    const rawSolToday = attrs.raw_solar_today_remaining_kwh ?? attrs.solar_today_remaining_kwh ?? 0;
    const calSolToday = attrs.calibrated_solar_today_remaining_kwh ?? attrs.solar_today_remaining_kwh ?? 0;
    const rawSolTomorrow = attrs.raw_solar_tomorrow_kwh ?? attrs.solar_tomorrow_kwh ?? 0;
    const calSolTomorrow = attrs.calibrated_solar_tomorrow_kwh ?? attrs.solar_tomorrow_kwh ?? 0;
    const calSolDayAfter = attrs.calibrated_solar_day_after_kwh ?? attrs.solar_day_after_kwh ?? 0;

    // ML Metrics
    const pred24h = attrs.predicted_24h_kwh ?? 0;
    const mlMae = attrs.ml_mae_watts ?? "--";
    const mlAcc = attrs.ml_accuracy_pct ?? "--";
    const mlR2 = attrs.ml_r2_score ?? "--";

    // Tariff
    const importPrice = attrs.import_price_eur ?? 0.1689;
    const exportPrice = attrs.export_price_eur ?? 0.04;

    // Thermostatic Valves
    const valves = Array.isArray(attrs.valve_recommendations) ? attrs.valve_recommendations : [];
    const valveSummary = attrs.valve_summary || "Aucun capteur de pièce annexe configuré";

    const isSwitchOn = (ent) => this._hass.states[ent]?.state === "on";

    const valvesHtml = valves.length > 0
      ? `<div class="valve-list">
          ${valves.map((v) => {
            const dir = v.direction || v.status || "ok";
            const cls = (dir.startsWith("close") || dir === "too_hot") ? "hot" : (dir.startsWith("open") || dir === "too_cold") ? "cold" : "ok";
            const deltaVal = v.delta ?? v.delta_c ?? 0;
            const tempVal = v.temp ?? v.temp_c ?? "--";
            const refVal = v.reference_temp ?? v.target_c ?? "--";
            const sign = deltaVal > 0 ? `+${deltaVal}` : `${deltaVal}`;
            return `<div class="valve-row">
              <div>
                <span class="valve-room">${v.room}</span>
                <span class="valve-temp">${tempVal} °C (réf. ${refVal} °C, écart ${sign} °C)</span>
              </div>
              <span class="valve-badge ${cls}">${v.action}</span>
            </div>`;
          }).join("")}
        </div>`
      : `<div class="metric-sub" style="padding: 6px 0;">${valveSummary}</div>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        ha-card {
          padding: 18px;
          background: var(--ha-card-background, var(--card-background-color, #1e1e2e));
          color: var(--primary-text-color, #fff);
          border-radius: 16px;
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 12px;
        }
        .title {
          font-size: 1.25rem;
          font-weight: 700;
        }
        .badge {
          padding: 5px 12px;
          border-radius: 20px;
          font-size: 0.8rem;
          font-weight: 600;
          background: rgba(16, 185, 129, 0.18);
          color: #10b981;
          border: 1px solid rgba(16, 185, 129, 0.4);
        }
        .decision-banner {
          background: rgba(59, 130, 246, 0.12);
          border-left: 4px solid #3b82f6;
          border-radius: 8px;
          padding: 10px 12px;
          margin-bottom: 14px;
          font-size: 0.82rem;
          line-height: 1.4;
        }
        .decision-banner strong {
          color: #60a5fa;
          display: block;
          margin-bottom: 2px;
          font-size: 0.76rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .grid-4 {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
          gap: 10px;
          margin-bottom: 14px;
        }
        .metric-box {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 12px;
        }
        .metric-label {
          font-size: 0.75rem;
          opacity: 0.72;
          margin-bottom: 4px;
        }
        .metric-val {
          font-size: 1.18rem;
          font-weight: 700;
        }
        .metric-sub {
          font-size: 0.72rem;
          opacity: 0.68;
          margin-top: 3px;
        }
        .section-title {
          font-size: 0.82rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          opacity: 0.75;
          margin: 14px 0 8px 0;
        }
        .valve-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 12px;
        }
        .valve-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.07);
          border-radius: 10px;
          padding: 8px 12px;
          font-size: 0.8rem;
        }
        .valve-room {
          font-weight: 600;
          margin-right: 8px;
        }
        .valve-temp {
          opacity: 0.7;
          font-size: 0.75rem;
        }
        .valve-badge {
          padding: 3px 9px;
          border-radius: 12px;
          font-size: 0.74rem;
          font-weight: 600;
        }
        .valve-badge.ok {
          background: rgba(16, 185, 129, 0.16);
          color: #34d399;
        }
        .valve-badge.hot {
          background: rgba(245, 158, 11, 0.18);
          color: #fbbf24;
        }
        .valve-badge.cold {
          background: rgba(59, 130, 246, 0.18);
          color: #60a5fa;
        }
        .controls {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }
        button.ctrl-btn {
          cursor: pointer;
          border: 1px solid rgba(255,255,255,0.15);
          background: rgba(255,255,255,0.06);
          color: inherit;
          padding: 8px 12px;
          border-radius: 10px;
          font-size: 0.8rem;
          font-weight: 600;
          transition: all 0.2s ease;
        }
        button.ctrl-btn.active {
          background: rgba(59, 130, 246, 0.28);
          border-color: #3b82f6;
          color: #60a5fa;
        }
        button.ctrl-btn:hover {
          background: rgba(255,255,255,0.12);
        }
      </style>
      <ha-card>
        <div class="header">
          <div class="title">${this._config.title}</div>
          <div class="badge">${this._formatPriorityLabel(priorityState)}</div>
        </div>

        <div class="decision-banner">
          <strong>Décision & Explication EMS en Temps Réel</strong>
          ${decisionReason}
        </div>

        <div class="section-title">Flux Énergétiques & Stockage Felicity (7 kWc / 15 kWh)</div>
        <div class="grid-4">
          <div class="metric-box">
            <div class="metric-label">Production Solaire PV</div>
            <div class="metric-val">${pvW} W</div>
            <div class="metric-sub">Surplus lissé : ${surplusW} W</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Batterie Felicity 15 kWh</div>
            <div class="metric-val">${battSoc} %</div>
            <div class="metric-sub">Seuil EV : ${battTargetSoc}% | Inertie : ${battThermalSoc}%</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Consommation Maison</div>
            <div class="metric-val">${loadW} W</div>
            <div class="metric-sub">Réseau : ${gridW} W</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Tarif Actif</div>
            <div class="metric-val">${(importPrice * 100).toFixed(2)} c€</div>
            <div class="metric-sub">Revente : ${(exportPrice * 100).toFixed(2)} c€/kWh</div>
          </div>
        </div>

        <div class="section-title">PAC Mitsubishi Ecodan Bi-Zone & Mobilité Tesla Fleet + Borne Tuya</div>
        <div class="grid-4">
          <div class="metric-box">
            <div class="metric-label">Eau Chaude Sanitaire (ECS)</div>
            <div class="metric-val">${dhwTemp} °C</div>
            <div class="metric-sub">Consigne : ${dhwTarget} °C</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Zone 1 (Chambres / Éléonore)</div>
            <div class="metric-val">${z1Temp} °C</div>
            <div class="metric-sub">Loi d'eau Ecodan</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Zone 2 (Salon Plancher)</div>
            <div class="metric-val">${z2Temp} °C</div>
            <div class="metric-sub">Cible : ${z2Target} °C (Inertie)</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Sally & Borne (${evPlugged ? "Branchée" : "Débranchée"})</div>
            <div class="metric-val">${evSoc} % ${evCharging ? `⚡ ${evAmps}A` : ""}</div>
            <div class="metric-sub">${this._formatSeqLabel(evSeqStatus)}</div>
          </div>
        </div>

        <div class="section-title">Étage d'Auto-Correction Solaire ML (Solcast Brut vs Calibré Installation) & Conso</div>
        <div class="grid-4">
          <div class="metric-box">
            <div class="metric-label">Puissance Solaire Prédite</div>
            <div class="metric-val">${calSolPowerW} W</div>
            <div class="metric-sub">Solcast brut : ${rawSolPowerW} W (Ratio ${solRatioPct}%)</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Reste Aujourd'hui J+0 Calibré</div>
            <div class="metric-val">${calSolToday} kWh</div>
            <div class="metric-sub">Solcast brut : ${rawSolToday} kWh</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Demain J+1 Calibré</div>
            <div class="metric-val">${calSolTomorrow} kWh</div>
            <div class="metric-sub">Brut : ${rawSolTomorrow} kWh | J+2 : ${calSolDayAfter} kWh</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Conso Prédite ML (24h)</div>
            <div class="metric-val">${pred24h} kWh</div>
            <div class="metric-sub">Fiabilité : ${mlAcc}% (±${mlMae} W, R²=${mlR2})</div>
          </div>
        </div>

        <div class="section-title">Conseiller d'Équilibrage des Vannes Thermostatiques (Chambres Zone 1)</div>
        ${valvesHtml}

        <div class="section-title">Pilotage & Forçages Rapides</div>
        <div class="controls">
          <button class="ctrl-btn ${isSwitchOn(this._config.auto_switch) ? "active" : ""}" id="btn-auto">
            Pilote Auto EMS
          </button>
          <button class="ctrl-btn ${isSwitchOn(this._config.dhw_switch) ? "active" : ""}" id="btn-dhw">
            Forcer Boost ECS (55°C)
          </button>
          <button class="ctrl-btn ${isSwitchOn(this._config.tesla_switch) ? "active" : ""}" id="btn-tesla">
            Forcer Charge Max Tesla
          </button>
          <button class="ctrl-btn ${isSwitchOn(this._config.thermal_switch) ? "active" : ""}" id="btn-thermal">
            Stockage Inertie Salon
          </button>
          <button class="ctrl-btn" id="btn-ml">
            Ré-entraîner Modèles ML
          </button>
        </div>
      </ha-card>
    `;

    this.shadowRoot.getElementById("btn-auto")?.addEventListener("click", () => this._toggleEntity(this._config.auto_switch));
    this.shadowRoot.getElementById("btn-dhw")?.addEventListener("click", () => this._toggleEntity(this._config.dhw_switch));
    this.shadowRoot.getElementById("btn-tesla")?.addEventListener("click", () => this._toggleEntity(this._config.tesla_switch));
    this.shadowRoot.getElementById("btn-thermal")?.addEventListener("click", () => this._toggleEntity(this._config.thermal_switch));
    this.shadowRoot.getElementById("btn-ml")?.addEventListener("click", () => this._retrainML());
  }

  getCardSize() {
    return 8;
  }
}

if (!customElements.get("smart-residential-ems-card")) {
  customElements.define("smart-residential-ems-card", SmartResidentialEMSCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-residential-ems-card",
  name: "Smart Residential EMS Card",
  description: "Supervision temps réel Felicity 15kWh, PAC Ecodan Bi-Zone, Tesla Fleet, Calibration Solcast & ML",
});
