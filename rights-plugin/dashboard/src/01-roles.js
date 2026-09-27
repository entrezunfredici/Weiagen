  // ---------------------------------------------------------------------
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
