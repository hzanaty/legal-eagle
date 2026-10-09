# Legal Eagle V5 Roadmap — Reinnovation

## Status
**Planning — follows V4 MCP Server on the product roadmap, but is architecturally independent**

V4 focuses on exposing Legal Eagle capabilities through MCP.

V5 redesigns how Legal Eagle builds a monitoring profile, understands regulatory news, assesses relevance, ranks attention, classifies findings, groups evidence, and hands the result back to the LPM for action in L2S.

V5 does **not** replace L2S and does **not** attempt to author the official Legal Change announcement itself.

The core V5 model is split into two lifecycles:

**Profile Intelligence**

`Taxonomy → Business Scope → Glossary + Laws → Authorities → Official Sources → Profile Setup Draft → Validate / Simulate / Update → LPM Review → Save Profile`

**Runtime Intelligence**

`Run Profile → Sources → News → Grounding → Ranking → Classification → Group → LPM Review → L2S → Published JIRA ID`

---

# 1. V5 Strategic Principles

## 1.1 Legal Eagle is not L2S

Legal Eagle should discover, understand, prioritize, classify, and group regulatory evidence.

L2S remains the system where the LPM creates or manages the official Legal Change / requirement.

Therefore V5 must respect the following boundary:

- Legal Eagle identifies candidate regulatory developments.
- Legal Eagle groups supporting news.
- Legal Eagle explains why the group matters.
- The LPM remains human-in-the-loop.
- The LPM creates the official announcement / Legal Change in L2S.
- Legal Eagle records the resulting **Published JIRA ID** against the relevant group.

The Published JIRA ID becomes the primary close-the-loop reference between Legal Eagle and L2S.

---

## 1.2 Ranking and Legal Change classification are different

V5 explicitly separates:

> **Ranking = how much attention the LPM should give this item or group.**

from:

> **Classification = what kind of finding this is.**

A high-rank finding is not automatically a Legal Change.

Examples:

- A market-critical new requirement can deserve very high attention even before it is confirmed as a formal Legal Change.
- A confirmed Legal Change can be lower urgency if implementation is minor or the effective date is distant.
- A clarification may be highly relevant without requiring a new development.

This separation is a core V5 design rule.

---

## 1.3 Profile setup becomes AI-assisted

V5 changes profile configuration from a mainly manual setup activity into an AI-assisted discovery process.

The system should be able to start from the localization scope and derive a first draft of:

- business scope,
- glossary,
- governing laws,
- authorities,
- official monitoring sources.

The LPM reviews and corrects the draft before saving.

This makes profile creation faster, more complete, and more maintainable.

---

# 2. V5 Architecture Overview

## 2.1 Profile Intelligence

```text
Taxonomy Snapshot
      ↓
Business Scope
      ↓
Glossary + Laws
      ↓
Authorities
      ↓
Official Sources
      ↓
Profile Setup Draft
      ↓
Validate / Simulate / Update
      ↓
LPM Review
      ↓
Save Profile
```

## 2.2 Runtime Intelligence

```text
Run Profile
    ↓
Sources
    ↓
News
    ↓
Grounding
 ├─ Glossary
 ├─ Law
 ├─ Taxonomy
 ├─ Authority
 ├─ Old RCM
 └─ Regulatory Urgency
    ↓
Ranking
    ↓
Classification
    ↓
Group Related High-Value News
    ↓
LPM Review / Override
    ↓
L2S Action by LPM
    ↓
Save Published JIRA ID
```

---

# 3. Profile Intelligence

## 3.1 Taxonomy Snapshot

The country Taxonomy should become the starting point for V5 profile setup.

The Taxonomy represents what the SAP localization is expected to cover for the selected country and Line of Business.

Because Taxonomy does not change frequently, Legal Eagle should not query it for every news item.

Instead, V5 should capture and store a **profile-level Taxonomy snapshot**.

The snapshot becomes stable grounding for:

- profile generation,
- business-scope definition,
- glossary generation,
- law discovery,
- runtime relevance assessment.

A refresh mechanism can be provided when the Taxonomy changes.

---

## 3.2 Business Scope

The Taxonomy snapshot should be transformed into a practical business-scope view for the profile.

Examples for HCM may include:

- payroll calculation,
- social insurance,
- income tax,
- statutory reporting,
- benefits,
- employment-related statutory processes,
- leave,
- employer incentives,
- master data required by legislation.

The business scope answers:

> **What does SAP localization cover in this country/profile?**

This becomes the primary product-side grounding for later relevance assessment.

---

## 3.3 Glossary Generation

Once the business scope is known, AI can propose a glossary for the profile.

The glossary should include:

- canonical business labels,
- native-language terminology,
- English terminology where useful,
- synonyms,
- abbreviations,
- common authority terminology,
- important payroll / statutory phrases.

The LPM reviews the glossary before approval.

The existing deterministic Glossary Match remains useful at runtime.

---

## 3.4 Law Discovery and Enrichment

The current law registry should be expanded beyond law number and name.

A law entry should include, where available:

- law ID,
- law number,
- official name,
- native name,
- short description / purpose,
- main business areas covered,
- key topics or relevant articles,
- responsible authority,
- status,
- effective-date metadata,
- official source URL.

### Why this matters

A regulator may publish an update without repeating the governing law number.

Example:

A GOSI portal article may discuss contribution rates without mentioning the GOSI law number because the legal context is implicit in the portal itself.

Therefore V5 should support semantic law understanding using the law description and business context.

### Law discovery function

During profile setup, AI should be able to:

1. start from the business-scope items,
2. search for the relevant governing laws,
3. collect basic legal descriptions,
4. identify the responsible authorities,
5. propose the law entries,
6. present them to the LPM for review.

The objective is not to produce legal advice.

The objective is to build enough background context for Legal Eagle to understand future news.

---

## 3.5 Authorities

Authorities should be derived from the identified laws and business scope.

For each authority, the profile should capture:

- authority name,
- native name,
- authority role,
- related laws,
- business areas,
- official domain / portal,
- source confidence.

Authorities form the bridge between:

**Law → Official Source**

---

## 3.6 Official Source Discovery

Once authorities are known, AI should propose the official monitoring sources.

Potential source types:

- authority websites,
- legal announcement portals,
- gazettes,
- RSS feeds,
- official social accounts,
- circular / decree pages,
- announcement sections,
- email sources where applicable.

The LPM can:

- approve,
- reject,
- edit,
- add additional sources.

V5 should therefore move from:

> “LPM manually knows which websites to configure”

toward:

> “Legal Eagle proposes the monitoring landscape from the legal/business profile.”

---

## 3.7 Profile Setup Draft

Legal Eagle should present one draft profile containing:

- Taxonomy snapshot,
- business scope,
- glossary,
- laws,
- authorities,
- official sources,
- known RCM history references where relevant.

The LPM should see the dependencies between them.

Example:

```text
Business Scope
  └─ Social Insurance
      ├─ Glossary terms
      ├─ Social Insurance Law
      │    └─ GOSI
      │         └─ Official GOSI portal
      └─ Historical RCM references
```

The setup should make the logic visible, not just store disconnected lists.

---

## 3.8 Validate / Simulate / Update

Before saving the profile, V5 should provide a simulation step.

The system should test whether the draft profile can successfully:

- reach the configured sources,
- collect sample news,
- match expected glossary concepts,
- infer or match relevant laws,
- map to Taxonomy scope,
- detect expected authority context,
- identify known RCM history where applicable.

The LPM can then adjust the profile before it becomes active.

This turns profile setup into:

> **Generate → Test → Correct → Save**

rather than a blind configuration exercise.

---

# 4. Runtime Grounding

Runtime grounding should answer:

> **What do we know about this news item, and why should the LPM care?**

The main grounding signals are:

- Glossary Match
- Law Match / Inference
- Taxonomy Match
- Authority Context
- Historical RCM Match
- Regulatory Urgency

These signals feed Ranking and Classification, but they should not be collapsed into one opaque AI score.

---

## 4.1 Glossary Match

Glossary Match remains a deterministic, profile-specific signal.

It answers:

> Which known business topics does this news touch?

The existing glossary-gap correction flow should remain available.

---

## 4.2 Law Match and Law Inference

V5 should support two law-resolution modes.

### Explicit Match

The article explicitly contains:

- law number,
- law name,
- article,
- regulation reference.

### Contextual Inference

The law is inferred using:

- source / portal,
- authority,
- Taxonomy business area,
- glossary topics,
- article semantics,
- stored law descriptions,
- law-to-authority relationships.

Persist:

- `law_match_method = explicit | inferred`
- `law_match_confidence`
- supporting evidence

An inferred law must never be displayed as if it were explicitly cited by the source.

---

## 4.3 Taxonomy Match

The stored country Taxonomy snapshot should be used to assess whether the article touches a business area that SAP localization covers.

Taxonomy becomes an active relevance signal.

It should answer:

> Does this regulatory news touch a business capability represented in this localization profile?

Taxonomy should not directly determine Rank.

It should strengthen relevance and classification confidence.

---

## 4.4 Historical RCM Match

A match with an old RCM announcement is a strong relevance signal.

It means:

> SAP has previously treated a similar subject as localization-relevant.

This does **not** automatically mean:

- the new item is a new Legal Change,
- the same solution is required again,
- or the same classification should be reused.

Historical RCM is evidence of relevance and precedent.

---

## 4.5 Regulatory Urgency

V5 should not rely on generic sentiment analysis for urgency.

Government communication can be emotionally neutral while operationally urgent.

Instead, introduce **Regulatory Urgency** detection.

Signals may include:

- effective immediately,
- deadline,
- mandatory / shall / must,
- penalty,
- retroactive applicability,
- transition period,
- filing window,
- implementation date proximity,
- suspension / cancellation,
- rate change,
- corrective filing requirement.

Some signals can be deterministic.

Others can be extracted by AI.

The output should be explainable.

---

# 5. Ranking

Ranking answers:

> **How much attention does this require from the LPM?**

Ranking should remain as deterministic as practical.

Potential inputs:

- Taxonomy relevance,
- Glossary relevance,
- Law relevance,
- historical RCM match,
- authority confidence,
- Regulatory Urgency,
- effective-date proximity,
- repetition / recurrence,
- profile-specific business importance.

The rank should remain explainable by visible signals.

Suggested scale:

1. **Noise**
2. **Signal**
3. **Watch**
4. **High Attention**
5. **Urgent**

V5 should avoid naming rank 4 itself “Legal Change,” because Legal Change becomes a separate classification.

---

# 6. Classification

Classification answers:

> **What kind of finding is this?**

Initial V5 classification candidates:

- **Legal Change**
- **Critical New Requirement**
- **Tracked / Existing Requirement**
- **Clarification / Guidance**
- **Already Covered**
- **SAP Scope — No Change Required**
- **Out of Current SAP Scope**
- **Informational / Monitor**
- **Not SAP Relevant**

## 6.1 Critical New Requirement

This classification is important because not every market-critical requirement begins as a clear statutory Legal Change.

Legal Eagle should be able to surface:

> “This is not confirmed as a Legal Change, but it appears to represent a new market requirement that should not be ignored.”

This prevents the ranking model from being artificially tied to LC status.

---

# 7. Grouping

After Ranking and Classification, Legal Eagle should group related high-value news.

The purpose of the group is not to create an official L2S announcement.

The purpose is to provide the LPM with one evidence package.

A group may contain:

- one source,
- multiple authorities,
- several updates,
- cross-language coverage,
- repeated or follow-up news.

Grouping should use:

- law identity,
- semantic similarity,
- authority,
- effective date,
- event semantics,
- related RCM history.

`same_legal_event()` can continue to help confirm whether items refer to the same underlying development.

---

## 7.1 Group Title Strategy

Legal Eagle should avoid unnecessary title invention.

Priority:

1. reuse a suitable historical RCM title when there is a strong match,
2. otherwise use the authoritative source title if clear,
3. only synthesize a title when several items must be represented together,
4. use minimal normalization when synthesis is necessary.

The group title is a Legal Eagle review aid, not the official L2S announcement title.

---

## 7.2 Group Lifecycle

Suggested lifecycle:

`open → reviewed → published`

While open:

- new related news can be appended,
- rank can change,
- classification can change,
- grounding can improve.

After the LPM creates the corresponding L2S/JIRA item:

- store the Published JIRA ID,
- mark the group as published,
- keep the evidence frozen for traceability.

Future materially different developments should create a new group even if they concern the same law.

---

# 8. LPM Review

The LPM remains the decision owner.

The review experience should allow the LPM to:

- inspect grouped evidence,
- inspect Taxonomy relevance,
- inspect law match / inference,
- inspect historical RCM match,
- inspect urgency signals,
- review Rank,
- review Classification,
- override Rank,
- override Classification,
- correct law / authority / Taxonomy mapping,
- split or merge groups,
- add justification.

Human corrections should be stored as grounding where appropriate.

---

# 9. Rank Override and Learning

The current override concept remains useful.

If the LPM overrides Rank:

- justification is required,
- original system rank is preserved,
- human rank is stored separately,
- the explanation should be available for future grounding.

The same learning philosophy can later be extended to:

- law corrections,
- Taxonomy corrections,
- Classification corrections,
- grouping corrections.

---

# 10. L2S Handoff

V5 should stop at a clean human-in-the-loop handoff.

Recommended flow:

1. Legal Eagle identifies and groups the relevant news.
2. Legal Eagle provides grounding, Rank, and Classification.
3. LPM reviews the group.
4. LPM opens / creates the official Legal Change or requirement in L2S.
5. LPM returns to Legal Eagle and records the Published JIRA ID.
6. Legal Eagle marks the group as published.

No Legal Eagle-generated official announcement is required.

No direct raw JIRA REST integration is required.

The system boundary remains clear:

**Legal Eagle = monitoring, intelligence, triage, evidence**

**L2S = official requirement / Legal Change workflow**

---

# 11. Simplified End-User Experience

V5 should simplify the UI around two main areas.

## 11.1 Profile Setup

One guided flow showing:

- Taxonomy
- business scope
- glossary
- laws
- authorities
- official sources
- simulation results
- LPM corrections

## 11.2 Review

One main review surface showing:

- high-value news groups,
- rank,
- classification,
- law,
- Taxonomy match,
- urgency,
- historical RCM relation,
- source evidence,
- Published JIRA ID.

The user should not need separate mental models for:

- flat news review,
- announcement generation,
- RCM preview.

The review focus becomes:

> **What happened, why does it matter, what is it, and what should I do next?**

---

# 12. Other-Country Taxonomy / Reuse Discovery

Other-country Taxonomy can be useful as a secondary capability.

Purpose:

> discover whether SAP has implemented a similar business requirement in another country.

This should not be a primary runtime signal because cross-country HCM localization commonality can be limited.

Use selectively when:

- the current-country Taxonomy shows no existing implementation,
- the finding appears to require a new capability,
- the LPM wants solution inspiration / reuse possibilities.

This likely requires MCP access rather than a static local snapshot.

The output should be treated as:

**Solution inspiration / reuse evidence**

not as proof that the current country should use the same implementation.

---

# 13. Impact Model Redesign

The current profile-specific Impact prompt should be retired or significantly reduced.

V5 should replace it with grounded signals derived from:

- country Taxonomy snapshot,
- glossary,
- enriched law registry,
- authority/source context,
- historical RCM,
- Regulatory Urgency,
- Classification logic.

If deeper technical/product assessment is needed, that can be added later as an on-demand capability rather than being required for every news item.

This keeps the runtime pipeline lighter and more explainable.

---

# 14. V5 Delivery Workstreams

## Workstream 1 — Profile Intelligence Foundation

- Taxonomy snapshot
- business-scope extraction
- profile data model update
- refresh mechanism

## Workstream 2 — AI-Assisted Profile Builder

- glossary generation
- law discovery
- law description enrichment
- authority discovery
- official-source discovery
- draft profile generation

## Workstream 3 — Profile Simulation

- test source access
- sample collection
- glossary/law/taxonomy validation
- LPM correction flow
- save approved profile

## Workstream 4 — Runtime Grounding

- contextual law inference
- Taxonomy Match
- historical RCM Match
- authority grounding
- Regulatory Urgency

## Workstream 5 — Ranking Redesign

- remove Legal Change from rank labels
- redefine deterministic gates
- integrate new grounding signals
- preserve explainability
- preserve human override

## Workstream 6 — Classification

- define Classification taxonomy
- separate LC from Rank
- introduce Critical New Requirement
- define tracked / covered / out-of-scope behavior

## Workstream 7 — Grouping and Review

- group related high-value news
- stable group lifecycle
- simpler title logic
- unified evidence review
- correction / split / merge

## Workstream 8 — L2S Handoff

- Published JIRA ID field
- published status
- link-out to L2S / JIRA
- traceability back to source news

## Workstream 9 — Optional Reuse Discovery

- other-country Taxonomy query
- similar-requirement lookup
- solution inspiration view
- MCP-based on-demand execution

---

# 15. V4 and V5 Relationship

V4 and V5 should remain separate.

## V4 — MCP Transformation

Focus:

- expose Legal Eagle capabilities through MCP,
- make Legal Eagle callable by other tools / agents,
- define interfaces,
- preserve existing core behavior,
- improve interoperability.

## V5 — Reinnovation

Focus:

- redesign profile setup,
- introduce Taxonomy-based grounding,
- enrich legal context,
- redesign runtime relevance,
- separate Ranking from Classification,
- simplify grouping and review,
- respect the L2S boundary.

V5 follows V4 in roadmap sequence but does not technically depend on V4 for its core architecture.

Future V5 capabilities can later be exposed through the V4 MCP interface.

---

# 16. Proposed V5 Architecture

```text
                PROFILE INTELLIGENCE

     GLO TAXONOMY
           │
           ▼
     BUSINESS SCOPE
           │
     ┌─────┴─────┐
     ▼           ▼
  GLOSSARY      LAWS
                   │
                   ▼
              AUTHORITIES
                   │
                   ▼
            OFFICIAL SOURCES
                   │
                   ▼
            PROFILE DRAFT
                   │
                   ▼
          VALIDATE / SIMULATE
                   │
                   ▼
              LPM REVIEW
                   │
                   ▼
             SAVE PROFILE


                RUNTIME INTELLIGENCE

              RUN PROFILE
                   │
                   ▼
                SOURCES
                   │
                   ▼
                  NEWS
                   │
                   ▼
               GROUNDING
        ┌──────────┼──────────┐
        │          │          │
     Glossary     Law      Taxonomy
        │          │          │
     Authority   Old RCM   Urgency
        └──────────┼──────────┘
                   │
                   ▼
                RANKING
                   │
                   ▼
             CLASSIFICATION
                   │
                   ▼
       GROUP RELATED HIGH-VALUE NEWS
                   │
                   ▼
              LPM REVIEW
           ┌───────┴────────┐
           │                │
      Override Rank      Accept
      + Justification       │
           └───────┬────────┘
                   │
                   ▼
             L2S BY LPM
                   │
                   ▼
          PUBLISHED JIRA ID
                   │
                   ▼
            GROUP PUBLISHED
```

---

# 17. V5 Success Criteria

V5 is successful when:

1. A new profile can be drafted largely from Taxonomy and public/legal context rather than from manual configuration alone.
2. The profile clearly connects business scope → glossary → laws → authorities → sources.
3. Law inference works even when the article does not explicitly mention the law number.
4. Country Taxonomy becomes active grounding for relevance.
5. Historical RCM becomes a strong but non-deterministic relevance signal.
6. Regulatory Urgency is detected without relying on generic sentiment.
7. Ranking is clearly separated from Legal Change classification.
8. Critical New Requirements can be surfaced even when they are not yet Legal Changes.
9. Related high-value news is grouped without Legal Eagle pretending to be L2S.
10. The LPM remains human-in-the-loop.
11. The Published JIRA ID closes the loop between Legal Eagle and L2S.
12. The review experience is simpler than the current News + Announcement split.
13. V5 intelligence remains explainable through visible grounding signals.

---

# Appendix A — Retained SAP / L2A References

These references are retained from the previous roadmap so they are not lost.

> **Important:** These are SAP-internal resources and should be re-verified for access, authentication, exact tool names, and capabilities before implementation.

## L2S / Requirements

| Resource | Type | Location | Intended use |
|---|---|---|---|
| **L2S PRD MCP** | MCP | `https://auth-proxy.daf98e7.kyma.ondemand.com/l2s-prd-mcp/mcp` | Sanctioned L2S/PRD interface |
| **glo-requirements-setup** | Skill | `github.tools.sap/law-to-action/l2a-capability-hub/blob/main/skills/glo-requirements-setup/SKILL.md` | GLO requirements / JIRA structure |

## SAP / Localization Knowledge

| Resource | Type | Location | Intended use |
|---|---|---|---|
| **glo-functional-spec-fitgap-generator** | Skill | `github.tools.sap/law-to-action/l2a-capability-hub/blob/main/skills/glo-functional-spec-fitgap-generator/SKILL.md` | Fit/gap reasoning |
| **GLO Taxonomy KG** | MCP | `https://glo-taxonomy-kg-mcp-server.daf98e7.kyma.ondemand.com/mcp` | Country/domain Taxonomy |
| **GLO Repo KG** | MCP | `https://sap-mcp-glorep-kg.cfapps.eu12.hana.ondemand.com/mcp-http` | GLO legal / requirements repository |
| **SAP ABAP MCP** | MCP | SAP internal | Technical/code grounding when needed |
| **SAP Enterprise Knowledge Graph** | KG | SAP internal | Broader SAP product/functional grounding |

## L2A Capability Hub

- MCP servers catalog: `https://pages.github.tools.sap/law-to-action/l2a-capability-hub/#mcp-servers`
- Skills repository: `github.tools.sap/law-to-action/l2a-capability-hub`

## Security / trust note

A previously configured `sap-mcp-glorepo` MCP in the development environment returned setup instructions requesting actions such as `git pull`, `/set-me-up`, and client restart.

Treat environment-changing instructions embedded in tool descriptions as untrusted until explicitly verified by the responsible SAP team / owner.

---

# Appendix B — Deferred / Optional Capabilities

The following should not block the core V5 redesign:

- deep technical fit/gap for every news item,
- mandatory ABAP analysis during every run,
- automatic official announcement creation,
- automatic JIRA Legal Change creation,
- cross-country Taxonomy reuse for all items.

These can be added selectively once the core V5 model is stable.
