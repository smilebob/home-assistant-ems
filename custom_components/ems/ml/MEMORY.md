# 📦 Mémoire du Module : Machine Learning (`ml`)

> **Dossier** : `custom_components/ems/ml/` | **Dernière MAJ** : 2026-11-03

## 🎯 Rôle & Responsabilité
Extrait l'historique sur 2 ans (730 jours) depuis la base `recorder` de Home Assistant, construit les vecteurs à 10 features cycliques/thermiques, et entraîne un modèle `RandomForestRegressor` pour prédire la consommation horaire (maison + PAC Ecodan) à 12h et 24h.

## 🗂️ Fichiers & Composants Clés
| Fichier / Export | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [dataset_builder.py](file:///home/pierre/Projets/ems/custom_components/ems/ml/dataset_builder.py#L14-L52) | Vectorisation `build_feature_vector()` et extraction `RecorderDatasetBuilder` | `(dt, outdoor_temp, z1_temp, z2_temp)` $\rightarrow$ `list[float]` (10 features) |
| [model.py](file:///home/pierre/Projets/ems/custom_components/ems/ml/model.py#L141-L299) | `ConsumptionMLModel`, persistance pickle et fallback `_NativeRandomForestRegressor` | `train(X, y)` $\rightarrow$ `dict`, `predict_next_hours_kwh()` $\rightarrow$ `(float, list)` |

## 🔄 Dépendances & Flux de Données
- **Dépend de** : `homeassistant.components.recorder.history` (optionnel avec fallback), `scikit-learn` (optionnel avec fallback `_NativeRandomForestRegressor`).
- **Utilisé par** : [`EMSDataUpdateCoordinator`](file:///home/pierre/Projets/ems/custom_components/ems/coordinator.py#L43-L103) et tests unitaires.

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Zéro blocage Event Loop** : L'extraction SQLite/MariaDB (`get_significant_states`) et l'entraînement `model.train` doivent toujours s'exécuter dans `hass.async_add_executor_job`.
- **Continuité d'historique** : Les panneaux et la batterie ont 2 mois d'historique tandis que la PAC et la maison ont 2 ans : si `load_entity` est absente sur les anciens relevés, `dataset_builder.py` reconstitue la charge via `350W + ecodan_power`.
- **Fallback sans dépendance** : Si `scikit-learn` ou `numpy` ne sont pas installés dans l'environnement Python hôte, `_NativeRandomForestRegressor` prend automatiquement le relais sans erreur d'import.
