---
name: docs-generator
description: Génération de documents bureautiques — tableurs Excel (.xlsx), documents Word (.docx) et diaporamas PowerPoint (.pptx)
operations:
  - create
---

# Générateur de documents

Ces outils créent et lisent des fichiers bureautiques (plugin Hermes `docs`).

**Pour envoyer un fichier créé à l'utilisateur** (Slack ou autre plateforme), recopier la
valeur `media` renvoyée par l'outil (`MEDIA:/chemin/…`) **seule sur sa ligne** dans la réponse
finale : Hermes joint alors le fichier au message. Donner le chemin seul ne sert à rien —
l'utilisateur n'a pas accès au disque de Hermes. Voir « Envoyer le fichier généré » plus bas.

`output_path` est **facultatif** : l'omettre, ou ne donner qu'un nom de fichier
(`"ventes_2025.xlsx"`), écrit le fichier dans le cache documents de Hermes, d'où il peut être
joint. Un chemin absolu hors des répertoires autorisés est refusé (`VALIDATION_ERROR`).

## `docs_create_xlsx` — Tableur Excel

Crée un fichier `.xlsx` avec une ou plusieurs feuilles de calcul.

```typescript
docs_create_xlsx({
  output_path?: string,     // facultatif — nom de fichier, ex. "rapport.xlsx"
  sheets: [
    {
      name?: string,                          // nom de l'onglet (défaut "Sheet")
      headers?: string[],                     // en-têtes — mis en gras + fond bleu clair
      rows?: any[][],                         // données (tableau de tableaux)
      freeze_top_row?: boolean,               // geler la ligne d'en-tête (défaut false)
      auto_filter?: boolean,                  // activer l'auto-filtre (défaut false)
      column_widths?: Record<string, number>, // ex. {"A": 20, "B": 35}
    }
  ]
})
```

Exemple — rapport de ventes avec deux feuilles :

```json
{
  "output_path": "ventes_2025.xlsx",
  "sheets": [
    {
      "name": "Résumé",
      "headers": ["Mois", "CA (€)", "Objectif (€)", "Écart"],
      "rows": [
        ["Janvier", 42000, 40000, 2000],
        ["Février", 38500, 40000, -1500]
      ],
      "freeze_top_row": true,
      "auto_filter": true
    },
    {
      "name": "Détail",
      "headers": ["Client", "Produit", "Quantité", "Prix unit."],
      "rows": [
        ["ACME", "Widget A", 10, 150],
        ["ACME", "Widget B", 5, 200]
      ]
    }
  ]
}
```

---

## `docs_create_docx` — Document Word

Crée un fichier `.docx` à partir d'une liste de blocs de contenu ordonnés.

```typescript
docs_create_docx({
  output_path?: string,  // facultatif — nom de fichier
  title?: string,        // titre principal du document (Heading 0)
  content: Block[]
})
```

Types de blocs disponibles :

| `type`           | Champs requis            | Description                     |
|------------------|--------------------------|---------------------------------|
| `heading`        | `text`, `level` (1-4)   | Titre de section                |
| `paragraph`      | `text`                   | Paragraphe de texte             |
| `bullet_list`    | `items: string[]`        | Liste à puces                   |
| `numbered_list`  | `items: string[]`        | Liste numérotée                 |
| `table`          | `headers`, `rows`        | Tableau avec en-têtes en gras   |
| `page_break`     | _(aucun)_                | Saut de page                    |

Exemple — compte-rendu de réunion :

```json
{
  "output_path": "CR_reunion.docx",
  "title": "Compte-rendu — Réunion projet Alpha",
  "content": [
    { "type": "heading", "level": 1, "text": "Participants" },
    { "type": "bullet_list", "items": ["Alice (PO)", "Bob (Dev)", "Claire (QA)"] },
    { "type": "heading", "level": 1, "text": "Points discutés" },
    { "type": "paragraph", "text": "L'équipe a validé le périmètre du sprint 4." },
    { "type": "heading", "level": 2, "text": "Actions décidées" },
    { "type": "numbered_list", "items": ["Déployer en staging avant vendredi", "Relire les specs UI"] },
    { "type": "heading", "level": 1, "text": "Métriques sprint 3" },
    {
      "type": "table",
      "headers": ["Ticket", "Statut", "Responsable"],
      "rows": [
        ["ALPHA-42", "Done", "Bob"],
        ["ALPHA-45", "In Review", "Claire"]
      ]
    }
  ]
}
```

---

## `docs_create_pptx` — Diaporama PowerPoint

Crée un fichier `.pptx` avec une ou plusieurs diapositives.

```typescript
docs_create_pptx({
  output_path?: string,  // facultatif — nom de fichier
  slides: Slide[]
})
```

Layouts disponibles :

| `layout`     | Champs                                       | Description                        |
|--------------|----------------------------------------------|------------------------------------|
| `title`      | `title`, `subtitle?`                         | Diapositive de titre centrée       |
| `content`    | `title`, `content: string[]`                 | Titre + liste à puces              |
| `two_column` | `title`, `left: string[]`, `right: string[]` | Titre + deux colonnes de puces     |
| `blank`      | `body?`                                      | Zone de texte libre sur fond blanc |

Exemple — présentation de bilan trimestriel :
```json
{
  "output_path": "bilan_Q1.pptx",
  "slides": [
    {
      "layout": "title",
      "title": "Bilan Q1 2025",
      "subtitle": "Présentation Direction — 28 mai 2025"
    },
    {
      "layout": "content",
      "title": "Chiffres clés",
      "content": [
        "CA total : 1,2 M€ (+8 % vs Q1 2024)",
        "Nouveaux clients : 14",
        "NPS : 72"
      ]
    },
    {
      "layout": "two_column",
      "title": "Points forts / Points d'amélioration",
      "left": ["Livraisons dans les délais", "Satisfaction client en hausse"],
      "right": ["Retard recrutement tech", "Coûts infra dépassés de 12 %"]
    },
    {
      "layout": "content",
      "title": "Prochaines étapes",
      "content": [
        "Lancement produit B en juin",
        "Recrutement 2 développeurs",
        "Audit coûts cloud"
      ]
    }
  ]
}
```

---

## `docs_read_xlsx` — Lire un tableur Excel

Extrait le contenu d'un fichier `.xlsx` existant.

```typescript
docs_read_xlsx({
  input_path: string,        // requis — chemin absolu vers le fichier (ex. un fichier envoyé sur Slack)
  sheet_names?: string[],    // optionnel — liste de feuilles à lire (toutes par défaut)
})
```

Réponse : `{ ok: true, path, sheets: [{ name, rows: string[][] }] }`

---

## `docs_read_docx` — Lire un document Word

Extrait le texte structuré d'un fichier `.docx` existant.

```typescript
docs_read_docx({
  input_path: string,   // requis — chemin absolu vers le fichier
})
```

Réponse : `{ ok: true, path, title, content: Block[] }` où `Block` est `{ type, text?, level?, headers?, rows? }`.

---

## `docs_read_pptx` — Lire une présentation PowerPoint

Extrait le texte de chaque diapositive d'un fichier `.pptx` existant.

```typescript
docs_read_pptx({
  input_path: string,   // requis — chemin absolu vers le fichier
})
```

Réponse : `{ ok: true, path, slide_count, slides: [{ slide, title, text: string[] }] }`

---

## Règles d'utilisation

- `output_path` : l'omettre ou donner un simple nom de fichier. L'extension est ajoutée si elle
  manque, et une extension différente est refusée.
- `input_path` : chemin absolu (un fichier envoyé par l'utilisateur sur Slack est déjà sur le
  disque de Hermes, son chemin figure dans le message reçu).
- En cas d'erreur : `{ "ok": false, "error": { "code": "VALIDATION_ERROR" | "UNHANDLED_ERROR", "message": "..." } }`.
- En cas de succès (création) : `{ "ok": true, "path": "...", "media": "MEDIA:...", ... }`.
- Un nom de fichier déjà utilisé est écrasé : omettre `output_path` génère un nom unique.

## Envoyer le fichier généré

Après une création réussie, terminer la réponse par la valeur `media`, **seule sur sa ligne** :

```markdown
Voici le rapport des ventes de 2025.

MEDIA:/opt/data/cache/documents/generated/ventes_2025.xlsx
```

Hermes retire la ligne `MEDIA:` du texte affiché et joint le fichier au message. Ne jamais
inventer ni modifier ce chemin : recopier exactement la valeur `media` renvoyée par l'outil.
