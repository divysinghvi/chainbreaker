"""Repo discovery for an org (PLAN C.1)."""
import logging

from . import gql

log = logging.getLogger(__name__)

ORG_QUERY = """query($login: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  organization(login: $login) {
    repositories(first: 50, after: $cursor, privacy: PUBLIC, isFork: false,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner stargazerCount isArchived defaultBranchRef { name } }
    }
  }
}"""


def org_repos(login: str, limit: int, use_cache: bool = True) -> list[dict]:
    out, cursor = [], None
    while len(out) < limit:
        data, _ = gql.post(ORG_QUERY, {"login": login, "cursor": cursor}, use_cache=use_cache)
        org = data.get("organization")
        if org is None:
            log.warning("org %s not found, skipping", login)
            break
        conn = org["repositories"]
        for n in conn["nodes"]:
            if n["isArchived"] or not n.get("defaultBranchRef"):
                continue
            owner, name = n["nameWithOwner"].split("/", 1)
            out.append({"owner": owner, "name": name, "id": n["nameWithOwner"].lower(),
                        "stars": n["stargazerCount"], "default_branch": n["defaultBranchRef"]["name"]})
            if len(out) >= limit:
                break
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
    return out
