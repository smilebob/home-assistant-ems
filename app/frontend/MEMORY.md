# 📦 Mémoire du Module : Frontend Application EMS (`app/frontend/`)

> **Dossier** : `app/frontend/` | **Dernière MAJ** : 2026-11-04 | **Version** : v2.0.6

## 🎯 Rôle & Responsabilité
Tableau de bord interactif React 18 / Tailwind CSS / Apache ECharts / Lucide, compilé via Vite en bundle statique (`dist/`) et servi directement par FastAPI sous Home Assistant Ingress ou en autonome sur le port 8080.

## 🗂️ Fichiers & Composants Clés
| Composant | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [`App.jsx`](file:///home/pierre/Projets/ems/app/frontend/src/App.jsx) | Conteneur principal, WebSocket client, gestion des 5 onglets | Onglets : `overview`, `ml`, `ecodan-ev`, `decisions`, `settings` |
| [`PowerFlow.jsx`](file:///home/pierre/Projets/ems/app/frontend/src/components/PowerFlow.jsx) | Diagramme de flux de puissance SVG animé (Solar, Battery, House, Grid, PAC, Tesla) | `state` temps réel (Watts, SoC, modes) |
| [`SolcastMLChart.jsx`](file:///home/pierre/Projets/ems/app/frontend/src/components/SolcastMLChart.jsx) | Graphiques ECharts : Prédiction vs Réel (W) & Comparatif journalier (kWh sur 7 jours) + bouton Réentraîner | `state`, `history`, fetch `./api/history/daily-solar`, `./api/ml/retrain` |
| [`SettingsView.jsx`](file:///home/pierre/Projets/ems/app/frontend/src/components/SettingsView.jsx) | Formulaire interactif de remapping des entités HA et seuils d'arbitrage | `GET /api/config`, `POST /api/config` |

## 🔄 Dépendances & Flux de Données
- **WebSocket** : Écoute `ws://.../ws` (ou Ingress relative path) avec reconnexion automatique en 4s.
- **REST APIs** : `./api/state`, `./api/history?hours=24`, `./api/decisions?limit=30`, `./api/history/daily-solar`, `./api/config`, `./api/action`.
- **Bibliothèques UI** : `lucide-react`, `echarts-for-react`, `tailwindcss`.

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Ingress Sub-pathing** : Tous les appels d'API et WebSocket doivent utiliser des chemins relatifs (`./api/...`) ou détecter `window.location.pathname` pour fonctionner de manière transparente derrière le proxy d'Ingress de Home Assistant (`/api/hassio_ingress/.../`).
- **Compilation Multi-Stage** : Construit dans l'étape 1 du Dockerfile (`FROM node:20-alpine AS frontend-builder`), ne nécessite aucune installation de Node.js sur l'hôte.
