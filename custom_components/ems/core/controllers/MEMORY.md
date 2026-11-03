# 📦 Mémoire du Module : Contrôleurs Matériels (`core/controllers`)

> **Dossier** : `custom_components/ems/core/controllers/` | **Dernière MAJ** : 2026-11-03

## 🎯 Rôle & Responsabilité
Traduit les décisions de l'arbitre énergétique en appels de services Home Assistant sécurisés pour l'onduleur hybride Felicity (`ha_felicity`), la PAC Mitsubishi Ecodan (`esphome-ecodan-hp`), et la charge véhicule (`teslafleet` + borne `local_tuya`).

## 🗂️ Fichiers & Composants Clés
| Fichier / Export | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [felicity.py](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/felicity.py#L21-L104) | `FelicityController` : calcul du SOC cible dynamique et gestion des modes Modbus | `calculate_dynamic_target_soc()` $\rightarrow$ `float`, `build_commands()` $\rightarrow$ `list[dict]` |
| [ecodan.py](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/ecodan.py#L26-L163) | `EcodanController` : planification ECS solaire (11h-15h) et stockage thermique dalle Zone 2 | `evaluate_dhw_need()`, `evaluate_zone2_thermal_storage()` |
| [tesla.py](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/tesla.py#L24-L185) | `TeslaController` : rampe d'ampérage douce 5A–16A et protection anti-court-cycle | `compute_charging_step()` $\rightarrow$ `(is_charging, amps, commands)` |

## 🔄 Dépendances & Flux de Données
- **Dépend de** : [`const.py`](file:///home/pierre/Projets/ems/custom_components/ems/const.py).
- **Utilisé par** : [`EnergyArbitrator`](file:///home/pierre/Projets/ems/custom_components/ems/core/arbitrator.py).

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Borne IRVE Tuya vs Tesla Fleet** : Ne **jamais** réduire brusquement le courant via la borne Tuya Local (cela fait planter la charge côté voiture). Toujours laisser le switch Tuya sur `ON` et piloter l'ampérage (`5A` à `16A`) via l'entité `number` de `teslafleet` par pas de `-1A` à la baisse et `+1A`/`+2A` à la hausse, espacés de `ev_ramp_seconds` (60s par défaut).
- **Inertie Zone 2 (Salon)** : La surchauffe d'inertie (`+1.0°C` max) sur le plancher chauffant auto-adaptatif ne doit s'activer que si `outdoor_temp < 16.0°C` et en Priorité 4.
