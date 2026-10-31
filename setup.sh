#!/usr/bin/env bash
# One-shot publisher. Requires: gh authenticated as mellowtidesec-tech with scopes repo,workflow.
# Secrets are piped from private files on the box and never printed.
set -euo pipefail
cd "$(dirname "$0")"
OWNER="${OWNER:-mellowtidesec-tech}"; REPO="${REPO:-spain-unrest-board}"; FULL="$OWNER/$REPO"
gh auth status >/dev/null 2>&1 || { echo "gh is not logged in: run  gh auth login -h github.com -p https -s workflow -w"; exit 1; }
git init -q -b main 2>/dev/null || true
git add -A && (git diff --cached --quiet || git commit -qm "Spain unrest board: initial")
if ! gh repo view "$FULL" >/dev/null 2>&1; then
  gh repo create "$FULL" --public --description "繁中即時看板：馬德里・巴塞隆納 罷工/抗議/縱火 (hourly)" --source . --remote origin --push
else
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$FULL.git"
  git push -u origin main
fi
# secrets (values read from private files, piped via stdin; never echoed)
sed -n 's/^TREG_TOKEN=//p' /home/box/.secrets/treg_ci.env | tr -d '\n' | gh secret set TREG_TOKEN --repo "$FULL"
sed -n 's/^GEMINI_API_KEY=//p' /home/box/.secrets/gemini.env | tr -d '\n' | gh secret set GEMINI_API_KEY --repo "$FULL"
# Pages from GitHub Actions
gh api -X POST "repos/$FULL/pages" -f build_type=workflow >/dev/null 2>&1 || gh api -X PUT "repos/$FULL/pages" -f build_type=workflow >/dev/null
gh workflow enable update.yml --repo "$FULL" 2>/dev/null || true
gh workflow run update.yml --repo "$FULL" -f force_all=1
sleep 8
RUN=$(gh run list --repo "$FULL" --workflow update.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN" --repo "$FULL" --exit-status || { gh run view "$RUN" --repo "$FULL" --log-failed | tail -60; exit 1; }
URL=$(gh api "repos/$FULL/pages" -q .html_url)
echo "Board: $URL"
echo "Repo:  https://github.com/$FULL"
curl -fsS "$URL" | grep -o '<title>[^<]*' | head -1
