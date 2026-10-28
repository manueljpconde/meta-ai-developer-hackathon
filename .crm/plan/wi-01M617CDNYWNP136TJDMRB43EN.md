Add the reviewed design proposal to main unchanged, one file only.

```yaml crm-plan
phase: integration
writer: integrator
assessors: [business, qa, code_review]
budget_usd: 3
pool: null
route_overrides: {}
config_version: 8
scope:
  - docs/proposals/**
criteria:
  - "Add `docs/proposals/2026-10-27-agentimo-hackathon-design.md` to `main`, byte for byte as it is on `crew-readiness`, for example with `git checkout origin/crew-readiness -- docs/proposals/2026-10-27-agentimo-hackathon-design.md`."
  - "Change nothing else. In particular, `docs/crew-readiness.md` on `crew-readiness` belongs to the readiness exercise and must not reach `main`."
  - "Do not edit the proposal. The owner's decisions on it are recorded in the comments of PR #4 and stay there."
proof:
  - "python3 -c \"import hashlib,sys; h=hashlib.sha256(open('docs/proposals/2026-10-27-agentimo-hackathon-design.md','rb').read()).hexdigest(); print(h); sys.exit(h!='faddbf3f7b5bbcefe79112cee67187ebe3e116dc14d54418c2b27385de8cd561')\""
target_branch: main
```
