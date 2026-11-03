# Smart Residential EMS (`home-assistant-ems`)

Intégration HACS clé en main pour **Home Assistant** dédiée à l'optimisation de l'autoconsommation solaire, la prédiction de consommation par **Machine Learning local** (sur 2 ans d'historique Recorder), et le pilotage coordonné de :
- **Onduleur Hybride & Batterie 15 kWh Felicity** (via [`ha_felicity`](https://github.com/partach/ha_felicity) en Modbus R/W)
- **Pompe à Chaleur Air-Eau Mitsubishi Ecodan Bi-Zone & ECS** (via [`esphome-ecodan-hp`](https://github.com/gekkekoe/esphome-ecodan-hp) en local CN105)
  - *Zone 1 (Étage)* : 3 chambres (Éléonore au Nord avec thermostat, Gaston, Parents) + Salle de bain en loi d'eau.
  - *Zone 2 (RDC)* : Grand salon avec plancher chauffant en mode auto-adaptatif (utilisé comme batterie thermique d'inertie en cas de fort excédent solaire).
  - *Eau Chaude Sanitaire (ECS)* : Planification solaire intelligente (11h00–15h00) et surchauffe thermique (55°C).
- **Mobilité Électrique : Tesla Fleet & Borne IRVE Local Tuya**
  - Alimentation sécurisée de la borne Tuya et **modulation douce de l'ampérage (5A à 16A/32A pas à pas) directement via `teslafleet`** pour éviter tout décrochage ou plantage de la borne lors des baisses de courant.
- **Prévisions Solaires Multi-Horizons (Solcast / Open-Meteo J+0, J+1, J+2)**

---

## Hiérarchie d'Arbitrage du Surplus Solaire

1. **Priorité 1 : Confort Thermique & Cycle ECS Quotidien** (fenêtre solaire 11h-15h où le COP de la PAC Ecodan et la production PV sont maximaux).
2. **Priorité 2 : Batterie Maison 15 kWh (`ha_felicity`)** jusqu'au **SOC Cible Dynamique** (calculé en croisant la consommation nocturne prédite par le modèle ML et les prévisions Solcast J+0/J+1 pour éviter tout achat réseau à 16,89 c€/kWh).
3. **Priorité 3 : Charge Solaire Tesla (`teslafleet`)** avec rampe progressive (+1A/-1A, temporisation anti-nuages et anti-court-cycle).
4. **Priorité 4 : Stockage Thermique d'Inertie** (+1°C sur le plancher chauffant du salon Zone 2 et Boost ECS à 55°C) avant toute injection réseau (rachetée seulement 4 c€/kWh).

---

## Évolutivité Tarifaire (Base $\rightarrow$ HP/HC $\rightarrow$ Dynamique)

Depuis l'interface de configuration ou via l'entité `select.ems_active_tariff_mode`, vous pouvez basculer instantanément entre :
- **`fixed`** : Tarif de Base actuel (16,89 c€/kWh achat, 4 c€/kWh injection).
- **`time_of_use`** : Tarif Heures Pleines / Heures Creuses ou Tempo.
- **`dynamic`** : Tarification spot horaire (Nordpool, Tibber, EPEX). Lorsque le prix descend sous le seuil configuré, l'EMS active automatiquement la charge forcée de la batterie Felicity (`Economic Mode`), le boost ECS et la charge Tesla.

---

## Installation (HACS ou Manuelle)

1. Copiez le dossier `custom_components/ems` dans le répertoire `config/custom_components/ems` de votre instance Home Assistant (ou ajoutez ce dépôt en tant que dépôt personnalisé dans **HACS $\rightarrow$ Intégrations**).
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres $\rightarrow$ Appareils et services $\rightarrow$ Ajouter une intégration** et recherchez **Smart Residential EMS**.
4. Choisissez au démarrage entre :
   - **L'Assistant pas-à-pas guidé (Wizard)**
   - **Le menu libre par onglets thématiques** (*Tarifs*, *Felicity*, *PAC Ecodan*, *Tesla & IRVE*, *Solcast & Machine Learning*).

---

## Carte Lovelace Clé en Main (`ems-card.js`)

L'intégration expose automatiquement la ressource `/ems_frontend/ems-card.js`.
Pour l'ajouter à votre tableau de bord :
1. Dans **Paramètres $\rightarrow$ Tableaux de bord $\rightarrow$ Ressources**, ajoutez `/ems_frontend/ems-card.js` (Type : *Module JavaScript*).
2. Ajoutez une carte personnalisée avec le code YAML suivant :

```yaml
type: custom:smart-residential-ems-card
title: Pilotage Énergétique Maison (EMS)
entity: sensor.ems_active_priority_state
```
