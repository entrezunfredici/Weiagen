# CHANGELOG_AGENT.md — Journal d'état du projet

> Mis à jour par l'agent après chaque modification significative.
> **But** : permettre de reprendre le travail sans contexte de session.
> Ne remplace pas `DECISIONS.md` (pourquoi) ni le README (usage) — répond à **"où en est le projet ?"**

---

## Comment lire ce fichier

- Lis les entrées **du bas vers le haut** — la plus récente est en bas.
- La section **"État global"** reflète toujours le présent.
- **Historique réinitialisé le 2026-09-27** : ce projet est repris comme dépôt
  indépendant sur GitHub, sans conserver le journal détaillé de son contexte
  de développement précédent. Les entrées reprennent à partir de cette date.

---

## État global du projet

| Élément | État |
| --- | --- |
| `odoo-plugin/` (plugin Hermes `odoo`) | Connecteur Odoo, CRUD deny-by-default délégué entièrement à `rights-plugin`. 181 tests verts. |
| `rights-plugin/` (plugin Hermes `rights`) | Autorisation générique (identité → rôles → droits), catalogue de rôles multi-rôles, annuaire Slack en cache, signature de jetons d'identité pour microservices MCP externes (HMAC + EdDSA). 337 tests verts. |
| `audit-plugin/` (plugin Hermes `audit`) | Journal d'audit append-only chaîné par hash (SQLite) de chaque appel de tool et décision d'approbation. 87/89 tests verts (2 erreurs de nettoyage de fichier temporaire propres à Windows, sans rapport avec le code). |
| `docs-plugin/` (plugin Hermes `docs`) | Génération/lecture xlsx/docx/pptx, livraison des fichiers par convention `MEDIA:<chemin>`. 40 tests verts. |
| Nommage | Bot : `Weiagen`. Dépôt/paquet : `weiagen_hermes`. Paquets internes sans le préfixe `sdk_` : `w_main`, `w_odoo`, `w_docs` (`odoo-plugin`/`docs-plugin`), `rights_w_main` (copie vendorée dans `rights-plugin`). |
| CI (`.github/workflows/ci.yml`) | GitHub Actions, 5 jobs (un par plugin + build du dashboard `rights-plugin`), déclenchés sur chaque push/pull request. |
| CD (`.github/workflows/cd.yml`) | GitHub Actions : build + push de l'image Docker sur push `dev`/`staging`/`main`. Déploiement Kubernetes préparé (`k8s/`) mais **désactivé** (pas de cluster disponible) — voir `DECISIONS.md`. |
| Procédure de déploiement | Aucune documentée pour l'instant — le mécanisme CD/Kubernetes ci-dessus n'a pas encore été exercé en conditions réelles (pas de run GitHub Actions déclenché, pas de cluster). |
| Tests contre un vrai Odoo (CRUD réel) | Pas faits — aucune instance Odoo de test disponible dans cet environnement. |
| Problème connu (local uniquement) | Sur certaines machines de développement, `rights-plugin/models.py` (import top-level `models`) peut être masqué par un paquet `site-packages` externe du même nom — casse le pont `odoo-plugin`→`rights-plugin` en local seulement, jamais en CI/déploiement (venv propre). Voir `DECISIONS.md`. |

---

## Historique

_(vide — voir la note de réinitialisation ci-dessus)_
