# Flying Legal Eagle — Autonomous LPM Agent

## 1. Brand Architecture

### Legal Eagle

**Legal Eagle** is the legal monitoring tool and capability platform.

Today, it is a standalone application composed of internal modules such as:

- Source collection
- Compare
- Glossary Match
- Rank
- Grouping
- RCM preparation
- Review and reporting

Its role is to monitor the legal environment, process incoming news, and turn raw source material into structured legal-change signals.

### Flying Legal Eagle

**Flying Legal Eagle** is the future autonomous LPM Agent.

It uses Legal Eagle together with other enterprise capabilities such as:

- Legal Eagle MCP
- JIRA MCP
- Taxonomy MCP
- Legal Repository MCP
- Other relevant enterprise tools and services

Its role is not only to monitor, but to decide what deserves attention, investigate further when needed, and report what the LPM should care about.

> **Legal Eagle watches. Flying Legal Eagle acts.**

---

## 2. Evolution Path

### Today — Legal Eagle as a Tool

Legal Eagle is a standalone tool composed of internal modules.

The modules execute defined parts of the monitoring pipeline, for example:

- RSS / URL collection
- Compare
- Glossary Match
- Rank
- Group
- RCM preparation

These are internal modules, not autonomous agents.

### Next — Legal Eagle as an MCP Server

Legal Eagle evolves into an **MCP server**.

Selected Legal Eagle capabilities are exposed through MCP tools, while the existing internal modules remain underneath.

Examples of future MCP tools could include:

- `run_monitoring`
- `get_profile_config`
- `list_sources`
- `get_latest_results`
- `compare_news`
- `match_glossary`
- `rank_news`
- `get_announcements`
- `prepare_rcm`

The principle is:

> **Expose Legal Eagle capabilities through MCP tools, reusing the existing modules underneath.**

Not every internal module has to be exposed one-to-one.

### Then — Flying Legal Eagle

Flying Legal Eagle becomes the autonomous layer above Legal Eagle.

It can use Legal Eagle together with other MCPs and decide which capability to call, in what sequence, and whether further investigation is required.

---

## 3. Flying Legal Eagle Definition

Flying Legal Eagle should contain more than a persona.

### Persona

Defines who the agent is supposed to be.

Example:

- Experienced SAP Localization Product Manager
- Understands legal-change monitoring
- Understands localization scope
- Thinks in terms of compliance, product impact, evidence, urgency, and prioritization

### Goals

Defines what the agent is trying to achieve.

Example:

- Keep the LPM informed about meaningful legal developments
- Reduce manual monitoring effort
- Investigate important signals before escalating them
- Avoid creating unnecessary work from weak or duplicate signals

### Operating Rules

Defines how the agent must behave.

Examples:

- Prefer authoritative evidence over assumptions
- Distinguish Signal, Watch, Legal Change, and Urgent Legal Change
- Do not treat repeated news automatically as a new legal change
- Investigate before escalating
- Stay within the assigned country and LoB scope
- Do not update enterprise systems unless explicitly allowed

### Decision Principles

Defines how the agent applies LPM judgment.

Examples:

- What is worth escalating
- When a weak signal becomes worth watching
- How much evidence is needed before calling something a Legal Change
- How urgency should affect prioritization
- When to check historical JIRA or legal repository context

### Tool Permissions

Defines what the agent is technically allowed to do.

Initial recommendation:

- Legal Eagle MCP — read + run
- JIRA MCP — read only
- Taxonomy MCP — read
- Legal Repository MCP — read
- Email / reporting — allowed
- Enterprise write actions — approval required

### State / Memory

The agent should retain lightweight operational state such as:

- Last successful run
- Items already reported
- Pending items still being watched
- Previous decisions
- Country / LoB context

This prevents the agent from repeatedly reporting the same information.

---

## 4. Standalone Operating Model

Flying Legal Eagle can run as a scheduled service, for example on SAP BTP.

The scheduler acts as the agent's alarm clock.

Every morning:

**Wake → Inspect → Reason → Investigate → Report → Sleep**

Example daily cycle:

1. Scheduler wakes Flying Legal Eagle.
2. Agent loads its persona, goals, rules, and state.
3. Agent calls Legal Eagle MCP to inspect new monitoring results.
4. Agent reviews new Signals, Watches, Legal Changes, and urgent items.
5. If needed, it calls JIRA, Taxonomy, or Legal Repository MCPs for additional context.
6. Agent decides what actually deserves LPM attention.
7. Agent prepares a concise briefing.
8. Agent sends the update.
9. Agent stores what it already reviewed or reported.
10. Agent goes idle until the next scheduled run.

---

## 5. Example Agent Reasoning Flow

A possible autonomous cycle:

1. Check Turkey HCM Legal Eagle results since the previous run.
2. Ignore clear Noise.
3. Review Signal and Watch items.
4. Identify one possible Legal Change related to social insurance.
5. Query Legal Eagle history for similar announcements.
6. Query JIRA to check whether an LC already exists.
7. If the topic already exists in Analysis, report the new development against the existing work rather than presenting it as a new requirement.
8. If the effective date is near, elevate the importance of the briefing.
9. Send only the information that requires LPM attention.

This is where the system becomes genuinely agentic: the agent decides what to do next and which capability to invoke.

---

## 6. Architecture

```text
                    Scheduler
                        |
                        v
               Flying Legal Eagle
                  Autonomous LPM Agent
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
   Legal Eagle MCP    JIRA MCP    Taxonomy MCP
          |                             |
          v                             v
   Legal Eagle Core              SAP / Product Context
          |
          +-----------------------------+
                        |
                        v
                Legal Repository MCP
                        |
                        v
               Agent Decision / Briefing
                        |
                        v
                  Email / Teams / UI
                        |
                        v
                       LPM
```

---

## 7. Human vs Agent Interaction

The Legal Eagle UI remains primarily for humans.

The MCP interface becomes primarily for agents.

### Human

Uses:

- Admin UI
- Review UI
- Configuration screens
- RCM preview

### Agent

Uses:

- Structured MCP tools
- Structured data responses
- Explicit permissions
- Persistent state

Browser automation such as Playwright should be a fallback only when a required capability is not exposed through MCP or API.

Preferred hierarchy:

1. MCP / API
2. Safe structured service access
3. Browser / Playwright / computer-use fallback

---

## 8. Core Positioning

The distinction between the two brands is simple:

### Legal Eagle

**Legal monitoring capability**

It watches sources, compares news, performs glossary matching, ranks items, groups announcements, and prepares structured legal-change content.

### Flying Legal Eagle

**Autonomous LPM Agent**

It uses Legal Eagle and other enterprise tools, applies LPM judgment, decides what matters, investigates further, and reports what action may be required.

> **Legal Eagle watches. Flying Legal Eagle acts.**
