# 🧠 Mémoire Globale du Projet : Smart Residential EMS (`home-assistant-ems`)

> **Dernière MAJ** : 2026-11-04 | **Statut** : Déployé en Production (V1.1.3) & Application Docker / Add-on Ingress v2.0 initiée

## 🎯 Vue d'Ensemble & Objectif
- **Description** : Double solution d'arbitrage solaire résidentiel optimisant l'autoconsommation d'une installation photovoltaïque (7 kWc) + batterie 15 kWh (`ha_felicity`), d'une PAC air-eau Mitsubishi Ecodan bi-zone + ECS (`esphome-ecodan-hp`), et d'une recharge véhicule électrique (`teslafleet` + borne `local_tuya`), pilotée par prévisions Solcast (J+0 à J+2) et Machine Learning local.
- **Deux Modes d'Exécution Disponibles** :
  1. **Intégration HACS native** : Composant léger [`custom_components/ems/`](file:///home/pierre/Projets/ems/custom_components/ems/) (V1.1.3 en production).
  2. **Application Conteneurisée Découplée (Docker & Add-on HA Ingress)** : [`app/`](file:///home/pierre/Projets/ems/app/) avec backend FastAPI, WebSockets natifs, stockage DuckDB local, passerelle MQTT universelle, et interface Web React 18 + Tailwind + Apache ECharts intégrée à la barre latérale.
- **Stack Technique** : Python 3.12+, FastAPI, WebSockets, DuckDB, `scikit-learn`, React 18, Vite, Apache ECharts, Tailwind CSS, Home Assistant Ingress.
- **Point d'Entrée Global** : [`custom_components/ems/__init__.py`](file:///home/pierre/Projets/ems/custom_components/ems/__init__.py)

## 🚀 Commandes Essentielles
| Action | Commande | Notes / Env |
| :--- | :--- | :--- |
| **Tests Unitaires** | `PYTHONPATH=/home/pierre/Projets/ems python3 -m unittest discover -s /home/pierre/Projets/ems/tests -v` | Exécute les 4 suites (ML, Tesla ramp, Tarifs, Arbitre) sans dépendance externe requise |
| **Service HA ML** | `service: ems.retrain_ml_model` | Force le ré-entraînement immédiat sur les 730 derniers jours du Recorder HA |

## 🗺️ Index des Sous-Modules (Cartographie Progressive Disclosure)
| Sous-Dossier / Module | Rôle & Responsabilité | Documentation Détaillée |
| :--- | :--- | :--- |
| `custom_components/ems/` | Composant racine HA, Config/Options Flow (Wizard + Onglets), Coordinateur 30s, Entités | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/MEMORY.md) |
| `custom_components/ems/core/` | Arbitre énergétique 4 priorités, filtre anti-nuages et gestionnaire tarifaire évolutif | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/core/MEMORY.md) |
| `custom_components/ems/core/controllers/` | Pilotes matériels : Onduleur/Batterie Felicity, PAC Ecodan Bi-Zone/ECS, Tesla Fleet | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/MEMORY.md) |
| `custom_components/ems/ml/` | Pipeline d'extraction Recorder (2 ans) et modèle prédictif `RandomForestRegressor` | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/ml/MEMORY.md) |
| `custom_components/ems/frontend/` | Carte Lovelace personnalisée (`smart-residential-ems-card`) auto-hébergée | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/frontend/MEMORY.md) |

## 📌 État Actuel & Feuille de Route
### ✅ Implémenté
- [x] **Configuration UI Hybride & Reconfiguration Sans Erreur** : Assistant guidé (Wizard) + Menu par onglets thématiques + `async_step_reconfigure` ([`config_flow.py`](file:///home/pierre/Projets/ems/custom_components/ems/config_flow.py)) avec traductions FR/EN.
- [x] **Machine Learning Local (Consommation 13 features + Auto-Calibration Solaire Solcast)** : Extraction `RecorderDatasetBuilder` + `ConsumptionMLModel` (MAE W, Fiabilité %, R²) + `SolarCalibrationModel` (ratios horaires bayésiens d'ombrage + Random Forest) ([`ml/`](file:///home/pierre/Projets/ems/custom_components/ems/ml/MEMORY.md)).
- [x] **Explicabilité & Conseiller Vannes Thermostatiques** : Capteur `decision_reason` avec journal glissant et capteur `valve_summary` analysant l'équilibrage des pièces de la Zone 1 (Éléonore, Gaston, Parents, SdB).
- [x] **Cascade d'Arbitrage 4 Priorités & Séquencement Strict EV** :
  1. Confort thermique & ECS solaire (11h–16h).
  2. Batterie Felicity 15 kWh jusqu'au SOC dynamique.
  3. Recharge VE avec séquencement strict : **Consigne courant Véhicule d'abord (`number.sally_courant_de_recharge`) $\rightarrow$ Attente confirmation état HA (timeout 15s) $\rightarrow$ Pilotage Borne Tuya (`number.garage_borne_voiture_set_charge_current` + `select.garage_borne_voiture_toggle_charging`)**.
  4. Stockage thermique d'inertie (uniquement lorsque `battery_soc >= 95%`, réglable via `battery_thermal_soc_threshold`) dans le plancher chauffant du salon (Zone 2, `+1°C`) et Boost ECS (`55°C`).
- [x] **Évolutivité Tarifaire** : Bascule transparente entre tarif Fixe (16,89 c€ achat / 4 c€ vente), HP/HC (`time_of_use`) et Spot Dynamique (`dynamic`).
- [x] **Carte Lovelace Clé en Main** : [`ems-card.js`](file:///home/pierre/Projets/ems/custom_components/ems/frontend/ems-card.js) et suite de tests unitaires ([`tests/test_ems_core.py`](file:///home/pierre/Projets/ems/tests/test_ems_core.py)).

### 🚧 Prochaines Évolutions Possibles
- [ ] Affinage des courbes de loi d'eau Zone 1 en fonction de l'écart entre la chambre Éléonore (Nord) et les capteurs Zigbee/BLE des chambres Gaston/Parents/SdB.
- [ ] Couplage direct aux prévisions horaires de prix J+1 (EPEX Spot / RTE Tempo) lors du changement de contrat électrique dans 1 an.

## ⚠️ Pièges Globaux & Règles Métier Critiques
- **Gotcha Borne IRVE Tuya vs Tesla** : Ne jamais moduler l'ampérage sur la borne Tuya Local (risque de mise en défaut côté voiture lors d'une baisse rapide). La borne Tuya sert uniquement de contacteur d'alimentation ON/OFF ; la modulation (`5A` à `16A`, `-1A` max par palier de 60s) passe exclusivement par `teslafleet` ([`tesla.py`](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/tesla.py)).
- **Gotcha Calcul Surplus** : Toujours retrancher la puissance de charge EV active de `house_load_w` lors du calcul de `raw_surplus_w` dans [`arbitrator.py:L79-L83`](file:///home/pierre/Projets/ems/custom_components/ems/core/arbitrator.py#L79-L83).
- **Gotcha Historique Asymétrique** : L'historique Recorder couvre 2 ans pour la PAC Ecodan et la maison, mais seulement 2 mois pour le solaire/batterie Felicity. Le builder ML reconstruit la charge historique même lorsque seules les entités PAC/conso étaient présentes.
