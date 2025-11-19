# System Patterns

## System Architecture
The Legal Eagle system is designed around a modular architecture that ensures scalability and ease of maintenance. Agents are employed to parse, analyze, and notify stakeholders on relevant legal changes. A central controller orchestrates these agents to align with business deadlines and objectives.

## Key Technical Decisions
- Adopting a microservices approach with each agent handling specific tasks, ensuring single responsibility and simplicity.
- Utilizing Python for its robust libraries and community for data analysis and AI-driven insights.
- Integrating Google and OpenAI APIs to leverage existing capabilities for email notifications and content analysis.

## Design Patterns in Use
1. **Observer Pattern**: Used to notify stakeholders when significant legal updates are detected.
2. **Factory Pattern**: Employed for dynamically initializing different agents as per the project necessity.
3. **Singleton Pattern**: Maintains a single initialized configuration object across different components of the system to ensure consistency.

## Component Relationships
Each agent within the system operates independently but communicates through defined APIs and shared data structures. The agents_controller coordinates their execution order and maintains an overview of data flows and dependencies within the system's architecture.
