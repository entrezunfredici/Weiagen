/* GENERATED FILE — do not edit directly.
 * Source: dashboard/src/*.js, assembled by dashboard/build.sh.
 * Edit the src/ files and re-run build.sh, then redeploy. */
/**
 * Hermes Access Groups — Dashboard Plugin
 *
 * Manage identity→role bindings and deny-by-default access rights from the
 * Hermes dashboard, instead of the `hermes rights role/right ...` CLI.
 * Generic on purpose: rights for Hermes's own built-ins (hermes_tool,
 * hermes_cron) and rights contributed by any plugin (odoo_model, ...) are
 * all the same shape here, grouped into one section per resource_type
 * found in the data — this plugin's dashboard has no built-in knowledge of
 * what odoo-plugin (or any other consumer) actually is. A plugin that wants
 * a richer, resource_type-specific editing experience keeps that in its
 * OWN dashboard tab instead (see odoo-plugin/dashboard/dist/index.js's
 * "Rights" section, which posts to THIS plugin's /rights endpoint under
 * the hood via its own backend).
 *
 * The role-binding form also offers a "pick from directory" dropdown of
 * cached Slack workspace members (id -> display name), backed by
 * ../directory.py — a UX convenience only, never part of the authorization
 * model. Refreshed lazily (once a day, or on-demand via "Refresh now").
 *
 * "Roles" section: an independent catalog of role entries (id/label/
 * description, see ../models.Role) managed separately from who holds them
 * (role bindings) and what they grant (rights) — RoleBindingForm and
 * RightForm both pick from this same catalog via a toggle multi-select
 * (RoleTagPicker) instead of a free-text field, and a right can now apply
 * to several roles at once.
 *
 * "MCP signing keys" section: one key (kid + secret) per EXTERNAL MCP
 * microservice (see ../token_signer.py / ../models.McpSigningKey) — governs
 * the opaque signed identity token injected into context every turn for
 * those services, entirely separate from the role/right CRUD above. This
 * plugin never verifies the token or enforces anything inside an MCP.
 *
 * SOURCE LAYOUT: this file is one of six under dashboard/src/ (00-core,
 * 01-roles, 02-role-bindings, 03-access-rights, 04-mcp-keys, 05-page),
 * concatenated by dashboard/build.sh into the single dashboard/dist/index.js
 * the Hermes dashboard host actually loads (manifest.json only names one
 * `entry`, and the host loads it via a classic <script src> — no ES module
 * import/export across separate files, and no runtime multi-file loading,
 * see ../.agents/DECISIONS.md). All six files share ONE closure (this file
 * opens the IIFE below, 05-page.js closes it) — do not wrap any of the
 * other five in their own `(function(){...})()`, they rely on sharing this
 * scope directly (var/function declarations here are visible to all of
 * them, no namespace object needed). **Edit the src/ files, then re-run
 * dashboard/build.sh — dist/index.js is generated, never hand-edited.**
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

  var API = "/api/plugins/rights";

  // Resource types Hermes itself defines (see rights_plugin/__init__.py's
  // pre_tool_call hook) — always shown, even empty, so an operator knows
  // where to configure access to Hermes's own built-in tools/crons without
  // having to create one first for the section to appear.
  var BUILTIN_RESOURCE_TYPES = ["hermes_tool", "hermes_cron"];
  var RESOURCE_TYPE_LABELS = {
    hermes_tool: "Hermes tools (built-in + other plugins' + MCP, by name)",
    hermes_cron: "Hermes crons",
  };

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

  function fieldLabel(text) {
    return h(Label, { className: "hermes-rights-field-label" }, text);
  }

  function textField(label, value, onChange, extra) {
    return h(
      "div",
      { className: "hermes-rights-field" },
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
      { className: "hermes-rights-checkbox" },
      h(Checkbox, { checked: checked, onCheckedChange: onChange }),
      label
    );
  }

  // Toggle multi-select of the role catalog, reused by RoleBindingForm
  // (which roles does this identity hold) and RightForm (which roles does
  // this right apply to) — same clickable-tag pattern as the directory
  // pick-list, but bascule (toggle) instead of single-select: clicking a
  // tag adds/removes it from `selected`.
  function RoleTagPicker(props) {
    var selected = props.selected || [];
    var allRoles = props.allRoles || [];
    return h(
      "div",
      { className: "hermes-rights-tag-list" },
      allRoles.length === 0
        ? h("span", { className: "hermes-rights-empty" }, "No role in the catalog yet — add one in the Roles section above.")
        : allRoles.map(function (r) {
            var isSelected = selected.indexOf(r.id) !== -1;
            return h(
              "button",
              {
                type: "button",
                key: r.id,
                className: "hermes-rights-tag" + (isSelected ? " hermes-rights-tag-selected" : ""),
                onClick: function () { props.onToggle(r.id); },
              },
              r.label || r.id
            );
          })
    );
  }  // ---------------------------------------------------------------------
  // Role catalog
  // ---------------------------------------------------------------------

  var EMPTY_ROLE = { id: "", label: "", description: "" };

  function RoleForm(props) {
    var stateArr = useState(EMPTY_ROLE);
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
      SDK.fetchJSON(API + "/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
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
        className: "hermes-rights-form",
        onSubmit: function (e) {
          e.preventDefault();
          submit();
        },
      },
      h("div", { className: "hermes-rights-form-title" }, "New role"),
      textField("Id (the slug used everywhere else)", form.id, set("id"), { placeholder: "admin" }),
      textField("Label", form.label, set("label"), { placeholder: "Administrateur" }),
      textField("Description (optional)", form.description, set("description")),
      err ? h("div", { className: "hermes-rights-error" }, err) : null,
      h(
        "div",
        { className: "hermes-rights-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(Button, { type: "submit", size: "sm", disabled: saving || !form.id }, saving ? "Saving..." : "Save")
      )
    );
  }

  // Adds one person to one role, from the role's own row — merges into
  // whatever roles that identity already holds (read-modify-write over the
  // same /role-bindings POST used everywhere else) rather than replacing
  // their binding outright, so adding someone to "finance" here never
  // silently drops their existing "admin". Reuses the same platform-picker
  // + directory-tag-picker pattern as RoleBindingForm, simplified (no
  // RoleTagPicker here — the role being added is fixed to props.roleId).
  function AddPersonToRoleForm(props) {
    var platformArr = useState("");
    var platform = platformArr[0];
    var setPlatform = platformArr[1];
    var userArr = useState("");
    var user = userArr[0];
    var setUser = userArr[1];
    var labelArr = useState("");
    var label = labelArr[0];
    var setLabel = labelArr[1];
    var savingArr = useState(false);
    var saving = savingArr[0];
    var setSaving = savingArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];

    var connectedPlatforms = props.connectedPlatforms || [];
    var directoryForPlatform = (props.directory || []).filter(function (e) {
      return e.platform === platform;
    });

    function pickFromDirectory(entry) {
      setUser(entry.external_user_id);
      if (!label) setLabel(entry.display_name);
    }

    function submit(e) {
      e.preventDefault();
      if (!platform || !user) return;
      setSaving(true);
      setErr("");
      var existing = (props.bindings || []).filter(function (b) {
        return b.platform === platform && b.external_user_id === user;
      })[0];
      var roles = existing ? existing.roles.slice() : [];
      if (roles.indexOf(props.roleId) === -1) roles.push(props.roleId);
      SDK.fetchJSON(API + "/role-bindings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: platform,
          user: user,
          roles: roles.join(","),
          label: label || (existing ? existing.label : ""),
        }),
      })
        .then(function () {
          setSaving(false);
          props.onDone();
        })
        .catch(function (e2) {
          setSaving(false);
          setErr(parseApiErrorMessage(e2));
        });
    }

    return h(
      "form",
      { className: "hermes-rights-form", onSubmit: submit },
      connectedPlatforms.length > 0
        ? h(
            "div",
            { className: "hermes-rights-field" },
            fieldLabel("Platform"),
            h(
              "select",
              {
                className: "hermes-rights-directory-select",
                value: platform,
                onChange: function (e) { setPlatform(e.target.value); setUser(""); },
              },
              h("option", { value: "" }, "— choose a platform —"),
              connectedPlatforms.map(function (p) {
                return h("option", { key: p.slug, value: p.slug }, p.label);
              })
            )
          )
        : textField("Platform", platform, setPlatform, { placeholder: "slack" }),
      directoryForPlatform.length > 0
        ? h(
            "div",
            { className: "hermes-rights-field" },
            fieldLabel("Pick a user"),
            h(
              "div",
              { className: "hermes-rights-tag-list" },
              directoryForPlatform.map(function (e) {
                var selected = user === e.external_user_id;
                return h(
                  "button",
                  {
                    type: "button",
                    key: e.external_user_id,
                    className: "hermes-rights-tag" + (selected ? " hermes-rights-tag-selected" : ""),
                    onClick: function () { pickFromDirectory(e); },
                  },
                  e.display_name || e.external_user_id
                );
              })
            )
          )
        : null,
      textField("User id", user, setUser, { placeholder: "U0123ABC" }),
      textField("Label (optional)", label, setLabel),
      err ? h("div", { className: "hermes-rights-error" }, err) : null,
      h(
        "div",
        { className: "hermes-rights-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(Button, { type: "submit", size: "sm", disabled: saving || !platform || !user }, saving ? "Adding..." : "Add")
      )
    );
  }

  function RoleRow(props) {
    var r = props.role;
    var addingArr = useState(false);
    var adding = addingArr[0];
    var setAdding = addingArr[1];

    // Every binding that currently lists this role — computed client-side
    // from the same `bindings` array the "Identity → role bindings"
    // section already fetched, no extra request.
    var members = (props.bindings || []).filter(function (b) {
      return (b.roles || []).indexOf(r.id) !== -1;
    });

    function removeMember(binding) {
      var remaining = (binding.roles || []).filter(function (x) { return x !== r.id; });
      if (remaining.length === 0) {
        // No roles left on this binding — unbind it outright rather than
        // leaving an empty, purposeless RoleBinding row around.
        props.onUnbind(binding);
      } else {
        props.onUpdateBindingRoles(binding, remaining);
      }
    }

    return h(
      Card,
      { className: "hermes-rights-row" },
      h(
        CardContent,
        { className: "hermes-rights-row-content-column" },
        h(
          "div",
          { className: "hermes-rights-row-content" },
          h(
            "div",
            { className: "hermes-rights-row-main" },
            h("span", { className: "hermes-rights-row-title" }, r.label || r.id),
            h("span", { className: "hermes-rights-row-sub" }, r.id + (r.description ? " · " + r.description : ""))
          ),
          h(
            "div",
            { className: "hermes-rights-row-actions" },
            h(Button, { size: "sm", onClick: function () { setAdding(!adding); } }, adding ? "Cancel" : "Add person"),
            h(
              Button,
              {
                size: "sm",
                variant: "destructive",
                onClick: function () {
                  if (
                    window.confirm(
                      "Delete role '" + (r.label || r.id) + "'? Bindings/rights that still reference it are not touched."
                    )
                  ) {
                    props.onDelete(r.id);
                  }
                },
              },
              "Delete role"
            )
          )
        ),
        h(
          "div",
          { className: "hermes-rights-tag-list" },
          members.length === 0
            ? h("span", { className: "hermes-rights-empty" }, "No one holds this role yet.")
            : members.map(function (b) {
                return h(
                  "span",
                  { key: b.id, className: "hermes-rights-tag hermes-rights-tag-selected hermes-rights-tag-removable" },
                  b.label || b.id,
                  h(
                    "button",
                    {
                      type: "button",
                      className: "hermes-rights-tag-remove",
                      title: "Remove this person from '" + (r.label || r.id) + "'",
                      onClick: function () { removeMember(b); },
                    },
                    "×"
                  )
                );
              })
        ),
        adding
          ? h(AddPersonToRoleForm, {
              roleId: r.id,
              connectedPlatforms: props.connectedPlatforms,
              directory: props.directory,
              bindings: props.bindings,
              onCancel: function () { setAdding(false); },
              onDone: function () {
                setAdding(false);
                props.onChanged();
              },
            })
          : null
      )
    );
  }

  function RolesSection(props) {
    var creatingArr = useState(false);
    var creating = creatingArr[0];
    var setCreating = creatingArr[1];

    return h(
      "div",
      { className: "hermes-rights-section" },
      h(
        "div",
        { className: "hermes-rights-section-header" },
        h("h3", null, "Roles"),
        !creating ? h(Button, { size: "sm", onClick: function () { setCreating(true); } }, "New role") : null
      ),
      h(
        "p",
        { className: "hermes-rights-intro" },
        "Managed independently of who holds them or what they grant — " +
          "\"everyone\" is always implicitly held by every identity, \"automation\" by cron/system sessions. " +
          "Each role below also lists who currently holds it, editable directly."
      ),
      creating
        ? h(RoleForm, {
            onCancel: function () { setCreating(false); },
            onSaved: function () {
              setCreating(false);
              props.onChanged();
            },
          })
        : null,
      props.roles.length === 0 && !creating
        ? h("div", { className: "hermes-rights-empty" }, "No role yet.")
        : props.roles.map(function (r) {
            return h(RoleRow, {
              key: r.id,
              role: r,
              bindings: props.bindings,
              connectedPlatforms: props.connectedPlatforms,
              directory: props.directory,
              onDelete: props.onDeleteRole,
              onChanged: props.onChanged,
              onUnbind: props.onUnbindMember,
              onUpdateBindingRoles: props.onUpdateBindingRoles,
            });
          })
    );
  }
  // ---------------------------------------------------------------------
  // Role bindings
  // ---------------------------------------------------------------------

  var EMPTY_BINDING = { platform: "", user: "", roles: [], label: "" };
  var OTHER_PLATFORM = "__other__";

  function RoleBindingForm(props) {
    // No "Edit" action exists today (RoleBindingRow only offers "Unbind"),
    // so props.initial is always null in practice. `roles` is kept as a
    // real array in form state (for RoleTagPicker) regardless — GET
    // /role-bindings already returns it as one, so no normalization needed
    // if an edit-in-place feature is added later.
    var initialProps = props.initial || {};
    var stateArr = useState(Object.assign({}, EMPTY_BINDING, initialProps));
    var form = stateArr[0];
    var setForm = stateArr[1];
    var savingArr = useState(false);
    var saving = savingArr[0];
    var setSaving = savingArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];
    var isNew = !props.initial;

    var connectedPlatforms = props.connectedPlatforms || [];
    // "select" once there's at least one known-connected platform to offer
    // (the common case) — "manual" (free-text) otherwise, e.g. a dev
    // deployment with nothing configured yet, or the admin picking "Other".
    var platformModeArr = useState(isNew && connectedPlatforms.length > 0 ? "select" : "manual");
    var platformMode = platformModeArr[0];
    var setPlatformMode = platformModeArr[1];

    var filterArr = useState("");
    var filter = filterArr[0];
    var setFilter = filterArr[1];

    function set(key) {
      return function (v) {
        setForm(Object.assign({}, form, { [key]: v }));
      };
    }

    function onPlatformSelect(e) {
      var v = e.target.value;
      if (v === OTHER_PLATFORM) {
        setPlatformMode("manual");
        return;
      }
      setForm(Object.assign({}, form, { platform: v, user: "" }));
    }

    // Picking a name from the cached directory (see directory.py) fills
    // both the user id and, if still empty, the label — instead of asking
    // an admin to copy/paste a raw Slack id by hand. Only offered for new
    // bindings (platform+user are locked/disabled once editing an existing
    // one, see the fields below) and only once a directory is actually
    // cached for the currently-typed platform.
    var directoryForPlatform = isNew
      ? (props.directory || []).filter(function (e) {
          return e.platform === (form.platform || "").trim().toLowerCase();
        })
      : [];

    var filteredDirectory = filter.trim()
      ? directoryForPlatform.filter(function (e) {
          var needle = filter.trim().toLowerCase();
          return (
            (e.display_name || "").toLowerCase().indexOf(needle) !== -1 ||
            e.external_user_id.toLowerCase().indexOf(needle) !== -1
          );
        })
      : directoryForPlatform;

    function pickFromDirectory(entry) {
      setForm(
        Object.assign({}, form, {
          user: entry.external_user_id,
          label: form.label || entry.display_name,
        })
      );
    }

    function toggleRole(roleId) {
      var roles = form.roles || [];
      var next = roles.indexOf(roleId) === -1 ? roles.concat([roleId]) : roles.filter(function (r) { return r !== roleId; });
      setForm(Object.assign({}, form, { roles: next }));
    }

    function submit() {
      setSaving(true);
      setErr("");
      SDK.fetchJSON(API + "/role-bindings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: form.platform,
          user: form.user,
          roles: (form.roles || []).join(","),
          label: form.label,
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
        className: "hermes-rights-form",
        onSubmit: function (e) {
          e.preventDefault();
          submit();
        },
      },
      h("div", { className: "hermes-rights-form-title" }, isNew ? "New role binding" : "Edit role binding"),
      platformMode === "select"
        ? h(
            "div",
            { className: "hermes-rights-field" },
            fieldLabel("Platform (connected on this deployment)"),
            h(
              "select",
              { className: "hermes-rights-directory-select", value: form.platform || "", onChange: onPlatformSelect },
              h("option", { value: "" }, "— choose a platform —"),
              connectedPlatforms.map(function (p) {
                return h("option", { key: p.slug, value: p.slug }, p.label);
              }),
              h("option", { value: OTHER_PLATFORM }, "Other (type manually)…")
            )
          )
        : textField("Platform", form.platform, set("platform"), { placeholder: "slack", disabled: !isNew }),
      directoryForPlatform.length > 0
        ? h(
            "div",
            { className: "hermes-rights-field" },
            fieldLabel("Pick a user (" + directoryForPlatform.length + " known)"),
            directoryForPlatform.length > 8
              ? h(Input, {
                  value: filter,
                  onChange: function (e) { setFilter(e.target.value); },
                  placeholder: "Filter by name or id...",
                  className: "h-8 text-sm",
                })
              : null,
            h(
              "div",
              { className: "hermes-rights-tag-list" },
              filteredDirectory.length === 0
                ? h("span", { className: "hermes-rights-empty" }, "No match")
                : filteredDirectory.map(function (e) {
                    var selected = form.user === e.external_user_id;
                    return h(
                      "button",
                      {
                        type: "button",
                        key: e.external_user_id,
                        className: "hermes-rights-tag" + (selected ? " hermes-rights-tag-selected" : ""),
                        onClick: function () { pickFromDirectory(e); },
                      },
                      e.display_name || e.external_user_id
                    );
                  })
            )
          )
        : null,
      textField("User id", form.user, set("user"), { placeholder: "U0123ABC", disabled: !isNew }),
      h(
        "div",
        { className: "hermes-rights-field" },
        fieldLabel("Roles"),
        h(RoleTagPicker, { allRoles: props.roles, selected: form.roles, onToggle: toggleRole })
      ),
      textField("Label (optional)", form.label, set("label"), { placeholder: "Real name, for readability" }),
      err ? h("div", { className: "hermes-rights-error" }, err) : null,
      h(
        "div",
        { className: "hermes-rights-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(
          Button,
          { type: "submit", size: "sm", disabled: saving || !form.platform || !form.user || !(form.roles || []).length },
          saving ? "Saving..." : "Save"
        )
      )
    );
  }

  function RoleBindingRow(props) {
    var b = props.binding;
    return h(
      Card,
      { className: "hermes-rights-row" },
      h(
        CardContent,
        { className: "hermes-rights-row-content" },
        h(
          "div",
          { className: "hermes-rights-row-main" },
          h("span", { className: "hermes-rights-row-title" }, b.label || b.id),
          (b.roles || []).map(function (r) {
            return h(Badge, { key: r, variant: "secondary" }, r);
          }),
          h("span", { className: "hermes-rights-row-sub" }, b.platform + " · " + b.external_user_id)
        ),
        h(
          "div",
          { className: "hermes-rights-row-actions" },
          h(
            Button,
            {
              size: "sm",
              variant: "destructive",
              onClick: function () {
                if (window.confirm("Unbind '" + (b.label || b.id) + "'? They fall back to the implicit \"everyone\" role only.")) {
                  props.onDelete(b);
                }
              },
            },
            "Unbind"
          )
        )
      )
    );
  }

  function formatSyncedAt(epochSeconds) {
    if (!epochSeconds) return "never synced";
    var deltaMin = Math.max(0, Math.round((Date.now() / 1000 - epochSeconds) / 60));
    if (deltaMin < 1) return "synced just now";
    if (deltaMin < 60) return "synced " + deltaMin + "m ago";
    var deltaH = Math.round(deltaMin / 60);
    if (deltaH < 48) return "synced " + deltaH + "h ago";
    return "synced " + Math.round(deltaH / 24) + "d ago";
  }

  function DirectoryStatus(props) {
    return h(
      "div",
      { className: "hermes-rights-directory-status" },
      h(
        "span",
        { className: "hermes-rights-row-sub" },
        "Slack directory: " +
          props.directory.length +
          " member(s), " +
          formatSyncedAt(props.syncedAt) +
          " — refreshed automatically once a day, or:"
      ),
      h(
        Button,
        {
          type: "button",
          size: "sm",
          variant: "secondary",
          disabled: props.syncing,
          onClick: props.onSync,
        },
        props.syncing ? "Syncing..." : "Refresh now"
      ),
      props.syncError ? h("span", { className: "hermes-rights-error" }, props.syncError) : null
    );
  }

  function RoleBindingsSection(props) {
    var creatingArr = useState(false);
    var creating = creatingArr[0];
    var setCreating = creatingArr[1];

    return h(
      "div",
      { className: "hermes-rights-section" },
      h(
        "div",
        { className: "hermes-rights-section-header" },
        h("h3", null, "Identity → role bindings"),
        !creating
          ? h(Button, { size: "sm", onClick: function () { setCreating(true); } }, "New binding")
          : null
      ),
      h(DirectoryStatus, {
        directory: props.directory,
        syncedAt: props.directorySyncedAt,
        syncing: props.directorySyncing,
        syncError: props.directorySyncError,
        onSync: props.onSyncDirectory,
      }),
      creating
        ? h(RoleBindingForm, {
            initial: null,
            directory: props.directory,
            connectedPlatforms: props.connectedPlatforms,
            roles: props.roles,
            onCancel: function () { setCreating(false); },
            onSaved: function () {
              setCreating(false);
              props.onChanged();
            },
          })
        : null,
      props.bindings.length === 0 && !creating
        ? h(
            "div",
            { className: "hermes-rights-empty" },
            "No binding — every identity falls back to the implicit \"everyone\" role (and \"automation\" for cron/system sessions)."
          )
        : props.bindings.map(function (b) {
            return h(RoleBindingRow, { key: b.id, binding: b, onDelete: props.onDeleteBinding });
          })
    );
  }
  // ---------------------------------------------------------------------
  // Access rights — generic, grouped client-side by resource_type
  // ---------------------------------------------------------------------

  function emptyRight(resourceType) {
    return {
      id: null,
      roles: [],
      resource_type: resourceType || "",
      // hermes_cron rights are a coarse capability, not a per-job ACL —
      // resource_id is always "*" (see .agents/DECISIONS.md, 2026-08-19).
      resource_id: resourceType === "hermes_cron" ? "*" : "",
      fields: "*",
      label: "",
      create: false,
      read: true,
      update: false,
      delete: false,
      execute: false,
      require_confirmation: false,
    };
  }

  // Native <select> (grouped by toolset via <optgroup>) fed by the live
  // Hermes tool catalog (see ../tools_catalog.py) — replaces free-typing a
  // tool name for hermes_tool rights. A flat filterable list would need
  // custom JS; <optgroup> is a plain HTML feature that does the grouping
  // for free.
  function ToolPicker(props) {
    var tools = props.tools || [];
    var groups = {};
    tools.forEach(function (t) {
      var key = t.toolset || "";
      if (!groups[key]) groups[key] = [];
      groups[key].push(t);
    });
    var toolsetNames = Object.keys(groups).sort(function (a, b) {
      if (!a) return 1; // unlabeled toolset last
      if (!b) return -1;
      return a < b ? -1 : a > b ? 1 : 0;
    });
    return h(
      "select",
      {
        className: "hermes-rights-directory-select",
        value: props.value || "",
        onChange: function (e) { props.onChange(e.target.value); },
      },
      h("option", { value: "" }, "— choose a tool —"),
      h("option", { value: "*" }, "* — any tool"),
      toolsetNames.map(function (toolset) {
        return h(
          "optgroup",
          { key: toolset || "(other)", label: toolset || "(other)" },
          groups[toolset].map(function (t) {
            return h("option", { key: t.name, value: t.name }, t.name);
          })
        );
      })
    );
  }

  function RightForm(props) {
    var initial = props.initial || emptyRight(props.defaultResourceType);
    var isNew = !props.initial;
    // GET /rights returns `fields` as a real JSON array (["*"]) — the text
    // input here expects a comma-separated string. Editing a right without
    // this normalization silently leaves form.fields as an array, which
    // the backend's Pydantic model rejects (422) the moment the user hits
    // Save without having touched the Fields box themselves — surfaced as
    // an opaque "[object Object]" (see parseApiErrorMessage below: a 422's
    // `detail` is a list of validator-error objects, not a string).
    var initialFields = Array.isArray(initial.fields) ? initial.fields.join(",") : initial.fields;
    var stateArr = useState(
      Object.assign({}, emptyRight(props.defaultResourceType), initial, { fields: initialFields })
    );
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

    function toggleRole(roleId) {
      var roles = form.roles || [];
      var next = roles.indexOf(roleId) === -1 ? roles.concat([roleId]) : roles.filter(function (r) { return r !== roleId; });
      setForm(Object.assign({}, form, { roles: next }));
    }

    // Fixed for the lifetime of this form instance: resource_type is
    // disabled/locked to props.defaultResourceType whenever one is set
    // (always true in practice — RightForm is only ever mounted from inside
    // ResourceTypeGroup, which always passes it), so there's no "switches
    // mid-form" case to handle.
    var isHermesTool = form.resource_type === "hermes_tool";
    var isHermesCron = form.resource_type === "hermes_cron";

    function submit() {
      setSaving(true);
      setErr("");
      SDK.fetchJSON(API + "/rights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // roles: array in form state (for RoleTagPicker) -> comma string on
        // the wire (RightBody.roles: str, same convention as
        // RoleBindingBody.roles) — same shape trap `fields` had (see the
        // comment above initialFields): never send the raw array.
        body: JSON.stringify(Object.assign({}, form, { id: form.id || null, roles: (form.roles || []).join(",") })),
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
        className: "hermes-rights-form",
        onSubmit: function (e) {
          e.preventDefault();
          submit();
        },
      },
      h("div", { className: "hermes-rights-form-title" }, isNew ? "New right" : "Edit right"),
      h(
        "div",
        { className: "hermes-rights-field" },
        fieldLabel("Roles"),
        h(RoleTagPicker, { allRoles: props.roles, selected: form.roles, onToggle: toggleRole })
      ),
      textField("Resource type", form.resource_type, set("resource_type"), {
        placeholder: "hermes_tool, odoo_model, ...",
        disabled: !!props.defaultResourceType,
      }),
      isHermesTool
        ? h(
            "div",
            { className: "hermes-rights-field" },
            fieldLabel("Tool"),
            h(ToolPicker, { tools: props.hermesTools, value: form.resource_id, onChange: set("resource_id") })
          )
        : isHermesCron
        ? h(
            "div",
            { className: "hermes-rights-field" },
            fieldLabel("Resource id"),
            h("div", { className: "hermes-rights-row-sub" }, "* — all cron jobs (no per-job scoping)")
          )
        : textField("Resource id", form.resource_id, set("resource_id"), {
            placeholder: "shell_exec, 1:project.task, or * for any",
          }),
      // hermes_tool/hermes_cron have no field concept at all (a bare tool
      // or cron call has no "fields" the way an Odoo model record does) —
      // the backend force-overrides this to ["*"] regardless of what's
      // submitted (see models.create_access_right), but the field was
      // still editable here, which is exactly how a right got silently
      // bricked in production: typing the tool name into this box (a
      // very natural but wrong guess at "scoping" the right) makes
      // engine.check_right stop matching this right at all, for any
      // operation, since it always evaluates hermes_tool/hermes_cron with
      // field="*" (see .agents/DECISIONS.md, 2026-08-20). Not editable
      // for these two types — nothing to type that would do anything.
      isHermesTool || isHermesCron
        ? null
        : textField("Fields (comma-separated, or *)", form.fields, set("fields"), { placeholder: "*" }),
      textField("Label (optional)", form.label, set("label")),
      // create/read/update/delete/execute are only meaningful for the
      // resource_type they actually gate (see rights_plugin/__init__.py::
      // _pre_tool_call) — showing the other, inert checkboxes is exactly
      // what caused the "what does CRUD mean for a tool?" confusion this
      // was built to fix.
      isHermesCron
        ? h(
            "div",
            { className: "hermes-rights-checkbox-row" },
            checkboxField("create", form.create, set("create")),
            checkboxField("read", form.read, set("read")),
            checkboxField("update", form.update, set("update")),
            checkboxField("delete", form.delete, set("delete"))
          )
        : isHermesTool
        ? h(
            "div",
            { className: "hermes-rights-checkbox-row" },
            checkboxField("execute", form.execute, set("execute"))
          )
        : h(
            "div",
            { className: "hermes-rights-checkbox-row" },
            checkboxField("create", form.create, set("create")),
            checkboxField("read", form.read, set("read")),
            checkboxField("update", form.update, set("update")),
            checkboxField("delete", form.delete, set("delete")),
            checkboxField("execute", form.execute, set("execute"))
          ),
      checkboxField("Require confirmation before any allowed op runs", form.require_confirmation, set("require_confirmation")),
      err ? h("div", { className: "hermes-rights-error" }, err) : null,
      h(
        "div",
        { className: "hermes-rights-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(
          Button,
          { type: "submit", size: "sm", disabled: saving || !(form.roles || []).length || !form.resource_type || !form.resource_id },
          saving ? "Saving..." : "Save"
        )
      )
    );
  }

  function RightRow(props) {
    var r = props.right;
    var ops = ["create", "read", "update", "delete", "execute"].filter(function (op) {
      return r[op];
    });
    return h(
      Card,
      { className: "hermes-rights-row" },
      h(
        CardContent,
        { className: "hermes-rights-row-content" },
        h(
          "div",
          { className: "hermes-rights-row-main" },
          h("span", { className: "hermes-rights-row-title" }, r.resource_id),
          (r.roles || []).map(function (roleId) {
            return h(Badge, { key: roleId, variant: "outline" }, roleId);
          }),
          ops.map(function (op) {
            return h(Badge, { key: op, variant: "secondary" }, op);
          }),
          r.require_confirmation ? h(Badge, { variant: "destructive" }, "confirm") : null,
          h(
            "span",
            { className: "hermes-rights-row-sub" },
            "fields: " + (Array.isArray(r.fields) ? r.fields.join(", ") : r.fields)
          )
        ),
        h(
          "div",
          { className: "hermes-rights-row-actions" },
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

  function ResourceTypeGroup(props) {
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

    var note = RESOURCE_TYPE_LABELS[props.resourceType];

    return h(
      "div",
      { className: "hermes-rights-group" },
      h(
        "div",
        { className: "hermes-rights-group-header" },
        h(
          "div",
          { className: "hermes-rights-group-title" },
          h("span", null, props.resourceType),
          h(Badge, { variant: "outline" }, String(props.rights.length))
        ),
        !creating && !editing
          ? h(Button, { size: "sm", onClick: function () { setCreating(true); } }, "New right")
          : null
      ),
      note ? h("div", { className: "hermes-rights-group-note" }, note) : null,
      creating
        ? h(RightForm, {
            initial: null,
            defaultResourceType: props.resourceType,
            roles: props.roles,
            hermesTools: props.hermesTools,
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
            defaultResourceType: props.resourceType,
            roles: props.roles,
            hermesTools: props.hermesTools,
            onCancel: closeForm,
            onSaved: function () {
              closeForm();
              props.onChanged();
            },
          })
        : null,
      props.rights.length === 0 && !creating
        ? h("div", { className: "hermes-rights-empty" }, "No right configured for this resource type yet.")
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

  function AccessRightsSection(props) {
    var groups = {};
    props.rights.forEach(function (r) {
      var key = r.resource_type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(r);
    });
    BUILTIN_RESOURCE_TYPES.forEach(function (t) {
      if (!groups[t]) groups[t] = [];
    });

    var resourceTypes = Object.keys(groups).sort(function (a, b) {
      var ai = BUILTIN_RESOURCE_TYPES.indexOf(a);
      var bi = BUILTIN_RESOURCE_TYPES.indexOf(b);
      if (ai !== -1 || bi !== -1) {
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      }
      return a < b ? -1 : a > b ? 1 : 0;
    });

    return h(
      "div",
      { className: "hermes-rights-section" },
      h("h3", null, "Access rights"),
      resourceTypes.map(function (rt) {
        return h(ResourceTypeGroup, {
          key: rt,
          resourceType: rt,
          rights: groups[rt],
          roles: props.roles,
          hermesTools: props.hermesTools,
          onChanged: props.onChanged,
          onDeleteRight: props.onDeleteRight,
        });
      })
    );
  }
  // ---------------------------------------------------------------------
  // MCP signing keys — one per EXTERNAL MCP microservice (see
  // ../token_signer.py / ../models.McpSigningKey). Distinct from every
  // section above: these back a signed, opaque token injected into context
  // every turn, never an authorization decision made by this plugin itself.
  // ---------------------------------------------------------------------

  var EMPTY_MCP_KEY = { id: "", label: "", alg: "HS256", secret: "", active: true };

  function McpKeyForm(props) {
    var isEdit = !!props.initial;
    var stateArr = useState(props.initial || EMPTY_MCP_KEY);
    var form = stateArr[0];
    var setForm = stateArr[1];
    var savingArr = useState(false);
    var saving = savingArr[0];
    var setSaving = savingArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];
    var revealedArr = useState("");
    var revealed = revealedArr[0];
    var setRevealed = revealedArr[1];

    function set(key) {
      return function (v) {
        setForm(Object.assign({}, form, { [key]: v }));
      };
    }

    function submit() {
      setSaving(true);
      setErr("");
      SDK.fetchJSON(API + "/mcp-signing-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      })
        .then(function (res) {
          setSaving(false);
          setRevealed((res.mcp_signing_key && res.mcp_signing_key.secret) || "");
        })
        .catch(function (e) {
          setSaving(false);
          setErr(parseApiErrorMessage(e));
        });
    }

    // Shown once right after a successful create/update — the one moment
    // the full secret is available to copy (list/get responses mask it).
    if (revealed) {
      return h(
        "div",
        { className: "hermes-rights-form" },
        h("div", { className: "hermes-rights-form-title" }, isEdit ? "Key updated" : "Key created"),
        h(
          "p",
          { className: "hermes-rights-intro" },
          "Copy this secret now and share it out-of-band with the external MCP team — " +
            "it won't be shown in full again here (use \"Reveal\" on the row later if you need it once more)."
        ),
        h("pre", { className: "hermes-rights-secret-reveal" }, revealed),
        h(
          "div",
          { className: "hermes-rights-form-actions" },
          h(Button, { type: "button", size: "sm", onClick: props.onSaved }, "Done")
        )
      );
    }

    return h(
      "form",
      {
        className: "hermes-rights-form",
        onSubmit: function (e) {
          e.preventDefault();
          submit();
        },
      },
      h("div", { className: "hermes-rights-form-title" }, isEdit ? "Edit key" : "New MCP signing key"),
      textField("Kid (id, referenced in the token header)", form.id, set("id"), {
        placeholder: "rag_mcp",
        disabled: isEdit,
      }),
      textField("Label", form.label, set("label"), { placeholder: "RAG MCP (self-hosted)" }),
      textField("Algorithm", form.alg, set("alg"), { placeholder: "HS256" }),
      textField(
        isEdit ? "New secret (leave blank to keep the current one)" : "Secret (leave blank to auto-generate)",
        form.secret,
        set("secret")
      ),
      checkboxField("Active — issues a token every turn while enabled", form.active, set("active")),
      err ? h("div", { className: "hermes-rights-error" }, err) : null,
      h(
        "div",
        { className: "hermes-rights-form-actions" },
        h(Button, { type: "button", size: "sm", onClick: props.onCancel }, "Cancel"),
        h(Button, { type: "submit", size: "sm", disabled: saving || !form.id }, saving ? "Saving..." : "Save")
      )
    );
  }

  function McpKeyRow(props) {
    var k = props.mcpKey;
    var editingArr = useState(false);
    var editing = editingArr[0];
    var setEditing = editingArr[1];
    var revealedArr = useState("");
    var revealedNow = revealedArr[0];
    var setRevealedNow = revealedArr[1];
    var revealErrArr = useState("");
    var revealErr = revealErrArr[0];
    var setRevealErr = revealErrArr[1];

    function reveal() {
      setRevealErr("");
      SDK.fetchJSON(API + "/mcp-signing-keys/" + encodeURIComponent(k.id) + "/reveal", { method: "POST" })
        .then(function (res) {
          setRevealedNow((res.mcp_signing_key && res.mcp_signing_key.secret) || "");
        })
        .catch(function (e) {
          setRevealErr(parseApiErrorMessage(e));
        });
    }

    if (editing) {
      return h(McpKeyForm, {
        initial: { id: k.id, label: k.label, alg: k.alg, secret: "", active: k.active },
        onCancel: function () { setEditing(false); },
        onSaved: function () {
          setEditing(false);
          props.onChanged();
        },
      });
    }

    return h(
      Card,
      { className: "hermes-rights-row" },
      h(
        CardContent,
        { className: "hermes-rights-row-content-column" },
        h(
          "div",
          { className: "hermes-rights-row-content" },
          h(
            "div",
            { className: "hermes-rights-row-main" },
            h("span", { className: "hermes-rights-row-title" }, k.label || k.id),
            h(
              "span",
              { className: "hermes-rights-row-sub" },
              "kid=" + k.id + " · " + k.alg + " · secret " + k.secret + (k.active ? "" : " · inactive")
            )
          ),
          h(
            "div",
            { className: "hermes-rights-row-actions" },
            h(Button, { size: "sm", onClick: reveal }, "Reveal"),
            h(Button, { size: "sm", onClick: function () { setEditing(true); } }, "Edit"),
            h(
              Button,
              {
                size: "sm",
                variant: "destructive",
                onClick: function () {
                  if (
                    window.confirm(
                      "Delete signing key '" + (k.label || k.id) +
                        "'? The external MCP identified by this kid will stop receiving a token."
                    )
                  ) {
                    props.onDelete(k.id);
                  }
                },
              },
              "Delete"
            )
          )
        ),
        revealErr ? h("div", { className: "hermes-rights-error" }, revealErr) : null,
        revealedNow ? h("pre", { className: "hermes-rights-secret-reveal" }, revealedNow) : null
      )
    );
  }

  function McpKeysSection(props) {
    var creatingArr = useState(false);
    var creating = creatingArr[0];
    var setCreating = creatingArr[1];

    return h(
      "div",
      { className: "hermes-rights-section" },
      h(
        "div",
        { className: "hermes-rights-section-header" },
        h("h3", null, "MCP signing keys"),
        !creating ? h(Button, { size: "sm", onClick: function () { setCreating(true); } }, "New key") : null
      ),
      h(
        "p",
        { className: "hermes-rights-intro" },
        "One key per EXTERNAL MCP microservice (a separate service, never a Hermes plugin). Every turn, an opaque " +
          "signed token is injected into context per active key below, labelled by its kid — the external MCP's own " +
          "tool description should tell the model which kid to relay. This plugin never verifies these tokens or " +
          "enforces anything inside an MCP; each service checks its own copy of the secret and decides its own access rules."
      ),
      creating
        ? h(McpKeyForm, {
            onCancel: function () { setCreating(false); },
            onSaved: function () {
              setCreating(false);
              props.onChanged();
            },
          })
        : null,
      props.mcpKeys.length === 0 && !creating
        ? h("div", { className: "hermes-rights-empty" }, "No MCP signing key yet.")
        : props.mcpKeys.map(function (k) {
            return h(McpKeyRow, {
              key: k.id,
              mcpKey: k,
              onDelete: props.onDeleteMcpKey,
              onChanged: props.onChanged,
            });
          })
    );
  }
  // ---------------------------------------------------------------------
  // Root
  // ---------------------------------------------------------------------

  function RightsPage() {
    var bindingsArr = useState([]);
    var bindings = bindingsArr[0];
    var setBindings = bindingsArr[1];
    var rightsArr = useState([]);
    var rights = rightsArr[0];
    var setRights = rightsArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];

    // Cached Slack directory (see ../directory.py) — used only as a
    // pick-list convenience in the role-binding form + a status row, never
    // part of the authorization model itself.
    var directoryArr = useState([]);
    var directoryList = directoryArr[0];
    var setDirectoryList = directoryArr[1];
    var directorySyncedAtArr = useState(0);
    var directorySyncedAt = directorySyncedAtArr[0];
    var setDirectorySyncedAt = directorySyncedAtArr[1];
    var directorySyncingArr = useState(false);
    var directorySyncing = directorySyncingArr[0];
    var setDirectorySyncing = directorySyncingArr[1];
    var directorySyncErrArr = useState("");
    var directorySyncErr = directorySyncErrArr[0];
    var setDirectorySyncErr = directorySyncErrArr[1];

    // Platforms Hermes looks configured for on this deployment (see
    // ../platforms.py) — offered as the role-binding form's platform
    // picker instead of a free-text field.
    var connectedPlatformsArr = useState([]);
    var connectedPlatforms = connectedPlatformsArr[0];
    var setConnectedPlatforms = connectedPlatformsArr[1];

    // The role catalog (see ../models.Role) — feeds RolesSection and every
    // RoleTagPicker (role-binding form + right form).
    var rolesArr = useState([]);
    var roles = rolesArr[0];
    var setRoles = rolesArr[1];

    // Live catalog of Hermes's own registered tools (see ../tools_catalog.py)
    // — feeds the hermes_tool right form's tool picker. Pure UI convenience,
    // same status as connectedPlatforms/directoryList: never part of the
    // authorization model itself.
    var hermesToolsArr = useState([]);
    var hermesTools = hermesToolsArr[0];
    var setHermesTools = hermesToolsArr[1];

    // Signing keys for MCP identity tokens (see ../models.McpSigningKey /
    // ../token_signer.py) — one per EXTERNAL MCP microservice, entirely
    // separate from role/right CRUD above.
    var mcpKeysArr = useState([]);
    var mcpKeys = mcpKeysArr[0];
    var setMcpKeys = mcpKeysArr[1];

    var reload = useCallback(function () {
      SDK.fetchJSON(API + "/role-bindings")
        .then(function (res) {
          setBindings(res.role_bindings || []);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
      SDK.fetchJSON(API + "/roles")
        .then(function (res) {
          setRoles(res.roles || []);
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
      // GET /directory does its own best-effort lazy refresh server-side
      // (see directory.py::ensure_fresh) — this call never fails just
      // because Slack is momentarily unreachable, it always returns
      // whatever is cached.
      SDK.fetchJSON(API + "/directory?platform=slack")
        .then(function (res) {
          setDirectoryList(res.directory || []);
          setDirectorySyncedAt(res.synced_at || 0);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
      SDK.fetchJSON(API + "/platforms")
        .then(function (res) {
          setConnectedPlatforms(res.platforms || []);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
      SDK.fetchJSON(API + "/hermes-tools")
        .then(function (res) {
          setHermesTools(res.tools || []);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
      SDK.fetchJSON(API + "/mcp-signing-keys")
        .then(function (res) {
          setMcpKeys(res.mcp_signing_keys || []);
        })
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }, []);

    useEffect(function () {
      reload();
    }, [reload]);

    function syncDirectory() {
      setDirectorySyncing(true);
      setDirectorySyncErr("");
      SDK.fetchJSON(API + "/directory/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: "slack" }),
      })
        .then(function (res) {
          setDirectorySyncing(false);
          setDirectoryList(res.directory || []);
          setDirectorySyncedAt(Math.floor(Date.now() / 1000));
        })
        .catch(function (e) {
          setDirectorySyncing(false);
          setDirectorySyncErr(parseApiErrorMessage(e));
        });
    }

    function deleteBinding(b) {
      SDK.fetchJSON(
        API + "/role-bindings?platform=" + encodeURIComponent(b.platform) + "&user=" + encodeURIComponent(b.external_user_id),
        { method: "DELETE" }
      )
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

    function deleteRole(id) {
      SDK.fetchJSON(API + "/roles/" + encodeURIComponent(id), { method: "DELETE" })
        .then(reload)
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }

    function deleteMcpKey(kid) {
      SDK.fetchJSON(API + "/mcp-signing-keys/" + encodeURIComponent(kid), { method: "DELETE" })
        .then(reload)
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }

    // Used by RoleRow's member list to drop just one role from someone's
    // binding (keeping their other roles) — a targeted update through the
    // same upsert POST every other write here uses, not a full replace.
    function updateBindingRoles(binding, newRoles) {
      SDK.fetchJSON(API + "/role-bindings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: binding.platform,
          user: binding.external_user_id,
          roles: newRoles.join(","),
          label: binding.label,
        }),
      })
        .then(reload)
        .catch(function (e) {
          setErr(parseApiErrorMessage(e));
        });
    }

    return h(
      "div",
      { className: "hermes-rights-page" },
      h("h2", null, "Access groups"),
      h(
        "p",
        { className: "hermes-rights-intro" },
        "Generic deny-by-default authorization: who (identity → role) can do what (role → resource). " +
          "Governs Hermes's own tools/crons directly, and anything a plugin delegates to it (e.g. Odoo, " +
          "grouped below by resource type) — plugins with a richer editing UX may also expose their own " +
          "scoped view of this same data in their own dashboard tab."
      ),
      err ? h("div", { className: "hermes-rights-error" }, err) : null,
      h(RolesSection, {
        roles: roles,
        bindings: bindings,
        connectedPlatforms: connectedPlatforms,
        directory: directoryList,
        onChanged: reload,
        onDeleteRole: deleteRole,
        onUnbindMember: deleteBinding,
        onUpdateBindingRoles: updateBindingRoles,
      }),
      h(RoleBindingsSection, {
        bindings: bindings,
        onChanged: reload,
        onDeleteBinding: deleteBinding,
        directory: directoryList,
        directorySyncedAt: directorySyncedAt,
        directorySyncing: directorySyncing,
        directorySyncError: directorySyncErr,
        onSyncDirectory: syncDirectory,
        connectedPlatforms: connectedPlatforms,
        roles: roles,
      }),
      h(AccessRightsSection, {
        rights: rights,
        onChanged: reload,
        onDeleteRight: deleteRight,
        roles: roles,
        hermesTools: hermesTools,
      }),
      h(McpKeysSection, {
        mcpKeys: mcpKeys,
        onChanged: reload,
        onDeleteMcpKey: deleteMcpKey,
      })
    );
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("rights", RightsPage);
  }
})();
