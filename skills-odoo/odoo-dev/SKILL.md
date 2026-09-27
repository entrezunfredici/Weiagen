---
name: odoo-dev
description: Développement et analyse de modules Odoo — structure, modèles Python, vues XML, sécurité, JavaScript OWL, tests, anti-patterns, performance. Versions 15 à 19.
models:
  - any
operations:
  - dev
---

# Odoo — Développement et analyse de modules

Ce skill guide le développement **et l'analyse** de modules Odoo custom (versions 15–19) en suivant les patterns OCA et les conventions des modules de référence du projet (`odoo_modules_examples/`).

---

## Environnement par version

| Version | PostgreSQL | Port WebSocket | `http_interface` | Workers | Notes |
|---------|-----------|---------------|-----------------|---------|-------|
| 15 | 14 | `longpolling_port = 8072` | absent | commenté | `unaccent = True`, `name_get()` |
| 16–17 | 14 | `gevent_port = 8072` | absent | commenté | `_compute_display_name` remplace `name_get` |
| 18 | 16 | `gevent_port = 8072` | `0.0.0.0` | commenté | |
| 19 | 16 + pgvector | dual (gevent + longpolling) | `0.0.0.0` | `workers = 2` actif | Support AI/vecteurs |

---

## Structure d'un module

```
my_module/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── my_model.py
├── views/
│   └── my_model_views.xml
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── data/
│   └── ir_cron.xml
├── wizards/
│   ├── __init__.py
│   └── my_wizard.py
├── controllers/
│   ├── __init__.py
│   └── main.py
├── static/src/
│   ├── js/*.esm.js
│   └── xml/templates.xml
├── report/
│   ├── __init__.py
│   └── my_report.py
├── tests/
│   ├── __init__.py
│   └── test_my_model.py
└── i18n/
```

---

## __manifest__.py

```python
{
    "name": "My Module",
    "version": "17.0.1.0.0",       # XX.0.major.minor.patch
    "category": "Technical Settings",
    "summary": "Short description",
    "author": "Your Company",
    "license": "AGPL-3",
    "installable": True,
    "application": False,           # True = menu racine visible
    "depends": ["base", "mail"],
    "external_dependencies": {
        "python": ["stdnum"],
    },
    "data": [
        "security/security.xml",        # sécurité EN PREMIER
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/my_model_views.xml",
    ],
    "assets": {
        "web._assets_backend": [
            "my_module/static/src/js/my_component.esm.js",
        ],
        "point_of_sale._assets_pos": [
            "my_module/static/src/js/pos_patch.esm.js",
            "my_module/static/src/xml/screens.xml",
        ],
    },
    "demo": ["data/demo.xml"],
    "development_status": "Beta",   # Alpha / Beta / Mature
    # Hooks d'installation
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
```

### Hooks de manifest (`__init__.py` racine)

```python
def pre_init_hook(env):
    """Exécuté AVANT l'installation (ex: vérifier des prérequis)."""
    pass

def post_init_hook(env):
    """Exécuté APRÈS l'installation (ex: migrer des données existantes)."""
    records = env["res.partner"].search([("vat", "!=", False)])
    for rec in records:
        rec.my_computed_field = _compute_from_vat(rec.vat)

def uninstall_hook(env):
    """Exécuté lors de la désinstallation (ex: nettoyage)."""
    env["ir.config_parameter"].sudo().search(
        [("key", "like", "my_module.%")]
    ).unlink()
```

---

## Types de champs — référence complète

```python
# --- Scalaires ---
name        = fields.Char(size=128, translate=True)
description = fields.Text(translate=True)
note        = fields.Html(sanitize=True, strip_style=False)
amount      = fields.Float(digits=(16, 2))           # (total_digits, decimal_places)
price       = fields.Monetary(currency_field="currency_id")
qty         = fields.Integer()
active      = fields.Boolean(default=True)           # False = archivé (filtre automatique)
state       = fields.Selection([("a","A"),("b","B")], default="a", required=True)
date        = fields.Date(default=fields.Date.today)
datetime    = fields.Datetime(default=fields.Datetime.now)

# --- Binaires ---
image       = fields.Image(max_width=1024, max_height=1024)   # stocké en base64, redimensionné
document    = fields.Binary(attachment=True)                  # attachment=True = stocké dans ir.attachment
filename    = fields.Char()                                   # companion champ filename pour Binary

# --- Relations ---
partner_id  = fields.Many2one("res.partner", ondelete="restrict",
                               domain="[('customer_rank','>',0)]",
                               context={"default_customer_rank": 1})
line_ids    = fields.One2many("my.line", "parent_id", copy=True)
tag_ids     = fields.Many2many(
                  "my.tag",
                  "my_model_tag_rel",   # nom de la table pivot (optionnel si unique)
                  "model_id",           # colonne left (optionnel)
                  "tag_id",             # colonne right (optionnel)
              )

# --- Calculés ---
total       = fields.Float(compute="_compute_total", store=True, readonly=True)
display     = fields.Char(compute="_compute_display", store=False)  # store=False = non persisté
alias       = fields.Char(related="partner_id.name", store=True, readonly=False)  # readonly=False = éditable

# --- Spéciaux ---
currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
company_id  = fields.Many2one("res.company", default=lambda self: self.env.company)
user_id     = fields.Many2one("res.users", default=lambda self: self.env.user)
color       = fields.Integer(string="Color Index")  # widget color dans les vues kanban

# --- Multi-company ---
# company_dependent=True : valeur différente par company (stocké dans ir.property)
margin_rate = fields.Float(company_dependent=True, default=0.15)

# --- Référence polymorphe ---
ref_doc     = fields.Reference([("sale.order","Sale"), ("purchase.order","Purchase")],
                                string="Source Document")

# --- JSON (v16+) ---
metadata    = fields.Json()  # dict Python ↔ JSON PostgreSQL

# --- Properties (v17+) — champs dynamiques définis par l'utilisateur ---
properties  = fields.Properties("definition_id", string="Properties")
# definition_id pointe vers un modèle qui définit les propriétés disponibles
```

**Règles `store=True` vs `store=False` :**
- `store=False` : recalculé à chaque lecture, **ne peut pas être utilisé dans un domain de recherche/filtre**
- `store=True` : persisté en base, utilisable en domain, déclenche une recompute si `@api.depends` change
- Un champ `related` sans `store=True` est `store=False` par défaut

---

## Modèles — patterns ORM complets

### Nouveau modèle avec toutes les options

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError

class MyModel(models.Model):
    _name = "my.model"
    _description = "My Model"
    _order = "date desc, id desc"
    _rec_name = "code"              # champ utilisé comme nom d'affichage
    _inherit = ["mail.thread", "mail.activity.mixin"]

    # Contraintes SQL (niveau PostgreSQL, vérifiées avant INSERT/UPDATE)
    _sql_constraints = [
        ("code_uniq", "UNIQUE(code, company_id)", "Le code doit être unique par société."),
        ("amount_positive", "CHECK(amount >= 0)", "Le montant doit être positif."),
    ]

    code = fields.Char(required=True, copy=False, index=True)
    amount = fields.Float()
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    # --- Compute avec inverse (champ éditable calculé) ---
    price_with_tax = fields.Float(
        compute="_compute_price_with_tax",
        inverse="_inverse_price_with_tax",
        store=False,
    )
    price = fields.Float()
    tax_rate = fields.Float(default=0.2)

    @api.depends("price", "tax_rate")
    def _compute_price_with_tax(self):
        for rec in self:
            rec.price_with_tax = rec.price * (1 + rec.tax_rate)

    def _inverse_price_with_tax(self):
        for rec in self:
            if rec.tax_rate != -1:
                rec.price = rec.price_with_tax / (1 + rec.tax_rate)

    # --- Contrainte Python ---
    @api.constrains("amount", "tax_rate")
    def _check_amounts(self):
        for rec in self:
            if rec.amount < 0:
                raise ValidationError(f"Montant invalide sur {rec.code}: doit être ≥ 0")
            if not (0 <= rec.tax_rate <= 1):
                raise ValidationError("Le taux de taxe doit être entre 0 et 1")

    # --- Onchange (UI seulement — ne pas mettre de logique critique ici) ---
    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            self.currency_id = self.partner_id.property_purchase_currency_id \
                               or self.env.company.currency_id
        else:
            self.currency_id = False

    # --- Override write pour détecter les changements ---
    def write(self, vals):
        if "state" in vals and vals["state"] == "done":
            for rec in self:
                if not rec.line_ids:
                    raise UserError(f"{rec.code} : impossible de clôturer sans lignes.")
        result = super().write(vals)
        if "amount" in vals:
            self._after_amount_change()
        return result

    # --- display_name (v16+ remplace name_get) ---
    @api.depends("code", "partner_id.name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.partner_id.name or '?'}"

    # v15 uniquement :
    # def name_get(self):
    #     return [(rec.id, f"[{rec.code}] {rec.partner_id.name}") for rec in self]
```

### `_inherits` — héritage par délégation

```python
# DIFFÉRENT de _inherit :
# _inherit = "x"   → étend le modèle x (même table ou table étendue)
# _inherits = {"x": "field_id"} → crée une table séparée avec FK vers x
#             tous les champs de x sont accessibles directement sur my.model

class MyEmployee(models.Model):
    _name = "my.employee"
    _inherits = {"res.partner": "partner_id"}  # my.employee A UN res.partner

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade")
    employee_number = fields.Char()
    # Maintenant my.employee.name == my.employee.partner_id.name (transparent)

# Cas d'usage : quand on veut enrichir un modèle existant en ajoutant une table
# liée sans modifier le modèle original (ex: hr.employee → res.partner)
# ATTENTION : _inherits crée une dépendance forte, difficile à maintenir
```

### Héritage classique `_inherit`

```python
# Extension (même _name) — ajoute des champs/méthodes au modèle existant
class ResPartner(models.Model):
    _inherit = "res.partner"          # pas de _name → même modèle, même table
    my_field = fields.Char()

# Copie avec nouveau nom — crée un nouveau modèle basé sur un existant
class MySpecialPartner(models.Model):
    _name = "my.special.partner"
    _inherit = "res.partner"          # copie le modèle, nouvelle table
    extra_field = fields.Char()
```

### AbstractModel (mixin réutilisable)

```python
class MyDateMixin(models.AbstractModel):
    _name = "my.date.mixin"
    _description = "Date Mixin"
    # Pas de _inherit → ne modifie aucun modèle existant
    # Les modèles l'utilisent via _inherit = ["my.date.mixin"]

    date_start = fields.Date(required=True)
    date_end = fields.Date()
    duration = fields.Integer(compute="_compute_duration", store=True)

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.duration = (rec.date_end - rec.date_start).days
            else:
                rec.duration = 0

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError("La date de fin doit être après la date de début.")
```

### Héritage de pos.session (chargement POS)

```python
class POSSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_res_partner(self):
        res = super()._loader_params_res_partner()
        res["search_params"]["fields"].append("my_field")
        return res
```

### `_search` override (domain custom)

```python
def _search_my_virtual_field(self, operator, value):
    """Permet d'utiliser my_virtual_field dans les domains de recherche."""
    # Traduit un domain sur un champ non stocké en domain sur champs stockés
    ids = self._cr.execute("SELECT id FROM my_model WHERE ...", (value,))
    return [("id", "in", [r[0] for r in self._cr.fetchall()])]

my_virtual_field = fields.Char(compute="_compute_virtual", search="_search_my_virtual_field")
```

### Multi-company

```python
class MyModel(models.Model):
    _name = "my.model"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    # Restreindre automatiquement aux companies accessibles
    @api.model
    def _check_company_auto(self):
        return True   # active le check auto sur les Many2one avec check_company=True

    partner_id = fields.Many2one(
        "res.partner",
        check_company=True,  # valide que partner_id appartient à la même company
    )

    # Champ dont la valeur dépend de la company (stocké dans ir.property)
    default_margin = fields.Float(company_dependent=True, default=0.15)
```

```python
# Dans les méthodes : accéder aux companies actives
current_company = self.env.company         # company principale de l'utilisateur
all_companies = self.env.companies         # toutes les companies actives (multi-company)
all_company_ids = self.env.context.get("allowed_company_ids", [self.env.company.id])
```

---

## Vues XML

### Formulaire avec header/statusbar/chatter

```xml
<record id="my_model_view_form" model="ir.ui.view">
    <field name="name">my.model.form</field>
    <field name="model">my.model</field>
    <field name="arch" type="xml">
        <form>
            <header>
                <button name="action_open" string="Open" type="object"
                    invisible="state != 'draft'" class="btn-primary"/>
                <field name="state" widget="statusbar" statusbar_visible="draft,open,done"/>
            </header>
            <sheet>
                <div class="oe_button_box" name="button_box">
                    <button class="oe_stat_button" icon="fa-list"
                        name="action_view_lines" type="object">
                        <field name="line_count" widget="statinfo" string="Lines"/>
                    </button>
                </div>
                <group>
                    <group>
                        <field name="partner_id"/>
                        <field name="date"/>
                    </group>
                    <group>
                        <field name="amount_total" widget="monetary"
                            options="{'currency_field': 'currency_id'}"/>
                    </group>
                </group>
                <notebook>
                    <page string="Lines" id="lines">
                        <field name="line_ids">
                            <tree editable="bottom">
                                <field name="product_id"/>
                                <field name="quantity"/>
                                <field name="price_unit"/>
                                <field name="price_subtotal" readonly="1"/>
                            </tree>
                        </field>
                    </page>
                </notebook>
            </sheet>
            <div class="oe_chatter">
                <field name="message_follower_ids"/>
                <field name="activity_ids"/>
                <field name="message_ids"/>
            </div>
        </form>
    </field>
</record>
```

### Tree avec décorations

```xml
<tree decoration-info="state=='draft'"
      decoration-success="state=='done'"
      decoration-danger="state=='pending'"
      decoration-muted="state in ('cancel','close')"
      decoration-warning="date_deadline and date_deadline &lt; today">
    <field name="code"/>
    <field name="partner_id"/>
    <field name="date"/>
    <field name="date_deadline" optional="hide"/>
    <field name="state"/>
    <field name="today" invisible="1"/>   <!-- champ technique pour decoration -->
</tree>
```

### Vue héritée via XPath

```xml
<record id="res_partner_form_inherit_my_module" model="ir.ui.view">
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.view_partner_form"/>
    <field name="arch" type="xml">
        <!-- Après un champ -->
        <xpath expr="//field[@name='phone']" position="after">
            <field name="my_field"/>
        </xpath>
        <!-- Modifier un attribut -->
        <xpath expr="//field[@name='email']" position="attributes">
            <attribute name="required">1</attribute>
        </xpath>
        <!-- Remplacer un nœud entier -->
        <xpath expr="//page[@name='internal']" position="replace">
            <page string="Internal (custom)" name="internal">
                <field name="comment"/>
            </page>
        </xpath>
        <!-- Raccourci par nom de champ (équivalent XPath) -->
        <field name="street" position="after">
            <field name="my_address_complement"/>
        </field>
    </field>
</record>
```

Positions XPath : `after`, `before`, `inside`, `replace`, `attributes`.

### Actions

```xml
<!-- Action window standard -->
<record id="my_model_action" model="ir.actions.act_window">
    <field name="name">My Model</field>
    <field name="res_model">my.model</field>
    <field name="view_mode">tree,form,pivot,graph</field>
    <field name="context">{'default_user_id': uid, 'search_default_my_filter': 1}</field>
    <field name="domain">[('company_id','=',allowed_company_ids[0])]</field>
</record>

<!-- Action serveur (déclenche du code Python) -->
<record id="action_mark_done" model="ir.actions.server">
    <field name="name">Mark as Done</field>
    <field name="model_id" ref="my_module.model_my_model"/>
    <field name="binding_model_id" ref="my_module.model_my_model"/>  <!-- apparaît dans Action menu -->
    <field name="state">code</field>
    <field name="code">records.write({"state": "done"})</field>
</record>

<!-- Action URL -->
<record id="action_open_url" model="ir.actions.act_url">
    <field name="name">Open External</field>
    <field name="url">https://example.com</field>
    <field name="target">new</field>
</record>

<!-- Action client (déclenche un composant OWL) -->
<record id="action_my_client" model="ir.actions.client">
    <field name="name">My Dashboard</field>
    <field name="tag">my_module.MyDashboard</field>
</record>
```

### Menu

```xml
<menuitem id="menu_root" name="My Module" sequence="50"
    web_icon="my_module,static/description/icon.png"/>
<menuitem id="menu_my_model" name="Records"
    parent="menu_root" action="my_model_action"/>
```

---

## Sécurité

### ir.model.access.csv

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model user,model_my_model,base.group_user,1,0,0,0
access_my_model_mgr,my.model manager,model_my_model,my_module.group_manager,1,1,1,1
```

Groupes standards : `base.group_user`, `base.group_system`, `account.group_account_user`.

### Record rules (security.xml)

```xml
<record id="rule_my_model_own" model="ir.rule">
    <field name="name">My Model: own records</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">[('user_id','=',user.id)]</field>
    <field name="groups" eval="[(4, ref('base.group_user'))]"/>
</record>
```

---

## Données initiales

```xml
<odoo>
    <record model="ir.cron" id="cron_my_daily_check">
        <field name="name">My Model: Daily Check</field>
        <field name="model_id" ref="my_module.model_my_model"/>
        <field name="state">code</field>
        <field name="user_id">1</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="numbercall">-1</field>
        <field name="code">model.cron_daily_check()</field>
    </record>

    <data noupdate="1">
        <record id="seq_my_model" model="ir.sequence">
            <field name="name">My Model</field>
            <field name="code">my.model</field>
            <field name="prefix">MM</field>
            <field name="padding">4</field>
            <field name="company_id" eval="False"/>
        </record>
    </data>
</odoo>
```

`noupdate="1"` = non écrasé lors des mises à jour du module.

---

## Wizards (TransientModel)

```python
from odoo import api, fields, models
from odoo.fields import Command

class MyWizard(models.TransientModel):
    _name = "my.wizard"
    _description = "My Wizard"

    record_id = fields.Many2one("my.model", required=True)
    partner_ids = fields.Many2many("res.partner")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get("active_id")
        if active_id:
            res["record_id"] = active_id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.record_id.write({
            "state": "done",
            "partner_ids": [Command.set(self.partner_ids.ids)],
        })
        return {"type": "ir.actions.act_window_close"}
```

---

## Controllers HTTP

```python
from odoo import http
from odoo.http import request

class MyController(http.Controller):

    @http.route("/my/module/data", type="json", auth="user", methods=["POST"])
    def get_data(self, record_id, **kw):
        record = request.env["my.model"].browse(record_id)
        record.check_access_rights("read")
        return {"name": record.name, "state": record.state}

    @http.route("/my/module/public/<int:record_id>", type="http", auth="public")
    def public_page(self, record_id, **kw):
        record = request.env["my.model"].sudo().browse(record_id)
        if not record.exists():
            return request.not_found()
        return request.render("my_module.public_template", {"record": record})
```

`auth` : `"user"` (connecté), `"public"` (tous), `"none"` (sans session).
`type` : `"json"` (dict → JSON), `"http"` (retourne Response/string).

---

## JavaScript / OWL (v17+)

### Patch d'une classe existante

```javascript
/** @odoo-module **/
import { SomeComponent } from "@module/path/to/component";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

patch(SomeComponent.prototype, {
    setup() {
        super.setup(...arguments);
        this.popup = useService("popup");
        this.changes.my_field = this.props.record.my_field || "";
    },
    get myLabel() {
        return _t("My label");
    },
});
```

### Template OWL hérité

```xml
<templates xml:space="preserve">
    <t t-name="MyComponent" t-inherit="OtherModule.OtherComponent"
       t-inherit-mode="extension" owl="1">
        <xpath expr="//div[hasclass('target-class')]" position="after">
            <div class="my-addition">
                <span t-out="myLabel"/>
                <input t-model="changes.my_field" class="form-control"/>
            </div>
        </xpath>
    </t>
</templates>
```

Directives OWL : `t-if`, `t-foreach`+`t-as`+`t-key`, `t-out`, `t-model`, `t-on-*`, `t-call`, `t-set`.

---

## Tests

```python
from odoo.tests import common, tagged

@tagged("post_install", "-at_install")
class TestMyModel(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})
        cls.record = cls.env["my.model"].create({
            "name": "Test",
            "partner_id": cls.partner.id,
        })

    def test_state_transition(self):
        self.assertEqual(self.record.state, "draft")
        self.record.action_open()
        self.assertEqual(self.record.state, "open")

    def test_constraint_violation(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.record.write({"amount": -1})

    def test_multicompany_isolation(self):
        company2 = self.env["res.company"].create({"name": "Company 2"})
        user2 = self.env["res.users"].create({
            "name": "User 2", "login": "u2@test.com",
            "company_ids": [(4, company2.id)],
            "company_id": company2.id,
        })
        with self.assertRaises(Exception):
            self.record.with_user(user2).read(["name"])
```

---

## Patterns courants

### Command (Many2many / One2many)

```python
from odoo.fields import Command

record.write({
    "tag_ids": [Command.set([1, 2, 3])],      # remplace tout
    "tag_ids": [Command.link(4)],              # ajoute un lien
    "tag_ids": [Command.unlink(4)],            # retire le lien
    "tag_ids": [Command.clear()],              # retire tout
    "line_ids": [Command.create({"qty": 1})],  # crée + lie
    "line_ids": [Command.delete(line_id)],     # retire + supprime
    "line_ids": [Command.update(line_id, {"qty": 2})],  # modifie sans retirer
})
```

### sudo() / with_user() / with_context()

```python
self.env["ir.sequence"].sudo().next_by_code("my.model")
record.with_user(user).read(["name"])
self.with_context(no_recompute=True, tracking_disable=True).write({"state": "open"})
```

### Gestion d'erreurs — quelle exception utiliser

```python
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

# UserError : action impossible dans l'état actuel, message affiché à l'utilisateur
raise UserError(_("Impossible de valider : la date de fin est dépassée."))

# ValidationError : contrainte métier violée (souvent dans @api.constrains)
raise ValidationError(_("Le montant doit être positif."))

# AccessError : l'utilisateur n'a pas les droits (levée auto par l'ORM, rarement manuellement)
raise AccessError(_("Vous n'avez pas accès à cet enregistrement."))

# RedirectWarning : erreur avec bouton d'action (ex: "Configurer maintenant")
action = self.env.ref("base.action_res_config_settings")
raise RedirectWarning(
    _("Veuillez configurer votre société avant de continuer."),
    action.id,
    _("Aller aux paramètres"),
)
```

### Context keys standards

```python
# Lire le contexte
active_id    = self.env.context.get("active_id")       # id de l'enregistrement actif (wizard)
active_ids   = self.env.context.get("active_ids", [])  # liste d'ids sélectionnés
active_model = self.env.context.get("active_model")    # nom du modèle actif

# Keys qui modifient le comportement ORM
self.with_context(
    tracking_disable=True,          # désactive les messages de tracking mail
    mail_notrack=True,              # idem (v15)
    no_recompute=True,              # désactive les recomputes différés
    default_partner_id=partner.id,  # valeur par défaut pour partner_id dans create
    search_default_my_filter=1,     # active un filtre dans la vue search
    group_by="state",               # groupe par défaut
    lang="fr_FR",                   # langue pour les traductions
    tz="Europe/Paris",              # timezone
    allowed_company_ids=[1, 2],     # companies actives multi-company
    bin_size=True,                  # Binary renvoie la taille au lieu du contenu
    prefetch_fields=False,          # désactive le prefetch automatique
)
```

### ir.config_parameter

```python
val = self.env["ir.config_parameter"].sudo().get_param("my_module.key", default="default")
self.env["ir.config_parameter"].sudo().set_param("my_module.key", "value")
```

### SQL direct (performance)

```python
self._cr.execute("""
    SELECT id, partner_id FROM my_model
    WHERE state = %s AND company_id = %s
""", ("open", self.env.company.id))
rows = self._cr.fetchall()
```

---

## Performance — patterns et pièges

### read_group (agrégation sans charger les records)

```python
# Compter par state
data = self.env["my.model"].read_group(
    domain=[("company_id", "=", self.env.company.id)],
    fields=["state", "amount_total:sum"],
    groupby=["state"],
)
# data = [{"state": "draft", "state_count": 5, "amount_total": 1200.0, ...}, ...]

# Mapper pour un compute
def _compute_my_count(self):
    data = self.env["my.model"].read_group(
        [("partner_id", "in", self.ids)],
        ["partner_id"],
        ["partner_id"],
    )
    mapped = {d["partner_id"][0]: d["partner_id_count"] for d in data}
    for rec in self:
        rec.my_count = mapped.get(rec.id, 0)
```

### mapped() vs boucle (éviter N+1)

```python
# MAL — N+1 requêtes si partner_id n'est pas prefetché
for rec in records:
    print(rec.partner_id.name)   # 1 requête par enregistrement

# BIEN — mapped() force le prefetch en batch
names = records.mapped("partner_id.name")  # 1-2 requêtes pour tous

# BIEN — filtrer un recordset sans boucle
open_records = records.filtered(lambda r: r.state == "open")
open_records = records.filtered("active")          # raccourci pour champ booléen

# BIEN — sorted()
sorted_records = records.sorted("date", reverse=True)
sorted_records = records.sorted(lambda r: (r.date, r.name))
```

### Prefetch et `with_prefetch()`

```python
# L'ORM prefetch automatiquement les champs du même modèle en batch
# Mais les champs Many2one de modèles différents sont chargés séparément

# Forcer un prefetch groupé
partner_ids = records.mapped("partner_id")
# Maintenant tous les partenaires sont en cache → accès à partner_id.name gratuit

# Désactiver le prefetch (rare, pour les très gros jeux de données)
for rec in records.with_context(prefetch_fields=False):
    process(rec)
```

### Indexes

```python
# Ajouter un index PostgreSQL via _auto_init
def _auto_init(self):
    super()._auto_init()
    tools.create_index(
        self._cr,
        "my_model_state_company_idx",
        self._table,
        ["state", "company_id"],
    )

# Ou via le champ (index simple)
state = fields.Selection([...], index=True)
```

### flush() et invalidate_cache()

```python
# flush() : écrit les valeurs en attente (dirty records) en base avant un SQL direct
self.env.flush_all()                      # flush tout
self.flush_recordset(["field1", "field2"]) # flush uniquement ces champs sur ce recordset

# invalidate_cache() : force la relecture depuis la base après un SQL direct
self.env.invalidate_all()
self.invalidate_recordset(["field1"])
```

---

## Anti-patterns — ce qu'il faut détecter et corriger

### sudo() abusif

```python
# MAL — contourne tous les droits sans raison
def get_partner_name(self):
    return self.env["res.partner"].sudo().browse(self.partner_id.id).name

# BIEN — lire un champ déjà accessible via relation
def get_partner_name(self):
    return self.partner_id.name  # déjà dans le contexte de sécurité courant

# sudo() est légitime pour :
# - accéder à ir.sequence, ir.config_parameter (toujours sudo)
# - opérations système dans des crons
# - hooks post_init où l'utilisateur n'est pas défini
```

### Compute sans store=True utilisé en domain

```python
# MAL — domain sur un champ compute non stocké = erreur ou résultat vide silencieux
is_overdue = fields.Boolean(compute="_compute_is_overdue")  # store=False par défaut
# Dans une vue search : domain="[('is_overdue','=',True)]" → ne fonctionne pas

# BIEN — soit store=True, soit un _search
is_overdue = fields.Boolean(compute="_compute_is_overdue", store=True)
# OU
is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")
```

### write() override sans super()

```python
# MAL
def write(self, vals):
    if "state" in vals:
        self._do_something()
    # OUBLI de super() → les valeurs ne sont jamais écrites en base !

# BIEN
def write(self, vals):
    if "state" in vals:
        self._do_something()
    return super().write(vals)
```

### create() override retournant super() sans return

```python
# MAL
def create(self, vals):
    vals["code"] = self.env["ir.sequence"].next_by_code("my.model")
    super().create(vals)    # oubli du return → retourne None

# BIEN
def create(self, vals):
    vals["code"] = self.env["ir.sequence"].next_by_code("my.model")
    return super().create(vals)
```

### @api.model sur create (v16+)

```python
# MAL en v16+ — create reçoit maintenant une liste de vals
@api.model
def create(self, vals):    # ne gère qu'un seul dict, pas les créations multi
    ...

# BIEN v16+
@api.model_create_multi
def create(self, vals_list):
    for vals in vals_list:
        ...
    return super().create(vals_list)
```

### name_get() en v16+

```python
# MAL en v16+ — name_get() est déprécié
def name_get(self):
    return [(rec.id, rec.code) for rec in self]

# BIEN v16+
@api.depends("code")
def _compute_display_name(self):
    for rec in self:
        rec.display_name = rec.code
```

### Logique métier dans @api.onchange

```python
# MAL — onchange ne s'exécute qu'en UI, pas lors des créations programmatiques
@api.onchange("partner_id")
def _onchange_partner_id(self):
    self.currency_id = self.partner_id.currency_id  # ignoré lors d'un import ou API call

# BIEN — logique dans compute + onchange pour UI seulement
@api.depends("partner_id")
def _compute_currency_id(self):
    for rec in self:
        rec.currency_id = rec.partner_id.currency_id or self.env.company.currency_id

currency_id = fields.Many2one("res.currency", compute="_compute_currency_id",
                               store=True, readonly=False)
```

### Domaines avec ID en dur

```python
# MAL — ID hardcodé, non portable entre bases
domain = [("stage_id", "=", 3)]

# BIEN — utiliser ref()
stage = self.env.ref("crm.stage_lead1", raise_if_not_found=False)
domain = [("stage_id", "=", stage.id)] if stage else []
```

### Missing ensure_one()

```python
# MAL — si self est un recordset de N records, self.name prend le premier
def action_send_email(self):
    template = self.env.ref("my_module.email_template")
    template.send_mail(self.id)   # self.id plante si len(self) != 1

# BIEN
def action_send_email(self):
    self.ensure_one()
    template = self.env.ref("my_module.email_template")
    template.send_mail(self.id)
```

### Boolean active non géré

```python
# Si un modèle a active = fields.Boolean(default=True),
# les search() filtrent automatiquement les records avec active=False
# Oubli courant : pour inclure les archivés dans une recherche
self.env["my.model"].with_context(active_test=False).search([...])
```

### Fuite mémoire dans les tests

```python
# MAL — setUpClass crée des objets qui persistent entre les tests de la classe
@classmethod
def setUpClass(cls):
    super().setUpClass()
    cls.partner = cls.env["res.partner"].create({"name": "Test"})
    # Si un test modifie cls.partner, ça affecte les autres tests

# BIEN — utiliser setUp() pour les objets modifiés entre tests,
# et setUpClass() seulement pour les fixtures en lecture seule
```

---

## Checklist analyse de code existant

Lors de l'analyse d'un module existant, vérifier :

**Modèles**
- [ ] `@api.model_create_multi` utilisé (pas `@api.model`) pour `create` en v16+
- [ ] `super()` appelé dans tous les overrides (`create`, `write`, `unlink`, `read`)
- [ ] `ensure_one()` dans les méthodes unitaires
- [ ] Champs compute utilisés en domain → `store=True` ou `search=` défini
- [ ] `name_get` remplacé par `_compute_display_name` en v16+
- [ ] Pas d'IDs hardcodés dans les domains ou données
- [ ] `sudo()` justifié (pas utilisé pour contourner des droits légitimes)
- [ ] `_sql_constraints` cohérentes avec les `@api.constrains`
- [ ] `active = fields.Boolean` géré avec `active_test=False` si besoin

**Sécurité**
- [ ] Toutes les tables ont une entrée dans `ir.model.access.csv`
- [ ] `check_access_rights` / `check_access_rule` dans les controllers publics
- [ ] Pas de données sensibles exposées dans les vues sans `groups=`

**Performance**
- [ ] Pas de boucle sur un recordset avec accès Many2one (N+1) → `mapped()` ou `read_group`
- [ ] `flush()` appelé avant SQL direct si des writes sont en attente
- [ ] `invalidate_recordset()` après SQL direct qui modifie des champs ORM
- [ ] Index sur les champs fréquemment filtrés/triés

**Vues**
- [ ] Champs `invisible` utilisés plutôt qu'`attrs` (v17+ préfère la syntaxe inline)
- [ ] `noupdate="1"` sur les séquences et données non-overridables
- [ ] `inherit_id` correct dans les vues héritées

**Manifest**
- [ ] Version au format `XX.0.Y.Y.Z`
- [ ] Ordre `data` : security → data → views
- [ ] `post_init_hook` si migration de données existantes nécessaire
