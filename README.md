# Ventes immobilières par quartier — Orléans

Une petite application web qui liste les quartiers d'Orléans et affiche, pour chaque
quartier, les ventes immobilières les plus récentes disponibles sur une carte.

## Comment ça marche (expliqué simplement)

Il y a 3 pièces qui s'emboîtent :

1. **Un robot qui va chercher les données** (`scripts/build_data.py`)
   Il télécharge automatiquement :
   - les ventes immobilières d'Orléans depuis **DVF** (la base officielle et
     gratuite du gouvernement — "Demandes de Valeurs Foncières") ;
   - les contours des 6 quartiers d'Orléans depuis **l'open data d'Orléans
     Métropole**.
   Il assemble tout ça et écrit 3 petits fichiers dans le dossier `data/` :
   `ventes.json`, `quartiers.geojson`, `meta.json`.

2. **Une tâche automatique** (`.github/workflows/update-data.yml`)
   Elle fait tourner le robot ci-dessus une fois par mois, tout seul, sur les
   serveurs de GitHub (gratuit). Si de nouvelles ventes sont publiées, les
   fichiers de données sont mis à jour automatiquement.

3. **La page web** (`index.html` + `assets/`)
   Une page avec la liste des quartiers à gauche et une carte à droite
   (via Leaflet + OpenStreetMap, gratuits). Elle affiche ce qu'il y a dans
   `data/`. Cliquer sur un quartier zoome la carte sur ce quartier et
   n'affiche que ses ventes.

Aucun serveur à payer, aucune base de données à gérer : tout est constitué
de fichiers statiques, ce qui permet un hébergement gratuit (GitHub Pages).

## Un point important : le délai des données

La base officielle DVF n'est pas publiée en temps réel : une vente met
entre **6 et 18 mois** à apparaître dans les données (c'est le temps que le
notariat et les impôts traitent le dossier), pour toute la France, pas
seulement Orléans. "La dernière année" affichée dans l'application veut
donc dire : les 365 jours les plus récents **parmi les données publiées**,
pas les 365 derniers jours calendaires. La période exacte couverte est
toujours affichée en haut de la page.

## Mettre l'application en ligne (une seule fois)

1. Aller dans les paramètres du dépôt GitHub : **Settings → Pages**.
2. Dans "Build and deployment", choisir **Deploy from a branch**.
3. Choisir la branche `main` (ou celle qui sera fusionnée) et le dossier
   `/ (root)`.
4. Enregistrer. GitHub donne une adresse du type
   `https://<utilisateur>.github.io/<nom-du-depot>/` — c'est l'adresse de
   votre application.

À partir de là, chaque mise à jour des données (automatique ou manuelle)
republie la page toute seule.

## Lancer une mise à jour des données manuellement

Dans l'onglet **Actions** du dépôt GitHub, choisir le workflow
"Mise à jour des données immobilières" puis cliquer sur **Run workflow**.

## Lancer le robot sur son propre ordinateur (optionnel)

```bash
pip install -r scripts/requirements.txt
python scripts/build_data.py
```
