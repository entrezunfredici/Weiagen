---
name: odoo-dev-reports
description: Rapports Odoo — QWeb PDF, ir.actions.report, templates XML, rapports SQL, export XLS
models:
  - ir.actions.report
  - ir.ui.view
operations:
  - dev
---

# Odoo — Rapports QWeb et PDF

## Déclarer un rapport (`ir.actions.report`)

```xml
<record id="action_report_my_model" model="ir.actions.report">
    <field name="name">My Model Report</field>
    <field name="model">my.model</field>
    <field name="report_type">qweb-pdf</field>           <!-- ou qweb-html -->
    <field name="report_name">my_module.report_my_model_document</field>  <!-- nom du template -->
    <field name="report_file">my_module.report_my_model_document</field>
    <field name="print_report_name">'My Report - %s' % object.code</field>  <!-- nom du PDF généré -->
    <field name="binding_model_id" ref="model_my_model"/>  <!-- apparaît dans le menu Imprimer -->
    <field name="binding_type">report</field>
</record>
```

`report_type` : `qweb-pdf` (PDF via wkhtmltopdf), `qweb-html` (HTML), `xlsx` (avec module OCA).

---

## Template QWeb

```xml
<!-- views/report_my_model.xml -->
<odoo>
    <!-- Template de mise en page (header/footer/marges) -->
    <template id="report_my_model_layout">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="doc">
                <t t-call="web.external_layout">
                    <div class="page">
                        <t t-call="my_module.report_my_model_document_body"/>
                    </div>
                </t>
            </t>
        </t>
    </template>

    <!-- Template principal du document -->
    <template id="report_my_model_document">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="doc">
                <t t-call="web.external_layout">
                    <div class="page">

                        <!-- En-tête du document -->
                        <div class="row">
                            <div class="col-6">
                                <h2 t-out="doc.code"/>
                                <p t-out="doc.partner_id.name"/>
                            </div>
                            <div class="col-6 text-end">
                                <p>Date : <span t-out="doc.date"/></p>
                                <p>Statut :
                                    <span t-out="dict(doc._fields['state'].selection).get(doc.state)"/>
                                </p>
                            </div>
                        </div>

                        <hr/>

                        <!-- Table des lignes -->
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Produit</th>
                                    <th class="text-end">Qté</th>
                                    <th class="text-end">Prix unitaire</th>
                                    <th class="text-end">Sous-total</th>
                                </tr>
                            </thead>
                            <tbody>
                                <t t-foreach="doc.line_ids" t-as="line">
                                    <tr>
                                        <td t-out="line.product_id.name"/>
                                        <td class="text-end"
                                            t-out="line.quantity"/>
                                        <td class="text-end"
                                            t-out="line.price_unit"
                                            t-options='{"widget": "monetary", "display_currency": doc.currency_id}'/>
                                        <td class="text-end"
                                            t-out="line.price_subtotal"
                                            t-options='{"widget": "monetary", "display_currency": doc.currency_id}'/>
                                    </tr>
                                </t>
                            </tbody>
                            <tfoot>
                                <tr>
                                    <td colspan="3" class="text-end"><strong>Total</strong></td>
                                    <td class="text-end">
                                        <strong t-out="doc.amount_total"
                                            t-options='{"widget": "monetary", "display_currency": doc.currency_id}'/>
                                    </td>
                                </tr>
                            </tfoot>
                        </table>

                        <!-- Bloc conditionnel -->
                        <div t-if="doc.note">
                            <h4>Notes</h4>
                            <p t-out="doc.note"/>
                        </div>

                        <!-- Image -->
                        <t t-if="doc.partner_id.image_128">
                            <img t-att-src="image_data_uri(doc.partner_id.image_128)"
                                 style="max-height: 80px;"/>
                        </t>

                    </div>
                </t>
            </t>
        </t>
    </template>
</odoo>
```

### Variables disponibles dans un template QWeb

| Variable | Contenu |
|----------|---------|
| `docs` | recordset des enregistrements à imprimer |
| `doc` | enregistrement courant (dans t-foreach) |
| `doc_ids` | liste des IDs |
| `doc_model` | nom du modèle |
| `user` | `res.users` courant |
| `company` | `res.company` courante |
| `time` | module Python `time` |
| `datetime` | module Python `datetime` |
| `formatLang(value, currency_obj=...)` | formatage monétaire/date |
| `image_data_uri(b64)` | convertit un Binary en data URI pour `<img>` |
| `keep_lines(text, max)` | tronque le texte |

---

## Surcharger la logique du rapport (Python)

```python
# report/my_model_report.py
from odoo import api, models

class MyModelReport(models.AbstractModel):
    _name = "report.my_module.report_my_model_document"  # convention: report.<module>.<template_id>
    _description = "My Model Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["my.model"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "my.model",
            "docs": docs,
            "data": data,
            # Variables custom disponibles dans le template
            "totals": {rec.id: self._compute_totals(rec) for rec in docs},
        }

    def _compute_totals(self, record):
        return {
            "subtotal": sum(record.line_ids.mapped("price_subtotal")),
            "taxes": sum(record.line_ids.mapped("tax_amount")),
        }
```

---

## Héritage d'un rapport existant

```xml
<template id="report_invoice_document_inherit_my_module"
          inherit_id="account.report_invoice_document">
    <xpath expr="//div[@name='informations']" position="after">
        <div>
            <strong>Ma référence interne :</strong>
            <span t-out="doc.my_ref"/>
        </div>
    </xpath>
</template>
```

---

## Rapport basé sur une vue SQL (rapport analytique)

```python
# report/my_analysis_report.py
from odoo import fields, models, tools

class MyAnalysisReport(models.Model):
    _name = "my.analysis.report"
    _description = "My Analysis Report"
    _auto = False          # ne pas créer de table, c'est une vue SQL
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", readonly=True)
    state = fields.Selection([("draft","Draft"),("done","Done")], readonly=True)
    amount_total = fields.Float(readonly=True)
    count = fields.Integer(readonly=True)

    def _query(self):
        return """
            SELECT
                m.id,
                m.partner_id,
                m.state,
                SUM(l.price_subtotal) AS amount_total,
                COUNT(l.id)           AS count
            FROM my_model m
            LEFT JOIN my_model_line l ON l.model_id = m.id
            GROUP BY m.id, m.partner_id, m.state
        """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS ({self._query()})
        """)
```

```xml
<!-- Vue pivot/graph sur le rapport SQL -->
<record id="my_analysis_report_view_pivot" model="ir.ui.view">
    <field name="name">my.analysis.report.pivot</field>
    <field name="model">my.analysis.report</field>
    <field name="arch" type="xml">
        <pivot string="Analysis">
            <field name="partner_id" type="row"/>
            <field name="state" type="col"/>
            <field name="amount_total" type="measure"/>
            <field name="count" type="measure"/>
        </pivot>
    </field>
</record>
```

---

## Déclencher un rapport depuis le code

```python
# Générer le PDF et retourner l'action de téléchargement
def action_print_report(self):
    self.ensure_one()
    return self.env.ref("my_module.action_report_my_model").report_action(self)

# Générer le PDF et l'attacher à l'enregistrement
def action_attach_report(self):
    report = self.env.ref("my_module.action_report_my_model")
    pdf_content, _ = report._render_qweb_pdf(self.ids)
    self.env["ir.attachment"].create({
        "name": f"{self.code}.pdf",
        "type": "binary",
        "datas": base64.b64encode(pdf_content),
        "res_model": self._name,
        "res_id": self.id,
        "mimetype": "application/pdf",
    })
```

---

## Anti-patterns rapports

- **Template QWeb sans `web.html_container`** → mise en page cassée, header/footer absent
- **Accès à des Many2one non prefetchés dans une boucle** → N+1 dans le rendu (même règle que Python)
- **`_get_report_values` sans `_name = "report.<module>.<template_id>"`** → non rattaché au rapport
- **`_auto = False` sans `init()`** → la vue SQL n'est jamais créée
- **Oubli de `tools.drop_view_if_exists`** dans `init()` → erreur à la mise à jour du module
