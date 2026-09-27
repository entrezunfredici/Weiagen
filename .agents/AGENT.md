# AGENT.md — Directives pour agents IA

> Complété par `CONVENTIONS.md` (stack et périmètres) et `DECISIONS.md` (choix
> déjà pris). Ce dépôt a deux périmètres — lire `CONVENTIONS.md` en premier
> pour savoir lequel s'applique à la tâche en cours : déploiement
> (`docker-compose.yml`/`.env`) ou développement du plugin (`odoo-plugin/`,
> `skills-odoo/`).

---

## 1. Comportement général

### En début de session

Lire dans cet ordre avant toute action :

1. `AGENT.md` — ce fichier
2. `CONVENTIONS.md` — stack technique et périmètres du projet
3. `CHANGELOG_AGENT.md` — état actuel du déploiement et du plugin
4. `DECISIONS.md` — décisions déjà prises (ne pas les remettre en question sans raison)

### Avant de modifier du code

- Lire les fichiers concernés avant d'écrire une ligne.
- Si une information manque, **poser la question avant de coder** — pas d'hypothèse silencieuse.
- Toute modification qui change une interface publique du plugin (nom de
  tool, forme du JSON-Schema d'un paramètre, code d'erreur
  `ConnectorError`) **doit être signalée explicitement** avant d'être faite
  — les skills dans `skills-odoo/` documentent ces contrats mot pour mot.
- Avant de toucher à `odoo-plugin/w_main/`, `w_odoo/`, ou `docs-plugin/w_docs/`,
  vérifier que le besoin n'est pas déjà couvert (ce sont des modules courts
  et purs — voir `CONVENTIONS.md`). Renommés depuis `sdk_main`/`sdk_odoo`/
  `sdk_docs` le 2026-09-27 (retrait du préfixe `sdk_`, voir `DECISIONS.md`) —
  la promesse "portés tels quels depuis l'origine OpenClaw" ne porte donc
  plus que sur le **contenu**, plus sur le nom du dossier. Toute autre
  modification de ces trois paquets doit rester exceptionnelle et être
  documentée dans `DECISIONS.md`.

### Pendant le développement

- Travailler **un module à la fois**.
- Ne pas refactorer hors du périmètre de la tâche en cours.
- Ne pas ajouter de dépendance externe sans la signaler et justifier le choix
  (mettre à jour `odoo-plugin/requirements.txt`).
- Après tout ajout d'un nouveau dossier de skill sous `skills-odoo/`, vérifier
  que `docker-compose.yml` a bien une entrée `volumes:` pour ce dossier
  (les montages sont déclarés un par un, pas de wildcard).

### Après chaque modification — obligatoire

1. **Mettre à jour `CHANGELOG_AGENT.md`** — fichiers touchés, ce qui est
   utilisable, hypothèses posées, dette éventuelle.
2. **Mettre à jour `README.md`** si un changement est visible de l'extérieur
   (nouvelle commande, nouveau tool, nouvelle variable de déploiement).
3. **Mettre à jour `odoo-plugin/README.md`** si le changement touche le
   plugin spécifiquement (nouveau tool, nouvelle option CLI).

### En cas d'ambiguïté

- Priorité : respecter l'architecture existante > conventions du projet > concision.
- Si deux approches sont valides, choisir la plus simple et documenter le choix dans `DECISIONS.md`.

---

## 2. Spécificités de ce projet

### Modifier le déploiement Hermes (`docker-compose.yml`, `.env`)

1. Modifier le fichier concerné.
2. `docker compose up -d`
3. Vérifier les logs : `docker compose logs -f hermes`
4. Vérifier le dashboard sur `http://127.0.0.1:9119` si le changement le concerne.

### Modifier un tool du plugin `odoo` (`odoo-plugin/tools.py`, `__init__.py`)

1. Modifier le schéma/handler dans `tools.py`, ou le hook/registration dans
   `__init__.py`. **Import relatif obligatoire** pour ces deux fichiers
   depuis `__init__.py` (`from .tools import ...`, `from .cli import ...`) —
   un import absolu percute le paquet `tools` natif de Hermes (voir
   `CONVENTIONS.md`).
2. Aucun build — c'est du Python interprété, monté directement dans le
   container par `docker-compose.yml` (`./odoo-plugin:/opt/data/plugins/odoo:ro`).
   Un fichier modifié sur l'hôte est immédiatement visible dans le container.
3. Si le plugin n'était pas encore activé : `docker exec hermes
   /opt/hermes/.venv/bin/hermes plugins enable odoo`. Sinon, un
   `docker restart hermes` suffit pour qu'il recharge le code modifié (le
   plugin est chargé une fois par démarrage de process, pas par appel).
4. Si le tool touche à l'autorisation (`odoo_sdk_*`), vérifier aussi si le
   hook `pre_tool_call` (`_pre_tool_call` dans `__init__.py`) doit être mis
   à jour en cohérence (même liste de champs vérifiés que le handler).
5. Pour déboguer un échec de chargement silencieux : `docker exec -e
   HERMES_PLUGINS_DEBUG=1 hermes /opt/hermes/.venv/bin/hermes plugins list`
   (sans ça, une exception dans `register()` est juste avalée en debug log).

### Modifier la logique métier pure (`w_main/`, `w_odoo/`, `docs-plugin/w_docs/`)

- Ces trois paquets ne dépendent que de stdlib + `keyring`/`odoo-client-lib`/
  `openpyxl`/`python-docx`/`python-pptx` — aucune dépendance à Hermes ou à
  OpenClaw. Les modifier reste possible, mais toute modification structurante
  doit être actée dans `DECISIONS.md` (ce sont les modules les plus
  susceptibles d'être un jour republiés comme paquet pip indépendant).

### Modifier les skills (`skills-odoo/`)

1. Modifier le `SKILL.md` (ou les fichiers de référence associés,
   `templates/*.md`, `dev/*.md`) directement dans `skills-odoo/`.
2. Aucune commande nécessaire pour un skill déjà monté — le dossier est monté
   directement dans le container par `docker-compose.yml`, le fichier modifié
   est immédiatement lu au prochain skill_view/session Hermes.
3. Si un **nouveau** dossier de skill est ajouté sous `skills-odoo/`, il faut
   ajouter son entrée `volumes:` dans `docker-compose.yml` puis
   `docker compose up -d` pour que le montage prenne effet.

---

## 3. Sécurité

- **`.env` (racine) ne doit jamais être commité.** Vérifié par le
  `.gitignore` racine.
- Ne jamais exposer de secret (mot de passe Odoo, clé API,
  `HERMES_DASHBOARD_BASIC_AUTH_SECRET`) dans les logs, les réponses de tool,
  ou les messages de commit.
- Le port `9119` (dashboard Hermes) est mappé en `127.0.0.1` uniquement — ne
  jamais l'exposer en `0.0.0.0` sans reverse proxy authentifié.
- Toute right Odoo (`hermes odoo right add`) est **deny-by-default** — ne
  jamais créer de right avec `fields: ['*']` + `delete: true` sans
  `--require-confirmation`, sauf demande explicite.
- Les secrets Odoo (mot de passe/clé API) passent par le keyring fichier de
  `w_main/data_manager/secret_service.py`, jamais par `config.yaml` de
  Hermes en clair.

---

## 4. Ce que l'agent NE doit PAS faire

| Interdit | Raison |
| --- | --- |
| Committer `.env` | Contient des secrets |
| Réintroduire un mécanisme de confirmation maison (poll REST, popup) | Hermes a un mécanisme natif (`pre_tool_call` → approbation) — voir `DECISIONS.md` |
| Router les secrets Odoo via `config.yaml` de Hermes | Le keyring fichier existant suffit et est déjà en place |
| Réécrire les imports internes de `w_main`/`w_odoo`/`w_docs` en imports relatifs | Casse la compatibilité avec le `sys.path` bootstrap dans `__init__.py`, qui existe justement pour que ces paquets restent importables comme paquets top-level malgré le chargement `importlib` de Hermes |
| Exposer le dashboard (`9119`) hors `127.0.0.1` sans reverse proxy authentifié | Fuite de clés API |
| Ajouter une gestion de providers IA dans le plugin | Redondant avec le système natif de Hermes |

---

## 5. Checklist avant de considérer une tâche terminée

- [ ] Périmètre respecté (déploiement vs plugin — voir `CONVENTIONS.md`)
- [ ] Aucun secret exposé (logs, réponses, commits, fichiers)
- [ ] Si modification d'un tool : schéma JSON-Schema cohérent, handler testé
      manuellement (au moins un appel réussi + un cas d'erreur attendu)
- [ ] Si modification touchant l'autorisation : hook `pre_tool_call` revu en cohérence
- [ ] `docker-compose.yml` toujours cohérent avec la structure de dossiers (une entrée `volumes:` par dossier de skill)
- [ ] `CHANGELOG_AGENT.md` mis à jour
- [ ] `DECISIONS.md` mis à jour si un choix structurant a été fait
- [ ] `README.md` / `odoo-plugin/README.md` mis à jour si pertinent

---

## 6. Format de rapport de fin de tâche

```markdown
## Tâche — [Description courte]

**Ce qui a été fait** : ...
**Choix techniques** : ...
**Ce qui n'est PAS couvert** : ...
**Points d'attention** : ... (dette, risques, commandes nécessaires)
```
