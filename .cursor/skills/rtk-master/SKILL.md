---
name: rtk-master
description: >-
  Guides work on the bundled rtk (Rust Token Killer) repo: token-saving CLI proxy,
  Rust conventions, tests, and Claude-packaged workflows. Use when the user works
  under `.claude/skills/rtk-master/`, mentions rtk/rtk-master, Rust Token Killer,
  CLI filter modules, or RTK triage/TDD/performance tasks.
---

# RTK 主仓库（工作区捆绑）

## 资源位置

- **主目录**（开发与检索用）：`.claude/skills/rtk-master/`
- **压缩包**（分发/备份）：`.claude/skills/rtk-master.zip` — 内容应与上述目录一致；若仅有 zip，解压到 `.claude/skills/rtk-master/` 后再操作。

## 项目是什么

**rtk（Rust Token Killer）**：高性能 CLI 代理，通过过滤、压缩、截断、去重等降低终端输出 token；常见命令可省 60–90% token。本仓库含若干面向 Agent 的规则与子技能。

**易混项目**：`rtk-ai/rtk`（本项目）与 `reachingforthejack/rtk`（Rust Type Kit）不同。验证：`rtk --version` 与 `rtk gain` 应可用。

## 何时读哪些文件

| 场景 | 优先阅读 |
|------|----------|
| 整体目标、构建与测试命令 | `.claude/skills/rtk-master/CLAUDE.md` |
| 架构与模块扩展 | `.claude/skills/rtk-master/docs/contributing/ARCHITECTURE.md` |
| Rust 风格与禁止项 | `.claude/skills/rtk-master/.claude/rules/rust-patterns.md` |
| 测试与性能目标 | `.claude/skills/rtk-master/.claude/rules/cli-testing.md` |
| Cursor 侧 Hook（需 `jq`、`rtk >= 0.23`） | `.claude/skills/rtk-master/hooks/cursor/README.md` |

## 子技能（按需 `Read`）

路径均相对于仓库根目录；在 **smart_insole** 工作区下为：

- `.claude/skills/rtk-master/.claude/skills/code-simplifier/SKILL.md` — Rust 惯用法简化
- `.claude/skills/rtk-master/.claude/skills/design-patterns/SKILL.md` — RTK 侧设计模式
- `.claude/skills/rtk-master/.claude/skills/performance/SKILL.md` — 启动时间、体积、正则等
- `.claude/skills/rtk-master/.claude/skills/rtk-tdd/SKILL.md` — TDD 与测试习惯
- `.claude/skills/rtk-master/.claude/skills/tdd-rust/SKILL.md` — 过滤器开发 TDD
- `.claude/skills/rtk-master/.claude/skills/issue-triage/SKILL.md` — Issue 分拣
- `.claude/skills/rtk-master/.claude/skills/pr-triage/SKILL.md` — PR 分拣与评审草稿
- `.claude/skills/rtk-master/.claude/skills/rtk-triage/SKILL.md` — 综合 triage（issue + PR）

## 开发时的默认命令习惯

在已安装 `rtk` 的前提下，终端类输出优先用 `rtk` 包装以降低上下文体积，例如：

- `rtk cargo build`、`rtk cargo test`、`rtk cargo clippy --all-targets`
- 需要完整输出或绕过过滤：`rtk proxy <command>`

## Windows 安装兼容提示（PowerShell）

如果用户在 Windows PowerShell 执行了 `... | sh` 并报错“`sh` 无法识别”，应按下列方式处理：

1. 原因：`install.sh` 是 POSIX shell 脚本，默认 PowerShell 环境没有 `sh`（通常只有 Git Bash/WSL 才有）。
2. 首选安装（跨平台、最稳）：`cargo install --git https://github.com/rtk-ai/rtk`
3. 如必须跑脚本安装：在 Git Bash 或 WSL 中执行 `curl ... | sh`，不要在纯 PowerShell 里执行。
4. 安装后强制校验：`rtk --version` 与 `rtk gain`（防止装到同名错误包）。

改 Rust 后提交前建议跑：`cargo fmt --all && cargo clippy --all-targets && cargo test --all`（与 `CLAUDE.md` 一致）。

## 指令摘要

1. 任务落在 **rtk 源码或文档** 上时，先 `Read` `CLAUDE.md` 再改代码。
2. **专项工作流**（triage、TDD、性能）打开上表对应 `SKILL.md`，不要凭通用 Rust 经验替代仓库约定。
3. **Cursor Hook** 相关只信 `hooks/cursor/` 下说明；与 Claude Code 的 JSON 字段名不同。
