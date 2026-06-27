# Legal Repository Strategy (v2)

## Purpose

The Legal Repository is the long-term institutional memory of Legal Eagle.

It is not a static document library.

It stores and organizes the knowledge generated while investigating legal changes and delivering localization features.

The repository is designed around a central principle:

```text
EPIC = Delivery Anchor

Repository Node = Knowledge Anchor
```

Each repository node is linked to a business EPIC and evolves together with it.

---

# Core Components

## Legal Eagle

Responsible for:

* News collection
* Filtering
* Grouping
* Email digests
* News review

Output:

```text
Potential legal change
```

---

## Law-to-Spec

Responsible for:

* Legal analysis
* SAP impact analysis
* EPIC creation
* Scope definition

Output:

```text
EPIC
```

Example:

```text
GSREQSE-15293
```

---

## Legal Repository

Responsible for:

* Knowledge preservation
* Traceability
* Historical context
* Legal-to-SAP mapping

Output:

```text
Repository Node
```

Example:

```text
GR
 └─ Labor
     └─ ERGANI
         └─ ERGANI II
             └─ Employment Relationship Modification
```

---

# End-to-End Flow

```text
Legal Eagle
    ↓
News Collection
    ↓
Filtering / Grouping
    ↓
Email Digest
    ↓
Manual News Review
```

When a news item is considered important:

```text
Critical News
      ↓
Generate Investigation Pack
```

The Investigation Pack contains:

* Source URL
* Official legal URL
* Country
* Authority
* Domain
* Suggested repository location
* Suggested legal topic

---

# Law-to-Spec Integration

The Investigation Pack is copied into Law-to-Spec.

Law-to-Spec performs:

* Legal analysis
* SAP impact assessment
* Scope proposal
* EPIC creation

Output:

```text
GSREQSE-XXXXX
```

---

# Repository Creation

Once the EPIC exists:

```text
News
    ↓
EPIC
    ↓
Repository Node
```

The repository node is created or updated.

The EPIC ID becomes the primary reference.

Example:

```yaml
epic_id: GSREQSE-15293

status: TO_BE_ANALYZED

country: Greece

authority: ERGANI

law_reference: Decision 32689/2025

source_news:
  NEWS-2026-051
```

---

# Traceability Model

```text
News Item
    ↓
Investigation Pack
    ↓
EPIC
    ↓
Repository Node
    ↓
Knowledge Map
```

Relationships:

```text
News ↔ EPIC

EPIC ↔ Repository Node

Repository Node ↔ Knowledge Assets
```

---

# Repository Node Lifecycle

```text
NEWS_IDENTIFIED
    ↓
INVESTIGATION_CREATED
    ↓
EPIC_CREATED
    ↓
TO_BE_ANALYZED
    ↓
UNDER_ANALYSIS
    ↓
ANALYZED
```

Possible outcomes:

```text
ANALYZED
    ├─ PRODUCT_IMPACT_CONFIRMED
    ├─ NO_PRODUCT_IMPACT
    ├─ WATCHLIST
    └─ ARCHIVED
```

---

# Knowledge Maturity Levels

Level 0

* News item

Level 1

* EPIC exists
* Repository node exists

Level 2

* Legal analysis completed

Level 3

* SAP impact identified

Level 4

* SAP objects mapped
* JIRAs linked
* Historical references linked

Level 5

* Full knowledge asset

Examples:

* ERGANI II Mind Map
* XML schemas
* SAP mappings
* Infotype mappings
* JIRA history
* Consultant notes
* Source documents

---

# HEAD and TAIL Concept

## HEAD (Knowledge Retrieval)

Before analysis:

```text
Repository
    ↓
Analyzer
```

Retrieve:

* Previous laws
* Existing SAP functionality
* Historical JIRAs
* Previous analyses
* Consultant knowledge

---

## TAIL (Knowledge Learning)

After analysis:

```text
Analyzer
    ↓
Repository
```

Store:

* New legal findings
* New SAP impacts
* New mappings
* New implementation knowledge

---

# Long-Term Vision

Legal Eagle = Journalist

Law-to-Spec = Product Lawyer

Legal Repository = Institutional Memory

The repository evolves through:

```text
News
    ↓
EPIC
    ↓
Repository Node
    ↓
Knowledge Asset
```

The repository becomes both:

HEAD → Context provider

TAIL → Knowledge accumulator

```
```
# Repository Roadmap

## Phase 1 – Local Knowledge Repository

Purpose:

* Capture legal knowledge generated from Legal Eagle reviews.
* Build country-specific legal maps.
* Maintain traceability between:

  * News
  * Repository Nodes
  * Delivery Artifacts

Repository acts as the primary working knowledge base.

---

## Phase 2 – Legal Analyzer Integration

Legal Analyzer begins using repository knowledge.

Repository provides:

* Historical legal context
* Previous SAP impacts
* Existing delivery artifacts
* Prior analyses

HEAD retrieval becomes active.

TAIL learning becomes active.

---

## Phase 3 – Enterprise Knowledge Synchronization

Repository nodes become candidates for publication into SAP GLO Repo.

Local repository remains the working area.

GLO Repo becomes the enterprise knowledge repository.

Example:

Legal Eagle
↓
Local Repository
↓
Published Knowledge Asset
↓
SAP GLO Repo

---

## Phase 4 – MCP Integration

GLO Repo becomes accessible through MCP.

Legal Analyzer retrieves knowledge from:

* Local Repository
* SAP GLO Repo
* LOKA
* JIRA
* RCM
* Future Enterprise Sources

---

## Design Principle

The local repository must remain platform-independent.

Repository nodes should not depend on:

* Local database IDs
* Specific Jira object types
* Specific MCP implementations

Repository nodes should be defined by business metadata:

* Country
* Domain
* Authority
* Topic
* Subtopic
* Legal References
* Delivery Artifacts

This ensures future migration to SAP GLO Repo with minimal restructuring.

