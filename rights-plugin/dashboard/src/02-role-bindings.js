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
