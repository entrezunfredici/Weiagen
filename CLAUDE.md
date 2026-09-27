# CLAUDE.md — Instructions pour Claude Code

Ce fichier est lu automatiquement par Claude Code à chaque session.
Il délègue les règles de comportement aux fichiers `.agents/`.

---

## Lecture obligatoire en début de session

Lis ces fichiers dans cet ordre avant toute action :

1. `.agents/AGENT.md` — comportement général, règles de codage, checklist de livraison
2. `.agents/CONVENTIONS.md` — stack technique et conventions spécifiques au projet
3. `.agents/CHANGELOG_AGENT.md` — état actuel du code (où en est le projet)
4. `.agents/DECISIONS.md` — décisions techniques déjà prises (ne pas les remettre en question sans raison)

> Déploiement : `.agents/DEPLOY.md` (ancienne procédure `test-server`) a été
> supprimé le 2026-09-27. Le nouveau mécanisme est `.github/workflows/cd.yml`
> (build + push Docker Hub, puis déploiement Kubernetes via `k8s/`) — voir
> `DECISIONS.md` pour le détail. **Le déploiement Kubernetes lui-même reste
> désactivé** (`K8S_PREPROD_ENABLED`/`K8S_PROD_ENABLED` non définies) tant
> que le cluster Weiagen n'existe pas.

---

## Règles non-négociables

- **Répondre systématiquement en français**, y compris le texte affiché à l'utilisateur, les messages de commit, les résumés et les mises à jour de statut — sauf si l'utilisateur écrit explicitement dans une autre langue ou demande une réponse dans une autre langue. Le code, les noms de variables/fonctions et les commentaires techniques restent en anglais selon les conventions du projet (voir `.agents/CONVENTIONS.md`).
- **Après chaque modification de code** : mettre à jour `CHANGELOG_AGENT.md` et `README.md`.
- **Toute fonction publique** doit avoir une docstring.
- **Ne pas modifier les interfaces publiques** sans signaler et attendre validation.
- **Ne pas ajouter de dépendance** sans la justifier.

> Le détail complet de ces règles est dans `.agents/AGENT.md`.
