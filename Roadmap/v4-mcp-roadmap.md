# Legal Eagle V4 Roadmap — MCP Server

## Status
**Planning — October 2026**

V4 makes Legal Eagle consumable.

Today Legal Eagle is a standalone Flask application. Only its admin UI user can interact with it.

V4 exposes Legal Eagle's capabilities as an **MCP server**, so that LPM colleagues and autonomous agents can use Legal Eagle as a tool — from Claude Desktop, SAP Joule Work Desktop, or any MCP-compatible client.

> V4 does not change what Legal Eagle does. It changes who can use it.

---

## 1. Design Principle

**Wrap, don't rewrite.**

Every MCP tool delegates to an existing module or API endpoint inside Legal Eagle.

No internal pipeline changes. No intelligence changes. Those are V5.

The MCP layer is a thin, structured interface on top of what already works.

---

## 2. Who Uses V4

### LPM Colleagues (primary consumer)

A colleague who does not have access to the Legal Eagle admin UI — or simply prefers their Claude/Joule environment — should be able to:

- ask Legal Eagle to run a monitoring cycle for their country/LoB,
- get the latest results,
- review ranked items,
- see announcements ready for RCM.

All from within their existing AI assistant, without opening the Legal Eagle UI.

### Flying Legal Eagle (autonomous agent layer)

The autonomous LPM agent defined in `Flying_Legal_Eagle_Autonomous_LPM_Agent.md` cannot exist without an MCP interface.

V4 is the prerequisite for Flying Legal Eagle.

---

## 3. Proposed MCP Tools

These map directly to existing Legal Eagle functionality.

| Tool | What it does | Existing module |
|---|---|---|
| `get_profiles` | List available monitoring profiles (country/LoB) | `config_loader.py` |
| `get_profile_config` | Return sources, settings, and scope for a profile | `config_loader.py` |
| `run_monitoring` | Trigger a full monitoring run for a profile | `agents_controller.py` |
| `get_run_status` | Return status and log of a run in progress or completed | `runs` table + log |
| `get_latest_results` | Return ranked items from the most recent run for a profile | `news_items` table |
| `get_announcements` | Return grouped announcements ready for LPM review | `news_announcements` table |
| `compare_news` | Check whether a news item has been seen before | `compare_news.py` |
| `match_glossary` | Apply glossary matching to an item or text | `glossary_match.py` |
| `rank_item` | Return the deterministic rank for an item | `news_ranker.py` |
| `prepare_rcm` | Return the RCM payload for an announcement | `announcement_agent.py` |
| `list_sources` | List configured RSS feeds, URL sources, and Twitter handles for a profile | DB tables |

Not every tool needs to be built in the first iteration. A working V4 can start with `get_profiles`, `run_monitoring`, `get_run_status`, and `get_latest_results`.

---

## 4. Transport and Deployment

### Option A — stdio (local)
- Runs as a local process.
- Works with Claude Desktop via MCP config.
- No additional server infrastructure.
- Easiest to build first.

### Option B — SSE over HTTP (hosted)
- Runs alongside the existing Flask app on BTP.
- Accessible by colleagues without local setup.
- Works with Joule Work Desktop and remote Claude configurations.
- Requires auth (admin secret or OAuth token).

**Recommendation:** Build stdio first for local Claude Desktop testing. Add SSE transport for BTP deployment in the same iteration.

---

## 5. Auth

Consistent with existing patterns in `admin/app.py`:

- Admin secret via `Authorization: Bearer <secret>` header or query param.
- For hosted deployment: OAuth2 token from SAP Identity Provider.

MCP tools should reject requests without a valid credential.

---

## 6. Consumer Setup

### Claude Desktop

```json
{
  "mcpServers": {
    "legal-eagle": {
      "command": "python",
      "args": ["/path/to/legal-eagle/mcp_server.py"],
      "env": {
        "LEGAL_EAGLE_ADMIN_SECRET": "..."
      }
    }
  }
}
```

### SAP Joule Work Desktop

MCP support in Joule Work Desktop should be verified before implementation starts.

If SSE transport is supported, the hosted BTP endpoint can be registered directly.

---

## 7. Implementation Scope

### What V4 builds

- `mcp_server.py` — MCP server entry point (stdio transport)
- Tool handlers delegating to existing modules/DB
- Optional: SSE wrapper for hosted deployment
- Optional: `scripts/legal_eagle_mcp.json` — Claude Desktop config template

### What V4 does NOT build

- No changes to pipeline logic
- No new agents
- No UI changes
- No new database tables (read-only access to existing data)
- No intelligence improvements (V5)

---

## 8. What V4 Unlocks

Once V4 ships:

- Colleagues on Claude/Joule can run Legal Eagle and review results without the admin UI.
- Flying Legal Eagle (autonomous LPM agent) becomes buildable — it needs exactly the MCP tools defined here.
- V5 intelligence improvements are exposed through the same MCP interface automatically as they ship.

---

## 9. Success Criteria

V4 is complete when a colleague can, from Claude Desktop or Joule:

1. Call `get_profiles` and see their country/LoB profile.
2. Call `run_monitoring` and wait for results.
3. Call `get_latest_results` and review ranked items.
4. Call `get_announcements` and see what is ready for RCM action.

Without opening the Legal Eagle admin UI.

---

## 10. V4 → V5 → Flying Legal Eagle Sequence

```text
V3.x  Current — standalone Flask app, admin UI only
  │
  ▼
V4    MCP Server — expose capabilities via MCP tools
  │   colleagues + Claude/Joule + Flying Legal Eagle prerequisite
  │
  ▼
V5    Intelligence — Legal Event model, Context Resolver 2.0,
  │   SAP Impact Assessment, Classification/Priority
  │   (see v5-roadmap.md)
  │
  ▼
Flying Legal Eagle — autonomous LPM agent
      uses Legal Eagle MCP + JIRA MCP + Taxonomy MCP + SAP KGs
      (see Flying_Legal_Eagle_Autonomous_LPM_Agent.md)
```
