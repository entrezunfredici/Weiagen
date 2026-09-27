/**
 * Hermes Audit — Dashboard Plugin (read-only).
 *
 * Lists the audit log recorded by ../__init__.py (every tool call and every
 * approval decision), with filters, per-status counts, and a hash-chain
 * integrity check (GET /verify). No write route on purpose: purging stays a
 * CLI-only operator action (`hermes audit purge --older-than-days N --yes`).
 *
 * Hand-written single file (unlike rights-plugin's src/*.js + build.sh):
 * small enough that a build step would add more moving parts than it saves.
 * Loaded by the host through a classic <script src> — no ES modules.
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
  var Button = SDK.components.Button;
  var Input = SDK.components.Input;
  var Label = SDK.components.Label;

  var API = "/api/plugins/audit";
  var STATUS_OPTIONS = ["", "ok", "error", "blocked", "cancelled", "timeout", "once", "session", "always", "deny"];

  function parseApiErrorMessage(err) {
    var msg = String((err && err.message) || err || "Unknown error");
    try {
      var idx = msg.indexOf(": ");
      var parsed = JSON.parse(idx >= 0 ? msg.slice(idx + 2) : msg);
      if (parsed && parsed.detail) {
        return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
      }
    } catch (_e) {
      /* not JSON */
    }
    return msg;
  }

  function query(params) {
    var parts = [];
    Object.keys(params).forEach(function (k) {
      if (params[k]) parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(params[k]));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  function field(label, input) {
    return h("div", { className: "hermes-audit-field" }, h(Label, null, label), input);
  }

  function statusClass(status) {
    if (status === "ok" || status === "once" || status === "session" || status === "always" || status === "smart_approve") {
      return "hermes-audit-status-ok";
    }
    if (status === "blocked" || status === "deny" || status === "smart_deny") return "hermes-audit-status-blocked";
    return "hermes-audit-status-other";
  }

  function EventRow(props) {
    var e = props.event;
    var openArr = useState(false);
    var open = openArr[0];
    var setOpen = openArr[1];
    return h(
      React.Fragment,
      null,
      h(
        "tr",
        { className: "hermes-audit-row", onClick: function () { setOpen(!open); } },
        h("td", { className: "hermes-audit-mono" }, (e.time || "").replace("T", " ").replace("+00:00", "Z")),
        h("td", null, e.user_id ? e.platform + ":" + e.user_id : h("span", { className: "hermes-audit-muted" }, "—")),
        h("td", { className: "hermes-audit-mono" }, e.event === "approval" ? "✋ " + (e.tool_name || "approval") : e.tool_name),
        h("td", null, h("span", { className: "hermes-audit-status " + statusClass(e.status) }, e.status || "—")),
        h("td", { className: "hermes-audit-mono hermes-audit-right" }, e.event === "tool_call" ? e.duration_ms + " ms" : "")
      ),
      open
        ? h(
            "tr",
            { className: "hermes-audit-detail" },
            h(
              "td",
              { colSpan: 5 },
              e.error_message ? h("div", { className: "hermes-audit-error-msg" }, e.error_message) : null,
              h("pre", null, JSON.stringify(e.args, null, 2)),
              h(
                "div",
                { className: "hermes-audit-muted hermes-audit-mono" },
                "#" + e.id + " · session " + (e.session_id || "—") + " · call " + (e.tool_call_id || "—") +
                  (e.event === "tool_call" ? " · result " + e.result_size + " chars" : "")
              )
            )
          )
        : null
    );
  }

  function AuditPage() {
    var filtersArr = useState({ user: "", tool: "", status: "", since: "24h" });
    var filters = filtersArr[0];
    var setFilters = filtersArr[1];
    var eventsArr = useState([]);
    var events = eventsArr[0];
    var setEvents = eventsArr[1];
    var statsArr = useState(null);
    var stats = statsArr[0];
    var setStats = statsArr[1];
    var verifyArr = useState(null);
    var verifyResult = verifyArr[0];
    var setVerifyResult = verifyArr[1];
    var errArr = useState("");
    var err = errArr[0];
    var setErr = errArr[1];

    var reload = useCallback(function () {
      setErr("");
      SDK.fetchJSON(API + "/events" + query(Object.assign({ limit: "200" }, filters)))
        .then(function (res) { setEvents(res.events || []); })
        .catch(function (e) { setErr(parseApiErrorMessage(e)); });
      SDK.fetchJSON(API + "/stats" + query({ since: filters.since }))
        .then(setStats)
        .catch(function (e) { setErr(parseApiErrorMessage(e)); });
    }, [filters]);

    useEffect(function () { reload(); }, [reload]);

    function setFilter(key, value) {
      setFilters(Object.assign({}, filters, (function () { var o = {}; o[key] = value; return o; })()));
    }

    function runVerify() {
      setVerifyResult({ pending: true });
      SDK.fetchJSON(API + "/verify")
        .then(setVerifyResult)
        .catch(function (e) { setVerifyResult({ ok: false, reason: parseApiErrorMessage(e) }); });
    }

    function textInput(key, placeholder) {
      return h(Input, {
        value: filters[key],
        placeholder: placeholder,
        className: "h-8 text-sm",
        onChange: function (ev) { setFilter(key, ev.target.value); },
      });
    }

    return h(
      "div",
      { className: "hermes-audit-page" },
      h("h2", null, "Audit log"),
      h(
        "p",
        { className: "hermes-audit-intro" },
        "Every tool call (including calls blocked by access rights) and every approval decision. " +
          "Arguments are redacted; tool results are never stored. Click a row for details."
      ),
      err ? h("div", { className: "hermes-audit-error" }, err) : null,
      stats
        ? h(
            "div",
            { className: "hermes-audit-stats" },
            h("span", null, h("strong", null, stats.total), " events"),
            Object.keys(stats.by_status || {}).map(function (s) {
              return h("span", { key: s, className: "hermes-audit-status " + statusClass(s) }, s + " " + stats.by_status[s]);
            }),
            h(
              "span",
              { className: "hermes-audit-muted" },
              "retention " + (stats.retention_days ? stats.retention_days + " d" : "unlimited") +
                (stats.oldest ? " · oldest " + stats.oldest.slice(0, 10) : "")
            )
          )
        : null,
      h(
        "div",
        { className: "hermes-audit-filters" },
        field("User id", textInput("user", "U0123…")),
        field("Tool", textInput("tool", "odoo_sdk_*")),
        field(
          "Status",
          h(
            "select",
            {
              className: "hermes-audit-select",
              value: filters.status,
              onChange: function (ev) { setFilter("status", ev.target.value); },
            },
            STATUS_OPTIONS.map(function (s) { return h("option", { key: s, value: s }, s || "any"); })
          )
        ),
        field("Since", textInput("since", "24h, 7d, 2026-09-01")),
        h(Button, { size: "sm", onClick: reload }, "Refresh"),
        h(Button, { size: "sm", variant: "outline", onClick: runVerify }, "Verify integrity")
      ),
      verifyResult
        ? h(
            "div",
            { className: verifyResult.pending ? "hermes-audit-muted" : verifyResult.ok ? "hermes-audit-verify-ok" : "hermes-audit-error" },
            verifyResult.pending
              ? "Verifying…"
              : verifyResult.ok
                ? "✓ Hash chain intact — " + verifyResult.checked + " events checked."
                : "✗ Chain broken at event #" + verifyResult.broken_at_id + ": " + verifyResult.reason
          )
        : null,
      h(
        "div",
        { className: "hermes-audit-table-wrap" },
        h(
          "table",
          { className: "hermes-audit-table" },
          h("thead", null, h("tr", null, h("th", null, "Time (UTC)"), h("th", null, "User"), h("th", null, "Tool"), h("th", null, "Status"), h("th", { className: "hermes-audit-right" }, "Duration"))),
          h(
            "tbody",
            null,
            events.length === 0
              ? h("tr", null, h("td", { colSpan: 5, className: "hermes-audit-muted" }, "No event for these filters."))
              : events.map(function (e) { return h(EventRow, { key: e.id, event: e }); })
          )
        )
      )
    );
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("audit", AuditPage);
  }
})();
