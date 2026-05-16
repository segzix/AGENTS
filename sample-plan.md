# Workflow Plan: Build User API Service

<!-- 中文注释：这是给 AGEMTS.md 中 orchestrator mode 使用的步骤计划文件。 -->

Pass this file path to the orchestrator when you want OpenCode to execute the whole workflow plan automatically.

Example invocation:

```text
Use orchestrator mode from AGEMTS.md with plan: sample-plan.md
```

## Global Rules

- Context directory: `/tmp/opencode/`
- Do not commit or push unless explicitly requested.
- Stop on the first failed step.
- Each step must write `/tmp/opencode/context_step_N.md`.
- The final report must be written to `/tmp/opencode/context_final.md`.

<!-- 中文注释：每一步只写 Workflow 字母和 Task，Task 可以用中文或英文；具体 agent 顺序由 AGEMTS.md 映射表决定。 -->

---

## Step 1: Research And Plan

- **Workflow**: F
- **Task**: 调研 FastAPI 与 async SQLAlchemy 的推荐项目结构和最佳实践，输出实现计划，覆盖目录结构、数据模型、API 端点和验证策略。不要修改项目文件。

## Step 2: Implement Core Code

- **Workflow**: C
- **Task**: 读取 `/tmp/opencode/context_step_1.md`，然后用最小正确改动实现 User model、CRUD API 端点和数据库初始化配置，并审查最终 diff。

## Step 3: Add Tests

- **Workflow**: H
- **Task**: 读取 `/tmp/opencode/context_step_2.md`，为用户创建、用户查询和错误处理补充聚焦的 pytest 测试，运行相关测试，并在需要时修复失败。

## Step 4: Final Review

- **Workflow**: E
- **Task**: 读取所有前序步骤的 context 文件，审查最终 diff 的正确性、安全性、一致性和回归风险，并将最终报告写入 `/tmp/opencode/context_final.md`。

---

## Step Dependencies

```text
Step 1 (research) -> Step 2 (implement) -> Step 3 (test) -> Step 4 (review)
```

<!-- 中文注释：下一步只读取上一步 summary，避免长上下文持续累积。 -->
