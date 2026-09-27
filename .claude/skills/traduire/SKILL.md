---
name: traduire
description: Traduit un texte, un message ou un contenu de l'anglais vers le français à la demande de l'utilisateur. Utiliser quand l'utilisateur demande explicitement une traduction ("traduis ça", "en français ?", "translate this to French", colle un texte anglais et demande une version française).
---

# Traduire (EN → FR)

Traduit fidèlement un contenu de l'anglais vers le français, à la demande explicite de l'utilisateur.

## Quand l'invoquer

- L'utilisateur colle un texte en anglais et demande une traduction en français.
- L'utilisateur demande de traduire un fichier, un message d'erreur, une documentation, un commit, un README, etc.
- L'utilisateur demande "traduis", "en français stp", "translate to French", ou équivalent.

Ne pas invoquer ce skill pour la langue de réponse générale de l'agent — celle-ci est déjà fixée sur le français par défaut dans `CLAUDE.md`. Ce skill sert uniquement à traduire un contenu source donné.

## Méthode

1. Identifier précisément le texte source à traduire (sélection de l'utilisateur, contenu d'un fichier, sortie d'une commande, message d'erreur, etc.). Si l'ambiguïté existe entre plusieurs contenus possibles, demander clarification.
2. Traduire en français courant, naturel et idiomatique — pas de traduction mot à mot.
3. Préserver impérativement, sans les traduire :
   - le code source, les noms de variables/fonctions/classes, les chemins de fichiers ;
   - les commandes shell, les flags CLI ;
   - les termes techniques qui n'ont pas d'équivalent français standard dans ce projet (ex. noms de frameworks, d'API, de champs Odoo) ;
   - le formatage Markdown existant (listes, blocs de code, tableaux, liens).
4. Adapter le registre au contexte : formel pour la documentation, neutre pour les messages d'erreur, direct pour les résumés techniques.
5. Si le texte source contient un mélange de code et de prose, ne traduire que la prose.
6. Restituer la traduction directement dans la réponse, sauf si l'utilisateur demande explicitement d'écrire le résultat dans un fichier (dans ce cas, utiliser Edit/Write sur le fichier concerné).

## Cas particuliers

- **Fichiers de documentation projet** (`README.md`, `.agents/*.md`) : si l'utilisateur demande de traduire un fichier entier, proposer d'abord de confirmer le fichier cible avant d'écraser son contenu.
- **Messages de commit** : ne pas traduire un message de commit déjà écrit en anglais sans confirmation explicite — l'historique git mélangé FR/EN peut être un choix délibéré du projet.
- **Termes ambigus** : en cas de terme technique sans traduction évidente, garder le terme anglais entre parenthèses après la traduction proposée, ex. « traitement par lots (batch processing) ».
