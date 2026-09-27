# DECISIONS.md — Journal des décisions techniques

> Rempli au fil du projet pour chaque choix structurant de ce dépôt
> (déploiement Hermes **et** les plugins). Les décisions internes à Hermes
> Agent lui-même appartiennent au projet upstream, pas à ce fichier.
> Objectif : comprendre "pourquoi c'est comme ça" sans avoir à relire
> l'historique git.
>
> **Ce fichier a été consolidé le 2026-09-27** : les entrées qui suivent
> reflètent l'état et l'architecture *actuels* du projet, pas un journal
> chronologique d'incidents. Le détail des bugs déjà corrigés, des
> déploiements passés et du contexte de développement précédent n'est plus
> conservé — seule la justification des choix encore en vigueur l'est.

---

## Format

```markdown
### [YYYY-MM-DD] Titre court

**Contexte** : Quel problème ou besoin motive ce choix.
**Décision** : Ce qui a été choisi et pourquoi.
**Alternative écartée** : Ce qui a été considéré mais rejeté, et pourquoi.
**Conséquences** : Ce que ça implique (contraintes, dette, dépendances).
```

---

## Décisions

### [2026-07-22] Portage d'un plugin OpenClaw vers un plugin Hermes natif

**Contexte** : le connecteur Odoo et la génération de documents bureautiques
existaient à l'origine comme plugin pour une autre plateforme d'agent
(OpenClaw, gateway Node.js). Ce dépôt en est un portage natif vers Hermes
Agent (Python).

**Décision** : la logique métier pure (moteur CRUD/secrets/droits,
connecteur Odoo, générateurs de documents) est copiée telle quelle — ce
sont des modules Python purs sans dépendance à OpenClaw. La glue OpenClaw
(bridge subprocess/JSON-stdio, poll REST de confirmation, panneau UI
flottant) est remplacée par l'intégration native Hermes : les tools
appellent directement le code Python (pas de subprocess), la confirmation
utilisateur passe par le hook natif `pre_tool_call` → approbation humaine
de Hermes, et la gestion des profils/droits passe par une CLI
(`hermes odoo profile/right ...`).

**Mécanisme d'import** : ces paquets (`odoo-plugin/w_main/`, `w_odoo/`,
`docs-plugin/w_docs/`) utilisent des imports absolus top-level
(`from w_main.data_manager import ...`), pas des imports relatifs. Comme
Hermes charge chaque plugin via `importlib` avec son propre
`submodule_search_locations`, ces imports ne résoudraient pas tels quels —
chaque `__init__.py` de plugin ajoute donc son propre répertoire à
`sys.path` au chargement, pour que ces paquets restent importables comme
paquets top-level sans réécrire leurs imports internes.

**Piège connu** : `odoo-plugin/tools.py`/`cli.py`, eux, **doivent** être
importés en relatif (`from .tools import ...`) depuis `__init__.py` — Hermes
a son propre paquet top-level `tools` ; un import absolu percuterait
silencieusement celui-là. Import obligatoire pour tout futur fichier ajouté
directement à la racine d'un plugin.

**Skills toujours découvrables** : `ctx.register_skill()` de Hermes
n'enregistre un skill qu'en résolution explicite (non listé dans le prompt
système). Les skills utilisateur d'un plugin (`skills-odoo/`, `skills-docs/`,
`skills-rights/`) sont donc montés/copiés comme des skills Hermes normaux,
pas via l'API de plugin.

---

### [2026-07-22] Déploiement local : image publiée + bind mounts, pas de build source

**Décision** : `docker-compose.yml` utilise l'image publiée
`nousresearch/hermes-agent:latest` (pas de build depuis les sources, pas de
clone vendorisé de Hermes Agent dans ce dépôt), réseau bridge classique
(ports `8642` gateway, `127.0.0.1:9119` dashboard), et bind-monte
`odoo-plugin/`, `rights-plugin/`, `audit-plugin/`, `docs-plugin/` et chaque
dossier de skill directement aux emplacements attendus par Hermes
(`/opt/data/plugins/<name>`, `/opt/data/skills/<name>`) — lecture seule,
directement depuis ce dépôt. Un fichier modifié sur l'hôte est
immédiatement visible dans le container, sans rebuild ni redémarrage pour
la plupart des changements (skills : rechargés au vol ; plugins Python :
un `docker restart` suffit).

**Piège déjà rencontré** : un *symlink* écrit dans `~/.hermes` (monté comme
`/opt/data`) mais pointant vers un chemin hors de ce volume ne se résout
**pas** à l'intérieur de l'espace de noms de montage du container — seul un
bind mount direct fonctionne, d'où le choix ci-dessus plutôt qu'un script
d'installation à base de symlinks.

**Réseau `ollama-net`** : rejoint en option pour un futur usage d'un LLM
local (Ollama) comme provider auxiliaire — jamais comme provider
principal (Hermes exige un contexte ≥ 64k tokens, hors de portée d'un LLM
local sur du CPU classique).

**`.gitignore`** : `.env` et variantes ne sont jamais commités (secrets en
clair : mots de passe dashboard, clés).

---

### [2026-07-24] Déploiement serveur : image Docker custom (`Dockerfile`)

**Contexte** : un serveur qui n'a pas ce dépôt cloné sur disque ne peut pas
utiliser de bind mount.

**Décision** : `Dockerfile` construit une image `FROM
nousresearch/hermes-agent:<tag épinglé>` qui bake les plugins, les skills et
leurs dépendances Python directement dedans (`COPY` + `uv pip install` au
build) — les dépendances survivent alors à une recréation de container,
contrairement au chemin local où `uv pip install` doit être relancé
manuellement après chaque `docker compose up -d --force-recreate`.
`docker-compose.server.yml` déploie cette image (`image: ${HERMES_IMAGE}`),
sans bind mount ni réseau `ollama-net` (propre à la machine locale).

Les deux chemins de déploiement (local par bind mount, serveur par image
custom) coexistent délibérément : le bind mount local reste la boucle de
développement principale (édition instantanée), l'image custom est
nécessaire uniquement quand le dépôt n'est pas présent sur la cible.

**Activation des plugins** : opt-in par défaut côté Hermes
(`hermes plugins enable <name>` + redémarrage), quel que soit le chemin de
déploiement — aucun mécanisme de dépendance déclarative entre plugins
aujourd'hui, à retenir opérationnellement (`rights` doit toujours être
activé avec `odoo`, `docs` doit être activé explicitement pour ne pas
perdre silencieusement ses tools).

---

### [2026-07-23] Sécurité de base : dashboard, secrets, exécution container

- **Dashboard** (`odoo-plugin/dashboard/`, `rights-plugin/dashboard/`,
  onglet `audit`) : système de plugin dashboard Hermes indépendant du
  système `plugin.yaml`/`register(ctx)` (un `manifest.json` + une route
  FastAPI `plugin_api.py`, montée par l'hôte). Ce process est **séparé** du
  gateway qui charge `__init__.py` — toute variable d'environnement ou
  chemin de données ajouté dans l'un doit être répliqué dans l'autre, rien
  n'est partagé automatiquement entre les deux.
- **Secrets Odoo au repos** : chiffrés (Fernet/`cryptography`) dans le
  keyring fichier via `ODOO_PLUGIN_ENCRYPTION_KEY` — valeurs individuelles
  chiffrées (pas le fichier JSON entier, pour rester inspectable), fallback
  clair + avertissement loggé si la clé est absente (ne casse jamais un
  déploiement existant sans la variable), migration à la volée des entrées
  en clair. Perdre cette clé rend les secrets déjà chiffrés irrécupérables.
- **`docker exec` sans `-u hermes`** tourne en root par défaut : ça casse la
  lecture ultérieure des données du plugin par les process gateway/dashboard
  (qui tournent en `hermes`). Réflexe : `chown -R hermes:hermes` sur les
  répertoires `*-plugin-data/` après toute commande de ce type, ou toujours
  passer `-u hermes` pour les commandes qui n'ont pas besoin de root
  (`uv pip install`, lui, a justement besoin de root : le `site-packages` du
  venv appartient à root).
- **Slack sans allowlist par utilisateur** (`SLACK_ALLOW_ALL_USERS=true`) :
  Hermes refuse par défaut les expéditeurs inconnus sans allowlist
  configurée (fail-closed voulu) — cette variable est l'opt-out explicite,
  spécifique à Slack, pour un usage où n'importe quel membre du workspace
  doit pouvoir parler au bot sans mise en liste blanche individuelle.

---

### [2026-07-29] Normalisation automatique des champs `html` côté `w_odoo`

**Contexte** : les champs Odoo de type `html` n'interprètent jamais un `\n`
brut — un texte écrit avec de simples retours à la ligne s'affichait tel
quel, sans mise en forme.

**Décision** : `w_odoo/odoo_html.py` (stdlib uniquement) convertit
automatiquement le texte simple en `<p>`/`<br/>` avant écriture
(`odoo_cli_for_ai.py`, juste avant l'appel réseau), en interrogeant le
schéma du modèle pour ne cibler que les champs `html`. Une valeur qui
contient déjà une balise HTML reconnue est laissée intacte (permet à
l'agent d'écrire du HTML réel pour styliser le contenu). Lookup de schéma
best-effort : une erreur désactive juste la normalisation pour cet appel,
ne bloque jamais l'écriture.

---

### [2026-08-06] Suite de tests `pytest` : deux comportements de code qu'elle a figés

**Contexte** : l'ajout d'une suite `pytest` pour `odoo-plugin/` a mis au
jour deux comportements à corriger, et une contrainte de collecte pytest à
respecter durablement.

**Décision** :
- `w_main/data_manager/field.py::ListField` : le défaut paresseux utilisait
  un sentinel cassé (`default=None` au lieu d'un sentinel dédié), donc un
  `ListField` non fourni (ex. `OdooRight.fields`) valait `None` au lieu de
  `[]`. Corrigé (une ligne).
- `w_main/data_manager/secret_service.py::SecretService` : le contrat de
  résolution de secret est, dans l'ordre, keyring fichier →
  `ODOO_SECRET_<REF>` (variable d'env) → keyring système (OS). Un
  environnement sans backend de keyring système installé (comme un runner
  CI) doit faire résoudre ce dernier niveau vers "introuvable"
  (`NotFoundError`), jamais vers une erreur de service — sinon la suite de
  tests devient non déterministe selon l'environnement où elle tourne.
- **Contrainte de collecte pytest** : `tests/pytest.ini` (et non
  `odoo-plugin/pytest.ini`) doit rester dans `tests/`, avec
  `--import-mode=importlib` — sinon pytest tente d'importer
  `odoo-plugin/__init__.py` comme paquet ancêtre du dossier de tests, ce qui
  déclenche tout le bootstrap `sys.path`/plugin au moment de la collecte,
  hors du contrôle du test. Même contrainte pour `rights-plugin/tests/`.

---

### [2026-08-13] `rights-plugin` : autorisation générique, remplace entièrement l'ancien modèle propre à Odoo

**Contexte** : le modèle d'autorisation initial d'`odoo-plugin` n'avait
aucune notion de **qui** demande l'opération (juste `profile_id` +
`odoo_model` + `field`) — insuffisant dès que plusieurs identités
distinctes doivent avoir des accès différents.

**Décision** : `rights-plugin/`, un plugin Hermes générique et
Odoo-agnostique, remplace entièrement l'ancien modèle :

- Modèle `(role, resource_type, resource_id, field, operation)` —
  `operation` inclut un 5ᵉ verbe synthétique `execute` (en plus de
  create/read/update/delete) pour gater un appel de tool générique, qui n'a
  pas de verbe CRUD naturel.
- Identité platform-agnostique (`RoleBinding(platform, external_user_id,
  roles)`) — pas câblée à une plateforme précise. Rôles implicites toujours
  présents : `everyone` (toute identité résolue), `automation` (aucune
  identité platform ne résout — cron, session système).
- **Combinaison multi-rôles = le plus permissif gagne** (choix délibéré,
  pas une lattice RBAC avec deny-overrides) : autorisé si *au moins un*
  rôle de l'identité l'autorise ; confirmation exigée seulement si *tous*
  les rôles qui autorisent l'exigent.
- Gate `pre_tool_call` (tout tool, built-in ou d'un autre plugin — le hook
  Hermes fire uniformément) **et** `pre_llm_call` (injection de contexte
  d'identité, jamais bloquant). `rights-plugin` n'impose jamais rien à
  l'intérieur d'un service MCP externe — chaque service reste responsable
  de son propre contrôle d'accès.
- **Vendoring, pas import cross-plugin, pour la base générique** partagée
  avec `odoo-plugin/w_main/` : `rights-plugin` doit rester le composant
  indépendant, pas un consommateur du mécanisme `sys.path` d'`odoo-plugin`.
  La copie vendorée vit sous `rights_w_main/` — **nom volontairement
  différent** de `w_main` : les deux plugins peuvent tourner dans le même
  process Hermes, et `sys.modules` est un cache global par nom de module ;
  deux paquets identiquement nommés se collisionneraient silencieusement
  (celui chargé en premier "gagnerait" pour toute la durée du process).
  Diverge de l'original sur un seul point documenté : l'opération `execute`
  en plus.
- **Appel cross-plugin pour les données live** (pas le code) :
  `odoo-plugin/w_odoo/rights_bridge.py` localise `rights-plugin` comme
  répertoire *sibling* déterministe et importe `rights_plugin_api.py`,
  l'unique contrat public stable de ce plugin. Recherche par `sys.path.
  append` (jamais `insert(0, ...)`, qui casserait la résolution du paquet
  `tests` de l'appelant une fois les deux répertoires sur `sys.path`). Si
  `rights-plugin` est absent/désactivé → **fail closed**
  (`ConfigurationError`, tout CRUD Odoo refusé), jamais fail-open.

**Alternative écartée** : microservice séparé — complexité opérationnelle
(déploiement/réseau/auth) inutile pour un besoin déjà couvert par les hooks
`pre_tool_call`/`pre_llm_call` natifs de Hermes.

**Conséquences** : `odoo-plugin` ne possède plus aucune logique
d'autorisation propre. Les deux plugins doivent **toujours** être activés
ensemble (aucun mécanisme de dépendance manifeste-déclarée dans Hermes
aujourd'hui).

---

### [2026-08-19] Garde-fous d'amorçage de `pre_tool_call` : ne jamais bloquer par surprise un type de ressource jamais configuré

**Principe** : activer `rights-plugin` sans aucune configuration ne doit
jamais bloquer instantanément tous les tools existants ("jour 1"). Le hook
vérifie donc d'abord qu'**au moins un** right existe pour le
`resource_type` concerné avant même de résoudre l'identité — si rien n'est
configuré pour ce type de ressource, le hook renvoie `None` (autorisé)
immédiatement, sans évaluer quoi que ce soit.

**Nuance par type de ressource**, affinée après plusieurs cas réels où ce
garde-fou masquait un right pourtant bien configuré :

- **`hermes_tool`** : le garde-fou se base sur "existe-t-il *au moins un*
  right `hermes_tool`, quel que soit l'outil visé" (`has_any_right_
  configured`), pas seulement sur l'outil exact demandé — un right scopé à
  un seul outil active bien l'évaluation deny-by-default pour **tous** les
  outils, pas seulement celui-là.
- **`hermes_cron`** : pas de tolérance d'amorçage du tout — un cron créé
  peut planter un prompt auto-exécutant persistant, une capacité plus
  sensible qu'un appel d'outil isolé. Toute action `cronjob` (create/list/
  update/pause/resume/remove, mappée vers l'opération CRUD correspondante)
  passe systématiquement par `check_right`, deny-by-default nativement.
- **Champ "Fields"** : concept propre à `odoo_model` (accès champ par
  champ), sans aucun sens pour `hermes_tool`/`hermes_cron` (un appel de
  tool/cron n'a pas de "champs"). `models.create_access_right()` force donc
  `fields=["*"]` pour ces deux types, quel que soit ce qui est soumis, et
  une fonction de normalisation corrige au chargement du plugin tout right
  déjà enregistré de façon non conforme. Le dashboard n'affiche plus ce
  champ du tout pour ces deux types.

Ces trois garde-fous sont défensifs à deux niveaux (modèle **et** UI) :
le modèle reste correct même si l'UI est contournée (CLI, API,
`rights_plugin_api` utilisé par un autre plugin).

---

### [2026-08-18] Catalogue de rôles et rights multi-rôles

**Décision** : `AccessRight.role` (une chaîne) devient `AccessRight.roles`
(une liste) — interface publique de `rights-plugin` (signalée comme telle).
Nouveau modèle `Role` (catalogue nommé, CLI `role catalog create/list/rm`),
picker multi-sélection dans le dashboard (`RoleTagPicker`). Migration+seed
au niveau module, idempotente.

---

### [2026-08-14] Dashboard `rights-plugin` : groupement générique par `resource_type`

**Contexte** : il n'existe aucun mécanisme de composition UI cross-plugin
côté Hermes — chaque `dashboard/manifest.json` déclare un onglet top-level
isolé, impossible d'injecter une section dans l'onglet d'un autre plugin.

**Décision** : l'onglet "Access Groups" de `rights-plugin` groupe les
droits **génériquement par `resource_type`** (les types natifs Hermes
`hermes_tool`/`hermes_cron`, plus tout type introduit par un plugin
délégant, `odoo_model` aujourd'hui) plutôt que de tenter une composition
UI cross-plugin. `odoo-plugin/dashboard/` garde sa propre UI d'édition
(gestion de profils Odoo, hors du périmètre générique de `rights-plugin`).

---

### [2026-08-18] Dashboard `rights-plugin` : code source en plusieurs fichiers, `dist/index.js` généré

**Contexte** : le dashboard host de Hermes ne charge qu'**un seul** point
d'entrée JS par plugin (script classique, pas de modules ES) — un vrai
chargement multi-fichiers au runtime demanderait un espace de noms partagé
entre plugins, avec un risque concret de collision de noms de fonctions
entre les dashboards `odoo-plugin` et `rights-plugin` (chargés dans la même
page).

**Décision** : le *code source* est découpé en plusieurs fichiers lisibles
sous `rights-plugin/dashboard/src/` (préfixés numériquement pour l'ordre de
concaténation, partageant une seule fermeture JS), réassemblés par
`dashboard/build.sh` (`cat src/*.js > dist/index.js`, POSIX pur) dans
l'unique fichier réellement servi. `dist/index.js` devient un **fichier
généré** — ne jamais l'éditer directement.

**Deux garde-fous contre la dérive `src/` ↔ `dist/`** : le job CI
`test-rights-plugin-dashboard-build` rejoue `build.sh` et échoue si le
`dist/index.js` commité diffère de ce que `src/` produit ; le `Dockerfile`
régénère aussi `dist/index.js` depuis `src/` au moment du build de l'image
(ceinture-et-bretelles pour le déploiement serveur, qui ne clone jamais ce
dépôt et ne rejoue donc jamais `build.sh` lui-même). Le déploiement local
(bind mount) continue de servir le `dist/index.js` du disque tel quel —
c'est pour ce chemin-là que le garde-fou CI reste utile.

**Règle à retenir** : toute modification du dashboard `rights-plugin` se
fait dans `dashboard/src/`, suivie de `./dashboard/build.sh` avant tout
test/déploiement.

---

### [2026-08-17] Annuaire Slack en cache et sélecteur de plateforme dans le dashboard

**Décision** : le dashboard propose un pick-list de personnes/rôles plutôt
qu'un champ texte libre. L'annuaire (`rights-plugin/directory.py` +
`slack_directory.py`) synchronise paresseusement les membres d'une
plateforme (TTL 24h via `pre_llm_call`, pas de vrai mécanisme cron côté API
plugin Hermes) avec un "Refresh now" explicite. Le sélecteur de plateforme
"connectée" duplique à la main la logique de `hermes status` (aucune API
Hermes core pour l'exposer autrement) plutôt que d'en dépendre. Ces deux
modules sont de pure commodité UI, jamais consultés par le moteur de
décision (`engine.py`) — une panne ou une incohérence de l'annuaire ne peut
jamais changer une décision d'autorisation.

---

### [2026-08-21] Jetons d'identité signés pour les microservices MCP externes

**Contexte** : un service MCP externe (hors de ce dépôt, jamais un plugin
Hermes) a besoin de connaître de façon fiable l'identité/les rôles de
l'appelant pour décider lui-même s'il autorise une action — sans que
`rights-plugin` n'impose quoi que ce soit à l'intérieur de ce service. Le
protocole MCP ne permet à aucun serveur d'aller chercher une info côté
Hermes : tout doit être poussé vers le LLM, qui le relaie dans les
arguments d'un appel de tool. Un texte d'identité en clair n'est pas fiable
pour une vraie décision d'accès : le LLM n'est pas un transport de
confiance pour recopier des noms de rôles sans les déformer ni les
inventer.

**Décision** : `pre_llm_call` injecte, en plus d'une ligne d'identité en
clair, un jeton opaque signé (`token_signer.py`) que le LLM ne fait que
relayer — format compact façon JWT fait main (`header.payload.signature`,
base64url), durée de vie courte (5 min par défaut,
`RIGHTS_MCP_TOKEN_TTL_SECONDS`, ajustable). **Un registre de clés de
signature** (`models.McpSigningKey`, une clé par microservice MCP externe)
géré depuis le dashboard ("MCP signing keys") ou `hermes rights mcp-key
add/list/reveal/rm` — pas de redémarrage requis pour ajouter/faire tourner
une clé. Secret masqué par défaut en listing, révélé une fois à la
création/édition ou via l'action explicite `reveal`.

**Deux schémas de signature supportés** : HMAC-SHA256 (par défaut, aucune
dépendance) et **EdDSA/Ed25519** (`cryptography`, importé en optionnel —
un déploiement sans cette dépendance continue de fonctionner en HMAC
seul). L'en-tête du jeton porte `alg`/`kid`, jamais codés en dur côté
vérificateur, pour permettre à chaque service externe de choisir/faire
évoluer son propre schéma de vérification indépendamment des autres.
`rights-plugin` n'impose jamais rien de plus que l'émission du jeton — la
vérification et le contrôle d'accès sont entièrement du ressort du service
MCP externe qui le reçoit.

**Opt-in et silencieux si non configuré** : sans clé configurée pour un
service donné, aucun jeton n'est émis pour lui, aucun tour n'est cassé.

---

### [2026-09-24] `audit-plugin` : plugin plutôt que microservice, SQLite plutôt que JSON

**Contexte** : aucune trace de qui a fait quoi n'existait, alors que
`rights-plugin` bloque par défaut et que déboguer un refus passe par la
lecture manuelle des logs du container.

**Décision** :
- **Plugin, pas microservice** : tous les événements naissent dans le
  process Hermes (hooks) — écriture directe plutôt qu'un appel HTTP par
  tool call, avec la question ouverte "service injoignable : bloquer le
  tool ou perdre l'événement ?". Condition de bascule vers un service
  séparé, si jamais nécessaire un jour : l'agent peut écrire dans
  `$HERMES_HOME` (un journal local ne serait alors que *tamper-evident*,
  pas fiable), plusieurs instances Hermes, ou une exigence de conformité.
- **Un seul hook, `post_tool_call`**, suffit : Hermes l'émet pour chaque
  issue (`ok`/`error`/`blocked`/`cancelled`/`timeout`), y compris un blocage
  de `rights-plugin`. `post_approval_response` complète avec la décision
  humaine.
- **SQLite (stdlib), exception aux JSON flat-files des autres plugins** :
  écritures concurrentes (plusieurs tools en parallèle) + lecture depuis un
  autre process (dashboard) — un JSON réécrit en entier à chaque événement
  serait O(n) et non sûr en concurrence. WAL permet la lecture pendant
  l'écriture.
- **Chaîne de hash + ancre de purge** : chaque ligne inclut le hash de la
  précédente ; `verify_chain()` détecte édition ou suppression. La purge
  (rétention configurable, 90 jours par défaut) mémorise le hash de la
  dernière ligne supprimée pour que `verify` reste valide après purge.
  Limite assumée : une réécriture complète de la chaîne ou une troncature
  de la queue ne sont pas détectables depuis le fichier seul.
- **Indépendant de `rights-plugin`** : l'identité est résolue directement
  via la session Hermes, sans dépendre des rôles — l'audit doit continuer à
  fonctionner si `rights-plugin` est désactivé ou cassé.
- **Confidentialité** : résultats de tools jamais stockés (taille
  seulement), arguments masqués par nom de clé puis par le masquage natif
  de Hermes. Le tool agent `audit_search` est opt-in
  (`AUDIT_AGENT_TOOL_ENABLED`) — sur un Slack ouvert à tout le monde, il
  exposerait l'activité de chacun ; à réserver à un rôle admin via un right
  `hermes_tool`.

---

### [2026-09-24] `docs-plugin` : sorti d'`odoo-plugin`, livraison par `MEDIA:`, écriture confinée

**Contexte** : la génération de documents bureautiques (xlsx/docx/pptx)
n'a jamais dépendu d'Odoo, mais vivait dans `odoo-plugin` — il fallait donc
activer un connecteur Odoo pour produire un simple tableur.

**Décision** :
- **Plugin séparé, code inchangé** (déplacement, pas réécriture) : les 6
  noms de tools et leurs arguments restent identiques. `odoo-plugin` ne les
  fournit plus — activer `docs-plugin` est **obligatoire** au déploiement,
  sinon ces tools disparaissent silencieusement.
- **Livraison par `MEDIA:<chemin>`** : une ligne `MEDIA:<chemin absolu>`
  dans la réponse finale de l'agent devient une pièce jointe native
  (Hermes reconnaît les extensions `.xlsx`/`.docx`/`.pptx`). `output_path`
  est facultatif, écriture par défaut dans le cache documents de Hermes
  (accepté même en mode de livraison strict) — le skill demande à l'agent
  de recopier cette ligne telle quelle dans sa réponse.
- **Écriture confinée** : seuls le cache documents et les racines absolues
  de `DOCS_OUTPUT_DIRS` sont autorisés en écriture, symlinks résolus avant
  contrôle, `..` refusé, extension imposée par le tool — empêche un appel
  (y compris issu d'une injection de prompt) d'écraser un fichier
  arbitraire accessible à l'utilisateur du process. La lecture reste libre
  (les lecteurs ne parsent que des fichiers bureautiques).

---

### [2026-09-27] Nommage actuel du projet

**Décision** : le bot s'appelle **Weiagen** ; le dépôt/paquet est
**`weiagen_hermes`** ; les paquets internes historiquement préfixés `sdk_`
(`sdk_main`, `sdk_odoo`, `sdk_docs`, et la copie vendorée `rights-plugin/
sdk_main` déjà renommée une première fois) sont désormais `w_main`,
`w_odoo`, `w_docs` et `rights_w_main` — le préfixe `w_` (plutôt que
supprimer le préfixe entièrement) a été retenu spécifiquement pour éviter
une collision de nom top-level : `odoo`/`main`/`docs` seuls auraient été
nettement plus risqués (`odoo` est le nom du vrai paquet Python du
framework Odoo ; `main`/`docs` sont des noms génériques), dans un projet
qui a déjà buté deux fois sur ce type de collision (voir l'entrée
`rights_w_main` ci-dessus, et le paquet natif `tools` de Hermes).
`rights_w_main` reste distinct de `w_main` tout court — condition
nécessaire à l'absence de collision `sys.modules` entre les deux plugins.

**Problème connu (environnement local uniquement)** : `rights-plugin/
models.py`, importé en top-level bare (`import models`, même convention
que `w_main`), peut être masqué par un paquet `site-packages` externe du
même nom sur une machine de développement où un tel paquet est déjà
installé globalement — un `venv` de CI/déploiement propre n'a pas ce
problème. Non corrigé (pas de demande explicite) ; solution possible si
nécessaire un jour : renommer `models.py` en quelque chose de plus
spécifique.

---

### [2026-09-27] Pas de procédure de déploiement documentée pour l'instant ; CD/Kubernetes préparés mais désactivés

**Contexte** : l'ancienne procédure de déploiement manuelle a été retirée
(contexte de développement précédent non conservé). Le nouveau mécanisme de
déploiement n'est pas encore finalisé.

**Décision** : `.github/workflows/cd.yml` build et pousse l'image Docker
sur Docker Hub à chaque push réussi sur `dev`/`staging`/`main` (une seule
image, `weiagen_hermes`, le `Dockerfile` de ce dépôt bake les plugins/
skills/dépendances). Des manifests Kubernetes minimaux existent sous `k8s/`
(`k8s/prod/`, `k8s/preprod/`) pour une architecture à 2 services — un
Deployment Hermes avec PVC pour les données persistantes ($HERMES_HOME :
config JSON, keyring chiffré, journal d'audit SQLite), un Deployment/
Service SearXNG interne (jamais exposé) — sans Postgres/Redis/PgAdmin
(ce projet ne stocke rien en base). Pas de chart Helm : `kubectl apply -f
k8s/prod/` (ou `preprod/`) directement, plus simple pour 2 services.

**Le déploiement Kubernetes lui-même reste désactivé** (variables GitHub
Actions `K8S_PREPROD_ENABLED`/`K8S_PROD_ENABLED` non définies) tant qu'un
cluster n'existe pas — `deploy_preprod`/`deploy_prod` restent `skipped` à
chaque run, c'est l'état par défaut attendu, pas une erreur à corriger.
Pas de palier "test" sur VPS (aucun VPS disponible actuellement) : la
branche `dev` construit et pousse l'image sans déployer nulle part.
Domaines d'Ingress en placeholder explicite (`<votre-domaine.com>`), à
remplacer avant le premier déploiement réel.

**Conséquences** : `.env.example` (racine) liste toutes les variables
nécessaires au déploiement (local ou Kubernetes) ; `k8s/secrets.env.example`
documente le Secret Kubernetes correspondant, à créer à la main sur le
cluster le moment venu. Rien de tout ceci n'a été exercé en conditions
réelles (pas de run GitHub Actions déclenché, pas de cluster disponible).

---

## Hors-scope

- Pas de gestion de providers IA dans les plugins — Hermes a son propre
  système natif multi-provider, un portage serait redondant.
