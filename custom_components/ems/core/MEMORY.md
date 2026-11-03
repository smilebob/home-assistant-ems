# 📦 Mémoire du Module : Moteur d'Arbitrage & Tarification (`core`)

> **Dossier** : `custom_components/ems/core/` | **Dernière MAJ** : 2026-11-03

## 🎯 Rôle & Responsabilité
Orchestre la cascade des 4 priorités énergétiques avec filtrage anti-nuages et gère l'abstraction tarifaire évolutive (Base fixe 16,89 c€ / 4 c€ $\rightarrow$ HP/HC $\rightarrow$ Dynamique Spot).

## 🗂️ Fichiers & Composants Clés
| Fichier / Export | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [arbitrator.py](file:///home/pierre/Projets/ems/custom_components/ems/core/arbitrator.py#L27-L216) | `EnergyArbitrator` : lissage du surplus PV et exécution des 4 priorités | `evaluate_cycle(...)` $\rightarrow$ `dict` (métriques + `commands`) |
| [tariff.py](file:///home/pierre/Projets/ems/custom_components/ems/core/tariff.py#L21-L78) | `TariffManager` : calcul du coût d'achat/vente, spread d'autoconsommation et opportunités réseau | `get_current_prices()`, `is_cheap_grid_opportunity()` |
| [controllers/MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/MEMORY.md) | Sous-module des pilotes matériels Felicity, Ecodan et Tesla | Voir mémoire dédiée |

## 🔄 Dépendances & Flux de Données
- **Dépend de** : `custom_components/ems/core/controllers/*`, [`const.py`](file:///home/pierre/Projets/ems/custom_components/ems/const.py).
- **Utilisé par** : [`EMSDataUpdateCoordinator`](file:///home/pierre/Projets/ems/custom_components/ems/coordinator.py).

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Calcul du Surplus Net** : `raw_surplus_w` doit soustraire la consommation de la maison **hors charge Tesla en cours** (`base_house_without_ev_w = house_load_w - ev_current_power_w`), sinon le démarrage de la charge Tesla annulerait artificiellement le surplus mesuré et provoquerait un pompage marche/arrêt.
- **Hiérarchie stricte** : Priorité 1 (Confort & ECS 11h-15h) $\rightarrow$ Priorité 2 (Batterie 15 kWh jusqu'au SOC dynamique) $\rightarrow$ Priorité 3 (Tesla Fleet) $\rightarrow$ Priorité 4 (Stockage thermique plancher Zone 2 + ECS 55°C).
