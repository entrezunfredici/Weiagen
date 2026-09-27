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
