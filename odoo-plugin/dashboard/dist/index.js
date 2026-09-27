/**
 * Hermes Odoo — Dashboard Plugin
 *
 * Manage Odoo connection profiles and deny-by-default rights from the
 * Hermes dashboard, instead of the `hermes odoo profile/right ...` CLI.
 *
 * Plain IIFE, no build step — same pattern as plugins/kanban/dashboard/dist/
 * index.js. Uses window.__HERMES_PLUGIN_SDK__ for React + shadcn-ish
 * primitives, and window.__HERMES_PLUGINS__.register() to mount.
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;

  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useCallback = SDK.hooks.useCallback;
  var Card = SDK.components.Card;
  var CardContent = SDK.components.CardContent;
  var Badge = SDK.components.Badge;
  var Button = SDK.components.Button;
  var Input = SDK.components.Input;
  var Label = SDK.components.Label;
  var Select = SDK.components.Select;
  var SelectOption = SDK.components.SelectOption;
  var Checkbox =
    SDK.components.Checkbox ||
    function (props) {
      return h("input", {
        type: "checkbox",
        checked: !!props.checked,
        onChange: function (e) {
          if (props.onCheckedChange) props.onCheckedChange(e.target.checked);
        },
      });
    };

  var API = "/api/plugins/odoo";

  // FastAPI's automatic 422 (pydantic validation failure — e.g. a field
  // sent as the wrong JSON type) shapes `detail` as a LIST of
  // {loc, msg, type} objects, not a string like our own ConnectorError ->
  // HTTPException(detail=...) mapping always produces. A bare
  // `String(detail)` on that shape gives "[object Object]" (Array.toString
  // calls .toString() on each plain object element) — real bug hit on
  // test-server, 2026-08-18, see .agents/CHANGELOG_AGENT.md. Render it properly
  // instead of guessing it can't happen again.
  function formatErrorDetail(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map(function (d) {
          if (d && typeof d === "object") {
            var where = Array.isArray(d.loc) ? d.loc.join(".") : "";
            return (where ? where + ": " : "") + (d.msg || JSON.stringify(d));
          }
          return String(d);
        })
        .join("; ");
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    return String(detail);
  }

  function parseApiErrorMessage(err) {
    var msg = String((err && err.message) || err || "Unknown error");
    try {
      var idx = msg.indexOf(": ");
      var body = idx >= 0 ? msg.slice(idx + 2) : msg;
      var parsed = JSON.parse(body);
      if (parsed && parsed.detail) return formatErrorDetail(parsed.detail);
    } catch (_e) {
      /* not JSON, fall through */
    }
    return msg;
  }

  function selectChangeHandler(setter) {
    return {
      onValueChange: function (v) {
        setter(v == null ? "" : v);
      },
      onChange: function (e) {
        setter(e && e.target ? e.target.value : e);
      },
    };
  }

  function fieldLabel(text) {
    return h(Label, { className: "hermes-odoo-field-label" }, text);
  }

  function textField(label, value, onChange, extra) {
    return h(
      "div",
      { className: "hermes-odoo-field" },
      fieldLabel(label),
      h(
        Input,
        Object.assign(
          {
            value: value,
            onChange: function (e) {
              onChange(e.target.value);
            },
            className: "h-8 text-sm",
          },
          extra || {}
        )
      )
    );
  }

  function checkboxField(label, checked, onChange) {
    return h(
      "label",
      { className: "hermes-odoo-checkbox" },
      h(Checkbox, { checked: checked, onCheckedChange: onChange }),
      label
    );
  }

  // ---------------------------------------------------------------------
  // Profiles
  // ---------------------------------------------------------------------

  var EMPTY_PROFILE = {
    id: "",
    label: "",
    base_url: "",
    database: "",
    login: "",
    password: "",
    port: 443,
    enabled: true,
  };

  function ProfileForm(props) {
    var initial = props.initial || EMPTY_PROFILE;
    var isNew = !props.initial;
    var stateArr = useState(Object.assign({}, EMPTY_PROFILE, initial, { password: "" }));
    var form = stateArr[0];
    var setForm = stateArr[1];
    var savingArr = useState(false);
    var saving = savingArr[0];
    var setSaving = savingArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];

    function set(key) {
      return function (v) {
        setForm(Object.assign({}, form, { [key]: v }));
      };
    }

    function submit() {
      setSaving(true);
      setErr("");
      SDK.fetchJSON(API + "/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: form.id,
          label: form.label,
          base_url: form.base_url,
          database: form.database,
          login: form.login,
          password: form.password,
          port: Number(form.port) || 443,
          enabled: !!form.enabled,
        }),
      })
        .then(function () {
          setSaving(false);
          props.onSaved();
        })
        .catch(function (e) {
          setSaving(false);
          setErr(parseApiErrorMessage(e));
        });
    }

    return h(
      "form",
      {
        className: "hermes-odoo-form",
        onSubmit: function (e) {
          e.preventDefault();
          submit();
        },
      },
      h("div", { className: "hermes-odoo-form-title" }, isNew ? "New connection profile" : "Edit profile " + form.id),
      textField("Profile id", form.id, set("id"), { disabled: !isNew }),
      textField("Label", form.label, set("label")),
      textField("Base URL", form.base_url, set("base_url"), { placeholder: "https://mycompany.odoo.com" }),
      textField("Database", form.database, set("database")),
      textField("Login", form.login, set("login")),
      textField("Password" + (isNew ? "" : " (leave blank to keep current)"), form.password, set("password"), {
        type: "password",
      }),
      textField("Port", form.port, set("port"), { type: "number" }),
      checkboxField("Enabled", form.enabled, set("enabled")),
      err ? h("div", { className: "hermes-odoo-error" }, err) : null,
      h(
        "div",
        { className: "hermes-odoo-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(
          Button,
          { type: "submit", size: "sm", disabled: saving || !form.id || !form.base_url || !form.database || !form.login },
          saving ? "Saving..." : "Save"
        )
      )
    );
  }

  function ProfileRow(props) {
    var p = props.profile;
    return h(
      Card,
      { className: "hermes-odoo-row" },
      h(
        CardContent,
        { className: "hermes-odoo-row-content" },
        h(
          "div",
          { className: "hermes-odoo-row-main" },
          h("span", { className: "hermes-odoo-row-title" }, p.label || p.id),
          h(Badge, { variant: p.enabled ? "default" : "secondary" }, p.enabled ? "enabled" : "disabled"),
          h("span", { className: "hermes-odoo-row-sub" }, p.id + " · " + p.base_url + " (" + p.database + ")")
        ),
        h(
          "div",
          { className: "hermes-odoo-row-actions" },
          h(Button, { size: "sm", onClick: function () { props.onEdit(p); } }, "Edit"),
          h(
            Button,
            {
              size: "sm",
              variant: "destructive",
              onClick: function () {
                if (window.confirm("Delete profile '" + p.id + "'? Existing rights referencing it will stop resolving.")) {
                  props.onDelete(p.id);
                }
              },
            },
            "Delete"
          )
        )
      )
    );
  }

  function ProfilesSection(props) {
    var editingArr = useState(null); // null = not editing, {} shape = editing/new
    var editing = editingArr[0];
    var setEditing = editingArr[1];
    var creatingArr = useState(false);
    var creating = creatingArr[0];
    var setCreating = creatingArr[1];

    function closeForm() {
      setEditing(null);
      setCreating(false);
    }

    return h(
      "div",
      { className: "hermes-odoo-section" },
      h(
        "div",
        { className: "hermes-odoo-section-header" },
        h("h3", null, "Connection profiles"),
        !creating && !editing
          ? h(Button, { size: "sm", onClick: function () { setCreating(true); } }, "New profile")
          : null
      ),
      creating
        ? h(ProfileForm, {
            initial: null,
            onCancel: closeForm,
            onSaved: function () {
              closeForm();
              props.onChanged();
            },
          })
        : null,
      editing
        ? h(ProfileForm, {
            initial: editing,
            onCancel: closeForm,
            onSaved: function () {
              closeForm();
              props.onChanged();
            },
          })
        : null,
      props.profiles.length === 0 && !creating
        ? h("div", { className: "hermes-odoo-empty" }, "No connection profile configured yet.")
        : props.profiles.map(function (p) {
            return h(ProfileRow, {
              key: p.id,
              profile: p,
              onEdit: function (p) {
                setCreating(false);
                setEditing(p);
              },
              onDelete: props.onDeleteProfile,
            });
          })
    );
  }

  // ---------------------------------------------------------------------
  // Rights
  // ---------------------------------------------------------------------

  var EMPTY_RIGHT = {
    id: null,
    profile_id: "",
    odoo_model: "",
    fields: "*",
    label: "",
    create: false,
    read: true,
    update: false,
    delete: false,
    require_confirmation: false,
  };

  function RightForm(props) {
    var initial = props.initial || Object.assign({}, EMPTY_RIGHT, { profile_id: (props.profiles[0] || {}).id || "" });
    var isNew = !props.initial;
    // GET /rights returns `fields` as a real JSON array (["*"]) — the text
    // input here expects a comma-separated string. Editing a right without
    // touching the Fields box leaves form.fields as an array, which the
    // backend rejects (422) the moment Save is hit — surfaced client-side
    // as an opaque "[object Object]" (see parseApiErrorMessage: a 422's
    // `detail` is a list of validator-error objects, not a string). Real
    // bug hit on test-server, 2026-08-18 — see .agents/CHANGELOG_AGENT.md.
    var initialFields = Array.isArray(initial.fields) ? initial.fields.join(",") : initial.fields;
    var stateArr = useState(Object.assign({}, EMPTY_RIGHT, initial, { fields: initialFields }));
    var form = stateArr[0];
    var setForm = stateArr[1];
    var savingArr = useState(false);
    var saving = savingArr[0];
    var setSaving = savingArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];
    var modelsArr = useState([]);
    var models = modelsArr[0];
    var setModels = modelsArr[1];
    var modelsLoadingArr = useState(false);
    var modelsLoading = modelsLoadingArr[0];
    var setModelsLoading = modelsLoadingArr[1];
    var modelsErrArr = useState("");
    var modelsErr = modelsErrArr[0];
    var setModelsErr = modelsErrArr[1];

    function set(key) {
      return function (v) {
        setForm(Object.assign({}, form, { [key]: v }));
      };
    }

    // Model list depends on which profile is selected (each profile is a
    // separate Odoo connection) — refetch live from Odoo (ir.model) whenever
    // profile_id changes, instead of a static/free-text field.
    useEffect(
      function () {
        if (!form.profile_id) {
          setModels([]);
          return;
        }
        setModelsLoading(true);
        setModelsErr("");
        SDK.fetchJSON(API + "/models?profile_id=" + encodeURIComponent(form.profile_id))
          .then(function (res) {
            setModels(res.models || []);
            setModelsLoading(false);
          })
          .catch(function (e) {
            setModels([]);
            setModelsLoading(false);
            setModelsErr(parseApiErrorMessage(e));
          });
      },
      [form.profile_id]
    );

    function submit() {
      setSaving(true);
      setErr("");
      SDK.fetchJSON(API + "/rights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({}, form, { id: form.id || null })),
      })
        .then(function () {
          setSaving(false);
          props.onSaved();
        })
        .catch(function (e) {
          setSaving(false);
          setErr(parseApiErrorMessage(e));
        });
    }

    return h(
      "form",
      {
        className: "hermes-odoo-form",
        onSubmit: function (e) {
          e.preventDefault();
          submit();
        },
      },
      h("div", { className: "hermes-odoo-form-title" }, isNew ? "New right" : "Edit right"),
      h(
        "div",
        { className: "hermes-odoo-field" },
        fieldLabel("Connection profile"),
        h(
          Select,
          Object.assign({ value: form.profile_id, className: "h-8 text-sm" }, selectChangeHandler(set("profile_id"))),
          props.profiles.map(function (p) {
            return h(SelectOption, { key: p.id, value: p.id }, p.label || p.id);
          })
        )
      ),
      h(
        "div",
        { className: "hermes-odoo-field" },
        fieldLabel("Odoo model"),
        modelsLoading
          ? h("div", { className: "hermes-odoo-row-sub" }, "Loading models from Odoo...")
          : h(
              Select,
              Object.assign({ value: form.odoo_model, className: "h-8 text-sm" }, selectChangeHandler(set("odoo_model"))),
              [h(SelectOption, { key: "__empty", value: "" }, "— select a model —")].concat(
                // Keep the current value selectable even if it's missing from
                // the live list (stale right referencing a removed model, or
                // the Odoo lookup failed) so editing doesn't silently drop it.
                (form.odoo_model && !models.some(function (m) { return m.model === form.odoo_model; })
                  ? models.concat([{ model: form.odoo_model, name: "" }])
                  : models
                ).map(function (m) {
                  return h(SelectOption, { key: m.model, value: m.model }, m.model + (m.name ? " — " + m.name : ""));
                })
              )
            ),
        modelsErr ? h("div", { className: "hermes-odoo-error" }, "Could not load models: " + modelsErr) : null
      ),
      textField("Fields (comma-separated, or *)", form.fields, set("fields"), { placeholder: "*" }),
      textField("Label (optional)", form.label, set("label")),
      h(
        "div",
        { className: "hermes-odoo-checkbox-row" },
        checkboxField("create", form.create, set("create")),
        checkboxField("read", form.read, set("read")),
        checkboxField("update", form.update, set("update")),
        checkboxField("delete", form.delete, set("delete"))
      ),
      checkboxField("Require confirmation before any allowed op runs", form.require_confirmation, set("require_confirmation")),
      err ? h("div", { className: "hermes-odoo-error" }, err) : null,
      h(
        "div",
        { className: "hermes-odoo-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(
          Button,
          { type: "submit", size: "sm", disabled: saving || !form.profile_id || !form.odoo_model },
          saving ? "Saving..." : "Save"
        )
      )
    );
  }

  function RightRow(props) {
    var r = props.right;
    var ops = ["create", "read", "update", "delete"].filter(function (op) {
      return r[op];
    });
    return h(
      Card,
      { className: "hermes-odoo-row" },
      h(
        CardContent,
        { className: "hermes-odoo-row-content" },
        h(
          "div",
          { className: "hermes-odoo-row-main" },
          h("span", { className: "hermes-odoo-row-title" }, r.odoo_model),
          ops.map(function (op) {
            return h(Badge, { key: op, variant: "secondary" }, op);
          }),
          r.require_confirmation ? h(Badge, { variant: "destructive" }, "confirm") : null,
          h(
            "span",
            { className: "hermes-odoo-row-sub" },
            "profile " + r.profile_id + " · fields: " + (Array.isArray(r.fields) ? r.fields.join(", ") : r.fields)
          )
        ),
        h(
          "div",
          { className: "hermes-odoo-row-actions" },
          h(Button, { size: "sm", onClick: function () { props.onEdit(r); } }, "Edit"),
          h(
            Button,
            {
              size: "sm",
              variant: "destructive",
              onClick: function () {
                if (window.confirm("Delete this right?")) props.onDelete(r.id);
              },
            },
            "Delete"
          )
        )
      )
    );
  }

  function RightsSection(props) {
    var editingArr = useState(null);
    var editing = editingArr[0];
    var setEditing = editingArr[1];
    var creatingArr = useState(false);
    var creating = creatingArr[0];
    var setCreating = creatingArr[1];

    function closeForm() {
      setEditing(null);
      setCreating(false);
    }

    var canCreate = props.profiles.length > 0;

    return h(
      "div",
      { className: "hermes-odoo-section" },
      h(
        "div",
        { className: "hermes-odoo-section-header" },
        h("h3", null, "Rights"),
        !creating && !editing && canCreate
          ? h(Button, { size: "sm", onClick: function () { setCreating(true); } }, "New right")
          : null
      ),
      !canCreate ? h("div", { className: "hermes-odoo-empty" }, "Create a connection profile first.") : null,
      creating
        ? h(RightForm, {
            initial: null,
            profiles: props.profiles,
            onCancel: closeForm,
            onSaved: function () {
              closeForm();
              props.onChanged();
            },
          })
        : null,
      editing
        ? h(RightForm, {
            initial: editing,
            profiles: props.profiles,
            onCancel: closeForm,
            onSaved: function () {
              closeForm();
              props.onChanged();
            },
          })
        : null,
      props.rights.length === 0 && !creating
        ? h("div", { className: "hermes-odoo-empty" }, "No right configured yet — the agent cannot access Odoo until at least one exists.")
        : props.rights.map(function (r) {
            return h(RightRow, {
              key: r.id,
              right: r,
              onEdit: function (r) {
                setCreating(false);
                setEditing(r);
              },
              onDelete: props.onDeleteRight,
            });
          })
    );
  }

  // ---------------------------------------------------------------------
  // Root
  // ---------------------------------------------------------------------

  function OdooPage() {
    var profilesArr = useState([]);
    var profiles = profilesArr[0];
    var setProfiles = profilesArr[1];
    var rightsArr = useState([]);
    var rights = rightsArr[0];
    var setRights = rightsArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];

    var reload = useCallback(function () {
      SDK.fetchJSON(API + "/profiles")
        .then(function (res) {
          setProfiles(res.profiles || []);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
      SDK.fetchJSON(API + "/rights")
        .then(function (res) {
          setRights(res.rights || []);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }, []);

    useEffect(function () {
      reload();
    }, [reload]);

    function deleteProfile(id) {
      SDK.fetchJSON(API + "/profiles/" + encodeURIComponent(id), { method: "DELETE" })
        .then(reload)
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }

    function deleteRight(id) {
      SDK.fetchJSON(API + "/rights/" + encodeURIComponent(id), { method: "DELETE" })
        .then(reload)
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }

    return h(
      "div",
      { className: "hermes-odoo-page" },
      h("h2", null, "Odoo connector"),
      h(
        "p",
        { className: "hermes-odoo-intro" },
        "Deny-by-default: the agent can only touch what a right below explicitly allows. See the odoo-sdk skill for the full agent-facing contract."
      ),
      err ? h("div", { className: "hermes-odoo-error" }, err) : null,
      h(ProfilesSection, { profiles: profiles, onChanged: reload, onDeleteProfile: deleteProfile }),
      h(RightsSection, { profiles: profiles, rights: rights, onChanged: reload, onDeleteRight: deleteRight })
    );
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("odoo", OdooPage);
  }
})();
