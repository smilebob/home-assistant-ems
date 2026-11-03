# ⚡ Smart Residential EMS (`home-assistant-ems`)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.1.1-blue.svg)](https://github.com/smilebob/home-assistant-ems/releases)

**Smart Residential EMS** est une intégration native pour **Home Assistant** dédiée au pilotage énergétique prédictif d'une habitation équipée de :
- **Onduleur Hybride & Batterie 15 kWh Felicity** (via [`ha_felicity`](https://github.com/partach/ha_felicity) en Modbus R/W)
- **Pompe à Chaleur Air-Eau Mitsubishi Ecodan Bi-Zone & ECS** (via [`esphome-ecodan-hp`](https://github.com/gekkekoe/esphome-ecodan-hp) en local CN105)
  - *Zone 1 (Étage)* : Chambres sur radiateurs en loi d'eau + **Conseiller d'équilibrage des vannes thermostatiques**.
  - *Zone 2 (RDC)* : Salon sur plancher chauffant à forte inertie thermique.
  - *Eau Chaude Sanitaire (ECS)* : Planification solaire intelligente et Boost thermique.
- **Mobilité Électrique : Tesla Fleet & Borne IRVE Tuya Local**
  - Séquencement strict **Véhicule d'abord $\rightarrow$ Confirmation Home Assistant $\rightarrow$ Borne IRVE** et modulation douce d'ampérage pas à pas.
- **Double Moteur de Machine Learning Local (Recorder HA)**
  1. **Modèle ML de Consommation (13 variables)** : apprend l'inertie thermique de la maison, les habitudes par jour de la semaine et la réponse de la PAC sur jusqu'à 2 ans d'historique Recorder.
  2. **Étage d'Auto-Calibration Solaire ML (Solcast $\rightarrow$ Installation Réelle)** : apprend l'ombrage horaire spécifique du toit et le derating thermique en comparant les prévisions théoriques de Solcast à la production PV réelle.

---

## 📑 Sommaire

1. [Installation & Reconfiguration](#-1-installation--reconfiguration)
2. [Fonctionnement de la Cascade d'Arbitrage (4 Priorités)](#-2-fonctionnement-de-la-cascade-darbitrage-4-priorités)
3. [Guide Détaillé des Paramètres par Onglet](#-3-guide-détaillé-des-paramètres-par-onglet)
4. [Fonctionnement des Modèles de Machine Learning](#-4-fonctionnement-des-modèles-de-machine-learning)
5. [Séquencement de Charge Véhicule & Borne IRVE](#-5-séquencement-de-charge-véhicule--borne-irve)
6. [Conseiller d'Équilibrage des Vannes Thermostatiques (Zone 1)](#-6-conseiller-déquilibrage-des-vannes-thermostatiques-zone-1)
7. [Référence Complète des Entités Créées](#-7-référence-complète-des-entités-créées)
8. [Carte Lovelace Clé en Main (`ems-card.js`)](#-8-carte-lovelace-clé-en-main-ems-cardjs)
9. [Services & Actions Home Assistant](#-9-services--actions-home-assistant)

---

## 🚀 1. Installation & Reconfiguration

### Via HACS (Recommandé)
1. Ouvrez **HACS $\rightarrow$ Intégrations $\rightarrow$ Menu (⋮) $\rightarrow$ Dépôts personnalisés**.
2. Ajoutez l'URL `https://github.com/smilebob/home-assistant-ems` dans la catégorie **Intégration**.
3. Installez **Smart Residential EMS (Ecodan / Felicity / Tesla)** puis redémarrez Home Assistant.
4. Allez dans **Paramètres $\rightarrow$ Appareils et services $\rightarrow$ Ajouter une intégration** et recherchez **Smart Residential EMS**.

### Modification de la configuration à tout moment
Toutes les entités et tous les seuils peuvent être modifiés à chaud sans jamais supprimer l'intégration :
- Soit via **Paramètres $\rightarrow$ Appareils et services $\rightarrow$ Smart Residential EMS $\rightarrow$ Configurer** (menu par onglets thématiques ou assistant complet).
- Soit via le menu **⋮ $\rightarrow$ Reconfigurer**.
- Toutes vos entités déjà sélectionnées sont automatiquement pré-remplies.

---

## 🎯 2. Fonctionnement de la Cascade d'Arbitrage (4 Priorités)

Toutes les **30 secondes**, le coordinateur calcule le surplus solaire réel disponible (en soustrayant les charges pilotables déjà actives pour éviter tout effet de pompage) et applique un lissage exponentiel anti-nuages avant d'arbitrer selon 4 priorités :

| Priorité | Nom de l'état | Conditions d'activation | Actions exécutées |
| :--- | :--- | :--- | :--- |
| **Priorité 1** | `priority_1_comfort_dhw` | Ballon ECS $< 43^\circ\text{C}$ (urgence) **ou** fenêtre solaire (`11h–16h`), ECS $<$ consigne normale (`48^\circ\text{C}`) et surplus $> 600\text{ W}$ | Maintien de la consigne ECS confort (`48°C`) et recommandation de chauffe ECS pendant que le COP et le soleil sont au maximum. |
| **Priorité 2** | `priority_2_battery` | Surplus solaire $> 150\text{ W}$ et `battery_soc` $<$ **SOC Cible Dynamique** | L'onduleur Felicity charge prioritairement la batterie 15 kWh pour garantir l'autonomie nocturne de la maison. |
| **Priorité 3** | `priority_3_tesla` | `battery_soc` $\ge$ **SOC Cible Dynamique**, véhicule branché, `ev_soc < ev_target_soc`, et puissance disponible $\ge$ courant min ($6\text{ A} \times 230\text{ V} = 1380\text{ W}$) | Démarrage et modulation douce du courant de charge (rampe $+2\text{ A}$ max à la hausse, $-1\text{ A}$ max à la baisse toutes les 60s). |
| **Priorité 4** | `priority_4_thermal_boost` | `battery_soc` $\ge$ **Seuil SOC Batterie Pleine (`95%`)** et surplus solaire restant $> 800\text{ W}$ non consommé par le véhicule | **Stockage thermique d'inertie** : consigne ECS relevée à `55°C` (+ `dhw_force`) et consigne du plancher chauffant Salon (Zone 2) relevée de `+1.0°C` (si $T_{\text{ext}} < 16^\circ\text{C}$). |
| **Tarif Bas** | `priority_dynamic_grid_charge` | Mode `dynamic` ou `time_of_use` actif et prix d'achat $\le$ seuil bas configuré | Bascule l'onduleur Felicity en charge réseau (`Economic mode` / `Charge`), active le Boost ECS (`55°C`) et autorise la charge véhicule à puissance max. |

> **Pourquoi l'inertie thermique (Priorité 4) s'applique-t-elle uniquement à la Zone 2 (Salon) et non à la Zone 1 (Chambres) ?**
> La Zone 2 est un plancher chauffant coulé dans une dalle béton à forte masse thermique : accumuler $+1^\circ\text{C}$ l'après-midi permet de restituer la chaleur toute la soirée sans déclencher la PAC la nuit. À l'inverse, la Zone 1 (chambres à l'étage) est équipée de radiateurs à faible inertie : surchauffer les chambres à 15h dissiperait immédiatement la chaleur avant le soir et dégraderait le confort de sommeil.

---

## 🛠️ 3. Guide Détaillé des Paramètres par Onglet

Chaque paramètre ci-dessous est modifiable dans **Configurer** :

### Onglet 1 : Général & Tarification (`tariff`)
| Paramètre | Description | Valeur conseillée / Exemple |
| :--- | :--- | :--- |
| `tariff_mode` | Mode tarifaire (`fixed`, `time_of_use`, `dynamic`) | `fixed` |
| `grid_import_price_fixed` | Prix d'achat fixe du kWh réseau (€/kWh) | `0.1689` (16,89 c€/kWh) |
| `grid_export_price_fixed` | Prix de revente du surplus injecté (€/kWh) | `0.04` (4,00 c€/kWh) |
| `grid_import_price_entity` | Capteur de prix d'achat temps réel (pour HP/HC ou Spot) | Optionnel |
| `grid_export_price_entity` | Capteur de prix de vente temps réel | Optionnel |
| `dynamic_cheap_threshold` | Seuil de prix bas déclenchant la charge forcée réseau (€/kWh) | `0.06` |

### Onglet 2 : Onduleur Hybride & Batterie 15 kWh (`felicity`)
| Paramètre | Description | Entité configurée sur votre installation |
| :--- | :--- | :--- |
| `pv_power_entity` | Puissance solaire PV totale produite (W) — *utilisée aussi par le ML de calibration solaire* | `sensor.felicity_inverter_total_pv_power` |
| `grid_power_entity` | Puissance réseau (W, positif = achat, négatif = injection) | `sensor.felicity_inverter_total_ac_input_power` |
| `house_load_entity` | Consommation totale de la maison (W) — *utilisée par le ML de consommation* | `sensor.felicity_inverter_loadpower_lineside` |
| `battery_soc_entity` | État de charge (SOC %) de la batterie 15 kWh | `sensor.felicity_inverter_battery_capacity` |
| `battery_power_entity` | Puissance batterie (W) | `sensor.felicity_inverter_battery_power` |
| `felicity_work_mode_entity` | Sélecteur du mode de fonctionnement de l'onduleur Felicity | `select.felicity_inverter_operating_mode` |
| `felicity_force_charge_entity` | Switch ou Select d'activation de la règle de charge réseau | `select.felicity_inverter_economic_mode_rule_1_enable` |
| `battery_capacity_kwh` | Capacité nominale du parc batterie (kWh) | `15.0` |
| `battery_min_soc` | SOC minimum de réserve de sécurité (%) | `20 %` |
| `battery_target_soc_ev` | SOC batterie minimum de référence avant d'autoriser le surplus vers la voiture (%) | `80 %` |
| `battery_thermal_soc_threshold` | **Seuil SOC Batterie Pleine (%)** requis avant d'activer le stockage par inertie thermique (Priorité 4) | `95 %` |

### Onglet 3 : PAC Mitsubishi Ecodan Bi-Zone & ECS (`ecodan`)
| Paramètre | Description | Entité configurée sur votre installation |
| :--- | :--- | :--- |
| `ecodan_power_entity` | Puissance électrique consommée par la PAC (W) — *utilisée par le ML de consommation* | `sensor.consommation_pac` |
| `dhw_temp_entity` | Température actuelle du ballon ECS (°C) | `sensor.ecodan_heatpump_temp_actuelle_ecs` |
| `dhw_target_entity` | Thermostat ou consigne cible ECS (`climate.*` ou `number.*`) | `climate.ecodan_heatpump_thermostat_ecs` |
| `dhw_force_entity` | Switch / Bouton de forçage chauffe ECS immédiate | `switch.ecodan_heatpump_forcer_ecs` |
| `dhw_normal_temp` / `dhw_boost_temp` | Consignes ECS Confort (`48°C`) et Boost Solaire (`55°C`) | `48.0 °C` / `55.0 °C` |
| `dhw_solar_window_start` / `end` | Fenêtre horaire optimale pour le cycle ECS solaire | `11h` à `16h` |
| `z1_temp_entity` | Capteur température de référence Zone 1 (Étage) | `sensor.ecodan_heatpump_z1_temp_pi_ce` |
| `z1_target_entity` | Thermostat / Consigne de référence Zone 1 | `climate.ecodan_heatpump_zone_1_temp_ambiante` |
| `z1_rooms_entities` | **Thermomètres annexes Zone 1** (évalués pour le réglage des vannes thermostatiques) | `sensor.ambiance_eleonore_temperature`, `sensor.ambiance_gaston_temperature_2`, `sensor.chambre_parents_temperature_4`, `sensor.tz3000_xr3htd96_ts0201_temperature_7` |
| `z2_temp_entity` | Capteur température ambiante Zone 2 (Salon RDC) | `sensor.ecodan_heatpump_z2_temp_pi_ce` |
| `z2_target_entity` | Thermostat / Consigne Zone 2 (Plancher chauffant Salon) | `climate.ecodan_heatpump_zone_2_temp_ambiante` |
| `z2_max_overheat_offset` | Surchauffe maximale autorisée sur le plancher du salon en Priorité 4 (+°C) | `+1.0 °C` |

### Onglet 4 : Mobilité Électrique — Tesla Fleet & Borne IRVE Tuya (`ev`)
| Paramètre | Description | Entité configurée sur votre installation |
| :--- | :--- | :--- |
| `ev_plugged_entity` | État de connexion du câble (`binary_sensor` véhicule ou `sensor` état borne) | `sensor.borne_voiture_etat` |
| `ev_soc_entity` | Niveau de batterie du véhicule (%) | `sensor.sally_niveau_de_batterie` |
| `ev_target_soc_entity` | Limite de recharge cible du véhicule (%) | `number.sally_limite_de_recharge` |
| `tesla_charge_switch` | Switch Marche/Arrêt charge côté véhicule | `switch.sally_charge` |
| `tesla_current_number` | Consigne de courant côté véhicule (A) — **toujours pilotée en premier** | `number.sally_courant_de_recharge` |
| `evse_power_switch` | Contrôle Marche/Arrêt côté borne Tuya (`select.*` ou `switch.*`) | `select.garage_borne_voiture_toggle_charging` |
| `evse_current_number` | Consigne de courant côté borne Tuya (A) — **pilotée après confirmation véhicule** | `number.garage_borne_voiture_set_charge_current` |
| `evse_power_entity` | Capteur de puissance de la borne (W ou kW, conversion auto) | `sensor.garage_borne_voiture_puissance` |
| `ev_min_current` / `ev_max_current` | Plage d'ampérage autorisée (A) | `6 A` à `16 A` |

### Onglet 5 : Prévisions Solcast / Météo & Machine Learning (`forecast`)
| Paramètre | Description | Entité configurée sur votre installation |
| :--- | :--- | :--- |
| `outdoor_temp_entity` | Capteur température extérieure (°C) — *utilisé par les 2 modèles ML* | `sensor.ecodan_heatpump_temp_ext` |
| `solar_forecast_power_now` | **Prévision Puissance Solaire Instantanée Solcast (W)** — *utilisée pour l'auto-calibration ML* | `sensor.solcast_pv_forecast_puissance_maintenant` |
| `solar_forecast_today_remaining` | Prévision solaire restante aujourd'hui J+0 (kWh) | `sensor.solcast_pv_forecast_previsions_de_production_restantes_aujourd_hui` |
| `solar_forecast_tomorrow` | Prévision solaire demain J+1 (kWh) | `sensor.solcast_pv_forecast_previsions_pour_demain` |
| `solar_forecast_day_after` | Prévision solaire après-demain J+2 (kWh) | `sensor.solcast_pv_forecast_prevision_jour_3` |
| `ml_training_days` | Profondeur d'historique Recorder analysée lors de l'entraînement (jours) | `730` (2 ans) |
| `ml_auto_train` | Ré-entraînement nocturne automatique chaque nuit à 03h00 | `Activé` |

---

## 🧠 4. Fonctionnement des Modèles de Machine Learning

### A. Modèle de Consommation de la Maison (`ConsumptionMLModel`)
- **Algorithme** : `RandomForestRegressor` (60 arbres) entraîné localement sur l'historique Home Assistant Recorder (sauvegardé dans `.storage/ems_ml_model.pkl`).
- **13 Variables Prédictives (Features)** :
  1. $\sin(\text{heure})$, $\cos(\text{heure})$ et $\text{heure}$ (`0..23`)
  2. $\sin(\text{jour\_semaine})$, $\cos(\text{jour\_semaine})$ et $\text{jour\_semaine}$ (`0=Lundi .. 6=Dimanche`)
  3. Indicateur `is_weekend` (`0` ou `1`)
  4. $\sin(\text{jour\_année})$, $\cos(\text{jour\_année})$ et $\text{mois}$ (`1..12`)
  5. Température extérieure ($^\circ\text{C}$)
  6. Degrés-Jours de Chauffage ($\text{HDD} = \max(0, 18^\circ\text{C} - T_{\text{ext}})$)
  7. Température intérieure moyenne Zone 1 / Zone 2 ($^\circ\text{C}$)
- **Métriques de justesse exposées** :
  - **Fiabilité (%)** : `sensor.smart_residential_ems_ems_ml_load_forecast_accuracy` ($100 \times (1 - \text{MAE} / \overline{P})$)
  - **Erreur moyenne absolue (MAE en W)** : `sensor.smart_residential_ems_ems_ml_load_forecast_error_mae`
  - **Coefficient de détermination ($R^2$)** : exposé dans l'attribut `ml_r2_score`.

### B. Étage Intermédiaire d'Auto-Calibration Solaire (`SolarCalibrationModel`)
Les prévisions Solcast sont théoriques et ne connaissent ni les masques d'ombrage proches (arbres, cheminée, bâtiments voisins en début/fin de journée), ni l'encrassement ou l'échauffement réel des panneaux.
- **Apprentissage Hybride** (sauvegardé dans `.storage/ems_solar_calibration.pkl`) :
  1. **Profil Bayésien d'Ombrage Horaire** : calcule pour chaque heure de la journée ($0\text{h}..23\text{h}$) le ratio réel observé $\text{PV}_{\text{réel}} / \text{Solcast}_{\text{prévu}}$ lissé par un prior bayésien afin d'apprendre les heures exactes où votre toiture est ombragée.
  2. **Modèle de Transfert Random Forest (8 variables)** : apprend la correction non-linéaire en fonction de la puissance Solcast brute, de l'heure, du mois, de l'élévation solaire saisonnière et de la température extérieure.
- **Double Correction en Temps Réel** :
  - Corrige la puissance instantanée attendue (`sensor.smart_residential_ems_ems_calibrated_solar_power_forecast` en W).
  - Corrige les bilans journaliers restants J+0 et J+1 (`calibrated_solar_forecast_today_remaining` et `calibrated_solar_forecast_tomorrow` en kWh) utilisés par l'arbitre pour calculer le SOC cible de la batterie.

---

## 🚗 5. Séquencement de Charge Véhicule & Borne IRVE

Pour éviter toute erreur de communication ou mise en sécurité de la borne Tuya Local lors des changements de consigne :

1. **Lors d'un démarrage ou d'une modification d'ampérage** :
   - **Étape 1 (`sequence_order: 1`)** : L'EMS envoie **d'abord** la nouvelle consigne de courant à la voiture (`number.sally_courant_de_recharge`).
   - **Étape 2 (Confirmation HA)** : Le coordinateur vérifie chaque seconde que l'état de `number.sally_courant_de_recharge` dans Home Assistant confirme bien la prise en compte de la consigne côté véhicule (avec un garde-fou de sécurité de 15 secondes).
   - **Étape 3 (`sequence_order: 3 & 4`)** : Une fois la consigne confirmée côté voiture, l'EMS règle le courant de la borne (`number.garage_borne_voiture_set_charge_current`) puis active la charge (`select.garage_borne_voiture_toggle_charging: "Start charging"`).
2. **Lors d'un arrêt de charge** :
   - L'EMS coupe d'abord la charge côté voiture (`switch.sally_charge: turn_off`), puis coupe la borne (`select.garage_borne_voiture_toggle_charging: "Stop charging"`).

---

## 🌡️ 6. Conseiller d'Équilibrage des Vannes Thermostatiques (Zone 1)

La Zone 1 (étage) fonctionne en loi d'eau pilotée par la PAC Ecodan. Pour vous aider à équilibrer manuellement les têtes thermostatiques des radiateurs des différentes chambres :
- L'intégration compare en continu la température de chaque pièce configurée dans `z1_rooms_entities` à la consigne de référence Zone 1 (`climate.ecodan_heatpump_zone_1_temp_ambiante`).
- Règles de recommandation exposées dans `sensor.smart_residential_ems_ems_thermostatic_valve_advice` et sur la carte Lovelace :
  - Écart compris entre $-0.5^\circ\text{C}$ et $+0.5^\circ\text{C}$ : **Équilibrée (ne pas toucher)**
  - Écart entre $+0.6^\circ\text{C}$ et $+1.2^\circ\text{C}$ : **Fermer légèrement (-1/4 tour)**
  - Écart $> +1.2^\circ\text{C}$ : **Fermer (-1/2 tour / -1 cran)**
  - Écart entre $-0.6^\circ\text{C}$ et $-1.2^\circ\text{C}$ : **Ouvrir légèrement (+1/4 tour)**
  - Écart $< -1.2^\circ\text{C}$ : **Ouvrir (+1/2 tour / +1 cran)**

---

## 📊 7. Référence Complète des Entités Créées

### Capteurs (`sensor.*`)
| Entité | Description | Unité |
| :--- | :--- | :--- |
| `sensor.smart_residential_ems_ems_active_priority_state` | État de priorité actif + **attributs complets** pour la carte Lovelace | Texte |
| `sensor.smart_residential_ems_ems_decision_explanation` | **Explication détaillée en français** de la décision en cours + attribut `decision_log` | Texte |
| `sensor.smart_residential_ems_ems_thermostatic_valve_advice` | Résumé et détail par pièce des réglages de vannes thermostatiques Zone 1 | Texte |
| `sensor.smart_residential_ems_ems_smoothed_solar_surplus` | Surplus solaire lissé (filtre exponentiel anti-nuages) | `W` |
| `sensor.smart_residential_ems_ems_ml_predicted_load_24h` | Consommation totale maison + PAC prédite sur les 24 prochaines heures | `kWh` |
| `sensor.smart_residential_ems_ems_ml_predicted_overnight_load_12h` | Consommation nocturne prédite (19h–08h) pour le dimensionnement batterie | `kWh` |
| `sensor.smart_residential_ems_ems_ml_load_forecast_accuracy` | Pourcentage de fiabilité du modèle ML de consommation | `%` |
| `sensor.smart_residential_ems_ems_ml_load_forecast_error_mae` | Erreur moyenne absolue (MAE) du modèle ML de consommation | `W` |
| `sensor.smart_residential_ems_ems_ml_training_samples_recorder` | Nombre d'heures d'historique Recorder utilisées par le modèle ML | `h` |
| `sensor.smart_residential_ems_ems_calibrated_solar_power_forecast` | Puissance solaire instantanée prédite **auto-calibrée** par le ML | `W` |
| `sensor.smart_residential_ems_ems_calibrated_solar_forecast_today_remaining` | Production solaire restante aujourd'hui (J+0) **auto-calibrée** | `kWh` |
| `sensor.smart_residential_ems_ems_calibrated_solar_forecast_tomorrow` | Production solaire prévue demain (J+1) **auto-calibrée** | `kWh` |
| `sensor.smart_residential_ems_ems_solcast_auto_correction_ratio` | Ratio d'auto-correction appris entre votre installation et Solcast | Ratio |
| `sensor.smart_residential_ems_ems_dynamic_battery_target_soc` | Seuil SOC batterie dynamique calculé avant délestage vers la voiture | `%` |
| `sensor.smart_residential_ems_ems_tesla_target_charging_current` | Consigne d'ampérage de charge calculée pour la voiture et la borne | `A` |
| `sensor.smart_residential_ems_ems_self_consumption_savings` | Économies cumulées réalisées grâce à l'autoconsommation pilotée | `EUR` |

### Interrupteurs de Pilotage (`switch.*`)
| Entité | Rôle |
| :--- | :--- |
| `switch.smart_residential_ems_ems_autonomous_optimization` | Active / Désactive le pilotage automatique global de l'EMS |
| `switch.smart_residential_ems_ems_force_ecodan_dhw_boost_55degc` | Force immédiatement une chauffe ECS Boost à 55°C |
| `switch.smart_residential_ems_ems_force_tesla_max_charge` | Force immédiatement la charge du véhicule au courant maximum (`16 A`) |
| `switch.smart_residential_ems_ems_allow_zone_2_underfloor_thermal_storage` | Autorise ou interdit la surchauffe d'inertie (`+1°C`) du plancher chauffant Salon en Priorité 4 |

### Curseurs de Réglage (`number.*`) & Sélecteur (`select.*`)
| Entité | Rôle | Plage |
| :--- | :--- | :--- |
| `number.smart_residential_ems_ems_battery_reserve_minimum_soc` | SOC minimum de sécurité de la batterie Felicity | `5 %` – `50 %` |
| `number.smart_residential_ems_ems_battery_target_soc_before_tesla` | SOC batterie minimum de référence avant de charger la voiture | `20 %` – `100 %` |
| `number.smart_residential_ems_ems_battery_soc_threshold_before_thermal_storage` | **Seuil SOC Batterie Pleine** requis avant d'activer l'inertie thermique (Priorité 4) | `75 %` – `100 %` (défaut `95 %`) |
| `number.smart_residential_ems_ems_zone_2_floor_thermal_storage_offset` | Hausse maximale de consigne autorisée sur le plancher chauffant Salon | `0.0 °C` – `3.0 °C` |
| `select.smart_residential_ems_ems_active_tariff_mode` | Sélecteur de mode tarifaire (`fixed`, `time_of_use`, `dynamic`) | Liste |

---

## 🖥️ 8. Carte Lovelace Clé en Main (`ems-card.js`)

L'intégration héberge automatiquement la carte personnalisée sur `/ems_frontend/ems-card.js`.

### Ajout au tableau de bord
1. Dans **Paramètres $\rightarrow$ Tableaux de bord $\rightarrow$ Ressources**, vérifiez ou ajoutez `/ems_frontend/ems-card.js` (Type : *Module JavaScript*).
2. Ajoutez une carte manuelle avec le code YAML suivant :

```yaml
type: custom:smart-residential-ems-card
title: Pilotage Énergétique Maison (EMS)
entity: sensor.smart_residential_ems_ems_active_priority_state
auto_switch: switch.smart_residential_ems_ems_autonomous_optimization
dhw_switch: switch.smart_residential_ems_ems_force_ecodan_dhw_boost_55degc
tesla_switch: switch.smart_residential_ems_ems_force_tesla_max_charge
thermal_switch: switch.smart_residential_ems_ems_allow_zone_2_underfloor_thermal_storage
```

---

## 🔄 9. Services & Actions Home Assistant

- **`ems.retrain_ml_model`** : Force l'extraction immédiate de l'historique Recorder et le ré-entraînement complet des deux modèles (`ConsumptionMLModel` et `SolarCalibrationModel`). Ce service est également déclenché par le bouton **« Ré-entraîner Modèles ML »** directement depuis la carte Lovelace.
