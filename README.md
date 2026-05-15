# realRoc/skills

个人 skills 仓库,用于 Claude Code 和其他 AI 编程助手。

## 快速安装

使用 [skills.sh](https://skills.sh) 生态系统一键安装所有 skills:

```bash
npx skills add realRoc/skills
```

## 包含的 Skills

| Skill | 描述 |
|-------|------|
| **backend-api-documenter** | 自动生成 FastAPI 后端 API 文档(AGENTS.md 格式) |
| **agents-md-generator** | 从现有文档生成完整的 AGENTS.md 规范文档 |
| **prd** | 生成产品需求文档(PRD) |
| **ralph** | 将 PRD 转换为 Ralph 自主代理的 JSON 格式 |
| **shumei-user-violation-audit** | 基于 MongoDB 用户和对话数据调用数美 input event, 输出按用户违禁率排序的 CSV |
| **newapi-usage-stats** | 通过 Tencent Cloud TAT 连入后端容器,查询 NewAPI MySQL 的 `logs` 表,产出指定时间窗内各模型的 RPM/TPM、峰值分钟与平均 tokens/请求 |

## 安装选项

### 安装所有 skills

```bash
# 全局安装(~/.claude/skills/)
npx skills add realRoc/skills -g

# 项目级安装(./.claude/skills/)
npx skills add realRoc/skills
```

### 安装特定 skill

```bash
npx skills add realRoc/skills --skill backend-api-documenter
npx skills add realRoc/skills --skill prd --skill ralph
```

### 指定 agent

```bash
# 只安装到 Claude Code
npx skills add realRoc/skills -a claude-code

# 安装到多个 agents
npx skills add realRoc/skills -a claude-code -a cursor
```

## 更新 Skills

```bash
# 检查更新
npx skills check

# 更新所有 skills 到最新版本
npx skills update
```

## 卸载

```bash
# 交互式卸载
npx skills remove

# 卸载特定 skill
npx skills remove backend-api-documenter
```

## 本地开发

### 同步本地 skills 到仓库

```bash
# 克隆仓库
git clone https://github.com/realRoc/skills.git
cd skills

# 同步本地更改
./scripts/sync-from-local.sh
```

脚本会自动:
- ✅ 检测新增的 skills → 直接推送到 main
- ✅ 检测修改的 skills → 创建 PR 分支并提示手动创建 PR
- ✅ 忽略未修改的 skills

### 手动创建 Skill

```bash
# 在本地创建新 skill
mkdir -p ~/.claude/skills/my-new-skill
npx skills init ~/.claude/skills/my-new-skill

# 编辑 SKILL.md
code ~/.claude/skills/my-new-skill/SKILL.md

# 同步到仓库
cd /path/to/realRoc-skills
./scripts/sync-from-local.sh
```

## 支持的 Agents

- Claude Code
- Cursor
- GitHub Copilot
- OpenCode
- Cline
- [35+ 其他 agents](https://skills.sh)

## 许可证

MIT

## 贡献

欢迎提交 Pull Request!请确保:
1. SKILL.md 包含有效的 YAML frontmatter(name + description)
2. 遵循现有 skills 的结构和风格
3. 添加适当的文档和示例
