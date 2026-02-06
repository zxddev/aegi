---
name: designing-ontologies
description: Use when designing data models that map real-world entities to digital objects, defining object types and their relationships, designing action types for operational workflows, evaluating ontology-based vs relational/graph modeling, or planning security boundaries for object and property level access control
---

# Designing Ontologies

## Overview

Ontology-Oriented Software Development (OOSD) replaces component-centric enterprise architecture with a decision-centric ontology as the shared integration layer. Core insight: **realizing operational AI is not an AI problem — it's an ontology problem.**

The ontology is a single language expressible in graphical, verbal, and programmatic forms — enabling humans, applications, and AI agents to share the same representation of the business.

## When to Use

- Designing a domain model that represents business entities, relationships, and operational actions
- Evaluating ontology-based modeling vs traditional relational/graph approaches
- Designing writeback workflows where users or AI modify operational data
- Planning security boundaries (which objects/properties need row/column-level control)
- Defining how AI agents interact with domain objects (Actions = AI tools)

**When NOT to use:** Pure analytical queries; simple CRUD with no cross-entity relationships.

## Core Design Principles

1. **Decisions first, data second** — Nouns → Object Types, Verbs → Actions
2. **Objects = real-world entities** — Not database table dumps
3. **Links = relationships** — Explicit, named, directional
4. **Actions = first-class mutations** — Permissions, validation, audit, side effects
5. **Functions = server-side logic** — Complex computations in TypeScript/Python
6. **Interfaces = polymorphism** — Shared properties across Object Types
7. **Properties stay minimal** — Don't duplicate derivable data
8. **Naming = natural language** — The ontology IS the business language
9. **Security by design** — Plan row/column/cell-level access at design time, not after

## Decision Model

Every decision = Data + Logic + Action:

```
Data (nouns)      →  Objects, Properties, Links, Object Sets
Logic (reasoning) →  Functions, AIP Logic, ML Models
Action (verbs)    →  Action Types, Webhooks, Writeback
```

## Design Flow

1. Describe what users/agents need to **decide**
2. Extract nouns → Object Types
3. Extract verbs → Action Types
4. Map relationships → Link Types
5. Identify shared shapes → Interfaces
6. Define minimal properties
7. Plan security boundaries
8. Validate with domain experts

## Quick Reference

| Dimension | Ontology (OOSD) | Knowledge Graph (OWL/RDF) | Relational DB |
|---|---|---|---|
| Goal | Operational decisions | Knowledge representation | Data storage |
| Core unit | Object + Action | Triple (S-P-O) | Table + Row |
| Polymorphism | Interfaces | rdfs:subClassOf | Table inheritance |
| AI integration | Actions auto-exposed as tools | None native | None native |
| Security | Built-in (row/col/cell) | Bolt-on | Bolt-on |

## Key Reference

See `palantir-ontology-reference.md` for Palantir Foundry's concrete design rules: OOSD rationale, seven core elements, Object/Link/Action design rules, security design, naming conventions, and primary key rules.
