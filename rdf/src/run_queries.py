"""Run the queries in a .rq file (separated by '#---') against a Turtle file."""
import sys
from rdflib import Graph
ttl, rq = sys.argv[1], sys.argv[2]
g = Graph().parse(ttl).parse(__file__.replace("src/run_queries.py", "ontology/cfa.ttl"))
for block in open(rq).read().split("#---"):
    title = next((l for l in block.splitlines() if l.startswith("# Q")), "# query")
    res = g.query(block)
    print("\n" + title)
    print(" | ".join(str(v) for v in res.vars))
    for row in res:
        print(" | ".join("" if x is None else str(x).rsplit("#", 1)[-1] for x in row))
