# 📦 Mémoire du Module : Backend Application EMS (`app/backend/`)

> **Dossier** : `app/backend/` | **Dernière MAJ** : 2026-11-04 | **Version** : v2.0.6

## 🎯 Rôle & Responsabilité
Backend asynchrone découplé en FastAPI orchestrant la boucle d'arbitrage EMS de 30 secondes, le stockage de séries temporelles sous SQLite natif, l'apprentissage continu par renforcement (Machine Learning & Solcast), l'accès REST & WebSockets pour le tableau de bord Ingress, et la synchronisation avec Home Assistant et MQTT.

## 🗂️ Fichiers & Composants Clés
| Fichier | Rôle | Entrées / Sorties Principales |
| :--- | :--- | :--- |
| [`main.py`](file:///home/pierre/Projets/ems/app/backend/main.py) | Point d'entrée FastAPI, endpoints REST, streaming `/ws`, gestion Ingress | `GET /api/state`, `GET /api/history`, `POST /api/config`, `POST /api/ml/retrain` |
| [`engine.py`](file:///home/pierre/Projets/ems/app/backend/engine.py) | Moteur d'arbitrage 30s (`EMSEngine`), boucle d'auto-renforcement | `execute_arbitration_cycle()`, `retrain_models()` |
| [`storage.py`](file:///home/pierre/Projets/ems/app/backend/storage.py) | Couche de persistance SQLite WAL (`EMSStorage`) sans dépendance binaire | `record_telemetry()`, `get_daily_solar_comparison()`, `get_hourly_training_dataset()` |
| [`config.py`](file:///home/pierre/Projets/ems/app/backend/config.py) | Schéma Pydantic `EMSConfig`, chargement `/data/options.json` ou `config.json` | `load_config() -> EMSConfig` |
| [`ha_client.py`](file:///home/pierre/Projets/ems/app/backend/ha_client.py) | Client asynchrone REST & WebSocket vers Home Assistant | `subscribe_events()`, `call_service()`, `get_states()` |
| [`mqtt_client.py`](file:///home/pierre/Projets/ems/app/backend/mqtt_client.py) | Client MQTT avec publication d'état et Auto-Discovery HA | `publish_state()`, `publish_discovery()` |

## 🔄 Dépendances & Flux de Données
- **Dépend de** : [`custom_components.ems.core.arbitrator`](file:///home/pierre/Projets/ems/custom_components/ems/core/arbitrator.py), [`custom_components.ems.ml.model`](file:///home/pierre/Projets/ems/custom_components/ems/ml/model.py), [`sqlite3`](https://docs.python.org/3/library/sqlite3.html).
- **Consommé par** : Interface React frontend ([`app/frontend/`](file:///home/pierre/Projets/ems/app/frontend/)), Home Assistant Ingress, broker MQTT.
- **Base de données** : Fichier SQLite `/data/ems.db` (tables `telemetry`, `decision_log`, `solar_observations`).

## ⚠️ Pièges & Consignes du Module (Gotchas)
- **Zero Heavy Binary Dependencies** : Ne JAMAIS importer `numpy`, `scikit-learn` ou `duckdb` dans ce conteneur. L'environnement force `EMS_DISABLE_NUMPY=1` et utilise le fallback purement natif Python (`_NativeRandomForestRegressor`) pour garantir une compatibilité totale sans crash CPU (pas d'erreur `X86_V2` ou `SIGILL 132`).
- **Remapping Dynamique** : `POST /api/config` met à jour l'instance `config` en mémoire ET sauvegarde sur `/data/options.json` pour persister au redémarrage.
- **Auto-renforcement** : La méthode `engine.retrain_models()` s'exécute automatiquement toutes les 120 boucles (1h) et agrège les données SQLite des 30 derniers jours avec le buffer glissant de 2000 observations.
