# Configuration — Draft for S8 Rewrite

S8 should generate the final table from actual settings and `.env.example` rather than maintaining stale prose.

Minimum groups:
- runtime profile (`APP_PROFILE`, `MODEL_RUNTIME`);
- bind/port/worker settings;
- remote model URL/token on review hosts;
- inference device;
- model/cache paths;
- workspace/state paths;
- CVAT URL/project/token configuration;
- logging and security-sensitive settings.

For every variable document:
- purpose;
- profile(s) that use it;
- default;
- required/optional;
- secret? yes/no;
- example safe value;
- restart required? yes/no.

Never print real tokens in docs, screenshots, tests, or logs.
