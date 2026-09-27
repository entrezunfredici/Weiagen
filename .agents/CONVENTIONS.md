# CONVENTIONS.md — Conventions du projet weiagen_hermes

> Fichier spécifique à ce dépôt. Lire avant toute implémentation.
> Pour les conventions de code internes à Hermes Agent lui-même (upstream,
> non vendorisé dans ce dépôt), voir directement
> [https://github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — ce dépôt ne les duplique pas.

---

## Nature du dépôt

`weiagen_hermes` a cinq périmètres, chacun gouverné différemment :

```text
weiagen_hermes/
├── README.md
├── CLAUDE.md                # point d'entrée agent (délègue à .agents/)
├── .agents/                  # ce dossier — gouverne les DEUX périmètres ci-dessous
│   ├── AGENT.md
│   ├── CONVENTIONS.md        # ce fichier
│   ├── CHANGELOG_AGENT.md
│   └── DECISIONS.md
│
├── docker-compose.yml        # PÉRIMÈTRE 1 : déploiement Hermes (local, bind mounts)
├── docker-compose.server.yml # déploiement serveur distant (image custom, pas de bind mount)
├── Dockerfile                 # bake odoo-plugin/ + rights-plugin/ + skills-odoo/* +
│                              # skills-rights/* + deps — sert UNIQUEMENT
│                              # docker-compose.server.yml, voir DECISIONS.md
├── .dockerignore
├── .env                      # secrets du déploiement (jamais en git)
│
├── odoo-plugin/               # PÉRIMÈTRE 2 : plugin Hermes "odoo"
│   ├── plugin.yaml
│   ├── __init__.py            # register(ctx)
│   ├── tools.py                # schémas JSON-Schema + handlers
│   ├── cli.py                  # `hermes odoo profile/right ...`
│   ├── dashboard/               # UI web (manifest.json + plugin_api.py FastAPI + dist/index.js)
│   ├── w_main/                # moteur CRUD/secrets/table (pur, portable)
│   ├── w_odoo/                 # connecteur Odoo (pur, portable) + rights_bridge.py
│   │                              # (pont vers rights-plugin, voir Périmètre 3)
│   ├── requirements.txt           # (w_docs/ et ses deps sont partis dans docs-plugin/)
│   └── README.md
├── rights-plugin/              # PÉRIMÈTRE 3 : plugin Hermes "rights"
│   ├── plugin.yaml
│   ├── __init__.py             # register(ctx) — hooks pre_tool_call + pre_llm_call
│   ├── models.py                # RoleBinding, AccessRight
│   ├── engine.py                 # check_right() — moteur de décision deny-by-default
│   ├── identity.py                # resolve_identity()
│   ├── cli.py                      # `hermes rights role/right/check/whoami ...`
│   ├── dashboard/                   # UI web "Access Groups" (même pattern qu'odoo-plugin/dashboard/)
│   ├── rights_w_main/              # copie VENDORÉE de w_main/ (nom différent — voir DECISIONS.md,
│   │                                  # collision sys.modules) + opération "execute" en plus
│   ├── rights_plugin_api.py           # contrat public stable, seul point d'import cross-plugin
│   ├── migrate_odoo_rights.py          # migration idempotente des anciens OdooRight
│   ├── requirements.txt               # vide (stdlib uniquement)
│   └── README.md
├── audit-plugin/               # PÉRIMÈTRE 4 : plugin Hermes "audit"
│   ├── plugin.yaml
│   ├── __init__.py             # register(ctx) — hooks post_tool_call + post_approval_response
│   ├── audit_store.py           # SQLite append-only + chaîne de hash, retention/purge
│   ├── audit_redact.py           # masquage des arguments (clés sensibles + redacteur Hermes)
│   ├── audit_identity.py          # session_id -> (platform, user_id), SANS passer par rights
│   ├── cli.py                      # `hermes audit list/stats/verify/purge`
│   ├── tools.py                     # `audit_search` (opt-in, AUDIT_AGENT_TOOL_ENABLED)
│   ├── dashboard/                    # onglet "Audit" lecture seule (dist/index.js écrit à la main, pas de build)
│   ├── requirements.txt              # vide (stdlib uniquement)
│   └── README.md
├── docs-plugin/                # PÉRIMÈTRE 5 : plugin Hermes "docs"
│   ├── plugin.yaml
│   ├── __init__.py             # register(ctx) — les 6 tools docs_*
│   ├── tools.py                 # schémas + handlers (tag MEDIA, codes d'erreur)
│   ├── docs_paths.py             # politique d'écriture (cache documents + DOCS_OUTPUT_DIRS)
│   ├── w_docs/                  # génération/lecture xlsx/docx/pptx (pur, portable — déplacé
│   │                              # tel quel depuis odoo-plugin le 2026-09-24)
│   ├── requirements.txt           # openpyxl, python-docx, python-pptx
│   └── README.md
├── skills-odoo/                # skills installés tels quels (pas via le plugin)
│   ├── odoo/, odoo-sdk/, odoo-crm/, odoo-hr/, odoo-accounting/,
│   │   odoo-inventory/, odoo-dev/
├── skills-docs/                 # même mécanisme, pour docs-plugin
│   └── docs/                     # skill "docs-generator" (ex skills-odoo/odoo-docs/)
├── skills-rights/               # même mécanisme que skills-odoo/, pour rights-plugin
│   └── rights/                   # comment rights-plugin gate les tool calls/crons,
│                                  # comment réagir à un blocage (voir DECISIONS.md,
│                                  # 2026-08-19)
└── skills/                     # skills Hermes génériques, non liés à Odoo (sauvegarde
                                 # portable — pas de bind mount ni de COPY Dockerfile,
                                 # à copier manuellement vers ~/.hermes/skills/ sur tout
                                 # déploiement où on les veut)
    └── mcp-tool-discovery/
```

**Périmètre 1 — déploiement.** `docker-compose.yml` + `.env` déploient
Hermes Agent (NousResearch) via l'image publiée `nousresearch/hermes-agent`
— pas de build source, pas de clone du code upstream dans ce dépôt (voir
`DECISIONS.md`). Pour toute question sur le fonctionnement interne de Hermes
lui-même, se référer au dépôt upstream, pas à ce dossier.

**Périmètre 2 — développement du plugin `odoo`.** `odoo-plugin/` et
`skills-odoo/` sont **notre code**, écrit pour l'API de plugin Hermes
(`plugin.yaml` + `__init__.py::register(ctx)`, `ctx.register_tool()`,
`ctx.register_hook()`, `ctx.register_cli_command()`). C'est un portage d'un
plugin OpenClaw antérieur (Odoo + génération de documents bureautiques) —
voir `DECISIONS.md` pour le détail de ce qui a été gardé, jeté, et pourquoi.
**Depuis le 2026-08-13, ce plugin ne possède plus aucune logique
d'autorisation propre** (`w_odoo/odoo_rights.py` supprimé) — il délègue
entièrement au Périmètre 3 ci-dessous via `w_odoo/rights_bridge.py`.

**Périmètre 3 — développement du plugin `rights`.** `rights-plugin/` est
**notre code**, un second plugin Hermes générique et Odoo-agnostique
(identité → rôle(s), rôle → droit sur une ressource), qui remplace
entièrement l'ancien système `OdooRight`. `odoo-plugin` en est un
**consommateur**, pas un propriétaire — voir `DECISIONS.md` ("rights-plugin
: vendoring vs import cross-plugin") pour l'architecture complète
(vendoring de la base `w_main` sous un nom différent, pont cross-plugin
via `rights_plugin_api`, règle de combinaison multi-rôles "le plus
permissif gagne", migration automatique des anciens `OdooRight`). Les deux
plugins doivent **toujours** être activés ensemble : `rights-plugin`
n'existe pas dans le vide (il n'a de sens que pour des plugins qui
délèguent chez lui), et `odoo-plugin` échoue fermé sans lui.

**Périmètre 4 — développement du plugin `audit`.** `audit-plugin/` est
**notre code** : un journal d'audit append-only, chaîné par hash, de chaque
appel de tool (y compris ceux bloqués par `rights`) et de chaque décision
d'approbation, dans un fichier SQLite local. **Volontairement indépendant de
`rights-plugin`** (aucun import de `rights_plugin_api`) : l'audit doit
continuer à enregistrer *qui* fait quoi même si `rights` est désactivé ou
cassé. Plugin plutôt que microservice, choix documenté dans `DECISIONS.md`
(2026-09-24), avec la condition qui ferait basculer vers un service séparé.

**Périmètre 5 — développement du plugin `docs`.** `docs-plugin/` est
**notre code** : création/lecture de fichiers xlsx/docx/pptx, sorti
d'`odoo-plugin` le 2026-09-24 (aucune dépendance à Odoo). `w_docs/` y est
déplacé **tel quel** (même promesse "porté depuis OpenClaw" que
`w_main`/`w_odoo`) ; les noms de tools et leurs arguments sont
inchangés. Nouveauté : les fichiers sont écrits dans le cache documents de
Hermes et renvoyés avec un tag `MEDIA:<chemin>` que l'agent recopie dans sa
réponse pour que le gateway joigne le fichier — voir `DECISIONS.md`
(2026-09-24).

**`skills/` — bibliothèque portable, hors périmètre.** Skills Hermes
généraux (pas spécifiques à Odoo) gardés ici uniquement pour ne pas les
perdre. Contrairement à `skills-odoo/`, rien ne les déploie automatiquement
— pas de bind mount dans `docker-compose*.yml`, pas de `COPY` dans le
`Dockerfile`. Pour les utiliser sur un déploiement Hermes donné, les copier
à la main dans `~/.hermes/skills/<nom>/` sur cet hôte.

---

## Comment le plugin atteint le container en cours d'exécution

Les plugins et skills utilisateur Hermes se chargent depuis
`~/.hermes/plugins/<name>/` et `~/.hermes/skills/<name>/` (le volume
`${HOME}/.hermes:/opt/data`). **`docker-compose.yml` monte `odoo-plugin/`,
`rights-plugin/` et chaque dossier de `skills-odoo/` directement en bind
mount** (`ro`) à ces emplacements précis — voir les entrées `volumes:` du
service `hermes`. Le nom du dossier monté diffère entre les deux chemins de
déploiement : `plugins/odoo`/`plugins/rights` en local
(`docker-compose.yml`) contre les mêmes noms via `COPY` dans le `Dockerfile`
(déploiement serveur) — le nom de répertoire du checkout local
(`rights-plugin/`) et celui monté dans le container (`rights`) diffèrent
volontairement ; c'est pour ça que `rights_bridge.py` essaie les deux noms
au lieu d'en coder un seul en dur (voir `DECISIONS.md`).

Une première version symlinkait ces dossiers depuis `~/.hermes` via un
script `install.sh` — **abandonné** : un symlink écrit dans le volume
`~/.hermes` mais pointant vers un chemin hors de ce volume (le clone git de
ce dépôt) ne se résout pas à l'intérieur de l'espace de noms de montage du
container. Voir `DECISIONS.md` pour le détail du bug et la correction. Le
bind mount direct n'a pas ce problème et ne dépend pas du chemin où le dépôt
est cloné sur l'hôte. **Aucun rebuild d'image n'est jamais nécessaire** pour
faire évoluer le plugin ou les skills sur ce déploiement **local** — c'est
la raison d'être de cette architecture.

Pour un **serveur distant** qui n'a pas ce dépôt cloné (donc pas de bind
mount possible), un second chemin de déploiement existe :
`docker-compose.server.yml` + `Dockerfile` (bake le plugin/les skills/leurs
dépendances dans une image custom poussée sur le GitHub Container Registry
(`ghcr.io`) du projet). Là, contrairement au déploiement local, un rebuild + push + pull
**est** nécessaire à chaque changement du plugin/des skills — voir
`DECISIONS.md` ("Image Docker custom pour le déploiement sur un serveur
distant") et `README.md` pour la procédure complète. Les deux chemins
coexistent délibérément ; ne pas faire disparaître le bind mount local au
profit de l'image custom (ça casserait l'itération instantanée en dev).

Après tout `docker compose up -d`, deux étapes manuelles restent
nécessaires (voir `README.md`) : installer les dépendances Python du plugin
dans le venv du container (`uv pip install ...` via `docker exec` — ne
persiste pas d'un `--force-recreate` à l'autre) et activer le plugin
(`hermes plugins enable odoo` — les plugins sont opt-in par défaut).

---

## Stack technique

| Élément                        | Valeur                                                                                                                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Runtime plugin                   | Python (celui dans lequel tourne Hermes — pas d'environnement séparé)                                                                                                 |
| Dépendances plugin`docs`      | `docs-plugin/requirements.txt` (openpyxl, python-docx, python-pptx) — même install manuel en local que `odoo`, bakées dans l'image serveur                        |
| Dépendances plugin`odoo`      | `odoo-plugin/requirements.txt` (odoo-client-lib, keyring, cryptography) — install manuel, pas de mécanisme déclaratif dans `plugin.yaml`                          |
| Dépendances plugin`rights`    | `rights-plugin/requirements.txt` — **vide**, stdlib uniquement, aucune étape `uv pip install` requise                                                        |
| Stockage config plugin`odoo`   | JSON flat-files + keyring fichier sous`$HERMES_HOME/odoo-plugin-data/` (pas de base de données ; délibérément PAS sous `plugins/odoo/`, monté en lecture seule) |
| Stockage config plugin`rights` | JSON flat-files sous`$HERMES_HOME/rights-plugin-data/` (pas de secret, donc pas de keyring) — même convention                                                        |
| Dépendances plugin`audit`     | `audit-plugin/requirements.txt` — **vide**, stdlib uniquement (`sqlite3`, `hashlib`)                                                                        |
| Stockage plugin`audit`         | **SQLite** (`$HERMES_HOME/audit-plugin-data/audit.db`, WAL) — exception délibérée aux JSON flat-files, voir `DECISIONS.md` (2026-09-24)                    |
| Chiffrement secrets plugin       | Fernet (`cryptography`), clé `ODOO_PLUGIN_ENCRYPTION_KEY` dans `.env` — sans elle, fallback plaintext + warning (voir `DECISIONS.md`)                          |
| Déploiement                     | Docker Compose, image publiée`nousresearch/hermes-agent:latest`                                                                                                       |
| Réseau déploiement             | bridge + réseau externe`ollama-net` (optionnel, LLM local auxiliaire)                                                                                                 |
| Secrets déploiement             | `.env` (jamais commité)                                                                                                                                               |

---

## Conventions de code — `odoo-plugin/`

- **Import des sous-paquets** : `w_main`, `w_odoo` (et `w_docs` côté
  `docs-plugin/`, même mécanique) sont
  importés comme paquets top-level via un ajout de `odoo-plugin/` à
  `sys.path` fait dans `__init__.py` (voir le commentaire à ce sujet dans le
  fichier) — pas des imports relatifs. Ne pas "corriger" ça en réécrivant
  leurs imports internes : c'est délibéré, ça garde ces paquets
  identiques à leur version d'origine (portable telle quelle si un jour ils
  redeviennent un paquet pip installable séparé).
- **`cli.py` et `tools.py` du plugin, eux, DOIVENT être importés en relatif**
  depuis `__init__.py` (`from .cli import ...`, `from .tools import ...`) —
  **pas** en absolu. Hermes a son propre paquet top-level `tools`
  (`tools/registry.py`, etc.) : un `from tools import ALL_TOOLS` absolu
  percute silencieusement ce paquet-là au lieu du `tools.py` du plugin, et le
  plugin échoue à charger (`ImportError: cannot import name 'ALL_TOOLS' from 'tools'`) — bug réel rencontré et corrigé pendant le portage, voir
  `DECISIONS.md`.
- **Tools** : schéma = dict JSON-Schema brut (`{"type":"object","properties": {...},"required":[...]}`), pas TypeBox. Handler = `def handler(args: dict) -> str`, retourne une chaîne JSON via `tools.registry.tool_result(...)`.
- **Erreurs** : `w_main.errors_manager.errors.ConnectorError` (et ses
  sous-classes `ValidationError`, `AuthorizationError`,
  `ConfirmationRequiredError`, `NotFoundError`, `ServiceError`,
  `ConfigurationError`) sont le contrat d'erreur — `.to_dict()` produit
  `{"ok": false, "error": {"code", "message", "details"}}`. Les skills dans
  `skills-odoo/` documentent ces codes exacts : ne pas changer leur forme
  sans mettre à jour les skills en conséquence.
- **Confirmation utilisateur** : ne pas réinventer un mécanisme de
  confirmation. Le hook `pre_tool_call` dans `odoo-plugin/__init__.py`
  délègue entièrement au mécanisme d'approbation natif de Hermes
  (`{"action": "approve", ...}`) — voir `DECISIONS.md`.
- **Secrets** : `w_main/data_manager/secret_service.py` (priorité fichier
  keyring → variable d'env `ODOO_SECRET_<REF>` → keyring système), chiffrées
  Fernet côté fichier (voir `DECISIONS.md`). Ne pas router les secrets via
  `config.yaml` de Hermes.
- **Dashboard (`dashboard/plugin_api.py`)** : tourne dans le **process du
  dashboard**, séparé du gateway qui charge `__init__.py` — il répète son
  propre bootstrap `sys.path`/variables d'env (rien n'est partagé entre les
  deux processus). Toute variable ajoutée dans l'un doit être répliquée dans
  l'autre. Le fichier `plugin_api.py` définit un `router = APIRouter()` sans
  préfixe (l'hôte l'ajoute lui-même) et n'a besoin d'aucun code d'auth — le
  middleware du dashboard gate déjà toutes les routes `/api/...`. Il n'existe
  **aucun mécanisme de composition UI cross-plugin** côté host (chaque
  `dashboard/manifest.json` déclare un onglet top-level isolé) — voir
  `DECISIONS.md` (2026-08-14) pour comment `rights-plugin/dashboard/`
  contourne ça (groupement générique par `resource_type` plutôt qu'une
  injection de section dans l'onglet d'un autre plugin).

## Conventions de code — `rights-plugin/`

- **Vendoring, pas import cross-plugin, pour la base générique** :
  `rights_w_main/` est une copie physique de `odoo-plugin/w_main/`
  (`errors_manager/`, `data_manager/`, `right_manager/right_manager.py`),
  **renommée** (pas juste recopiée telle quelle) pour éviter une collision
  `sys.modules` si les deux plugins tournent dans le même process Hermes —
  voir `DECISIONS.md`. Ne jamais renommer cette copie en `w_main` pour
  "coller" au nom d'origine : c'est précisément le bug déjà corrigé.
  Diverge de l'original sur un seul point documenté en tête de fichier :
  une 5ᵉ opération `execute` (`Right.execute`/`confirm_execute`,
  `RightManager.assert_execute`), nécessaire pour gater un appel de tool
  générique (pas de verbe CRUD naturel).
- **`rights_plugin_api.py` est l'unique contrat public** de ce plugin —
  toute autre fonction/module (`models.py`, `engine.py`, `identity.py`,
  `rights_w_main/`) est un détail d'implémentation, non garanti stable
  pour un consommateur externe (`odoo-plugin` ou tout futur plugin). Un
  changement de signature dans `rights_plugin_api.py` est un changement
  d'interface publique à signaler explicitement (règle `AGENT.md`).
- **Résolution d'identité** (`identity.py::resolve_identity`) : toujours au
  moins le rôle implicite `"everyone"` ; ajoute `"automation"` quand aucune
  identité platform ne résout (cron, session système). Ne jamais coder en
  dur une plateforme précise (Slack) dans cette logique — `platform` est un
  champ libre, pas une énumération fermée.
- **Combinaison multi-rôles = le plus permissif gagne** (`engine.py`) : une
  opération est autorisée si *au moins un* rôle l'autorise ; confirmation
  exigée seulement si *tous* les rôles qui autorisent l'exigent. Choix
  délibéré (pas une lattice RBAC deny-overrides), voir `DECISIONS.md` avant
  de le changer.
- **`pre_tool_call` ne doit jamais bloquer par surprise** : le hook vérifie
  d'abord qu'un `AccessRight` existe pour `(resource_type="hermes_tool", resource_id=tool_name)` avant même de résoudre l'identité — si aucun
  right n'est configuré pour ce tool, le hook renvoie `None` immédiatement.
  Activer ce plugin ne doit jamais casser silencieusement un built-in
  Hermes non configuré.
- **Consommateur cross-plugin (`odoo-plugin/w_odoo/rights_bridge.py`)** :
  localise `rights-plugin` comme répertoire *sibling* déterministe (deux
  noms essayés dans l'ordre, `../rights` puis `../rights-plugin` — voir
  plus haut) via `sys.path.append(...)` (**jamais** `insert(0, ...)` — voir
  `DECISIONS.md` pour la collision de paquet-namespace `tests` que ça
  provoquerait sinon). Si l'import échoue, `RIGHTS_AVAILABLE = False` et
  toute opération d'écriture lève `ConfigurationError` (fail closed) —
  jamais fail-open.

## Conventions de code — `audit-plugin/`

- **Tous les modules top-level sont préfixés `audit_`** (`audit_store`,
  `audit_redact`, `audit_identity`) : `rights-plugin` possède déjà
  `identity`, `models`, `engine`… en top-level dans le **même** process
  Hermes, et `sys.modules` est un cache global par nom (même bug que
  `rights_w_main`, voir `DECISIONS.md`). `cli.py`/`tools.py` restent en
  import relatif depuis `__init__.py`, comme les autres plugins.
- **Les hooks sont des observateurs purs** : ils renvoient toujours `None`
  et avalent toute exception (loggée) — un échec d'audit ne doit jamais
  bloquer ni modifier un appel de tool.
- **Jamais de résultat de tool stocké**, seulement sa taille ; arguments et
  messages d'erreur toujours passés par `audit_redact` avant écriture. Toute
  nouvelle colonne alimentée par des données d'appel doit passer par le
  même chemin.
- **La chaîne de hash couvre `_HASHED_COLUMNS`** (`audit_store.py`) : ajouter
  une colonne à la table sans l'ajouter à ce tuple la laisse modifiable sans
  détection ; l'ajouter change le hash des lignes existantes → prévoir une
  migration (nouvel ancrage) plutôt que de casser `verify` sur l'historique.
- **Aucune route d'écriture dans le dashboard** : la purge reste une action
  CLI explicite (`--yes`).

---

## Commandes utiles

| Action                                                                                             | Commande                                                                                                                                                                        |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Démarrer / mettre à jour le déploiement                                                         | `docker compose up -d`                                                                                                                                                        |
| Voir les logs                                                                                      | `docker compose logs -f hermes`                                                                                                                                               |
| Installer les dépendances Python des plugins`odoo` et `docs` (dans le container, pas l'hôte) | `docker exec hermes uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/plugins/odoo/requirements.txt -r /opt/data/plugins/docs/requirements.txt`               |
| Activer la génération de documents                                                               | `docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable docs` puis `docker restart hermes`                                                                          |
| Activer les plugins (opt-in par défaut,`rights` requis pour `odoo`)                           | `docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable odoo && docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable rights` puis `docker restart hermes` |
| Configurer un profil Odoo                                                                          | `docker exec hermes /opt/hermes/.venv/bin/hermes odoo profile add ...` (voir `odoo-plugin/README.md`)                                                                       |
| Gérer les droits (rôles, accès)                                                                 | `docker exec hermes /opt/hermes/.venv/bin/hermes rights role bind/right add/...` (voir `rights-plugin/README.md`)                                                           |
| Débug chargement plugin                                                                           | `docker exec -e HERMES_PLUGINS_DEBUG=1 hermes /opt/hermes/.venv/bin/hermes plugins list`                                                                                      |
| Réparer les permissions après un`docker exec` (root) sur les données du plugin                | `docker exec hermes chown -R hermes:hermes /opt/data/odoo-plugin-data/ /opt/data/rights-plugin-data/ /opt/data/audit-plugin-data/`                                            |
| Activer le journal d'audit                                                                         | `docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable audit` puis `docker restart hermes`                                                                         |
| Consulter / vérifier le journal d'audit                                                           | `docker exec -u hermes hermes /opt/hermes/.venv/bin/hermes audit list --since 24h` / `... audit verify` (toujours `-u hermes`, sinon permissions cassées)                |
| Générer une clé de chiffrement                                                                  | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`                                                                                  |
| Gérer profils/droits Odoo en UI                                                                   | `http://127.0.0.1:9119` → onglet "Odoo" (après "Skills")                                                                                                                    |
| Gérer les groupes d'accès génériques en UI                                                     | `http://127.0.0.1:9119` → onglet "Access Groups" (après "Odoo")                                                                                                             |
| Accéder au dashboard                                                                              | `http://127.0.0.1:9119` (basic auth, credentials dans `.env`) — **ne jamais** exposer ce port hors localhost sans reverse proxy authentifié                         |
| Builder l'image custom (déploiement serveur)                                                      | `docker build -t ghcr.io/<org-github>/weiagen_hermes:<tag> .`                                                                                                                 |
| Pousser l'image sur le GitHub Container Registry                                                   | `docker push ghcr.io/<org-github>/weiagen_hermes:<tag>`                                                                                                                       |
| Déployer sur le serveur distant                                                                   | `docker compose -f docker-compose.server.yml pull && docker compose -f docker-compose.server.yml up -d` (nécessite `HERMES_IMAGE` dans le `.env` du serveur)             |

---

## Tests (`odoo-plugin/tests/`, `rights-plugin/tests/`, `audit-plugin/tests/`) et CI (`.github/workflows/ci.yml`)

Depuis le 2026-08-06, `odoo-plugin/` a une suite `pytest` (~200 tests,
`odoo-plugin/tests/`) qui tourne aussi en CI (`.github/workflows/ci.yml`, sur
chaque push/PR — pas de build/push d'image, le déploiement reste manuel). Le
dépôt a quitté GitLab pour GitHub le 2026-09-27 : la CI vivait dans
`.gitlab-ci.yml` jusque-là, remplacé à l'identique par `.github/workflows/ci.yml`
(mêmes jobs, mêmes commandes — voir `DECISIONS.md`).
Couvre `w_main`/`w_odoo` (logique pure) et la couche
d'intégration (`tools.py`, `cli.py`, `__init__.py::_pre_tool_call`/
`register()`), sans Odoo réel ni container Hermes — les deux sont simulés
(`FakeOdooClient`, stub du paquet natif `tools` de Hermes et de
`hermes_constants`). Détails d'implémentation (pourquoi `tests/pytest.ini`
doit vivre dans `tests/` et pas dans `odoo-plugin/`, comment le plugin est
chargé sans vrai Hermes) dans `tests/conftest.py` et `DECISIONS.md`
(entrée du même jour). Un bug préexistant dans `w_main/data_manager/ field.py::ListField` (défaut `None` au lieu de `[]`) a été trouvé par cette
suite, signalé, puis corrigé sur demande explicite de Fred — voir
`DECISIONS.md`. `test_rights_bridge.py` s'y est ajouté depuis (2026-08-13) —
il exerce le vrai code de `rights-plugin` via la recherche sibling, pas un
mock, donc une régression du contrat `rights_plugin_api` casse ce fichier.

`rights-plugin/` a sa propre suite `pytest` (~170 tests,
`rights-plugin/tests/`), même pattern exact (`conftest.py`/`pytest.ini`,
stub de `hermes_constants`/`tools.registry`/`hermes_state.SessionDB`), sa
propre job CI (`test-rights-plugin`, miroir de
`test-odoo-plugin`). Couvre la copie vendorée `rights_w_main/` (tests de
parité prouvant qu'elle se comporte identiquement à l'originale), les
modèles, le moteur de décision (parité + union multi-rôles + wildcards), la
résolution d'identité, les hooks, le CLI et `rights_plugin_api.py`.

`audit-plugin/` a sa propre suite `pytest` (~90 tests, `audit-plugin/tests/`),
même pattern (`conftest.py`/`pytest.ini` dans `tests/`, stubs
`hermes_constants`/`tools.registry`/`hermes_state.SessionDB`), job CI
`test-audit-plugin`. Couvre le store SQLite (chaîne de hash, détection
d'édition/suppression, purge + ancrage, écritures concurrentes), le
masquage, les deux hooks, la CLI et `audit_search`.

`docs-plugin/` a sa suite `pytest` (~40 tests, `docs-plugin/tests/`), job CI
`test-docs-plugin` : générateurs/lecteurs sur de vrais fichiers (tests
déplacés depuis `odoo-plugin/tests/`), politique de chemin de sortie
(`docs_paths.py` : dossier par défaut, racines autorisées, `..`/symlink,
extension) et handlers.

Activation des plugins via `hermes plugins enable odoo`/`enable rights`
reste manuelle après un déploiement (pas d'automatisation possible côté
Hermes pour ça). Le déploiement lui-même passe désormais par
`.github/workflows/cd.yml` (voir section suivante) plutôt que par une
procédure manuelle documentée (`DEPLOY.md`, supprimé le 2026-09-27, voir
`DECISIONS.md`).

## CD (`.github/workflows/cd.yml`) et Kubernetes (`k8s/`)

Depuis le 2026-09-27, `.github/workflows/cd.yml` se déclenche à la fin d'un
run CI réussi (`push`) sur `dev`/`staging`/`main` :

1. **`push_images`** — build l'image custom (`Dockerfile` racine) et la
   pousse sur Docker Hub : `weiagen_hermes_test` (dev), `weiagen_hermes_preprod`
   (staging), `weiagen_hermes` (main). Nécessite les secrets GitHub
   `DOCKERHUB_USERNAME`/`DOCKERHUB_PASSWORD`.
2. **`tag_release`** (staging/main) — retague l'image `:latest` déjà poussée
   avec une version `AAAA.MM.n` (sans rebuild) et crée un tag git + une
   Release GitHub.
3. **`deploy_preprod`/`deploy_prod`** — `kubectl apply -f k8s/preprod/` (ou
   `k8s/prod/`) puis `kubectl rollout restart` sur le Deployment Hermes.
   **Désactivés par défaut** (variables GitHub Actions `K8S_PREPROD_ENABLED`/
   `K8S_PROD_ENABLED` à `true` pour les activer) — le cluster Kubernetes de
   Weiagen n'existe pas encore, voir `DECISIONS.md`. Pas de palier "test" sur
   VPS pour l'instant (contrairement à un ancien template dont ce CD est
   adapté) : la branche `dev` ne fait que builder/pousser l'image.
4. **`notify`** — notification Discord (secret optionnel `DISCORD_LOG`).

`k8s/` contient les manifests bruts (pas de chart Helm — architecture trop
simple pour le justifier, voir `DECISIONS.md`) : `k8s/prod/` et
`k8s/preprod/` (namespace, ConfigMap, Deployment+PVC pour Hermes, Deployment
pour SearXNG interne, Service, Ingress vers le dashboard uniquement),
`k8s/secrets.env.example` (modèle du Secret à créer à la main sur le
cluster, jamais commité rempli), `k8s/cert-manager/` (ClusterIssuer Let's
Encrypt), `k8s/priorityclasses.yml` et `k8s/node-topology.sh` (arbitrage
multi-nœuds, cluster-scoped, à appliquer une seule fois). Pas de Postgres/
Redis/PgAdmin : ce plugin ne stocke rien en base (voir la ligne "Stockage"
plus haut) — architecture minimale à 2 services (Hermes + SearXNG).
