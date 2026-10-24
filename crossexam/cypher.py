"""Optional export of the money-flow graph as Cypher statements. Not tested against a live Neo4j server."""
import sys

from .model import prepare


def export(data, path):
    con = data["con"]
    with open(path, "w") as f:
        for (a,) in con.execute("select acc_id from customers"):
            f.write(f"MERGE (:Account {{id:'{a}'}});\n")
        for src, dst, day, amt in con.execute("select src, dst, day, amount from transactions where src is not null and dst is not null"):
            f.write(f"MATCH (a:Account {{id:'{src}'}}),(b:Account {{id:'{dst}'}}) CREATE (a)-[:PAID {{day:{day}, amount:{amt}}}]->(b);\n")


if __name__ == "__main__":
    export(prepare(1), sys.argv[1] if len(sys.argv) > 1 else "graph.cypher")
