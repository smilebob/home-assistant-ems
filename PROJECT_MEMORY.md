# 🧠 Mémoire Globale du Projet : Smart Residential EMS (`home-assistant-ems`)

> **Dernière MAJ** : 2026-11-04 | **Statut** : En Production (Intégration HACS v1.1.3 & Add-on HA Ingress v2.0.6)

## 🎯 Vue d'Ensemble & Objectif
- **Description** : Système prédictif d'arbitrage énergétique résidentiel maximisant l'autoconsommation d'un ensemble solaire PV 7 kWc + batterie 15 kWh (`ha_felicity`), d'une PAC Mitsubishi Ecodan bi-zone + ECS (`esphome-ecodan-hp`), et d'un véhicule électrique (`teslafleet` + borne `local_tuya`). Piloté par prévisions Solcast (J+0 à J+2) et Machine Learning local.
- **Deux Modes d'Exécution Disponibles** :
  1. **Intégration HACS native** : Composant léger [`custom_components/ems/`](file:///home/pierre/Projets/ems/custom_components/ems/) (V1.1.3 en production).
  2. **Application Conteneurisée Découplée (Docker & Add-on HA Ingress)** : [`app/`](file:///home/pierre/Projets/ems/app/) et [`addon-ems/`](file:///home/pierre/Projets/ems/addon-ems/) (V2.0.6) avec backend FastAPI, WebSockets natifs, persistance SQLite WAL, interface React 18 + Tailwind + Apache ECharts intégrée en barre latérale Home Assistant.
- **Stack Technique** : Python 3.12+, FastAPI, WebSockets, SQLite 3 (WAL mode), Pure Python ML Ensemble, React 18, Vite, Apache ECharts, Tailwind CSS, Home Assistant Ingress.
- **Points d'Entrée** :
  - Intégration HACS : [`custom_components/ems/__init__.py`](file:///home/pierre/Projets/ems/custom_components/ems/__init__.py)
  - Application Conteneurisée : [`app/backend/main.py`](file:///home/pierre/Projets/ems/app/backend/main.py)

## 🚀 Commandes Essentielles
| Action | Commande | Notes / Env |
| :--- | :--- | :--- |
| **Tests Unitaires** | `python3 -m unittest discover tests -v` | 7 tests validant Arbitre, Contrôleurs, ML, Tarifs, et SQLite Storage |
| **Build Docker Multi-Arch** | `docker buildx build --platform linux/amd64,linux/arm64 -f app/Dockerfile -t ghcr.io/smilebob/home-assistant-ems:latest .` | Automatisé via GitHub Actions sur push `main` |
| **Service HA ML** | `service: ems.retrain_ml_model` ou `POST /api/ml/retrain` | Force le réapprentissage immédiat des modèles |

## 🗺️ Index des Sous-Modules (Cartographie Progressive Disclosure)
| Sous-Dossier / Module | Rôle & Responsabilité | Documentation Détaillée |
| :--- | :--- | :--- |
| `app/backend/` | Serveur FastAPI, orchestrateur 30s, stockage SQLite WAL, APIs REST/WS | [MEMORY.md](file:///home/pierre/Projets/ems/app/backend/MEMORY.md) |
| `app/frontend/` | Dashboard Ingress React 18, flux SVG animé, graphiques ECharts, remapping UI | [MEMORY.md](file:///home/pierre/Projets/ems/app/frontend/MEMORY.md) |
| `addon-ems/` | Packaging Add-on officiel Home Assistant (manifest, config.yaml, DOCS.md) | [DOCS.md](file:///home/pierre/Projets/ems/addon-ems/DOCS.md) |
| `custom_components/ems/` | Composant racine HACS, Config/Options Flow (Wizard + Onglets), Coordinateur 30s | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/MEMORY.md) |
| `custom_components/ems/core/` | Logique d'arbitrage 4 priorités, lissage anti-nuages et gestionnaire tarifaire | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/core/MEMORY.md) |
| `custom_components/ems/core/controllers/` | Pilotes matériels : Onduleur Felicity, PAC Ecodan Bi-Zone/ECS, Tesla Fleet / Tuya | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/core/controllers/MEMORY.md) |
| `custom_components/ems/ml/` | Pipeline de données (13 features trigonométriques) & Ensembles RandomForest / Bayésien | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/ml/MEMORY.md) |
| `custom_components/ems/frontend/` | Carte Lovelace personnalisée (`smart-residential-ems-card`) pour Lovelace natif | [MEMORY.md](file:///home/pierre/Projets/ems/custom_components/ems/frontend/MEMORY.md) |

## 📌 État Actuel & Fonctionnalités Clés
### ✅ Implémenté (v2.0.6)
- [x] **Add-on Home Assistant Ingress Portable** : Image multi-arch `ghcr.io/smilebob/home-assistant-ems:2.0.6` sans dépendance binaire lourde (`numpy`, `duckdb` proscrits pour compatibilité tout CPU sans crash `X86_V2` ou `SIGILL`).
- [x] **Stockage Séries Temporelles SQLite WAL** : Fichier autonome `/data/ems.db` enregistrant la télémétrie, les décisions et les observations solaires.
- [x] **Machine Learning Local & Auto-Renforcement Continu** :
  - 13 caractéristiques trigonométriques pour le jour de la semaine (`dow`, `is_weekend`, `sin/cos`) et de l'année (`doy`, `month`, `sin/cos` sur 365.25 jours) + sensibilité thermique (`HDD`).
  - Auto-calibration bayésienne des ombrages de toiture par créneau horaire sur Solcast.
  - Auto-renforcement automatique toutes les heures (120 cycles) et sauvegarde persistante sur `/data/*.pkl`.
- [x] **Courbes et Bilan Solaire Journalier (ECharts)** :
  - Sélecteur de mode : Solaire (Solcast vs Réel en W) et Consommation (Modèle ML vs Réel Maison en W).
  - Graphique à barres : Production journalière réelle vs prévision Solcast sur 7 jours avec taux de réalisation en %.
- [x] **Remapping Complet des Entités HA** :
  - Depuis l'onglet standard "Configuration" de l'Add-on HA (`addon-ems/config.yaml` + `fr.yaml`).
  - Directement depuis l'onglet "Configuration & Entités HA" du dashboard Ingress (`POST /api/config`).
- [x] **Cascade d'Arbitrage 4 Priorités & Séquencement IRVE Véhicule d'Abord** :
  1. Confort thermique & ECS solaire (11h–16h).
  2. Charge batterie Felicity 15 kWh jusqu'au SOC cible dynamique.
  3. Recharge VE : Consigne courant Tesla d'abord (`5A..16A`, rampe douce) $\rightarrow$ Confirmation HA $\rightarrow$ Contacteur borne Tuya.
  4. Stockage d'inertie thermique (dès `battery_soc >= 95%`) dans la dalle Zone 2 (`+1.0°C`) et Boost ECS (`55°C`).

## ⚠️ Pièges Globaux & Règles Métier Critiques
- **Compatibilité CPU Universelle** : Maintenir l'environnement conteneur exempt de bibliothèques compilées exigeant `x86-64-v2` ou `AVX` (`EMS_DISABLE_NUMPY=1`).
- **Séquencement Borne Tuya vs Tesla** : Ne jamais moduler l'ampérage directement sur la borne Tuya Local (risque de disjonction/mise en défaut du chargeur embarqué Tesla). La modulation d'intensité passe exclusivement par l'API Tesla Fleet via `number.sally_courant_de_recharge`.
- **Calcul Net du Surplus** : Toujours déduire la puissance active de charge EV de `house_load_w` lors du calcul de surplus solaire net.
- **Relance / Mise à Jour Add-on** : Lors de la publication d'une nouvelle version sur GitHub, forcer la détection dans Home Assistant via **Boutique des modules > 3 petits points > « Vérifier les mises à jour »**.
