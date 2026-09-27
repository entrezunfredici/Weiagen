# Bon de Commande Fournisseur

## Identification
- Référence : {{name}}
- Référence fournisseur : {{partner_ref}}
- Statut : {{state}}
<!-- Choix : draft | sent | purchase | done | cancel -->

## Fournisseur
- Fournisseur : {{partner_id}}
- Adresse de facturation : {{partner_id}}
- Devise : {{currency_id}}
- Conditions de paiement : {{payment_term_id}}

## Dates
- Date de commande : {{date_order}}
- Date de livraison prévue : {{date_planned}}
- Date d'échéance : {{date_approve}}

## Entrepôt & Livraison
- Société de livraison : {{dest_address_id}}
- Entrepôt de réception : {{picking_type_id}}
- Incoterm : {{incoterm_id}}

## Lignes de commande
### Ligne 1
- Produit : {{line_product_id}}
- Description : {{line_name}}
- Quantité : {{line_product_qty}}
- UdM : {{line_product_uom}}
- Prix unitaire : {{line_price_unit}}
- Taxes : {{line_taxes_id}}
- Compte analytique : {{line_account_analytic_id}}
- Date prévue : {{line_date_planned}}

## Totaux
- Montant HT : {{amount_untaxed}}
- Montant taxes : {{amount_tax}}
- Montant TTC : {{amount_total}}

## Informations internes
- Acheteur : {{user_id}}
- Société : {{company_id}}
- Source : {{origin}}
- Notes internes : {{notes}}

## Checklist
- [ ] Fournisseur validé (actif, non bloqué)
- [ ] Date de livraison cohérente
- [ ] Toutes les lignes ont un produit et un prix
- [ ] Entrepôt de réception correct
- [ ] Conditions de paiement renseignées
- [ ] Bon confirmé avant réception
