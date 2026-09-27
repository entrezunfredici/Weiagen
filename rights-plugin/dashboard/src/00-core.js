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
  }