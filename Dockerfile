# Image custom pour le déploiement sur un serveur distant qui n'a pas ce
# dépôt cloné sur disque (donc pas de bind mount possible). Le déploiement
# local (docker-compose.yml) continue d'utiliser l'image publiée +
# bind mounts en lecture seule — voir DECISIONS.md, "Aucun rebuild d'image
# n'est jamais nécessaire" reste vrai pour ce chemin-là. Cette image-ci ne
# sert QUE le déploiement serveur (docker-compose.server.yml).
#
# Tag de base épinglé (pas ":latest") pour la reproductibilité — voir
# DECISIONS.md pour la procédure de mise à jour délibérée.
FROM nousresearch/hermes-agent:v2026.7.20

# Plugin "bundled" (au lieu de "user" comme en dev) : /opt/hermes/plugins/
# est le dossier scanné par get_bundled_plugins_dir() (hermes_cli/plugins.py)
# — même emplacement que les plugins bundled natifs (kanban, etc.).
COPY odoo-plugin/ /opt/hermes/plugins/odoo/

# Plugin générique d'autorisation deny-by-default — odoo-plugin délègue ses
# checks de droits à celui-ci (voir DECISIONS.md, "rights-plugin: vendoring
# vs cross-plugin import"). Doit toujours être activé en même temps
# qu'odoo-plugin : sans lui, tout CRUD Odoo est refusé (fail closed).
# Depuis le 2026-09-22 (voir DECISIONS.md, "rights-plugin : signature EdDSA
# pour les jetons d'identité MCP"), dépend de `cryptography` — installée
# explicitement ci-dessous (ligne 61+) plutôt que de compter sur le fait
# qu'odoo-plugin la déclare déjà dans le même venv : une dépendance déclarée
# par ce plugin doit être installée pour ce plugin, pas héritée par hasard.
COPY rights-plugin/ /opt/hermes/plugins/rights/

# rights-plugin/dashboard/dist/index.js est un fichier GÉNÉRÉ (assemblé
# depuis dashboard/src/*.js par dashboard/build.sh, jamais édité à la main —
# voir DECISIONS.md, 2026-08-18). Régénéré ici à la construction de l'image,
# en ceinture-et-bretelles avec le job CI qui échoue si le dist/index.js
# commité dérive de src/ : même si ce garde-fou était contourné, l'image
# figée transférée sur test-server est toujours reconstruite fraîche depuis src/
# à ce moment précis (le serveur cible n'a pas de dépôt cloné — il ne
# fait que lancer l'image reçue, jamais de build lui-même).
RUN sh /opt/hermes/plugins/rights/dashboard/build.sh

# Journal d'audit append-only et chaîné par hash de chaque appel de tool (y
# compris ceux bloqués par rights-plugin) et de chaque décision
# d'approbation. Indépendant de rights-plugin, stdlib uniquement (aucune
# ligne à ajouter au `uv pip install` ci-dessous) — voir DECISIONS.md,
# 2026-09-24. Même activation manuelle : `hermes plugins enable audit`.
COPY audit-plugin/ /opt/hermes/plugins/audit/

# Génération de documents bureautiques (xlsx/docx/pptx), sortie
# d'odoo-plugin le 2026-09-24 (voir DECISIONS.md) — ses dépendances
# (openpyxl, python-docx, python-pptx) sont installées plus bas avec les
# autres. Activation manuelle : `hermes plugins enable docs`.
COPY docs-plugin/ /opt/hermes/plugins/docs/

# Skills : /opt/hermes/skills/ est le dossier "bundled" source
# (get_bundled_skills_dir()) que le hook de démarrage du container
# (docker/stage2-hook.sh -> tools/skills_sync.py) recopie automatiquement
# dans $HERMES_HOME/skills/ à chaque boot — c'est ce qui les rend
# découvrables sans bind mount ni étape d'installation supplémentaire.
COPY skills-odoo/odoo /opt/hermes/skills/odoo
# odoo-sdk, odoo-crm, odoo-hr, odoo-accounting et odoo-inventory ne sont pas
# (encore) versionnés dans skills-odoo/ : les COPY sont retirés pour ne pas
# casser le build. À rétablir une fois les dossiers committés.
COPY skills-odoo/odoo-dev /opt/hermes/skills/odoo-dev

# How rights-plugin gates tool calls/cron jobs and how to react to a block
# — same always-discoverable mechanism as the skills-odoo/ skills above
# (see .agents/DECISIONS.md, 2026-08-19: added after Fred caught the
# agent spending 12 minutes gathering cron details before ever finding
# out it was going to be denied).
COPY skills-rights/rights /opt/hermes/skills/rights

# Skill du plugin docs (anciennement skills-odoo/odoo-docs). skills_sync ne
# supprime PAS l'ancienne copie `odoo-docs` déjà synchronisée dans
# $HERMES_HOME/skills/ — nettoyage manuel une fois sur chaque déploiement existant.
COPY skills-docs/docs /opt/hermes/skills/docs

# Dépendances du plugin installées au build (dans le venv scellé de l'image,
# root-owned) au lieu d'un `uv pip install` manuel après coup — elles
# survivent donc à un `docker compose up -d --force-recreate` ou une
# recréation de container, contrairement au déploiement dev (voir
# DECISIONS.md, dette "dépendances non persistantes").
RUN uv pip install --python /opt/hermes/.venv/bin/python \
    -r /opt/hermes/plugins/odoo/requirements.txt \
    -r /opt/hermes/plugins/rights/requirements.txt \
    -r /opt/hermes/plugins/docs/requirements.txt

# Les plugins restent opt-in par défaut même "bundled" (aucun mécanisme
# d'activation automatique côté Hermes) — `hermes plugins enable odoo`,
# `hermes plugins enable rights`, `audit` ET `docs` restent des étapes manuelles une fois par
# volume de données, voir README.md.
