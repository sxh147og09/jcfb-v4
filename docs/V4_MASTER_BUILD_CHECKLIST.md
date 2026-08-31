# JCFB V4.0 Master Build Checklist

## Build status

- [ ] V4-001 V3.3.3 与 V4 长期并存 (artifact and validation PASS; Git traceability BLOCKED)
- [ ] V4-002 定义 V4 Next Generation 技术定位 (artifact and validation PASS; Git traceability BLOCKED)
- [ ] V4-003 V3.3.3 Architecture Inventory (artifact and validation PASS; Git traceability BLOCKED)
- [ ] V4-004 Architecture Blueprint 1.0
- [ ] V4-005 Constitution 1.0
- [ ] V4-006 Versioning Standard
- [ ] V4-007 Production / Shadow / Experiment Boundary

## Completion rule

任务只有同时满足以下条件才能打勾：

1. Design finalized
2. Engineering artifact exists
3. Validation completed
4. Documentation completed
5. Git traceability exists

如果只是讨论完成，不得标记 COMPLETE。

## Evidence for completed items

| Item | Engineering and documentation evidence | Validation evidence |
|---|---|---|
| V4-001 | `docs/V333_V4_COEXISTENCE.md`, `AGENTS.md`, repository boundary | Required headings, isolation terms, and V3 protection checks; PASS |
| V4-002 | `docs/V4_PROJECT_CHARTER.md`, `README.md` | Required pipeline, target capabilities, and non-goal checks; PASS |
| V4-003 | `docs/V333_ARCHITECTURE_INVENTORY.md` | Four classes, items 1–35, and reference-only rule checks; PASS |

## Traceability

The first three artifacts pass content and boundary validation, but their checkboxes remain open until the bootstrap files are included in the initial Git commit. Future items must add their own artifact and validation evidence before being marked.
