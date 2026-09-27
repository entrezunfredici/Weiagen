---
name: odoo-dev-mail
description: Intégration mail Odoo — mail.thread, message_post, mail.template, automated actions, subtypes, activités
models:
  - mail.thread
  - mail.template
  - mail.activity
  - ir.actions.server
operations:
  - dev
---

# Odoo — Mail, Chatter et Actions automatisées

## mail.thread — Activer le chatter sur un modèle

```python
class MyModel(models.Model):
    _name = "my.model"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(tracking=True)           # tracking=True = log dans le chatter au changement
    state = fields.Selection([...], tracking=3) # tracking=N : priorité d'ordre dans le message
    amount = fields.Float(tracking=1)
```

Dans la vue XML, ajouter le chatter :

```xml
<div class="oe_chatter">
    <field name="message_follower_ids"/>
    <field name="activity_ids"/>
    <field name="message_ids"/>
</div>
```

---

## message_post — Envoyer/logger un message

```python
# Message interne (note)
record.message_post(
    body="<p>Traitement effectué.</p>",
    message_type="comment",
    subtype_xmlid="mail.mt_note",        # note interne, non envoyée par email
)

# Message envoyé par email aux abonnés
record.message_post(
    body="<p>Votre commande a été validée.</p>",
    subject="Commande validée",
    message_type="email",
    subtype_xmlid="mail.mt_comment",     # commentaire visible et envoyé
    partner_ids=[partner.id],            # destinataires supplémentaires
    email_layout_xmlid="mail.mail_notification_light",  # layout email
)

# Log d'un changement de state (pas d'email)
record.message_post(
    body=f"<p>Statut changé : <b>{old_state}</b> → <b>{new_state}</b></p>",
    subtype_xmlid="my_module.mt_state_change",  # subtype custom
)
```

### `message_type` vs `subtype_xmlid`

| `message_type` | Usage |
|----------------|-------|
| `"email"` | Message reçu ou envoyé par email |
| `"comment"` | Commentaire utilisateur dans le chatter |
| `"notification"` | Message système automatique |

| `subtype_xmlid` | Comportement |
|-----------------|-------------|
| `mail.mt_comment` | Visible dans le chatter, envoyé aux abonnés |
| `mail.mt_note` | Note interne, visible seulement par les membres internes |
| `mail.mt_activities` | Activités (géré automatiquement) |
| `my_module.mt_state_change` | Subtype custom (voir ci-dessous) |

---

## Subtypes — contrôler les notifications par événement

```xml
<!-- data/mail_data.xml -->
<odoo>
    <!-- Subtype custom pour un changement d'état -->
    <record id="mt_state_change" model="mail.message.subtype">
        <field name="name">State Changed</field>
        <field name="res_model">my.model</field>
        <field name="default" eval="True"/>     <!-- abonné par défaut -->
        <field name="internal" eval="False"/>   <!-- visible externement -->
        <field name="description">The state of the record has changed</field>
    </record>

    <!-- Subtype lié à un subtype parent (propagation) -->
    <record id="mt_my_model_done" model="mail.message.subtype">
        <field name="name">Done</field>
        <field name="res_model">my.model</field>
        <field name="parent_id" ref="sale.mt_order_confirmed"/>
        <field name="relation_field">order_id</field>  <!-- champ Many2one vers sale.order -->
    </record>
</odoo>
```

```python
# Déclencher le bon subtype selon le changement
def _track_subtype(self, init_values):
    self.ensure_one()
    if "state" in init_values:
        if self.state == "done":
            return self.env.ref("my_module.mt_my_model_done")
        return self.env.ref("my_module.mt_state_change")
    return super()._track_subtype(init_values)
```

---

## mail.template — Templates d'email

```xml
<!-- data/mail_template.xml -->
<record id="email_template_my_model" model="mail.template">
    <field name="name">My Model: Notification</field>
    <field name="model_id" ref="my_module.model_my_model"/>
    <field name="subject">{{ object.code }} — {{ object.partner_id.name }}</field>
    <field name="email_from">{{ (object.user_id.email_formatted or user.email_formatted) }}</field>
    <field name="email_to">{{ object.partner_id.email }}</field>
    <field name="partner_to">{{ object.partner_id.id }}</field>
    <field name="body_html" type="html">
        <div>
            <p>Bonjour <t t-out="object.partner_id.name"/>,</p>
            <p>Votre dossier <strong><t t-out="object.code"/></strong>
               a été mis à jour.</p>
            <p>Montant : <t t-out="object.amount_total"/> <t t-out="object.currency_id.name"/></p>
            <p>Cordialement,<br/>
               <t t-out="object.user_id.name or user.name"/></p>
        </div>
    </field>
    <field name="auto_delete" eval="True"/>   <!-- supprime le mail.mail après envoi -->
    <field name="lang">{{ object.partner_id.lang }}</field>
</record>
```

### Envoyer un template depuis Python

```python
def action_send_notification(self):
    self.ensure_one()
    template = self.env.ref("my_module.email_template_my_model")

    # Envoi simple (sans boîte de dialogue)
    template.send_mail(self.id, force_send=True)

    # Ouvrir le wizard de composition (avec prévisualisation)
    return template.send_mail(
        self.id,
        email_values={"email_cc": "cc@example.com"},
        notif_layout="mail.mail_notification_light",
        raise_exception=True,
    )

    # Ouvrir le wizard de composition pour l'utilisateur
    ctx = {
        "default_model": self._name,
        "default_res_ids": self.ids,
        "default_use_template": True,
        "default_template_id": template.id,
        "default_composition_mode": "comment",
    }
    return {
        "type": "ir.actions.act_window",
        "res_model": "mail.compose.message",
        "view_mode": "form",
        "target": "new",
        "context": ctx,
    }
```

### Variables disponibles dans un template

| Variable | Valeur |
|----------|--------|
| `object` | L'enregistrement courant |
| `user` | L'utilisateur qui envoie |
| `ctx` | Le contexte courant |

---

## Activités (mail.activity.mixin)

```python
# Créer une activité
record.activity_schedule(
    "mail.mail_activity_data_todo",          # type d'activité (xml_id)
    date_deadline=fields.Date.today() + relativedelta(days=7),
    summary="À valider",
    note="<p>Merci de vérifier et valider ce dossier.</p>",
    user_id=record.user_id.id or self.env.user.id,
)

# Marquer une activité comme faite
record.activity_feedback(
    ["mail.mail_activity_data_todo"],
    feedback="Validé le %s" % fields.Date.today(),
)

# Annuler des activités
record.activity_unlink(["mail.mail_activity_data_todo"])

# Types d'activités standards
# mail.mail_activity_data_email   → Email
# mail.mail_activity_data_call    → Appel téléphonique
# mail.mail_activity_data_meeting → Réunion
# mail.mail_activity_data_todo    → À faire
# mail.mail_activity_data_upload_document → Document à uploader
```

### Définir un type d'activité custom

```xml
<record id="mail_activity_type_my_validation" model="mail.activity.type">
    <field name="name">My Validation</field>
    <field name="icon">fa-check-circle</field>
    <field name="decoration_type">success</field>  <!-- success, warning, danger -->
    <field name="res_model">my.model</field>        <!-- restreint à ce modèle -->
    <field name="default_note">Merci de valider ce dossier.</field>
</record>
```

---

## Actions automatisées (ir.actions.server)

Les actions automatisées s'exécutent automatiquement quand des conditions sont remplies.

### Via XML (déclencheur sur changement de champ)

```xml
<record id="auto_action_on_state_change" model="base.automation">
    <field name="name">My Model: Notify on done</field>
    <field name="model_id" ref="my_module.model_my_model"/>
    <field name="trigger">on_write</field>           <!-- on_create, on_write, on_create_or_write, on_unlink, on_time -->
    <field name="filter_pre_domain">[("state","!=","done")]</field>   <!-- état AVANT écriture -->
    <field name="filter_domain">[("state","=","done")]</field>        <!-- état APRÈS écriture -->
    <field name="action_server_ids" eval="[(4, ref('my_module.server_action_notify_done'))]"/>
</record>

<record id="server_action_notify_done" model="ir.actions.server">
    <field name="name">Send done notification</field>
    <field name="model_id" ref="my_module.model_my_model"/>
    <field name="state">code</field>
    <field name="code">
for record in records:
    template = env.ref("my_module.email_template_my_model")
    template.send_mail(record.id, force_send=False)
    </field>
</record>
```

### Déclencheurs disponibles

| `trigger` | Moment |
|-----------|--------|
| `on_create` | Après création |
| `on_write` | Après modification |
| `on_create_or_write` | Après création ou modification |
| `on_unlink` | Avant suppression |
| `on_time` | Selon une date sur le record (ex: date_deadline) |
| `on_stage_set` | Quand une étape change (CRM/Helpdesk) |
| `on_priority_set` | Quand la priorité change |

### Action serveur de type "email"

```xml
<record id="server_action_send_email" model="ir.actions.server">
    <field name="name">Send Email</field>
    <field name="model_id" ref="my_module.model_my_model"/>
    <field name="state">email</field>
    <field name="template_id" ref="my_module.email_template_my_model"/>
</record>
```

---

## Abonnés (followers)

```python
# Abonner des partenaires
record.message_subscribe(partner_ids=[partner.id])
record.message_subscribe(partner_ids=[partner.id],
                          subtype_ids=[self.env.ref("my_module.mt_state_change").id])

# Désabonner
record.message_unsubscribe(partner_ids=[partner.id])

# Vérifier si quelqu'un est abonné
is_following = record.message_is_follower
```

---

## Patterns courants

### Envoyer un email sans template (message bas niveau)

```python
self.env["mail.mail"].create({
    "subject": "Notification",
    "email_to": "dest@example.com",
    "email_from": self.env.company.email or "noreply@example.com",
    "body_html": "<p>Corps du message</p>",
    "auto_delete": True,
}).send()
```

### Notifier des utilisateurs spécifiques sans email

```python
record.message_notify(
    partner_ids=[user.partner_id.id for user in users_to_notify],
    subject="Action requise",
    body="<p>Votre intervention est requise sur ce dossier.</p>",
    record_name=record.display_name,
    model_description="My Model",
)
```

### Log sans notification (tracking silencieux)

```python
record.with_context(tracking_disable=True).write({"state": "done"})
# OU
record.with_context(mail_notrack=True).write({"amount": 100})
```

---

## Anti-patterns mail

- **`send_mail(..., force_send=True)` dans un cron** → bloque le cron, préférer `force_send=False` (envoi différé par la queue)
- **`message_post` dans un `create()` override sans `@api.model_create_multi`** → appel N fois si création multiple
- **Template avec `auto_delete=False`** → accumulation de `mail.mail` en base (nettoyer périodiquement)
- **`_track_subtype` sans `super()`** → perd les subtypes des mixins parents
- **Créer une activité dans `write()` sans vérifier si elle existe déjà** → duplications si le champ est modifié plusieurs fois
- **`message_subscribe` sur un modèle sans `_inherit = "mail.thread"`** → erreur silencieuse ou crash
