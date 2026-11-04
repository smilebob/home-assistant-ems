# Home Assistant Add-on: Smart Residential EMS

Application conteneurisée d'arbitrage énergétique résidentiel haute performance avec tableau de bord temps réel plein écran intégré à la barre latérale de Home Assistant (Ingress).

## Fonctionnalités

- **Flux d'énergie SVG animé en direct** : Visualisation en temps réel des transferts entre le Soleil, la Batterie (Felicity 15 kWh), la Maison, le Réseau Enedis, la PAC Mitsubishi Ecodan et la Tesla Sally.
- **Courbes Apache ECharts haute résolution** :
  - Prédiction de consommation sur 24h par Machine Learning (modèle Ridge local).
  - Auto-calibration en temps réel du prévisionnel Solcast vs production réelle.
- **Zéro redémarrage de Home Assistant** : Le moteur tourne dans son conteneur Docker dédié. Les mises à jour et les calculs ML lourds ne sollicitent pas le thread principal de Home Assistant.
- **Passerelle MQTT universelle** : Publication automatique des métriques et création des entités dans Home Assistant via MQTT Auto-Discovery.
- **Stockage DuckDB persistant** : Base de données ultra-rapide conservant des mois d'historique indépendamment du recorder de HA.

## Configuration

L'add-on utilise automatiquement l'API Supervisor interne (`http://supervisor/core`) et son jeton sécurisé. Si vous disposez d'un broker Mosquitto, activez simplement l'option `mqtt_enabled: true`.
