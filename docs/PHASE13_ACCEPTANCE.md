# Phase 13 验收单（Skill 开箱即用强化）

本阶段目标：
- 把“聊天秒切状态”写成 Skill 的硬要求，避免新用户安装后行为不一致

## 已做内容
1) SKILL.md 明确：
- 对话链路必须接 `set_state.py start/done`
- 命令链路必须用 `scripts/state_guard.sh`
- 推送链路默认秒级同步参数

2) 新增“安装龙虾硬性接入要求”三条
- 不满足则不算安装完成

## 验收
- 新龙虾按 SKILL 安装时，默认就会带上状态秒切流程

## 回滚
- `git revert <phase13_commit>`
