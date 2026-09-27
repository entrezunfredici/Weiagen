# Commande de Vente

## Identification
- Référence : {{name}}
- Référence client : {{client_order_ref}}
- Statut : {{state}}
<!-- Choix : draft | sent | sale | done | cancel -->
- Source : {{source_id}}
- Campagne : {{campaign_id}}

## Client
- Client : {{partner_id}}
- Adresse de facturation : {{partner_invoice_id}}
- Adresse de livraison : {{partner_shipping_id}}
- Conditions de paiement : {{payment_term_id}}
- Vendeur : {{user_id}}
- Équipe commerciale : {{team_id}}

## Dates
- Date de la commande : {{date_order}}
- Date de livraison prévue : {{commitment_date}}
- Date d'expiration du devis : {{validity_date}}

## Lignes de commande
### Ligne 1
- Produit : {{line_product_id}}
- Description : {{line_name}}
- Quantité : {{line_product_uom_qty}}
- UdM : {{line_product_uom}}
- Prix unitaire : {{line_price_unit}}
- Remise (%) : {{line_discount}}
- Taxes : {{line_tax_id}}
- Date de livraison : {{line_customer_lead}}

## Totaux
- Montant HT : {{amount_untaxed}}
- Montant taxes : {{amount_tax}}
- Montant TTC : {{amount_total}}

## Livraison & Stock
- Entrepôt : {{warehouse_id}}
- Politique de livraison : {{picking_policy}}
<!-- Choix : direct (Au fur et à mesure) | one (Tout en une fois) -->
- Incoterm : {{incoterm}}

## Facturation
- Politique de facturation : {{invoice_status}}
<!-- Choix : nothing | to invoice | invoiced -->

## Notes
- Notes internes : {{note}}
- Signature client : {{signature}}

## Checklist
- [ ] Client et adresses corrects
- [ ] Toutes les lignes ont un produit et un prix
- [ ] Remises validées commercialement
- [ ] Date de livraison cohérente avec le stock
- [ ] Conditions de paiement conformes au contrat client
- [ ] Devis confirmé avant lancement de la production/livraison
