import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.getenv("CB_ROOT") or Path(__file__).resolve().parent.parent)
load_dotenv(ROOT / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DEMO_ORG = os.getenv("DEMO_ORG", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
ANTHROPIC_WORKSPACE_ID = os.getenv("ANTHROPIC_WORKSPACE_ID", "")  # needed when the API key is not workspace-scoped
FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_PASSWORD = os.getenv("FALKORDB_PASSWORD", "chainbreaker")
PUBLIC_MODE = os.getenv("PUBLIC_MODE", "0") == "1"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")
REDACTION_SALT = os.getenv("REDACTION_SALT", "change-me")
FIX_ENGINE = os.getenv("FIX_ENGINE", "auto")
MAX_DEPTH = max(1, min(8, int(os.getenv("MAX_DEPTH", "6"))))
CNCF_MAX_REPOS_PER_ORG = int(os.getenv("CNCF_MAX_REPOS_PER_ORG", "30"))
AGENT_RATE_LIMIT = int(os.getenv("AGENT_RATE_LIMIT", "12"))

DATA = ROOT / "data"
CACHE = DATA / "cache"
SNAPSHOTS = DATA / "snapshots"
GROUND_TRUTH = DATA / "demo_ground_truth.json"
REPLAY = DATA / "replay_tj_2025.json"
WEB = ROOT / "web"
NOTES = ROOT / "NOTES.md"

CNCF_ORGS = """kubernetes kubernetes-sigs prometheus open-telemetry envoyproxy istio cilium argoproj fluxcd helm
containerd etcd-io grpc jaegertracing linkerd coredns cri-o fluent open-policy-agent thanos-io
cortexproject vitessio rook kedacore knative dapr falcosecurity cert-manager backstage crossplane
kubevirt kyverno buildpacks cloudevents opencost chaos-mesh litmuschaos longhorn spiffe nats-io
kubeedge karmada-io volcano-sh openkruise tikv kubeflow cncf""".split()


def clamp_depth(d: int | None) -> int:
    return max(1, min(8, int(d if d is not None else MAX_DEPTH)))
