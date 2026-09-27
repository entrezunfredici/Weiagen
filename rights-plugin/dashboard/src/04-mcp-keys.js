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
