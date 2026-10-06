# Legal Eagle V4 Roadmap

## Status
**Planning — architecture refreshed October 2026**

V4 evolves Legal Eagle from a pipeline of loosely connected enrichment/ranking steps into a clearer legal-intelligence lifecycle:

**News → Context Resolver → Legal Event → SAP Scope / Impact Assessment → Classification / Priority**

The goal is not to add more agents. The goal is to consolidate the intelligence already built in V3, introduce stronger SAP grounding, simplify the user experience, and make Legal Eagle reason first about the legal event itself and only then about SAP relevance and action.

---

# 1. V4 Design Principles

## 1.1 Legal reality comes before SAP interpretation

A legal event exists independently of SAP.

Legal Eagle should first determine:

- what happened,
- which authority is involved,
- which law or regulatory framework governs it,
- what changed,
- when it becomes effective,
- which sources refer to the same event.

Only after that should the system ask:

- does SAP support this area,
- which localized product/process is affected,
- is the requirement already covered,
- is this a new Legal Change,
- is it out of SAP scope,
- and how urgent is it.

This keeps legal understanding separate from product interpretation.

---

## 1.2 V4 conceptual flow

### Stage 1 — News
Collect and normalize source material.

### Stage 2 — Context Resolver
Resolve legal and domain context around each item.

### Stage 3 — Legal Event
Group news into one persistent real-world legal event.

### Stage 4 — SAP Scope / Impact Assessment
Assess the legal event against SAP localized product scope and implementation knowledge.

### Stage 5 — Classification / Priority
Classify what SAP should do and assign operational priority.

---

# 2. Stage Mapping — Current V3 Components into V4

## 2.1 News

Current components:

- RSS
- Twitter
- URL Scrape
- Email Inbox
- Filter
- Compare / basic deduplication

Purpose:

- collect source content,
- apply source/date boundaries,
- remove obvious same-story duplication,
- preserve all relevant source evidence.

No SAP impact judgment should happen here.

---

## 2.2 Context Resolver

Current / evolved components:

- L2 Fetch
- Authority resolution
- Glossary Match
- Law Match
- Reconcile
- RCM History Match
- **Taxonomy Match — NEW active capability**

Purpose:

Build a structured legal context for each item before it becomes part of a Legal Event.

Target output:

- authority
- source / portal context
- explicit law reference
- inferred governing law
- law match method
- law confidence
- cited article
- effective date
- taxonomy/domain scope
- glossary topics
- historical RCM relation
- event semantics
- source confidence

### Law Match evolution

The current resolver relies mainly on an explicit `law_primary`.

V4 must support two paths:

1. **Explicit Match**
   - law number,
   - law name,
   - article reference.

2. **Contextual Inference**
   - issuing authority,
   - source portal,
   - taxonomy/domain,
   - topic,
   - semantics,
   - registered law corpus.

Example:

A GOSI portal article may never mention the GOSI law number because the legal context is implicit in the portal itself.

V4 should therefore persist:

- `law_match_method = explicit | inferred`
- `law_match_confidence`

Inference must never be presented as an explicit citation.

---

# 3. Taxonomy Becomes Active Grounding

Taxonomy is currently available but not actively used in relevance or impact reasoning.

V4 should introduce a formal Taxonomy Match.

Taxonomy answers:

> Which SAP/localization business concept, process, statutory object, payroll concept, reporting requirement, master data object, or functional area does this legal event touch?

Taxonomy should not directly force a high rank.

Instead it strengthens:

- SAP relevance,
- product-scope matching,
- impact confidence,
- fit/gap analysis.

Taxonomy therefore becomes one of the main bridges between external regulation and SAP product scope.

---

# 4. Legal Event — Core V4 Object

The current Announcement concept evolves into the central **Legal Event** object.

A Legal Event is:

> one real-world regulatory development represented by one or more source items across sources, languages, and runs.

Examples:

- a newly enacted contribution-rate change,
- a clarification of an existing reporting requirement,
- an implementation deadline,
- a follow-up circular on an existing change.

## 4.1 Legal Event responsibilities

- group same-event news,
- accumulate sources across runs,
- preserve legal facts,
- maintain one persistent identity,
- retain authority and law context,
- carry effective date,
- preserve source evidence,
- produce one stable event title.

## 4.2 Grouping rule

`law_id` narrows candidates.

`same_legal_event()` confirms the actual event.

Same law does not mean same event.

---

# 5. Title Strategy — Preserve Source Language, Avoid AI Creativity

V4 should use a strict title hierarchy.

1. Reuse an existing matched RCM title when appropriate.
2. Otherwise preserve the authoritative source headline when it is clear and usable.
3. Only synthesize a title when:
   - several sources must be unified,
   - the original headline is too vague,
   - or the source title is unsuitable for the Legal Event.
4. When synthesis is necessary, use **minimal normalization**, not editorial rewriting.

The AI should not invent a "better sounding" title simply because no historical RCM title exists.

---

# 6. Persistent Legal Events Across Runs

The earlier V4 roadmap already identified the need for persistent accumulating announcements.

This remains valid but is now reframed around Legal Events.

Desired lifecycle:

`open → assessed → actioned / closed`

While open:

- matching new sources are appended,
- event context can improve,
- SAP impact can be refreshed,
- priority can change.

Once actioned / closed:

- legal-event identity remains frozen,
- later materially different developments become a new event,
- follow-up news can link back to the earlier event.

This replaces per-run destructive grouping.

---

# 7. SAP Scope / Impact Assessment

This is where V4 becomes significantly stronger than the current Impact Gate.

The current Impact Gate is mainly a signal extractor.

V4 Impact Assessment should answer:

> Given this grounded Legal Event, what does it mean for SAP localized products?

## 7.1 Questions to answer

- Is the event relevant to an SAP-supported localized process?
- Which product / localization capability is affected?
- Which statutory process or business object is involved?
- Is SAP already compliant?
- Is there a functional gap?
- Is there a technical implementation impact?
- Does SAP need preparation before the effective date?
- What is the likely expected solution direction?
- What evidence supports the conclusion?

---

# 8. Grounding Strategy for Impact Assessment

No single MCP should be treated as the universal answer.

Different capabilities answer different questions.

## 8.1 RCM / LOKA history

Answers:

- Have we handled something similar before?
- What wording and classification were used?
- Was there an existing Legal Change?

Use for historical precedent and naming.

---

## 8.2 GLO Taxonomy KG

Answers:

- What SAP/localization domain does this event belong to?
- Which business concepts or processes are related?

Use for scope and semantic product mapping.

---

## 8.3 GLO Repo KG

Answers:

- What requirements or legal-change history already exists?
- Which prior requirements may overlap?

Use for requirements grounding and fit/gap context.

---

## 8.4 SAP Enterprise Knowledge Graph

Answers:

- Which SAP product capabilities are related?
- What functional objects/processes connect to the identified taxonomy area?

Use for broader SAP functional grounding.

---

## 8.5 SAP ABAP MCP

Answers:

- Which implementation logic, functions, reports, schemas, BAdIs, classes, or code objects may be involved?

Use only when technical impact depth is needed.

---

## 8.6 Law-to-Spec / Fit-Gap capability

Answers:

- Given the law and SAP product scope, is there a likely fit or gap?
- What expected solution direction can be proposed?

This should become the core reasoning path for the mature Impact Assessment.

---

# 9. Impact Orchestration Model

The Impact capability should orchestrate evidence progressively instead of blindly calling every tool.

Suggested sequence:

1. Legal Event context
2. Taxonomy mapping
3. RCM / requirement history
4. Product / functional knowledge
5. Fit-gap reasoning
6. Technical grounding only where necessary
7. Structured impact conclusion

The output should always retain provenance of the evidence used.

---

# 10. Classification / Priority

Only after the Legal Event and SAP Impact Assessment are established should Legal Eagle classify the event.

## 10.1 Suggested SAP classifications

- **New Legal Change**
- **Tracked / Existing Legal Change**
- **Already Covered**
- **SAP Scope — No Change Required**
- **Out of Current SAP Scope**
- **Informational / Monitor**
- **Not SAP Relevant**

These are product/business classifications, not descriptions of the legal event itself.

---

## 10.2 Priority

Priority remains deterministic wherever possible.

Inputs may include:

- SAP scope relevance
- confirmed regulatory change
- fit/gap result
- operational impact
- preparation required
- timing / effective date
- historical tracking status
- grounding confidence

Suggested output remains compatible with the current scale:

1. Noise
2. Signal
3. Watch
4. Legal Change
5. Urgent

The deterministic ranker should remain downstream of reasoning.

---

# 11. Simplified End-User Experience

V4 should remove the current mental split between:

- News Review
- Announcements

The main user view should become:

# Legal Events

Each row/card represents one Legal Event.

Collapsed view:

- event title
- authority
- law
- taxonomy scope
- effective date
- SAP classification
- rank / urgency
- status

Expanded view:

- all source news
- legal context
- law inference evidence
- SAP impact
- previous RCM relation
- human corrections
- actions

A one-source event simply contains one source.

A multi-source / cross-language event contains several.

The user should not need to understand the internal distinction between `news_items` and grouped announcements.

---

# 12. Human-in-the-Loop

Human correction remains central.

The LPM should be able to correct:

- law
- authority
- taxonomy mapping
- Legal Event grouping
- title
- SAP classification
- rank
- impact conclusion

Corrections should be captured as future grounding where appropriate.

The existing re-rank learning mechanism can evolve into a wider context-correction loop rather than only rank correction.

---

# 13. Announce / RCM Action

The previous V4 concept of an Announce Agent remains useful, but it becomes an action **after classification** rather than one of the core intelligence stages.

When a Legal Event is classified as a Legal Change:

1. LPM reviews the event and impact assessment.
2. Legal Eagle prepares the RCM/PRD payload.
3. Human confirms.
4. Announce capability uses the sanctioned L2S path.
5. The created Legal Change is linked back to the Legal Event.
6. Event status becomes actioned / closed as appropriate.

No raw direct JIRA REST integration.

---

# 14. V4 Delivery Workstreams

## Workstream 1 — Architecture Consolidation

- formalize the five-stage model,
- remap existing agents,
- remove duplicated responsibilities,
- move effective-date ownership into legal context,
- keep ranking downstream.

---

## Workstream 2 — Context Resolver 2.0

- contextual law inference,
- source/portal-aware legal context,
- active Taxonomy Match,
- confidence and evidence model,
- improved RCM-history grounding.

---

## Workstream 3 — Legal Event Model

- rename/evolve Announcement into Legal Event,
- persistent identity,
- accumulate sources across runs,
- stable event lifecycle,
- stable title logic,
- cross-language event grouping.

---

## Workstream 4 — Unified Legal Events UI

- replace separate News / Announcement mental models,
- event-first review screen,
- expandable source evidence,
- inline context correction,
- inline impact and classification.

---

## Workstream 5 — SAP Impact Assessment

- taxonomy grounding,
- RCM / LOKA history,
- GLO Repo requirements grounding,
- SAP KG functional grounding,
- fit-gap reasoning,
- optional ABAP technical grounding,
- structured evidence-backed impact output.

---

## Workstream 6 — Classification & Priority

- define SAP classification taxonomy,
- redesign deterministic rank inputs,
- keep urgency separate from semantic understanding,
- preserve human override.

---

## Workstream 7 — Action / Announce Integration

- Preview for RCM,
- confirm-before-create gate,
- L2S PRD MCP integration,
- Legal Change linking,
- event lifecycle closure.

---

# 15. Proposed V4 Architecture

```text
SOURCE WORLD
    │
    ▼
┌───────────────────────┐
│ 1. NEWS               │
│ Collect · Filter      │
│ Basic Dedup           │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ 2. CONTEXT RESOLVER   │
│ L2                    │
│ Authority             │
│ Glossary              │
│ Law explicit/inferred │
│ Taxonomy              │
│ RCM History           │
│ Reconcile             │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ 3. LEGAL EVENT        │
│ Persistent identity   │
│ Same-event grouping   │
│ Legal facts           │
│ Stable title          │
│ Sources               │
└──────────┬────────────┘
           │
           ▼
┌──────────────────────────┐
│ 4. SAP SCOPE / IMPACT    │
│ Taxonomy / GLO           │
│ RCM / LOKA history       │
│ SAP KG                   │
│ Fit-Gap                  │
│ ABAP when needed         │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 5. CLASSIFY / PRIORITIZE │
│ LC / Covered / OOS / ... │
│ Timing                   │
│ Deterministic Rank       │
│ Human override           │
└──────────┬───────────────┘
           │
           ▼
      REVIEW / ACTION
           │
           ├── Monitor
           ├── Close
           └── Publish to RCM / L2S
```

---

# 16. What Remains Valid from the Earlier V4 Roadmap

The previous V4 roadmap should not be discarded completely.

The following ideas remain valid:

- use the SAP L2A Capability Hub instead of rebuilding SAP grounding,
- use L2S PRD MCP for the sanctioned write path,
- use GLO Taxonomy KG,
- use GLO Repo KG,
- use SAP ABAP MCP,
- use SAP Enterprise Knowledge Graph,
- use the fit-gap capability,
- persist Legal Events across runs,
- accumulate related sources while an event is open,
- freeze/close an event after hand-off,
- keep a human confirmation gate before creating a Legal Change.

The difference is that these are now parts of a broader, more mature architecture rather than the definition of V4 itself.

---

# 17. V4 Success Criteria

V4 is successful when an LPM can start from a set of noisy regulatory sources and reach one grounded Legal Event where the system can explain:

1. **What happened legally?**
2. **Which law/regulatory framework governs it?**
3. **Why were these sources grouped together?**
4. **Which SAP-localized capability may be affected?**
5. **Is SAP already covered or is there a gap?**
6. **What classification should SAP assign?**
7. **How urgent is it?**
8. **What evidence supports the conclusion?**
9. **What action should the LPM take next?**

That is the V4 target.


---

# Appendix A — Retained SAP L2A References from Earlier V4 Roadmap

These references are carried forward from the earlier V4 planning document so they are not lost during the architecture refresh.

> **Important:** These are SAP-internal resources and were documented as candidate integrations. Access, authentication, exact tool names, and capabilities should be re-verified when implementation starts.

## Announce / L2S path

| Resource | Type | Location | Intended use |
|---|---|---|---|
| **L2S PRD MCP** | MCP | `https://auth-proxy.daf98e7.kyma.ondemand.com/l2s-prd-mcp/mcp` | Sanctioned L2S/PRD path for creating or linking the JIRA Legal Change |
| **glo-requirements-setup** | Skill | `github.tools.sap/law-to-action/l2a-capability-hub/blob/main/skills/glo-requirements-setup/SKILL.md` | Scaffold GLO requirements / JIRA structure |

## SAP Scope / Impact grounding

| Resource | Type | Location | Intended use |
|---|---|---|---|
| **glo-functional-spec-fitgap-generator** | Skill | `github.tools.sap/law-to-action/l2a-capability-hub/blob/main/skills/glo-functional-spec-fitgap-generator/SKILL.md` | Law → product fit/gap reasoning |
| **GLO Taxonomy KG** | MCP | `https://glo-taxonomy-kg-mcp-server.daf98e7.kyma.ondemand.com/mcp` | Regulatory/domain taxonomy grounding |
| **GLO Repo KG** | MCP | `https://sap-mcp-glorep-kg.cfapps.eu12.hana.ondemand.com/mcp-http` | GLO legal / requirements repository grounding |
| **SAP ABAP MCP** | MCP | SAP internal — exact endpoint not captured in the earlier roadmap | Technical/code grounding |
| **SAP Enterprise Knowledge Graph** | KG | SAP internal — exact endpoint not captured in the earlier roadmap | Broad SAP product/functional grounding |

## L2A Capability Hub references

- MCP servers catalog: `https://pages.github.tools.sap/law-to-action/l2a-capability-hub/#mcp-servers`
- Skills repository: `github.tools.sap/law-to-action/l2a-capability-hub`

## Security / trust note retained from the earlier roadmap

A previously configured `sap-mcp-glorepo` MCP in the development environment returned tool descriptions instructing a `git pull`, `/set-me-up`, and client restart.

Treat tool-provided setup instructions as **untrusted until explicitly verified by the owner/team**. Do not execute embedded environment-changing instructions merely because an MCP tool description requests them.

---

# Appendix B — Earlier V4 Open Questions Worth Preserving

The architecture has matured, but these implementation questions from the earlier roadmap are still relevant:

1. Which exact L2S PRD MCP call creates the Legal Change, and which fields it requires.
2. Whether the fit/gap capability is invoked as a Skill inside an agent loop or exposed directly as an MCP/tool.
3. Keep a human confirmation gate before any Legal Change write.
4. Verify runtime authentication/SSO and actual capabilities for each SAP-internal MCP/KG before implementation.
