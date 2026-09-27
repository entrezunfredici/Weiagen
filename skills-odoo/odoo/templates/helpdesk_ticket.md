# Ticket Helpdesk / Support

## Identification
- Titre : {{name}}
- Référence : {{ticket_ref}}
<!-- Généré automatiquement -->
- Équipe : {{team_id}}
- Type de ticket : {{ticket_type_id}}
- Étiquettes : {{tag_ids}}

## Contact
- Client : {{partner_id}}
- Email : {{partner_email}}
- Téléphone : {{partner_phone}}
- Nom du contact : {{partner_name}}

## Priorité & Statut
- Priorité : {{priority}}
<!-- Choix : 0 (Normal) | 1 (Low) | 2 (High) | 3 (Urgent) -->
- Étape : {{stage_id}}
- SLA appliqué : {{sla_id}}
- Date limite SLA : {{sla_deadline}}

## Assignation
- Assigné à : {{user_id}}
- Suiveurs : {{message_follower_ids}}

## Dates
- Date d'ouverture : {{create_date}}
- Date de clôture : {{close_date}}
- Première réponse : {{first_response_date}}

## Canal de création
- Source : {{channel}}
<!-- Choix : email | form | api | phone -->

## Description du problème
{{description}}

## Résolution
- Solution appliquée : {{kanban_state}}
<!-- Choix : normal | done | blocked -->
- Notes de résolution : {{resolution}}

## Checklist
- [ ] Client identifié et notifié
- [ ] Priorité cohérente avec l'urgence réelle
- [ ] SLA cohérent avec le contrat client
- [ ] Assigné à un agent disponible
- [ ] Description claire et complète
- [ ] Ticket clôturé uniquement si résolu et confirmé
