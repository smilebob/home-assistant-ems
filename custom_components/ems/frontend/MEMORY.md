# 📦 Mémoire du Module : Carte Lovelace (`frontend`)

> **Dossier** : `custom_components/ems/frontend/` | **Dernière MAJ** : 2026-11-03

## 🎯 Rôle & Responsabilité
Fournit la Custom Lovelace Card (`smart-residential-ems-card`) affichant en temps réel les flux PV/Batterie/Réseau, le statut PAC Ecodan Bi-Zone & Tesla Fleet, les prévisions Solcast (J+0/J+1/J+2) vs Machine Learning (24h), et les boutons d'action rapide.

## 🗂️ Fichiers & Composants Clés
| Fichier / Export | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [ems-card.js](file:///home/pierre/Projets/ems/custom_components/ems/frontend/ems-card.js#L1-L263) | Web Component `SmartResidentialEMSCard` (`custom:smart-residential-ems-card`) | Lit `sensor.ems_active_priority_state` + ses `extra_state_attributes` |

## 🔄 Dépendances & Flux de Données
- **Servi par** : [`__init__.py`](file:///home/pierre/Projets/ems/custom_components/ems/__init__.py#L36-L48) sur l'URL statique `/ems_frontend/ems-card.js`.
- **Services appelés** : `homeassistant.toggle` (sur les 4 switches EMS) et `ems.retrain_ml_model`.

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Source unique d'attributs** : Pour minimiser la configuration utilisateur dans Lovelace, toutes les métriques temps réel sont exposées dans `extra_state_attributes` de l'entité principale `sensor.ems_active_priority_state` (voir [`sensor.py:L119-L147`](file:///home/pierre/Projets/ems/custom_components/ems/sensor.py#L119-L147)).
