# Legal Eagle — UI5/Fiori Migration Roadmap

**Version:** 1.0  
**Last Updated:** 2026-04-24  
**Status:** Planned

This document outlines the strategic plan for migrating Legal Eagle's Admin UI from Flask/Jinja2 templates to a modern SAPUI5/Fiori application.

---

## Table of Contents

1. [Overview & Objectives](#1-overview--objectives)
2. [MCP Server Configuration](#2-mcp-server-configuration)
3. [Architecture Changes](#3-architecture-changes)
4. [Implementation Phases](#4-implementation-phases)
5. [Technical Requirements](#5-technical-requirements)
6. [REST API Conversion Guide](#6-rest-api-conversion-guide)
7. [Page Migration Details](#7-page-migration-details)
8. [Testing Strategy](#8-testing-strategy)
9. [Deployment Considerations](#9-deployment-considerations)
10. [Migration Checklist](#10-migration-checklist)
11. [Alternative Approach](#11-alternative-approach-full-ui5--cap-backend)
12. [Summary](#12-summary)

---

## 1. Overview & Objectives

### Current State (v2.12)

- Flask backend with Jinja2 templates
- Custom CSS using SAP Fiori design tokens
- Visual Fiori styling (colors, spacing, typography)
- **NOT** using actual SAPUI5 components

### Target State (Future)

- Flask backend serving REST API
- SAPUI5 frontend application
- True Fiori UX with UI5 controls
- Modern SAP user experience

### Migration Approach: Hybrid Architecture (Recommended)

- Keep Flask backend (Python logic intact)
- Replace HTML templates with UI5 views
- Flask serves UI5 app as static files
- Gradual, page-by-page migration

### Why Hybrid?

- ✅ Minimal backend changes
- ✅ Reuse existing Python agents
- ✅ Lower risk, faster delivery
- ✅ Incremental testing possible
- ❌ Not a "pure" UI5 app (acceptable tradeoff)

---

## 2. MCP Server Configuration

To leverage AI assistance during migration, configure these MCP servers:

### Primary: UI5 MCP Server

**Purpose**: UI5 expertise and best practices

**Repository**: https://github.com/UI5/mcp-server

**Installation**:
```bash
npm install -g @ui5/mcp-server
```

**Configuration** (add to Cline MCP settings):
```json
{
  "mcpServers": {
    "ui5-mcp": {
      "command": "npx",
      "args": ["@ui5/mcp-server"]
    }
  }
}
```

**Capabilities**:
- UI5 component documentation
- Best practice guidance
- Code generation assistance
- Pattern recommendations

### Secondary: SAPUI5 MCP Server

**Purpose**: SAPUI5 API Reference documentation

**Repository**: https://github.tools.sap/PIRIN/sapui5-mcp-server

**Installation**:
```bash
git clone https://github.tools.sap/PIRIN/sapui5-mcp-server.git
cd sapui5-mcp-server
npm install
```

**Configuration**:
```json
{
  "mcpServers": {
    "sapui5-api": {
      "command": "node",
      "args": ["/path/to/sapui5-mcp-server/index.js"]
    }
  }
}
```

**Capabilities**:
- Control API reference
- Property/event/aggregation lookup
- Code examples
- Type information

### Optional: Fiori Elements Brain MCP Server

**Purpose**: Fiori Elements patterns (if using Object Page, List Report, etc.)

**Repository**: https://github.tools.sap/MCP-LABS/fiori-element-brain-mcp-stdio

**Note**: Likely overkill for Legal Eagle admin UI, but useful if adopting Fiori Elements patterns.

### Additional Resources

**SAP MCP Server Registry**
- **Repository**: https://github.tools.sap/frontrunners/sap-mcp-server-list
- **Section**: SAPUI5 & Frontend (https://github.tools.sap/frontrunners/sap-mcp-server-list#sapui5--frontend)
- **Purpose**: Comprehensive registry of all available SAP MCP servers
- **Use Cases**: 
  - Browse complete list of UI5-related MCP servers
  - Discover additional tools for UI5 development
  - Check for new MCP servers added after this roadmap was created
  - Find specialized MCP servers for specific UI5 use cases

**Note**: The registry is actively maintained and may contain additional MCP servers beyond those documented in this roadmap. Check it periodically for updates.

---

## 3. Architecture Changes

### Before (Current):

```
┌─────────────────────────────────────────────────┐
│              Flask Application                   │
│  ┌───────────────────────────────────────────┐  │
│  │   Routes (GET /admin/profiles/<id>)       │  │
│  │          ↓                                 │  │
│  │   Business Logic (Python)                 │  │
│  │          ↓                                 │  │
│  │   Jinja2 Templates (HTML + Custom CSS)    │  │
│  │          ↓                                 │  │
│  │   HTTP Response (HTML page)               │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### After (Hybrid):

```
┌─────────────────────────────────────────────────┐
│              Flask Application                   │
│  ┌───────────────────────────────────────────┐  │
│  │   REST API Routes                          │  │
│  │   GET /api/profiles/<id>  → JSON          │  │
│  │   POST /api/profiles/<id>/run → JSON      │  │
│  │          ↓                                 │  │
│  │   Business Logic (Python)                 │  │
│  │   (Agents, DB operations)                 │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │   Static File Serving                      │  │
│  │   GET /ui5/* → UI5 app files              │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│           SAPUI5 Application                     │
│  ┌───────────────────────────────────────────┐  │
│  │   Component.js (App bootstrap)            │  │
│  │   manifest.json (App descriptor)          │  │
│  │          ↓                                 │  │
│  │   Router (Client-side navigation)         │  │
│  │          ↓                                 │  │
│  │   Views (XML) + Controllers (JS)          │  │
│  │   - Dashboard.view.xml                    │  │
│  │   - Profile.view.xml                      │  │
│  │   - Run.view.xml                          │  │
│  │   - Review.view.xml                       │  │
│  │          ↓                                 │  │
│  │   UI5 Controls (sap.m.*, sap.uxap.*)     │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**Key Changes**:
1. Flask routes return JSON instead of HTML
2. UI5 app makes AJAX calls to Flask REST API
3. Flask serves UI5 app from `/admin/ui5/` directory
4. Client-side routing (no page reloads)

---

## 4. Implementation Phases

### Phase 1: Setup & Infrastructure (Week 1)

**Tasks**:
1. Install MCP servers (UI5 MCP, SAPUI5 MCP)
2. Create UI5 app structure in `/admin/ui5/`
3. Set up UI5 tooling (ui5.yaml, package.json)
4. Create Flask REST API endpoints (parallel to existing routes)
5. Test REST API with Postman/curl

**Deliverables**:
- `/admin/ui5/` directory with UI5 skeleton
- Flask routes returning JSON (e.g., `/api/profiles`)
- MCP servers configured and tested

**File Structure**:
```
admin/
├── app.py                    # Flask app (add /api/* routes)
├── ui5/                      # NEW: UI5 application
│   ├── Component.js          # App component
│   ├── manifest.json         # App descriptor
│   ├── index.html            # Entry point
│   ├── view/                 # XML views
│   │   ├── App.view.xml
│   │   ├── Dashboard.view.xml
│   │   ├── Profile.view.xml
│   │   ├── Run.view.xml
│   │   └── Review.view.xml
│   ├── controller/           # JavaScript controllers
│   │   ├── App.controller.js
│   │   ├── Dashboard.controller.js
│   │   ├── Profile.controller.js
│   │   ├── Run.controller.js
│   │   └── Review.controller.js
│   ├── model/                # Data models
│   │   └── formatter.js
│   ├── fragment/             # Reusable fragments
│   │   ├── AddRSSDialog.fragment.xml
│   │   ├── AddURLDialog.fragment.xml
│   │   └── MessageStrip.fragment.xml
│   └── css/                  # Custom CSS (if needed)
│       └── style.css
└── templates/                # Keep for backward compatibility
    └── ...
```

---

### Phase 2: Core UI5 Application (Week 2)

**Tasks**:
1. Create Component.js and manifest.json
2. Set up routing (Shell.controller.js)
3. Build base layout (Shell bar, navigation)
4. Create reusable fragments (Dialogs, MessageStrip)
5. Implement data models (JSON models for profiles, etc.)

**Deliverables**:
- Working UI5 app with navigation
- Shell bar with profile switcher
- Routing between pages
- Reusable dialog fragments

**Component.js Example**:
```javascript
sap.ui.define([
    "sap/ui/core/UIComponent",
    "sap/ui/model/json/JSONModel"
], function (UIComponent, JSONModel) {
    "use strict";

    return UIComponent.extend("com.sap.legaleagle.Component", {
        metadata: {
            manifest: "json"
        },

        init: function () {
            // Call parent init
            UIComponent.prototype.init.apply(this, arguments);

            // Create router
            this.getRouter().initialize();

            // Set global models
            var oAppModel = new JSONModel({
                busy: false,
                layout: "OneColumn"
            });
            this.setModel(oAppModel, "appView");
        }
    });
});
```

**manifest.json Example**:
```json
{
  "sap.app": {
    "id": "com.sap.legaleagle",
    "type": "application",
    "title": "Legal Eagle - Compliance Management",
    "description": "SAP Localization Compliance Monitoring",
    "applicationVersion": {
      "version": "2.12.0"
    }
  },
  "sap.ui": {
    "technology": "UI5",
    "deviceTypes": {
      "desktop": true,
      "tablet": true,
      "phone": true
    }
  },
  "sap.ui5": {
    "rootView": {
      "viewName": "com.sap.legaleagle.view.App",
      "type": "XML",
      "id": "app"
    },
    "dependencies": {
      "minUI5Version": "1.120.0",
      "libs": {
        "sap.ui.core": {},
        "sap.m": {},
        "sap.uxap": {},
        "sap.ui.layout": {}
      }
    },
    "models": {
      "i18n": {
        "type": "sap.ui.model.resource.ResourceModel",
        "settings": {
          "bundleName": "com.sap.legaleagle.i18n.i18n"
        }
      }
    },
    "routing": {
      "config": {
        "routerClass": "sap.m.routing.Router",
        "viewType": "XML",
        "viewPath": "com.sap.legaleagle.view",
        "controlId": "app",
        "controlAggregation": "pages",
        "transition": "slide"
      },
      "routes": [
        {
          "pattern": "",
          "name": "dashboard",
          "target": "dashboard"
        },
        {
          "pattern": "profile/{profileId}",
          "name": "profile",
          "target": "profile"
        },
        {
          "pattern": "profile/{profileId}/run",
          "name": "run",
          "target": "run"
        },
        {
          "pattern": "profile/{profileId}/review",
          "name": "review",
          "target": "review"
        }
      ],
      "targets": {
        "dashboard": {
          "viewName": "Dashboard",
          "viewLevel": 1
        },
        "profile": {
          "viewName": "Profile",
          "viewLevel": 2
        },
        "run": {
          "viewName": "Run",
          "viewLevel": 2
        },
        "review": {
          "viewName": "Review",
          "viewLevel": 2
        }
      }
    }
  }
}
```

---

### Phase 3: Page-by-Page Migration (Weeks 3-4)

**Dashboard Page**:
- Convert to `sap.m.Table` with profile list
- Add create profile button
- Status badges (Active/Inactive)
- Click to navigate to profile details

**Profile Page (Configure Tab)**:
- Convert to `sap.uxap.ObjectPageLayout`
- Sections: Language, Schedule, Twitter, RSS, URL Sources, Email, Monitor, Glossary
- Each section uses `sap.m.Table` for lists
- Inline editing with dialogs

**Run Page**:
- Convert to `sap.m.SplitContainer`
- Left pane: Run history list
- Right pane: Live logs with SSE
- Run/Cancel buttons

**Review Page**:
- Convert to `sap.m.Table` with filtered news
- Score slider for each item
- Approve/Reject buttons
- Pagination support

**Deliverables**:
- All 4 pages migrated to UI5
- Full functionality preserved
- Responsive design

---

### Phase 4: Polish & Testing (Week 5)

**Tasks**:
1. Add loading indicators (`sap.m.BusyIndicator`)
2. Implement error handling (MessageToast, MessageBox)
3. Add keyboard shortcuts
4. Optimize performance (lazy loading, caching)
5. Cross-browser testing
6. Mobile responsiveness testing
7. Accessibility (ARIA labels, keyboard navigation)

**Deliverables**:
- Production-ready UI5 app
- Test report
- Performance metrics
- Deployment guide

---

## 5. Technical Requirements

### Dependencies

**UI5 SDK**:
```json
{
  "dependencies": {
    "@sapui5/types": "^1.120.0",
    "@ui5/cli": "^3.0.0"
  }
}
```

**Development Tools**:
- Node.js 18+ (for UI5 tooling)
- npm or yarn
- VS Code with UI5 extensions

**Build Configuration** (`ui5.yaml`):
```yaml
specVersion: "3.0"
metadata:
  name: com.sap.legaleagle
type: application
framework:
  name: SAPUI5
  version: "1.120.0"
  libraries:
    - name: sap.m
    - name: sap.ui.core
    - name: sap.uxap
    - name: sap.ui.layout
```

---

## 6. REST API Conversion Guide

### Flask Route Transformation

**Before** (HTML response):
```python
@app.route("/admin/profiles/<int:profile_id>")
def admin_profile_detail(profile_id: int):
    profile = resolve_profile_by_id(profile_id)
    rss_feeds = load_rss_feeds(profile_id)
    return render_template("profile.html", profile=profile, rss_feeds=rss_feeds)
```

**After** (JSON response):
```python
@app.route("/api/profiles/<int:profile_id>")
def api_get_profile(profile_id: int):
    profile = resolve_profile_by_id(profile_id)
    rss_feeds = load_rss_feeds(profile_id)
    tweet_accounts = load_tweet_accounts(profile_id)
    url_sources = load_url_sources(profile_id)
    email_receivers = load_email_receivers_with_lang(profile_id)
    glossary = load_glossary(profile_id)
    
    return jsonify({
        "profile": profile,
        "sources": {
            "rss_feeds": rss_feeds,
            "tweet_accounts": tweet_accounts,
            "url_sources": url_sources
        },
        "email_receivers": email_receivers,
        "glossary": glossary
    })
```

### API Endpoint Mapping

| Current Route | New API Endpoint | Method | Description |
|--------------|------------------|--------|-------------|
| `GET /admin/` | `GET /api/profiles` | GET | List all profiles |
| `GET /admin/profiles/<id>` | `GET /api/profiles/<id>` | GET | Get profile details |
| `POST /admin/profiles/<id>/rss/add` | `POST /api/profiles/<id>/rss` | POST | Add RSS feed |
| `POST /admin/profiles/<id>/rss/delete` | `DELETE /api/profiles/<id>/rss/<feed_id>` | DELETE | Delete RSS feed |
| `POST /admin/profiles/<id>/run/start` | `POST /api/profiles/<id>/runs` | POST | Start execution |
| `GET /admin/profiles/<id>/run/<run_id>/logs` | `GET /api/runs/<run_id>/logs` | GET | Stream logs (SSE) |

### JSON Response Formats

**Profile List**:
```json
{
  "profiles": [
    {
      "id": 1,
      "country_code": "SA",
      "lob": "HCM",
      "name": "Saudi Arabia HCM",
      "active": 1,
      "language": "en",
      "created_at": "2026-01-15T10:30:00Z"
    }
  ]
}
```

**Profile Details**:
```json
{
  "profile": {
    "id": 1,
    "country_code": "SA",
    "lob": "HCM",
    "active": 1,
    "language": "en"
  },
  "sources": {
    "rss_feeds": [
      {"id": 1, "url": "https://example.com/rss", "max_lookback_days": 7}
    ],
    "tweet_accounts": [
      {"id": 1, "handle": "example", "max_lookback_days": 7}
    ],
    "url_sources": [
      {"id": 1, "url": "https://example.com", "mode": "auto"}
    ]
  },
  "email_receivers": [
    {"id": 1, "email": "user@example.com", "translation_lang": "en"}
  ],
  "glossary": ["term1", "term2"]
}
```

---

## 7. Page Migration Details

### Dashboard → sap.m.Table

**UI5 Controls**:
- `sap.m.Page` (container)
- `sap.m.Table` (profile list)
- `sap.m.ColumnListItem` (rows)
- `sap.m.ObjectStatus` (Active/Inactive badge)
- `sap.m.Button` (Create Profile)

**Key Features**:
- Sortable columns
- Search filter
- Click row to navigate
- Create button in header

---

### Profile → sap.uxap.ObjectPageLayout

**UI5 Controls**:
- `sap.uxap.ObjectPageLayout` (container)
- `sap.uxap.ObjectPageHeader` (profile title)
- `sap.uxap.ObjectPageSection` (each configuration section)
- `sap.m.Table` (for lists: RSS, Twitter, URL Sources, etc.)
- `sap.m.Dialog` (for add/edit forms)

**Sections**:
1. Language Settings
2. Schedule Configuration
3. Twitter Accounts
4. RSS Feeds
5. URL Sources
6. Email Receivers
7. Monitor Updates
8. Glossary Terms

---

### Run → sap.m.SplitContainer

**UI5 Controls**:
- `sap.m.SplitContainer` (two-pane layout)
- `sap.m.List` (run history, left pane)
- `sap.m.CustomListItem` (run entries)
- `sap.m.TextArea` (logs display, right pane)
- `sap.m.Button` (Run, Cancel)

**Key Features**:
- Live log streaming via EventSource (SSE)
- Auto-scroll to bottom
- Run status indicators
- Metrics display (items collected, filtered, etc.)

---

### Review → sap.m.Table

**UI5 Controls**:
- `sap.m.Page` (container)
- `sap.m.Table` (filtered news items)
- `sap.m.Slider` (relevance score)
- `sap.m.Button` (Approve, Reject)
- `sap.m.Toolbar` (filters, pagination)

**Key Features**:
- Score adjustment per item
- Bulk approve/reject
- Pagination (100 items per page)
- Clear all button

---

## 8. Testing Strategy

### Unit Tests (QUnit)

**Controller Tests**:
```javascript
QUnit.test("Dashboard controller loads profiles", function (assert) {
    var oController = new DashboardController();
    var oModel = new JSONModel();
    oController.getView().setModel(oModel);
    
    // Mock API call
    sinon.stub(jQuery, "ajax").returns(Promise.resolve({
        profiles: [{id: 1, country_code: "SA", lob: "HCM"}]
    }));
    
    return oController.onInit().then(function () {
        assert.equal(oModel.getProperty("/profiles").length, 1);
    });
});
```

### Integration Tests

**API Tests** (Postman/Newman):
- Test all REST endpoints
- Verify JSON response formats
- Check error handling
- Test authentication

### E2E Tests (UIVeri5 or Selenium)

**Test Scenarios**:
1. Create new profile
2. Add RSS feed
3. Run profile execution
4. Review filtered news
5. Approve/reject items

---

## 9. Deployment Considerations

### BTP Deployment Changes

**manifest.yaml** (add static file serving):
```yaml
applications:
- name: legal-eagle
  memory: 512M
  buildpacks:
  - python_buildpack
  command: gunicorn admin.app:app
  env:
    FLASK_STATIC_FOLDER: admin/ui5
  routes:
  - route: legal-eagle.cfapps.eu10.hana.ondemand.com
```

**Flask Static Serving**:
```python
# In admin/app.py
@app.route("/ui5/<path:filename>")
def serve_ui5(filename):
    return send_from_directory("ui5", filename)

@app.route("/")
def index():
    return send_from_directory("ui5", "index.html")
```

### Build Process

**Development**:
```bash
cd admin/ui5
npm install
ui5 serve --port 8080
```

**Production**:
```bash
cd admin/ui5
ui5 build --dest ../../dist/ui5
```

---

## 10. Migration Checklist

### Phase 1: Setup (Week 1)

- [ ] Install UI5 MCP Server
- [ ] Install SAPUI5 MCP Server
- [ ] Create `/admin/ui5/` directory structure
- [ ] Set up `ui5.yaml` and `package.json`
- [ ] Create Flask `/api/*` routes (parallel to existing)
- [ ] Test REST API with Postman

### Phase 2: Core App (Week 2)

- [ ] Create `Component.js` and `manifest.json`
- [ ] Implement routing configuration
- [ ] Build shell bar and navigation
- [ ] Create reusable fragments (Dialogs, MessageStrip)
- [ ] Set up data models (JSON models)

### Phase 3: Page Migration (Weeks 3-4)

- [ ] Migrate Dashboard to `sap.m.Table`
- [ ] Migrate Profile to `sap.uxap.ObjectPageLayout`
- [ ] Migrate Run to `sap.m.SplitContainer`
- [ ] Migrate Review to `sap.m.Table`
- [ ] Test all functionality

### Phase 4: Polish (Week 5)

- [ ] Add loading indicators
- [ ] Implement error handling
- [ ] Add keyboard shortcuts
- [ ] Optimize performance
- [ ] Cross-browser testing
- [ ] Mobile responsiveness
- [ ] Accessibility audit
- [ ] Write deployment guide

### Phase 5: Deployment

- [ ] Build UI5 app for production
- [ ] Update BTP manifest.yaml
- [ ] Deploy to BTP
- [ ] Smoke test production
- [ ] Update documentation

---

## 11. Alternative Approach: Full UI5 + CAP Backend

**Note**: This approach is NOT recommended for Legal Eagle due to higher complexity and risk. Documented here for completeness.

### Architecture

- Replace Flask with SAP Cloud Application Programming Model (CAP)
- CDS data models instead of SQLite
- OData services instead of REST API
- UI5 Fiori Elements app (auto-generated from CDS)

### Pros

- Pure SAP stack
- Better BTP integration
- Auto-generated CRUD operations
- Built-in authentication

### Cons

- Complete rewrite required
- Steep learning curve (CAP, CDS, OData)
- Python agents need Node.js integration
- Much longer timeline (3-6 months)
- Higher risk of bugs

### Recommendation

Stick with Hybrid approach (Flask + UI5) unless there's a strategic mandate to move to full SAP stack.

---

## 12. Summary

### Recommended Path

**Hybrid Architecture** (Flask + SAPUI5)

### Timeline

5 weeks for full migration

### Effort Breakdown

- Phase 1 (Setup): 1 week
- Phase 2 (Core App): 1 week
- Phase 3 (Page Migration): 2 weeks
- Phase 4 (Polish): 1 week

### Key Success Factors

1. Use MCP servers for AI-assisted development
2. Migrate incrementally (page by page)
3. Test thoroughly at each phase
4. Keep Flask backend stable
5. Maintain backward compatibility during transition

### When to Start

- After v2.12 is stable and deployed
- When team has capacity for 5-week project
- When MCP servers are configured and tested

### Next Steps

1. Get stakeholder approval for migration
2. Set up development environment with MCP servers
3. Create proof-of-concept (Dashboard page only)
4. Review POC and refine approach
5. Execute full migration plan

---

**Related Documentation:**
- [SPEC.md](SPEC.md) — Current v2.12 technical specification
- [README.md](README.md) — Project overview and user guide
- [CHANGELOG.md](CHANGELOG.md) — Version history

---

*End of UI5/Fiori Migration Roadmap*