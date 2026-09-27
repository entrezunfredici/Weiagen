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
