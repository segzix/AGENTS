# AGEMTS.md

This file contains the full workflow rules and orchestrator protocol for this project.

<!-- 中文注释：本文件是完整规则，精简版见 AGENTS.md。 -->

## Core Principles

- Understand the relevant project structure and code before making changes.
- Make the smallest correct change that satisfies the task.
- Do not modify unrelated files.
- Do not revert or overwrite changes made by the user or another agent.
- Do not read, print, copy, summarize, or modify real secrets, tokens, passwords, private keys, or `.env*` files unless explicitly requested.
- Do not run destructive commands such as `rm -rf`, `sudo`, `git reset --hard`, `git clean -fd`, `chmod -R`, or `chown -R`.
- Do not run `git push` or `git commit` unless explicitly requested.
- Inspect `git diff` after editing.
- Final responses for code changes must include changed files, reasons, verification, and remaining risks.

## Workflow Summary

| Workflow | Name | Chinese note | Best used for | Role sequence |
|---|---|---|---|---|
| A | Read-Only Analysis | 只读分析；用于理解结构、调用链、根因，不改代码。 | Understanding project structure, call chains, root causes, or design without editing files. | `planner` |
| B | Plan First, Then Wait | 先出方案再等确认；用于高风险、不明确或影响较大的改动。 | Risky, unclear, or high-impact tasks that need approval before implementation. | `planner` -> stop |
| C | Implement With Review | 常规实现并审查；用于普通功能开发或 bug 修复。 | Normal feature implementation or bug fixes. | `planner` -> `coder` -> `reviewer` |
| D | Debug and Fix | 先定位再修复；用于报错、失败命令、测试失败或运行时异常。 | Errors, failed commands, test failures, API failures, or runtime exceptions. | `debugger` -> `planner` -> `coder` -> `reviewer` |
| E | Review Only | 只做审查不修改；用于检查 diff、指定文件或提交前代码质量。 | Reviewing current diff, selected files, or provided code without editing. | `reviewer` |
| F | Research Then Plan | 先查资料再规划；用于需要外部文档、API 行为或兼容性判断。 | External documentation, API behavior, framework usage, or compatibility research. | `researcher` -> `planner` -> stop |
| G | Refactor Safely | 安全重构；用于整理结构但必须保持现有行为不变。 | Refactoring while preserving existing behavior. | `planner` -> `coder` -> `debugger` -> `reviewer` |
| H | Add Tests | 补充测试；用于为功能、修复或边界行为添加/改进测试。 | Adding or improving tests for features, fixes, or edge cases. | `planner` -> `coder` -> `debugger` -> `reviewer` |
| I | Local Bridge / Provider Debugging | 本地桥接/模型供应商排错；用于 OpenCode、uvicorn bridge、路由、key、base URL、streaming 问题。 | OpenCode, uvicorn bridge, provider routing, API keys, base URLs, SSL, or streaming issues. | `debugger` -> `planner` -> `coder` -> `reviewer` |
| J | Quick Small Change | 快速小改；用于非常小、低风险且目标明确的修改。 | Very small, low-risk, clearly scoped changes. | `coder` -> `reviewer` |

## Workflow Selection

- If the user explicitly names a workflow, follow that workflow.
- Use Workflow A for explanation-only or read-only analysis.
- Use Workflow B for unclear, risky, or high-impact work.
- Use Workflow C for normal implementation tasks.
- Use Workflow D for errors, failed commands, failing tests, and runtime exceptions.
- Use Workflow E for review-only requests.
- Use Workflow F when external documentation or compatibility research is needed.
- Use Workflow I for OpenCode, bridge, provider, model routing, or streaming issues.
- Use Workflow J for very small, low-risk changes; switch to Workflow C if the scope grows.

## Role Responsibilities

- `planner`: Analyze relevant files, identify root causes or design issues, and produce a minimal plan. Do not edit files.
- `coder`: Implement the smallest necessary change, preserve style, and run focused verification.
- `debugger`: Reproduce or localize failures, inspect the minimal relevant path, propose fixes, and verify them.
- `reviewer`: Review `git diff` for correctness, security, compatibility, regression risk, and unintended changes. Do not edit files.
- `researcher`: Check documentation, API behavior, external references, and compatibility. Do not edit files.

## Orchestrator Mode

When the user provides a step plan file, the orchestrator executes multiple workflows in sequence and passes phase summaries through files to avoid long conversation context.

<!-- 中文注释：orchestrator 只读取计划文件中的 Workflow 字母和 Task，不要求每一步手写 agent 调用顺序。 -->

### Step Plan Format

A step plan only needs to declare the workflow and task for each step:

```markdown
## Step 1: Research & Plan
- **Workflow**: F
- **Task**: Research the relevant approach and produce an implementation plan without modifying project files.

## Step 2: Implement
- **Workflow**: C
- **Task**: Read Step 1 context, implement the minimal change, and review the result.
```

Do not write the `planner`, `coder`, `debugger`, `reviewer`, or `researcher` sequence in the plan file. The orchestrator derives the role sequence from the workflow letter.

### Context File Convention

- All phase summaries are written under `/tmp/opencode/`.
- Step N writes `/tmp/opencode/context_step_N.md`.
- Step N+1 reads `/tmp/opencode/context_step_N.md` before starting.
- Multi-role steps may use `/tmp/opencode/context_step_N_role_{role_name}.md` as temporary micro-context.
- The final run summary is written to `/tmp/opencode/context_final.md`.

<!-- 中文注释：用文件传递 summary，避免把完整长上下文传给下一轮 agent。 -->

### Orchestrator Execution Loop

1. Read the user-provided step plan file.
2. Parse each step's `Workflow` and `Task`.
3. Read the previous step context, skipping this for Step 1.
4. Resolve the workflow letter into a role sequence.
5. Map each role to an available subagent.
6. Execute each role and write role-level micro-context when needed.
7. Write `context_step_N.md` when the current step completes.
8. Stop and report to the user if any step fails.

### Workflow To Subagent Mapping

| Workflow | Roles | Subagent calls |
|---|---|---|
| A | `planner` | `general` |
| B | `planner` -> stop | `general`, then stop for confirmation |
| C | `planner` -> `coder` -> `reviewer` | `general` -> `general` -> `reviewer` |
| D | `debugger` -> `planner` -> `coder` -> `reviewer` | `debugger` -> `general` -> `general` -> `reviewer` |
| E | `reviewer` | `reviewer` |
| F | `researcher` -> `planner` -> stop | `researcher` -> `general`, then stop for confirmation |
| G | `planner` -> `coder` -> `debugger` -> `reviewer` | `general` -> `general` -> `debugger` -> `reviewer` |
| H | `planner` -> `coder` -> `debugger` -> `reviewer` | `general` -> `general` -> `debugger` -> `reviewer` |
| I | `debugger` -> `planner` -> `coder` -> `reviewer` | `debugger` -> `general` -> `general` -> `reviewer` |
| J | `coder` -> `reviewer` | `general` -> `reviewer` |

## MCP Tool Rules

- Use available MCP tools automatically when a task needs to read, extract, or inspect supported special files.
- For PDFs, use `pdf-tools` and save safe derived text under `docs_extracted/`; do not modify the original PDF.
- For extracted text previews, use `pdf-tools/read_text_preview`.
- For images, use available image tools to extract information; do not modify the original image.
- Ask the user first if a tool may modify source files, delete files, call external services, or perform costly operations.

## File Editing Rules

- Make the smallest correct change.
- Preserve the existing structure, naming conventions, and code style.
- Do not introduce unrelated refactors.
- Do not silently remove existing behavior.
- Do not modify generated files unless the task explicitly requires it or synchronization is necessary.
- Explain what will be changed before editing.
- Inspect the diff after editing.

## Debugging Rules

When debugging a failure, check in this order:

1. Reproduce the error.
2. Identify the failing command, endpoint, file, or function.
3. Inspect the minimal relevant code path.
4. Check environment variable and configuration names without exposing values.
5. Check request paths, model names, base URLs, schemas, streaming behavior, and response parsing.
6. Propose the smallest fix.
7. Verify the fix with a focused command.

## Final Response Requirements

For completed code changes, the final response must include:

- Files changed.
- Why they were changed.
- Verification performed.
- Remaining risks or manual checks.
