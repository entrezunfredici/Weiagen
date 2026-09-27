# Facture Client

## Identification
- Nom / Référence : {{name}}
- Type : {{move_type}}
<!-- Choix : out_invoice (Facture client) | out_refund (Avoir client) | in_invoice (Facture fournisseur) | in_refund (Avoir fournisseur) -->
- Statut : {{state}}
<!-- Choix : draft | posted | cancel -->

## Client
- Client : {{partner_id}}
- Adresse de facturation : {{partner_id}}
- Référence client : {{ref}}
- Numéro de commande client : {{invoice_origin}}

## Dates
- Date de facturation : {{invoice_date}}
- Date d'échéance : {{invoice_date_due}}
- Période comptable : {{invoice_date}}

## Conditions de paiement
- Conditions de paiement : {{invoice_payment_term_id}}
- Journal : {{journal_id}}
- Devise : {{currency_id}}

## Lignes de facture
### Ligne 1
- Produit : {{line_product_id}}
- Description : {{line_name}}
- Quantité : {{line_quantity}}
- Prix unitaire : {{line_price_unit}}
- Taxes : {{line_tax_ids}}
- Compte : {{line_account_id}}

## Totaux
- Montant HT : {{amount_untaxed}}
- Montant taxes : {{amount_tax}}
- Montant TTC : {{amount_total}}
- Montant résiduel (à payer) : {{amount_residual}}

## Informations comptables
- Compte client : {{account_id}}
- Analytique : {{analytic_account_id}}
- Société : {{company_id}}

## Notes
- Notes internes : {{narration}}
- Notes pied de page : {{narration}}

## Checklist
- [ ] Client correct et actif
- [ ] Date de facturation renseignée
- [ ] Conditions de paiement définies
- [ ] Toutes les lignes ont un produit et un prix
- [ ] Taxes correctes appliquées
- [ ] Validée (posted) avant envoi
