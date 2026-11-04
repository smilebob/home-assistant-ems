# 📦 Mémoire du Module : Machine Learning (`ml`)

> **Dossier** : `custom_components/ems/ml/` | **Dernière MAJ** : 2026-11-04 | **Version** : v2.0.6

## 🎯 Rôle & Responsabilité
Gère les deux modèles d'apprentissage automatique de l'EMS :
1. **Modèle de Consommation (`ConsumptionMLModel`)** : Apprend la consommation globale du foyer (usages de vie + inertie thermique PAC Ecodan) via un vecteur trigonométrique à 13 variables.
2. **Étage d'Auto-Calibration Solaire (`SolarCalibrationModel`)** : Apprend l'ombrage horaire spécifique du toit (masques solaires matin/soir) et le derating thermique en confrontant les prévisions Solcast théoriques aux mesures réelles de l'onduleur Felicity.

## 🗂️ Fichiers & Composants Clés
| Fichier / Export | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [`dataset_builder.py`](file:///home/pierre/Projets/ems/custom_components/ems/ml/dataset_builder.py#L13-L105) | Vectorisation `build_feature_vector()` (13 features) et `build_solar_feature_vector()` (8 features) | `(dt, temps...)` $\rightarrow$ `list[float]` trigonométrique |
| [`model.py:ConsumptionMLModel`](file:///home/pierre/Projets/ems/custom_components/ems/ml/model.py#L160-L350) | Modèle Random Forest / Ensemble natif pour la consommation | `record_observation()`, `train()`, `predict_power_watts()` |
| [`model.py:SolarCalibrationModel`](file:///home/pierre/Projets/ems/custom_components/ems/ml/model.py#L360-L570) | Calibration bayésienne par heure + Random Forest solaire | `record_observation()`, `train()`, `calibrate_daily_forecasts()` |

## 🔄 Dépendances & Flux de Données
- **Features Consommation (13)** : $\sin/\cos(\text{heure})$, heure, $\sin/\cos(\text{jour de semaine})$, `dow`, `is_weekend`, $\sin/\cos(\text{jour de l'année 365.25j})$, mois, $T_{\text{ext}}$, $\text{HDD} = \max(0, 19 - T_{\text{ext}})$, $T_{\text{int\_avg}}$.
- **Features Solaire (8)** : $P_{\text{Solcast}}$, heure, $\sin/\cos(\text{heure})$, mois, $\sin/\cos(\text{doy})$, $T_{\text{ext}}$.
- **Auto-renforcement** : Buffer glissant en mémoire (`_online_X`, max 2000 échantillons), réentraînement périodique automatique toutes les heures (120 cycles) et persistance sur `/data/*.pkl`.

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Zero-Dependency Native Fallback** : Si `scikit-learn` et `numpy` sont indisponibles ou désactivés (`EMS_DISABLE_NUMPY=1`), `_NativeRandomForestRegressor` prend automatiquement le relais avec un arbre de régression purement Python sans planter le CPU.
- **Continuité Trigonométrique** : L'encodage $\sin/\cos$ sur $365.25$ jours garantit la continuité entre le 31 décembre et le 1er janvier.
- **Ratios Bayésiens Solaire** : L'étage solaire applique un lissage bayésien avec a priori $1.0$ (poids équivalent à $1500\text{ W}$ par heure) pour éviter les sur-ajustements lors des passages nuageux passagers.
