# Author: msq
"""Seed a demo Neo4j case for PyKEEN link-prediction API verification."""

from __future__ import annotations

import random

from neo4j import GraphDatabase

from aegi_core.settings import settings


def main() -> None:
    case_uid = "case_pykeen_live_20260211"
    random.seed(42)

    entities = [f"lp_entity_{i}" for i in range(12)]
    relations = ["ALLIES_WITH", "TRADES_WITH", "OPPOSES"]

    triples: set[tuple[str, str, str]] = set()
    while len(triples) < 140:
        head = random.choice(entities)
        relation = random.choice(relations)
        tail = random.choice(entities)
        if head != tail:
            triples.add((head, relation, tail))

    triples.discard(("lp_entity_0", "ALLIES_WITH", "lp_entity_11"))

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    with driver.session(database="neo4j") as session:
        session.run("MATCH (n {case_uid: $case_uid}) DETACH DELETE n", case_uid=case_uid)

        for uid in entities:
            session.run(
                "MERGE (n:Entity {uid: $uid}) "
                "SET n.case_uid=$case_uid, n.name=$name, n.type='Entity'",
                uid=uid,
                case_uid=case_uid,
                name=uid.replace("_", " ").title(),
            )

        for head, relation, tail in triples:
            session.run(
                f"MATCH (a:Entity {{uid: $head}}), (b:Entity {{uid: $tail}}) "
                f"MERGE (a)-[rel:{relation}]->(b) "
                "SET rel.case_uid=$case_uid",
                head=head,
                tail=tail,
                case_uid=case_uid,
            )

        count_nodes = session.run(
            "MATCH (n {case_uid: $case_uid}) RETURN count(n) AS c",
            case_uid=case_uid,
        ).single()["c"]
        count_triples = session.run(
            "MATCH (a {case_uid: $case_uid})-[r]->(b {case_uid: $case_uid}) "
            "RETURN count(r) AS c",
            case_uid=case_uid,
        ).single()["c"]

    print(
        {
            "case_uid": case_uid,
            "nodes": count_nodes,
            "triples": count_triples,
        }
    )


if __name__ == "__main__":
    main()
