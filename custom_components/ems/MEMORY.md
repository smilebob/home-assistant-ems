# 📦 Mémoire du Module : Intégration Home Assistant (`custom_components/ems`)

> **Dossier** : `custom_components/ems/` | **Dernière MAJ** : 2026-11-03

## 🎯 Rôle & Responsabilité
Point d'entrée du Custom Component HACS (`domain: ems`), gérant le cycle de vie Home Assistant, le Config Flow / Options Flow hybride (Wizard pas-à-pas + Onglets thématiques), le `DataUpdateCoordinator` (cycle 30s) et les plateformes d'entités (`sensor`, `switch`, `select`, `number`).

## 🗂️ Fichiers & Composants Clés
| Fichier / Export | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [__init__.py](file:///home/pierre/Projets/ems/custom_components/ems/__init__.py#L25-L79) | Setup HACS, enregistrement `/ems_frontend`, service `ems.retrain_ml_model` | `async_setup_entry()`, `async_unload_entry()` |
| [const.py](file:///home/pierre/Projets/ems/custom_components/ems/const.py#L1-L105) | Clés de configuration, constantes et valeurs par défaut | `DOMAIN`, `CONF_*`, `DEFAULT_*`, `PRIORITY_*` |
| [config_flow.py](file:///home/pierre/Projets/ems/custom_components/ems/config_flow.py#L294-L535) | `EMSConfigFlow` & `EMSOptionsFlowHandler` (Wizard + Onglets) | Schémas `voluptuous` + `selector.EntitySelector` |
| [coordinator.py](file:///home/pierre/Projets/ems/custom_components/ems/coordinator.py#L43-L254) | `EMSDataUpdateCoordinator` : lecture états, inférence ML, arbitrage et appels services | `_async_update_data()` $\rightarrow$ `dict` |
| [sensor.py](file:///home/pierre/Projets/ems/custom_components/ems/sensor.py#L22-L240) | 16 capteurs EMS (dont explications, vannes Z1, précision ML et prévisions Solcast calibrées) | `EMSSensor` |
| [switch.py](file:///home/pierre/Projets/ems/custom_components/ems/switch.py#L18-L99) | 4 interrupteurs de pilotage (Mode Auto, Boost ECS, Force Tesla, Inertie Salon) | `EMSSwitch` |
| [select.py](file:///home/pierre/Projets/ems/custom_components/ems/select.py#L24-L72) | Sélecteur de mode tarifaire dynamique (`fixed`, `time_of_use`, `dynamic`) | `EMSTariffModeSelect` |
| [number.py](file:///home/pierre/Projets/ems/custom_components/ems/number.py#L25-L135) | 4 curseurs temps réel (SOC min batterie, SOC cible avant EV, Seuil SOC batterie pleine 95% avant inertie, Offset Z2) | `EMSConfigNumber` |

## 🔄 Sous-Modules Internes
- [`core/MEMORY.md`](file:///home/pierre/Projets/ems/custom_components/ems/core/MEMORY.md) : Moteur d'arbitrage et gestionnaire tarifaire.
- [`core/controllers/MEMORY.md`](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/MEMORY.md) : Pilotes Felicity, Ecodan et Tesla Fleet.
- [`ml/MEMORY.md`](file:///home/pierre/Projets/ems/custom_components/ems/ml/MEMORY.md) : Apprentissage automatique Recorder (2 ans).
- [`frontend/MEMORY.md`](file:///home/pierre/Projets/ems/custom_components/ems/frontend/MEMORY.md) : Carte Lovelace personnalisée.

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Imports Home Assistant** : [`__init__.py`](file:///home/pierre/Projets/ems/custom_components/ems/__init__.py) protège ses imports `homeassistant.*` dans un bloc `try/except ImportError` pour permettre l'exécution des tests unitaires hors conteneur Home Assistant.
- **Fusion `data` + `options`** : Toujours fusionner `{**entry.data, **entry.options}` lors de l'initialisation ou du rechargement du coordinateur pour que les modifications faites via l'Options Flow écrasent immédiatement la configuration initiale.
