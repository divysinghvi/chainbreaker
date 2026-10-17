"""The demo-org scenario (PLAN Appendix A) as plain data.

Tokens: __ORG__, __SHA_CHANGED_FILES_GOOD__, __SHA_LINT_REPORTER_V1__ — filled with str.replace
(str.format / Template would choke on `${{ }}`).
"""

ACTION_REPOS = ["cb-changed-files", "cb-setup-reviewer", "cb-lint-reporter", "cb-ci-toolkit", "cb-release-kit",
                "cb-shared-workflows"]
APP_REPOS = ["web-frontend", "docs-site", "analytics", "mobile-app", "payments-api", "auth-service", "orders-api",
             "billing-worker", "search-api", "notifications", "infra-terraform", "data-pipeline"]
REPOS = ACTION_REPOS + APP_REPOS

README = "# {repo}\n\nSynthetic repo for the ChainBreaker lab. No real secrets.\n"

# repo -> tag that must point at the commit that last wrote its action.yml
TAGS = {"cb-changed-files": "v3", "cb-setup-reviewer": "v1", "cb-lint-reporter": "v1", "cb-ci-toolkit": "v2",
        "cb-release-kit": "v1"}

ACTIONS = {
    "cb-changed-files": """name: cb-changed-files
description: ChainBreaker lab demo action. Harmless.
runs:
  using: composite
  steps:
    - run: echo "cb-changed-files (demo)"
      shell: bash
""",
    "cb-setup-reviewer": """name: cb-setup-reviewer
description: ChainBreaker lab demo action. Harmless.
runs:
  using: composite
  steps:
    - run: echo "cb-setup-reviewer (demo)"
      shell: bash
""",
    "cb-lint-reporter": """name: cb-lint-reporter
description: ChainBreaker lab demo composite action.
runs:
  using: composite
  steps:
    - uses: __ORG__/cb-setup-reviewer@v1
    - uses: __ORG__/cb-changed-files@v3
    - run: echo "lint report (demo)"
      shell: bash
""",
    "cb-ci-toolkit": """name: cb-ci-toolkit
description: ChainBreaker lab demo composite action.
runs:
  using: composite
  steps:
    - uses: __ORG__/cb-lint-reporter@v1
    - run: echo "ci toolkit (demo)"
      shell: bash
""",
    "cb-release-kit": """name: cb-release-kit
description: ChainBreaker lab demo composite action.
runs:
  using: composite
  steps:
    - uses: __ORG__/cb-changed-files@__SHA_CHANGED_FILES_GOOD__ # v3
    - run: echo "release kit (demo)"
      shell: bash
""",
}

SHARED_CI = """name: shared-ci
on:
  workflow_call:
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-ci-toolkit@v2
"""


def _deploy(perms: str, secrets: list[str]) -> str:
    env = "\n".join(f"          {s}: ${{{{ secrets.{s} }}}}" for s in secrets)
    return f"""name: deploy
on:
  push:
    branches: [main]
{perms}jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-ci-toolkit@v2
      - run: echo "deploy (demo)"
        env:
{env}
"""


WRITE = "permissions:\n  contents: write\n"

WORKFLOWS = {
    "web-frontend": (".github/workflows/pr-check.yml", """name: pr-check
on:
  pull_request_target:
    types: [opened, synchronize]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-changed-files@v3
      - run: echo "publish preview (demo)"
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
"""),
    "docs-site": (".github/workflows/docs.yml", """name: docs
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-changed-files@v3
      - run: echo "build docs (demo)"
"""),
    "analytics": (".github/workflows/lint.yml", """name: lint
on:
  pull_request:
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-lint-reporter@v1
"""),
    "mobile-app": (".github/workflows/build.yml", """name: build
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-lint-reporter@__SHA_LINT_REPORTER_V1__ # v1
      - run: echo "sign app (demo)"
        env:
          APPLE_SIGNING_KEY: ${{ secrets.APPLE_SIGNING_KEY }}
"""),
    "payments-api": (".github/workflows/deploy.yml",
                     _deploy("permissions:\n  contents: write\n  id-token: write\n",
                             ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])),
    "auth-service": (".github/workflows/deploy.yml", _deploy(WRITE, ["JWT_SIGNING_KEY"])),
    "orders-api": (".github/workflows/deploy.yml", _deploy("", ["DATABASE_URL"])),
    "billing-worker": (".github/workflows/deploy.yml", _deploy("", ["STRIPE_API_KEY"])),
    "search-api": (".github/workflows/deploy.yml", _deploy(WRITE, ["ELASTIC_API_KEY"])),
    "notifications": (".github/workflows/deploy.yml", _deploy(WRITE, ["TWILIO_AUTH_TOKEN"])),
    "infra-terraform": (".github/workflows/plan.yml", """name: plan
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  shared:
    uses: __ORG__/cb-shared-workflows/.github/workflows/ci.yml@main
    secrets: inherit
  plan:
    runs-on: ubuntu-latest
    steps:
      - run: echo "terraform plan (demo)"
        env:
          TF_API_TOKEN: ${{ secrets.TF_API_TOKEN }}
"""),
    "data-pipeline": (".github/workflows/etl.yml", """name: etl
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  etl:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-release-kit@v1
      - run: echo "etl (demo)"
        env:
          SNOWFLAKE_PASSWORD: ${{ secrets.SNOWFLAKE_PASSWORD }}
"""),
}

EXPECTED_SEVERITY = {
    "web-frontend": "HIGH", "mobile-app": "HIGH", "payments-api": "HIGH", "auth-service": "HIGH",
    "search-api": "HIGH", "notifications": "HIGH", "infra-terraform": "HIGH", "data-pipeline": "HIGH",
    "orders-api": "HIGH", "billing-worker": "HIGH", "docs-site": "LOW", "analytics": "LOW",
}


def render(text: str, org: str, sha_good: str = "", sha_lint_v1: str = "") -> str:
    return (text.replace("__ORG__", org)
            .replace("__SHA_CHANGED_FILES_GOOD__", sha_good)
            .replace("__SHA_LINT_REPORTER_V1__", sha_lint_v1))
