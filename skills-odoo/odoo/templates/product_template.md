# Produit

## Identification
- Nom : {{name}}
- Référence interne : {{default_code}}
- Code-barre : {{barcode}}
- Catégorie : {{categ_id}}
- Type de produit : {{type}}
<!-- Choix : consu (Consommable) | service (Service) | product (Stockable) -->
- Actif : {{active}}

## Prix & Coût
- Prix de vente : {{list_price}}
- Coût : {{standard_price}}
- Devise : {{currency_id}}
- Méthode de coût : {{cost_method}}
<!-- Choix : standard | fifo | average -->

## Unités de mesure
- Unité de vente : {{uom_id}}
- Unité d'achat : {{uom_po_id}}

## Vente
- Peut être vendu : {{sale_ok}}
- Taxes client : {{taxes_id}}
- Politique de facturation : {{invoice_policy}}
<!-- Choix : order (Quantités commandées) | delivery (Quantités livrées) -->
- Description vente : {{description_sale}}

## Achat
- Peut être acheté : {{purchase_ok}}
- Taxes fournisseur : {{supplier_taxes_id}}
- Délai fournisseur (jours) : {{purchase_delay}}
- Description achat : {{description_purchase}}

## Stock
- Itinéraire : {{route_ids}}
- Délai de fabrication (jours) : {{produce_delay}}
- Règle de réapprovisionnement : {{reordering_rules}}
- Emplacement de stockage : {{property_stock_location}}

## Variantes & Attributs
- Attributs : {{attribute_line_ids}}
<!-- Exemples : Couleur, Taille, Matière -->
- Variantes actives : {{product_variant_ids}}

## Médias
- Image : {{image_1920}}
- Documents techniques : {{document_ids}}

## Comptabilité
- Compte de produit (vente) : {{property_account_income_id}}
- Compte de charge (achat) : {{property_account_expense_id}}

## Notes internes
{{description}}

## Checklist
- [ ] Référence interne unique
- [ ] Catégorie correcte
- [ ] Prix de vente et coût renseignés
- [ ] UdM cohérentes
- [ ] Taxes correctes (vente et achat)
- [ ] Politique de facturation définie
- [ ] Stock : itinéraires configurés si stockable
