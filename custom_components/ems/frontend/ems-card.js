/**
 * Smart Residential EMS - Custom Lovelace Card (ems-card.js)
 * Displays live PV/Battery/Grid/Ecodan/Tesla energy flows, 4-Priority state,
 * Solcast (D+0/D+1/D+2) vs ML 24h Load forecast, and one-click override switches.
 */

class SmartResidentialEMSCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: config.title || "Smart Residential EMS",
      entity: config.entity || "sensor.ems_active_priority_state",
      auto_switch: config.auto_switch || "switch.ems_autonomous_optimization",
      dhw_switch: config.dhw_switch || "switch.ems_force_ecodan_dhw_boost_55_c",
      tesla_switch: config.tesla_switch || "switch.ems_force_tesla_max_charge",
      thermal_switch: config.thermal_switch || "switch.ems_allow_zone_2_underfloor_thermal_storage",
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

  _render() {
    if (!this._hass || !this.shadowRoot) return;

    const mainState = this._hass.states[this._config.entity];
    const attrs = mainState ? mainState.attributes : {};
    const priorityState = mainState ? mainState.state : "idle";

    const pvW = attrs.pv_power_w ?? 0;
    const gridW = attrs.grid_power_w ?? 0;
    const loadW = attrs.house_load_w ?? 0;
    const surplusW = attrs.smoothed_surplus_w ?? 0;
    const battSoc = attrs.battery_soc ?? 0;
    const battTargetSoc = attrs.dynamic_battery_target_soc ?? 80;
    const dhwTemp = attrs.dhw_temp ?? "--";
    const dhwTarget = attrs.dhw_target ?? 48;
    const z1Temp = attrs.z1_temp ?? "--";
    const z2Temp = attrs.z2_temp ?? "--";
    const z2Target = attrs.z2_target ?? "--";
    const evPlugged = attrs.ev_plugged ?? false;
    const evSoc = attrs.ev_soc ?? "--";
    const evCharging = attrs.ev_charging ?? false;
    const evAmps = attrs.ev_target_amps ?? 0;
    const solToday = attrs.solar_today_remaining_kwh ?? 0;
    const solTomorrow = attrs.solar_tomorrow_kwh ?? 0;
    const solDayAfter = attrs.solar_day_after_kwh ?? 0;
    const pred24h = attrs.predicted_24h_kwh ?? 0;
    const importPrice = attrs.import_price_eur ?? 0.1689;
    const exportPrice = attrs.export_price_eur ?? 0.04;
    const mlMae = attrs.ml_mae_watts ?? "--";

    const isSwitchOn = (ent) => this._hass.states[ent]?.state === "on";

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
          margin-bottom: 14px;
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
        .grid-4 {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
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
          font-size: 1.2rem;
          font-weight: 700;
        }
        .metric-sub {
          font-size: 0.72rem;
          opacity: 0.65;
          margin-top: 3px;
        }
        .section-title {
          font-size: 0.85rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          opacity: 0.75;
          margin: 14px 0 8px 0;
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
            <div class="metric-sub">Seuil dynamique EV : ${battTargetSoc} %</div>
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

        <div class="section-title">PAC Mitsubishi Ecodan Bi-Zone & Mobilité Tesla Fleet</div>
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
            <div class="metric-label">Tesla Fleet (${evPlugged ? "Branchée" : "Débranchée"})</div>
            <div class="metric-val">${evSoc} %</div>
            <div class="metric-sub">${evCharging ? `En charge à ${evAmps} A` : "Charge en pause"}</div>
          </div>
        </div>

        <div class="section-title">Prévisions Solcast (J+0/J+1/J+2) & Machine Learning (2 ans Recorder)</div>
        <div class="grid-4">
          <div class="metric-box">
            <div class="metric-label">Solcast Restant J+0</div>
            <div class="metric-val">${solToday} kWh</div>
            <div class="metric-sub">Demain J+1 : ${solTomorrow} kWh</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Solcast Après-Demain J+2</div>
            <div class="metric-val">${solDayAfter} kWh</div>
            <div class="metric-sub">Horizon 48h</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Conso Prédite ML (24h)</div>
            <div class="metric-val">${pred24h} kWh</div>
            <div class="metric-sub">Précision MAE : ±${mlMae} W</div>
          </div>
        </div>

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
            Ré-entraîner ML (2 ans)
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
    return 6;
  }
}

if (!customElements.get("smart-residential-ems-card")) {
  customElements.define("smart-residential-ems-card", SmartResidentialEMSCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-residential-ems-card",
  name: "Smart Residential EMS Card",
  description: "Supervision temps réel Felicity 15kWh, PAC Ecodan Bi-Zone, Tesla Fleet, Solcast & ML",
});
