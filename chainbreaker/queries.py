"""Every Cypher string ChainBreaker runs. LLM output is never executed as Cypher.

`{D}` is a clamped integer (1..8) inlined with depth(): FalkorDB cannot take a parameter in a
var-length bound, LIMIT or SKIP.
"""
from .config import clamp_depth

CRAWL_LABELS = ["Repo", "Workflow", "Action", "ActionRef", "DockerImage", "Meta"]
USES_LABELS = {"Workflow", "ActionRef", "DockerImage"}


def depth(q: str, d: int | None) -> str:
    return q.replace("{D}", str(clamp_depth(d)))


# ---------- schema ----------
INDEXES = [f"CREATE INDEX FOR (n:{lbl}) ON (n.id)" for lbl in
           ["Repo", "Workflow", "Action", "ActionRef", "DockerImage", "Advisory", "FixPlan", "Fix", "Finding"]]
FT_INDEX = "CALL db.idx.fulltext.createNodeIndex('Action', 'search')"

# ---------- load (Q-LOAD) ----------
DELETE_LABEL = "MATCH (n:{label}) DETACH DELETE n"  # label from CRAWL_LABELS only
LOAD_NODES = "UNWIND $rows AS row CREATE (n:{label}) SET n += row"
LOAD_HAS_WORKFLOW = ("UNWIND $rows AS row MATCH (r:Repo {id: row.src}), (w:Workflow {id: row.dst}) "
                     "CREATE (r)-[:HAS_WORKFLOW]->(w)")
LOAD_VERSION_OF = ("UNWIND $rows AS row MATCH (a:ActionRef {id: row.src}), (b:Action {id: row.dst}) "
                   "CREATE (a)-[:VERSION_OF]->(b)")
LOAD_USES = ("UNWIND $rows AS row MATCH (s:{src} {{id: row.src}}), (d:{dst} {{id: row.dst}}) "
             "CREATE (s)-[e:USES]->(d) SET e += row.props")

# ---------- stats ----------
COUNT_LABEL = "MATCH (n:{label}) RETURN count(n) AS c"
COUNT_USES = "MATCH ()-[e:USES]->() RETURN count(e) AS c"
WORKFLOW_COUNTS = """MATCH (w:Workflow)
RETURN sum(CASE WHEN w.at_ref IS NULL THEN 1 ELSE 0 END) AS head,
       sum(CASE WHEN w.at_ref IS NULL AND w.entry = true THEN 1 ELSE 0 END) AS entry,
       sum(CASE WHEN w.at_ref IS NULL THEN 0 ELSE 1 END) AS at_ref"""
REF_PIN_SHARE = """MATCH (w:Workflow)-[e:USES]->(r:ActionRef)
WHERE w.at_ref IS NULL AND r.local = false
RETURN count(e) AS refs, sum(CASE WHEN r.pinned = true THEN 1 ELSE 0 END) AS pinned"""
META_CREATE = "CREATE (:Meta {id: 'meta', dataset: $ds, crawled_at: $at, orgs: $orgs, stats: $stats})"
META = "MATCH (m:Meta) RETURN m.crawled_at AS crawled_at, m.orgs AS orgs LIMIT 1"

# ---------- advisories (Q-ADV-LINK) ----------
ADV_FIND = """MATCH (a:Advisory {action_id: $aid}) RETURN a.id AS id, a.refs AS refs, a.known_good_sha AS known_good_sha
ORDER BY a.created_at DESC"""
ADV_IDS = "MATCH (a:Advisory) RETURN a.id AS id"
ADV_CREATE = """CREATE (a:Advisory {id: $id, action_id: $aid, refs: $refs, known_good_sha: $sha,
                created_at: $now, summary: $summary}) RETURN a.id AS id"""
ADV_GET = "MATCH (a:Advisory {id: $adv}) RETURN a.id AS id, a.action_id AS action_id, a.refs AS refs, " \
          "a.known_good_sha AS known_good_sha, a.created_at AS created_at, a.summary AS summary"
ADV_UNLINK_ALL = "MATCH (:Advisory)-[c:COMPROMISES]->() DELETE c"
ADV_LINK = """MATCH (adv:Advisory {id: $adv})
MATCH (:Action {id: adv.action_id})<-[:VERSION_OF]-(r:ActionRef)
WHERE r.pinned = false AND (size(adv.refs) = 0 OR r.ref IN adv.refs)
CREATE (adv)-[:COMPROMISES]->(r)
RETURN count(r) AS compromised"""
ADV_COMPROMISED = "MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(r:ActionRef) RETURN r.id AS id ORDER BY id"
ACTION_EXISTS = "MATCH (a:Action {id: $aid}) RETURN a.id AS id"
ACTION_REFS = """MATCH (a:Action {id: $aid})<-[:VERSION_OF]-(r:ActionRef)
RETURN r.id AS id, r.ref AS ref, r.pinned AS pinned, r.kind AS kind ORDER BY r.ref"""

# ---------- blast radius (Q-BLAST, Q-PINNED) ----------
BLAST = """MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
MATCH p = (w:Workflow)-[:USES*1..{D}]->(bad)
WHERE w.at_ref IS NULL AND w.entry = true
RETURN w.id AS workflow, w.repo_id AS repo, w.severity AS severity,
       w.severity_reasons AS reasons, min(length(p)) AS depth"""
# coalesce: a first hop into a HEAD workflow (local reusable call) has no `pinned` prop, and null <> true is null
PINNED = """MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
MATCH p = (w:Workflow)-[:USES*1..{D}]->(bad)
WHERE w.at_ref IS NULL AND w.entry = true
WITH w, collect(DISTINCT coalesce(nodes(p)[1].pinned, false)) AS first_pins
WHERE size([x IN first_pins WHERE x <> true]) = 0
RETURN w.id AS workflow"""

# ---------- path evidence (Q-PATH, Q-PATH-FALLBACK) ----------
PATH = """MATCH (w:Workflow {id: $wid})
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
CALL algo.SPpaths({sourceNode: w, targetNode: bad, relTypes: ['USES'], weightProp: 'weight',
                   relDirection: 'outgoing', maxLen: {D}, pathCount: 1})
YIELD path, pathWeight
RETURN path, pathWeight ORDER BY pathWeight ASC LIMIT 1"""
PATH_FALLBACK = """MATCH (w:Workflow {id: $wid}), (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
MATCH p = (w)-[:USES*1..{D}]->(bad)
RETURN p ORDER BY length(p) ASC LIMIT 1"""

# ---------- viz subgraph (Q-VIZ) ----------
VIZ_EDGES = """MATCH (:Action {id: $aid})<-[:VERSION_OF]-(r:ActionRef)
MATCH p = (w:Workflow)-[:USES*1..{D}]->(r)
WHERE w.at_ref IS NULL AND w.entry = true
WITH p LIMIT 5000
UNWIND relationships(p) AS e
WITH DISTINCT e
RETURN startNode(e).id AS src, endNode(e).id AS dst, e.kind AS kind, e.uses AS uses,
       e.file_path AS file_path, e.lines AS lines"""
NODES_BY_ID = "MATCH (n:{label}) WHERE n.id IN $ids RETURN n"  # label from USES_LABELS only

# ---------- min-cut (Q-CAP-1, Q-CAP-2, Q-MAXFLOW, Q-EDGES-EXPORT) — scratch graphs only ----------
CAP_1 = """MATCH ()-[e:USES]->(b)
SET e.cap = CASE WHEN e.src_immutable = true THEN 10000 WHEN b.pinned = true THEN 1 ELSE 3 END"""
CAP_2 = """MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(b:ActionRef)
MATCH ()-[e:USES]->(b)
WHERE e.src_immutable = false
SET e.cap = 1"""
MAXFLOW = """MATCH (w:Workflow) WHERE w.id IN $sources
WITH collect(w) AS srcs
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(b:ActionRef)
WITH srcs, collect(b) AS tgts
CALL algo.maxFlow({sourceNodes: srcs, targetNodes: tgts, relationshipTypes: ['USES'], capacityProperty: 'cap'})
YIELD nodes, edges, edgeFlows, maxFlow
RETURN nodes, edges, edgeFlows, maxFlow"""
PROBE_CREATE = """CREATE (s:P {id:'s'}), (a:P {id:'a'}), (b:P {id:'b'}), (t:P {id:'t'}),
       (s)-[:R {cap: 1}]->(a), (s)-[:R {cap: 1}]->(b), (a)-[:R {cap: 5}]->(t), (b)-[:R {cap: 5}]->(t)"""
PROBE = """MATCH (s:P {id:'s'}), (t:P {id:'t'})
CALL algo.maxFlow({sourceNodes: [s], targetNodes: [t], relationshipTypes: ['R'], capacityProperty: 'cap'})
YIELD nodes, edges, edgeFlows, maxFlow
RETURN nodes, edges, edgeFlows, maxFlow"""
EDGES_EXPORT = """MATCH (s)-[e:USES]->(d)
RETURN id(e) AS eid, id(s) AS sid, id(d) AS did, e.cap AS cap, s.id AS s_key, d.id AS d_key,
       labels(s)[0] AS s_label, labels(d)[0] AS d_label"""
DELETE_EDGE = "MATCH (s:{sl} {{id: $s}})-[e:USES]->(d:{dl} {{id: $d}}) DELETE e"  # labels from USES_LABELS

# ---------- fix plans ----------
PLAN_IDS = "MATCH (p:FixPlan) RETURN p.id AS id"
PLAN_CREATE = """MATCH (adv:Advisory {id: $adv})
CREATE (p:FixPlan {id: $id, advisory_id: $adv, targets: $targets, cut_size: $cut_size, protected: $protected,
                   naive: $naive, engine: $engine, created_at: $now, sources: $sources, max_flow: $max_flow})
CREATE (p)-[:FOR]->(adv)
WITH p
UNWIND $fixes AS f
CREATE (x:Fix) SET x += f
CREATE (p)-[:INCLUDES]->(x)
RETURN count(x) AS fixes"""
PLAN_GET = "MATCH (p:FixPlan {id: $pid}) RETURN p"
PLAN_FIXES = "MATCH (:FixPlan {id: $pid})-[:INCLUDES]->(f:Fix) RETURN f ORDER BY f.id"
PLAN_PRS = """MATCH (:FixPlan {id: $pid})-[:INCLUDES]->(f:Fix)<-[:IMPLEMENTS]-(pr:FixPR)
RETURN pr, f.id AS fix_id ORDER BY pr.phase, pr.id"""
FIXPR_CREATE = """MATCH (f:Fix {id: $fix})
CREATE (pr:FixPR {id: $id, url: $url, number: $number, repo: $repo, phase: $phase, status: $status})
CREATE (pr)-[:IMPLEMENTS]->(f)"""
FIXPR_STATUS = "MATCH (pr:FixPR {id: $id}) SET pr.status = $status, pr.merge_sha = $sha"
FIX_SET_NEW = "MATCH (f:Fix {id: $fix}) SET f.new_uses = $new_uses"

# ---------- leaderboard (Q-PR, Q-DIRECT, Q-REACH) ----------
PAGERANK = """CALL algo.pageRank(null, 'USES') YIELD node, score
WITH node, score WHERE 'ActionRef' IN labels(node) AND node.local = false
MATCH (node)-[:VERSION_OF]->(a:Action)
RETURN a.id AS action, sum(score) AS pagerank
ORDER BY pagerank DESC LIMIT 25"""
DIRECT = """MATCH (:Action {id: $aid})<-[:VERSION_OF]-(:ActionRef)<-[:USES]-(w:Workflow)
WHERE w.at_ref IS NULL AND w.entry = true RETURN count(DISTINCT w) AS direct"""
DIRECT_ALL = """MATCH (a:Action)<-[:VERSION_OF]-(r:ActionRef)<-[:USES]-(w:Workflow)
WHERE w.at_ref IS NULL AND w.entry = true AND r.local = false
RETURN a.id AS action, count(DISTINCT w) AS direct ORDER BY direct DESC LIMIT 60"""
REACH = """MATCH (:Action {id: $aid})<-[:VERSION_OF]-(r:ActionRef)
MATCH (w:Workflow)-[:USES*1..{D}]->(r)
WHERE w.at_ref IS NULL AND w.entry = true
RETURN count(DISTINCT w) AS reach,
       count(DISTINCT CASE WHEN r.pinned = false THEN w END) AS mutable_reach"""
COMPOSITE_REACH = """MATCH (a:Action)<-[:VERSION_OF]-(r:ActionRef)<-[:USES]-(:ActionRef)
WHERE r.local = false
RETURN a.id AS action, count(*) AS via_composites ORDER BY via_composites DESC LIMIT 40"""
BETWEENNESS = """CALL algo.betweenness({relationshipTypes: ['USES']}) YIELD node, score
WITH node, score WHERE 'ActionRef' IN labels(node) AND score > 0
RETURN node.id AS id, score ORDER BY score DESC LIMIT 10"""
TRANSITIVE_MUTABLE = """MATCH (w:Workflow) WHERE w.at_ref IS NULL AND w.entry = true
OPTIONAL MATCH (w)-[:USES*2..{D}]->(r:ActionRef) WHERE r.pinned = false AND r.local = false
WITH w, count(r) AS m
RETURN count(w) AS total, sum(CASE WHEN m > 0 THEN 1 ELSE 0 END) AS with_transitive_mutable"""
MAX_DEPTH_SEEN = """MATCH p = (w:Workflow)-[:USES*1..{D}]->(:ActionRef)
WHERE w.at_ref IS NULL AND w.entry = true RETURN max(length(p)) AS d"""

# ---------- search (Q-FT) ----------
FT_SEARCH = "CALL db.idx.fulltext.queryNodes('Action', $q) YIELD node, score RETURN node.id AS id, score LIMIT 10"
CONTAINS_SEARCH = "MATCH (a:Action) WHERE a.id CONTAINS toLower($q) RETURN a.id AS id LIMIT 10"
ALL_ACTION_IDS = "MATCH (a:Action) RETURN a.id AS id"

# ---------- workflows ----------
WORKFLOW_GET = "MATCH (w:Workflow {id: $wid}) RETURN w"

# ---------- memory ----------
FINDING_CREATE = """CREATE (f:Finding {id: $id, question: $question, answer: $answer, created_at: $now,
                    action_id: $aid})
WITH f OPTIONAL MATCH (a:Action {id: $aid})
FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END | CREATE (f)-[:ABOUT]->(a))"""
FINDINGS = """MATCH (f:Finding) WHERE $aid = '' OR f.action_id = $aid OR f.action_id CONTAINS $aid
RETURN f.created_at AS date, f.question AS question, f.answer AS answer, f.action_id AS action_id
ORDER BY f.created_at DESC LIMIT 5"""
