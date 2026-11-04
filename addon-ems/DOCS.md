# Home Assistant Add-on: Smart Residential EMS (Dashboard & Arbitrage)

Application conteneurisée d'arbitrage énergétique résidentiel haute performance avec tableau de bord temps réel plein écran intégré à la barre latérale de Home Assistant (Ingress).

Compatible multi-architecture (`amd64`, `aarch64`) sur tout type de CPU sans exigence de jeu d'instructions avancé (pas de dépendance AVX/x86_v2).

---

## 🌟 Fonctionnalités Principales

### 1. Tableau de Bord Ingress Interactif (5 Onglets)
- **⚡ Pilotage & Flux (Overview)** :
  - Diagramme SVG animé des transferts de puissance en direct (Panneaux PV 7 kWc, Batterie Felicity 15 kWh, Réseau Enedis, Maison, PAC Ecodan, Tesla Sally).
  - Bandeau d'explication en français de la décision d'arbitrage active et des actions en cours.
  - Interrupteurs de forçage manuel (Mode Auto ON/OFF, Forçage ECS Boost, Forçage Charge Tesla, Surchauffe thermique).
- **📈 Solcast & Machine Learning** :
  - **Courbes en temps réel (Watts)** : Sélecteur instantané *Solaire (Solcast calibré vs Réel onduleur)* et *Consommation (Modèle ML vs Réel maison)*.
  - **Comparatif de production journalière (kWh)** : Barres comparatives sur 7 jours avec taux de réalisation en % et écart net.
  - **Auto-renforcement continu** : Apprentissage en ligne permanent (prise en compte du jour de la semaine et de l'année) + bouton *« Réentraîner maintenant »*.
- **🔥 PAC Ecodan & Mobilité VE** :
  - Suivi des températures de consigne et d'ambiance Zone 1 (Étage) et Zone 2 (Salon).
  - Température et état de forçage du ballon ECS thermodynamique.
  - État de branchement, niveau de batterie et ampérage dynamique de la Tesla Sally.
  - Conseiller d'équilibrage thermique des radiateurs Zone 1 (Chambres Éléonore, Gaston, Parents).
- **📜 Timeline des Décisions** :
  - Journal chronologique persistant des transitions de priorité et des motifs d'arbitrage.
- **⚙️ Configuration & Entités HA** :
  - Formulaire visuel permettant de remapper à chaud n'importe quelle entité Home Assistant (capteurs PV, batterie, PAC, Tesla, Solcast) sans redémarrer le conteneur.

### 2. Architecture & Robustesse
- **Zéro charge sur le thread Home Assistant** : Le moteur tourne dans son conteneur indépendant via FastAPI et WebSockets asynchrones.
- **Stockage Séries Temporelles SQLite WAL** : Base de données locale autonome (`/data/ems.db`) sans dépendance binaire lourde.
- **Passerelle MQTT Universelle** : Envoi des métriques et publication Auto-Discovery Home Assistant.

---

## ⚙️ Configuration & Remapping des Entités

Deux méthodes équivalentes sont proposées pour adapter le module à votre installation :

### Méthode A : Depuis le Dashboard Ingress (Recommandé)
1. Ouvrez **Smart EMS** dans la barre latérale.
2. Allez sur le 5ᵉ onglet : **« Configuration & Entités HA »**.
3. Modifiez vos identifiants d'entités ou vos seuils d'arbitrage.
4. Cliquez sur **« Sauvegarder & Appliquer »**. Les modifications sont immédiatement actives et sauvegardées dans `/data/options.json`.

### Méthode B : Depuis l'onglet standard « Configuration » de l'Add-on
1. Dans Home Assistant, allez dans **Paramètres** > **Modules complémentaires** > **Smart Residential EMS**.
2. Cliquez sur l'onglet **« Configuration »**.
3. Chaque entité et chaque paramètre d'arbitrage dispose d'un champ avec description en français.
4. Modifiez les valeurs et cliquez sur **Enregistrer**, puis redémarrez l'add-on.

---

## 📋 Référence des Paramètres d'Arbitrage

| Paramètre | Description | Défaut |
| :--- | :--- | :--- |
| `battery_capacity_kwh` | Capacité totale utilisable du banc de batterie (kWh) | `15.0` |
| `battery_min_soc` | Réserve de sécurité minimale de la batterie (%) | `15.0` |
| `battery_target_soc_ev` | Niveau de batterie requis avant d'autoriser la recharge VE solaire (%) | `80.0` |
| `battery_thermal_soc_threshold` | Seuil SOC requis pour autoriser le stockage thermique d'inertie (%) | `95.0` |
| `dhw_normal_temp` | Consigne normale confort du ballon ECS (°C) | `50.0` |
| `dhw_boost_temp` | Consigne de surchauffe ECS en surplus ou tarif bas (°C) | `55.0` |
| `dhw_solar_window_start` | Début de la fenêtre solaire prioritaire ECS (heure) | `11` |
| `dhw_solar_window_end` | Fin de la fenêtre solaire prioritaire ECS (heure) | `16` |
| `z2_max_overheat_offset` | Rehausse maximale autorisée sur le plancher chauffant Zone 2 (°C) | `1.0` |
| `grid_import_price_fixed` | Prix d'achat fixe du kWh réseau (€) | `0.1689` |
| `grid_export_price_fixed` | Tarif d'achat du surplus solaire injecté (€) | `0.0400` |
