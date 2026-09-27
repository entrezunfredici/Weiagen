#!/bin/sh
# Concatenates dashboard/src/*.js (in filename order — hence the numeric
# prefixes) into dashboard/dist/index.js, the single file the Hermes
# dashboard host actually loads (manifest.json's `entry`, fetched via a
# classic <script src> — no ES module import/export across files, no
# runtime multi-file loading, see .agents/DECISIONS.md, 2026-08-18).
#
# The five source files share ONE closure: 00-core.js opens the IIFE,
# 04-page.js closes it. None of the individual src/ files is valid
# standalone JS on its own (linting one in isolation will show unbalanced
# braces) — that's expected, they're fragments, not modules.
#
# dist/index.js is GENERATED — never hand-edit it, edit src/ and re-run
# this script. No Node/npm required, plain POSIX `cat`.
#
# Usage: ./build.sh   (from this directory, or any cwd — path is resolved
# relative to this script, not $PWD)
set -e
cd "$(dirname "$0")"

{
  echo "/* GENERATED FILE — do not edit directly."
  echo " * Source: dashboard/src/*.js, assembled by dashboard/build.sh."
  echo " * Edit the src/ files and re-run build.sh, then redeploy. */"
  cat src/00-core.js src/01-roles.js src/02-role-bindings.js src/03-access-rights.js src/04-mcp-keys.js src/05-page.js
} > dist/index.js

echo "Built dist/index.js from $(ls src/*.js | wc -l) source files."
