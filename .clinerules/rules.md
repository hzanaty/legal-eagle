# Legal Eagle — Project Goal & Scope

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

### Environment Variables
- All secrets in environment variables (never in code or database)
- Use `LEGAL_EAGLE_` prefix for project-specific vars
- Document new env vars in `SPEC.md` Section 8.1
- Provide sensible defaults where possible
