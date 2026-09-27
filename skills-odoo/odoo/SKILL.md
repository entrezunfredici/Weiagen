---
name: odoo
description: Safe usage guidance for the Odoo plugin
---

# Odoo Skill

Use this connector as a bounded, deny-by-default Odoo integration.

All access is governed by rights (`OdooRight`) configured by the user. The agent cannot read, create, update, or delete anything unless a right explicitly allows it for the requested profile, model, and fields.

## Commandes disponibles

### Diagnostic & découverte

| Outil | Description |
|-------|-------------|
| `odoo_config_validate` | Vérifie que la configuration SDK est valide (profils + droits) |
| `odoo_list_connection_profiles` | Liste les profils de connexion disponibles |
| `odoo_list_rights` | Liste les droits configurés (filtrable par `profile_id` ou `odoo_model`) |
| `odoo_sdk_list_models` | Liste tous les modèles Odoo accessibles via un profil |
| `odoo_sdk_list_fields` | Liste les champs d'un modèle Odoo (introspection schéma) |

### CRUD

| Outil | Description |
|-------|-------------|
| `odoo_sdk_read` | Lire des enregistrements (filtrés par droits) |
| `odoo_sdk_create` | Créer un enregistrement (champs filtrés par droits) |
| `odoo_sdk_update` | Modifier un ou plusieurs enregistrements |
| `odoo_sdk_delete` | Supprimer un ou plusieurs enregistrements |

## Paramètres communs à tous les outils CRUD

```
profile_id  (requis)  — id du profil de connexion
model       (requis)  — nom du modèle Odoo, ex: "project.task"
confirmed   (optionnel, bool) — true après validation explicite de l'utilisateur
```

## Syntaxe de référence

```
odoo_config_validate()

odoo_list_connection_profiles(include_disabled?: bool)

odoo_list_rights(profile_id?: string, odoo_model?: string)

odoo_sdk_list_models(profile_id: string)

odoo_sdk_list_fields(profile_id: string, model: string)

odoo_sdk_read(
  profile_id: string,
  model: string,
  fields?: string[],        // défaut: ["id", "name"]
  domain?: any[][],         // ex: [["state", "=", "posted"]]
  limit?: number,           // défaut: 25
  confirmed?: bool
)

odoo_sdk_create(
  profile_id: string,
  model: string,
  values: { [field]: value },
  confirmed?: bool
)

odoo_sdk_update(
  profile_id: string,
  model: string,
  id?: number,              // un seul enregistrement
  ids?: number[],           // plusieurs enregistrements
  values: { [field]: value },
  confirmed?: bool
)

odoo_sdk_delete(
  profile_id: string,
  model: string,
  id?: number,
  ids?: number[],
  confirmed?: bool
)
```

## Champs riches (type `html`)

Pour les champs `html` (ex. `project.task.description`) : utiliser `\n` pour un simple retour à la ligne (converti automatiquement en `<p>`/`<br/>`), et du vrai HTML (`<b>`, `<ul><li>`, `<h2>`, `<a href="...">`) — jamais du markdown — pour styliser le contenu. Détail complet : voir `odoo-sdk/SKILL.md`.

## Obtenir le profile_id

Si le `profile_id` n'est pas connu :
```
1. odoo_list_connection_profiles()  → liste les profils actifs
2. Utiliser l'id du profil pertinent dans tous les appels suivants
```

## Safety rules

- Never assume access is allowed — always check `allowed_fields` in responses.
- Never expose or request secret values (passwords, API keys).
- Always call `odoo_sdk_read` before any write to confirm current state.
- Never bypass `CONFIRMATION_REQUIRED` — present to user, wait for explicit confirmation, then retry with `confirmed: true`.
- Treat delete as irreversible — always require explicit user validation before `confirmed: true`.
- If `ok: false`, report the error to the user; never retry silently.

## Comportement des droits

- Tout est **refusé par défaut**. Seuls les champs couverts par un `OdooRight` actif passent.
- Les champs non autorisés sont silencieusement filtrés et retournés dans `denied_fields`.
- `odoo_sdk_delete` nécessite un droit avec `fields: ["*"]` et `delete: true`.

## Codes d'erreur

| Code | Signification |
|------|---------------|
| `AUTHORIZATION_DENIED` | Aucun droit ne couvre l'opération/le champ demandé |
| `CONFIRMATION_REQUIRED` | Le droit exige `confirmed: true` avant d'exécuter |
| `VALIDATION_ERROR` | Payload invalide (champ obligatoire manquant, etc.) |
| `SERVICE_ERROR` | Échec de connexion ou de transport vers Odoo |
| `NOT_FOUND` | Profil, enregistrement ou ressource introuvable |
| `UNHANDLED_ERROR` | Erreur Python interne inattendue |
