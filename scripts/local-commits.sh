#!/usr/bin/env bash
# Count your own commits per day in local clones, and print them as JSON.
# Runs anywhere git runs; reads nothing but git logs; sends nothing.
#
#   scripts/local-commits.sh "you@company.com,you@other.com" /path/to/repo1 /path/to/repo2 ...
#
# Paste the printed JSON into the "Add local counts" workflow on
# github.com/rabiee-nasri/rabiee-nasri (Actions tab, Run workflow) with the
# source name it belongs to, for example bitbucket:akkodis. Counts only: the
# output holds dates and numbers, never repository names or messages.
set -euo pipefail
emails="${1:?comma-separated author emails}"; shift
[ "$#" -gt 0 ] || { echo "give at least one repository path" >&2; exit 1; }
pattern="$(printf '%s' "$emails" | sed 's/,/\\|/g')"
for repo in "$@"; do
  git -C "$repo" log --all --author="$pattern" --format=%ad --date=short 2>/dev/null
done | sort | uniq -c | awk 'BEGIN{printf "{"} {printf "%s\"%s\":%d", (n++?",":""), $2, $1} END{print "}"}'
