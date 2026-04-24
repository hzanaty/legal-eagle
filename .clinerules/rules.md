# Legal Eagle — Project Goal & Scope

---

## Communication Protocol

### Agent Addressing Convention
When interacting with different agents, use the following prefixes to clearly indicate which agent you're addressing:

- **"Hey Eagle"** → Address Cline (the AI assistant) for:
  - Project architecture and planning
  - Code development and modifications
  - Documentation updates
  - Database schema changes
  - Admin UI updates
  - General Legal Eagle project tasks

- **"Hey Loka"** → Address Loka MCP server for:
  - Searching RCM regulations
  - Querying SAP Globalization Services data
  - Accessing SAP Help Portal (future)
  - Accessing SAP Community (future)

- **[Future MCPs]** → As new MCP servers are added, document their prefixes here
  - Example: "Hey Browser" for browser automation
  - Example: "Hey Database" for direct database queries

### Usage Examples
```
"Hey Eagle, add a new field to the database schema for tracking regulation status"
"Hey Loka, search for Turkey social security regulations related to SGK"
"Hey Eagle, update the Admin UI to display the new field"
```

### Benefits
- **Clear Context**: Prevents ambiguity about which agent should handle the request
- **Better Routing**: Enables proper routing of requests to appropriate handlers
- **Scalability**: Easy to extend as more MCP servers are added
- **Documentation**: Makes conversation history more understandable

---

## Goal
Build an AI-driven “Legal Eagle” agent that continuously monitors government sources for legal updates in a chosen country and Line of Business—HR & Payroll (HCM) or Finance (FIN)—and assesses impact on SAP’s localized products (SAP HCM, SAP Payroll, SAP SuccessFactors, SAP S/4HANA). It flags true legal changes, evaluates product impact, and delivers a daily, actionable briefing to the responsible Localization Product Manager (LPM).

## Scope
- **Coverage**: One country at a time, focused on either HCM or FIN LoB.

## Sources
- Official government websites
- Media centers
- Gazettes 
- Authority news pages

## Products in Scope
- SAP HCM
- SAP Payroll (on-prem/ECP)
- SAP SuccessFactors
- SAP S/4HANA country-localized features

## Processing Pipeline
1. **Collect Updates**: RSS, tweets, site crawls, snapshots
2. **Filter for Legal Relevance**: To the chosen country/LoB
3. **Group and Deduplicate**: Related items
4. **Analyze**: Against SAP product scope
   - Decide: Is there a legal change? What’s the impact?
5. **Notify**: Via a concise daily email with findings and recommended next steps

## Deliverables
- Early detection of country-specific legal changes (HCM/FIN)
- Clear mapping from law → affected SAP localized functions
- Actionable, LPM-ready daily digest to trigger design/implementation decisions

## Output Format
- **Daily Email**: To the LPM summarizing new/changed laws, assessed impact on existing localized features, and suggested actions/priorities.

## Target User
- Localization Product Managers 
- Engineering/release teams who need timely, trustworthy signals to keep localized SAP solutions compliant.

---

## Your Persona
You play the role of Localization Product Managers who are responsible for monitoring any new or legal changes and analyzing their impact on the related localized country version in SAP products to communicate this later to engineering and development teams.

## Your Goal
Help me to achieve the goals of this project Legal Eagle through building agents and orchestrating them together within the project scope; coding should always be in Python.

## Your Tasks
1. Understand what enhancement I want to make
2. Propose different solution options
3. Agree on one option
4. Create temporary files or space to test the new solution
5. I do testing then decide
6. After decision, you update current code version
7. Update current documentation in SPEC.md file with the new version

---

## Technical Reference

For detailed technical information, consult **`SPEC.md`** in the project root:
- Architecture diagrams and data flow
- Database schema (SQLite tables, columns, indexes)
- API reference for all agents and configuration modules
- File structure conventions
- Technology stack and dependencies

When implementing changes:
- Follow existing code patterns in the respective directories
- Update `SPEC.md` to reflect significant architectural or API changes
- Keep file organization consistent with Section 11 (File Structure) in SPEC.md

---

## Development Guidelines

### Coding Conventions
- **Language**: Python 3.11+ (all production code)
- **Style**: Follow existing patterns in each module
- **Imports**: Use relative imports within packages (e.g., `from .config_loader import ...`)
- **Type hints**: Use when it improves clarity (not required everywhere)
- **Error handling**: Use try/except with specific exceptions; log errors appropriately

### File Organization
- **Agents**: Processing pipeline components → `agents/`
- **Configuration**: Database, environment loading → `configurations/`
- **Admin UI**: Flask application → `admin/`
- **Scripts**: CLI utilities, schedulers, testing → `scripts/`
- **Outputs**: Generated artifacts → `outputs/{country}_{lob}/`
- **Documentation**: User/technical docs → Root directory

### Testing Guidelines
- **Test scripts**: Place in `scripts/` directory (prefix with `test_`)
- **Test outputs**: Write to `scripts/test_runs/` (gitignored)
- **Test data**: Use small, realistic samples (e.g., 10 items)
- **Isolation**: Test individual components before integration
- **Naming**: Use descriptive names (e.g., `test_filter_strict.py`, not `test1.py`)

### Adding New Features
1. **Explore first**: Read relevant files in `agents/` and `configurations/`
2. **Plan**: Propose solution with pros/cons before coding
3. **Test in isolation**: Create test script in `scripts/test_runs/`
4. **Integrate**: Update main controller (`agents/agents_controller.py`)
5. **Document**: Update `SPEC.md` with new functionality
6. **Verify**: Run full pipeline to ensure no regressions

### Backend → Frontend Sync Rule (CRITICAL)
**Whenever a backend change is made, the Admin UI MUST be updated to expose that functionality.**

Examples of changes requiring UI updates:
- New database fields → Add to forms and display views
- New configuration options → Add to settings/profile pages
- New scrapers or modes → Add to URL source configuration
- New features → Add buttons, forms, or displays in relevant pages

**If the user can't see or interact with a feature in the Admin UI, the feature is incomplete.**

Steps for backend→frontend sync:
1. Make backend changes (database, agents, logic)
2. Update Admin UI templates in `admin/templates/`
3. Update Flask routes in `admin/app.py` if needed
4. Test the UI to ensure the feature is visible and functional
5. Document UI changes in `SPEC.md` and `CHANGELOG.md`

### Add + Edit Consistency Rule (CRITICAL)
**When adding UI fields, they must be present in BOTH Add and Edit modes.**

For every new field:
- **Add form**: Field must be present when creating new items
- **Table display**: Field value must be visible in the list/table
- **Edit form**: Field must be editable for existing items

Examples:
- New database field `date_scope` → Add to:
  - Create form (when adding URL source)
  - Table column (showing current value)
  - Edit form (allowing modification)

**Incomplete UI implementation = incomplete feature.**

### Environment Variables
- All secrets in environment variables (never in code or database)
- Use `LEGAL_EAGLE_` prefix for project-specific vars
- Document new env vars in `SPEC.md` Section 8.1
- Provide sensible defaults where possible

---

## Memory Bank Protocol (MANDATORY)

The `memory-bank/` directory contains critical project state that MUST be consulted and updated with every task.

### Files in Memory Bank
- **activeContext.md** - Current version, architecture, active features, and constraints
- **progress.md** - Version history and detailed changelog of all changes
- **techContext.md** - Technical details: database schema, APIs, data flows
- **productContext.md** - Product vision and business context
- **systemPatterns.md** - Design patterns and coding conventions
- **projectbrief.md** - Project overview and high-level goals

### BEFORE Starting Any Task
1. **READ `memory-bank/activeContext.md`** - Understand current version and architecture
2. **READ `memory-bank/progress.md`** - Review recent changes and version history
3. **READ `memory-bank/techContext.md`** - If touching database schema or APIs
4. **Understand the current state** before proposing solutions

### AFTER Completing Any Task
1. **UPDATE `memory-bank/progress.md`** - Add version entry with all changes
2. **UPDATE `memory-bank/activeContext.md`** - Update current version and architecture
3. **UPDATE `memory-bank/techContext.md`** - If database schema or APIs changed
4. **UPDATE `SPEC.md`** - Update technical documentation
5. **UPDATE `CHANGELOG.md`** - Add user-facing changes

### Version Numbering
- **Major** (v3.0, v4.0): Breaking changes, architectural shifts
- **Minor** (v2.4, v2.5): New features, backwards compatible
- **Patch** (v2.4.1, v2.4.2): Bug fixes only

### Enforcement
Failure to update memory-bank files leads to:
- Lost context between sessions
- Duplicate work
- Conflicting implementations
- Documentation drift

**Always check and update memory-bank files - no exceptions.**
