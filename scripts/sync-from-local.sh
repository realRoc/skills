#!/bin/bash
set -e

# 配置
LOCAL_SKILLS_DIR="$HOME/.claude/skills"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_SKILLS_DIR="$REPO_DIR/skills"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔄 Syncing skills from local to repository...${NC}\n"

# 确保在仓库目录中
cd "$REPO_DIR"

# 检查 Git 状态
if [[ -n $(git status --porcelain) ]]; then
  echo -e "${RED}❌ Working directory is not clean. Please commit or stash changes first.${NC}"
  git status
  exit 1
fi

# 确保在 main 分支
current_branch=$(git branch --show-current)
if [[ "$current_branch" != "main" ]]; then
  echo -e "${YELLOW}⚠️  Not on main branch (current: $current_branch)${NC}"
  read -p "Switch to main branch? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    git checkout main
    git pull origin main
  else
    exit 1
  fi
fi

# 运行检测脚本
source "$REPO_DIR/scripts/detect-changes.sh"

# 处理新增 skills
if [[ ${#NEW_SKILLS[@]} -gt 0 ]]; then
  echo -e "\n${GREEN}📦 Processing new skills...${NC}"

  for skill in "${NEW_SKILLS[@]}"; do
    echo -e "${GREEN}  → Adding: $skill${NC}"
    cp -r "$LOCAL_SKILLS_DIR/$skill" "$REPO_SKILLS_DIR/"
    git add "$REPO_SKILLS_DIR/$skill"
  done

  # 提交新 skills
  git commit -m "Add new skills: ${NEW_SKILLS[*]}

Skills added:
$(for skill in "${NEW_SKILLS[@]}"; do echo "- $skill"; done)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

  echo -e "${GREEN}✓ Committed new skills${NC}"

  # 推送到远程
  echo -e "${BLUE}Pushing to origin/main...${NC}"
  git push origin main
  echo -e "${GREEN}✓ Pushed successfully${NC}"
fi

# 处理修改的 skills
if [[ ${#MODIFIED_SKILLS[@]} -gt 0 ]]; then
  echo -e "\n${YELLOW}📝 Modified skills detected (requires PR):${NC}"

  for skill in "${MODIFIED_SKILLS[@]}"; do
    echo -e "${YELLOW}  • $skill${NC}"

    # 创建分支名
    BRANCH_NAME="update/$skill-$(date +%Y%m%d-%H%M%S)"

    echo -e "    Creating branch: ${BLUE}$BRANCH_NAME${NC}"
    git checkout -b "$BRANCH_NAME"

    # 同步更改
    rsync -av --delete "$LOCAL_SKILLS_DIR/$skill/" "$REPO_SKILLS_DIR/$skill/"

    # 提交更改
    git add "$REPO_SKILLS_DIR/$skill"
    git commit -m "Update skill: $skill

Changes:
$(cd "$LOCAL_SKILLS_DIR/$skill" && find . -type f -name "*.md" -o -name "*.py" -o -name "*.sh" | head -10)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

    # 推送分支
    git push -u origin "$BRANCH_NAME"

    # 提示创建 PR（因为没有 gh CLI）
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}📋 Please create a Pull Request manually:${NC}"
    echo -e "   Repository: ${BLUE}https://github.com/realRoc/skills${NC}"
    echo -e "   Branch: ${GREEN}$BRANCH_NAME${NC}"
    echo -e "   Title: ${BLUE}Update skill: $skill${NC}"
    echo -e "   Base: ${BLUE}main${NC}"
    echo -e ""
    echo -e "   Direct link:"
    echo -e "   ${BLUE}https://github.com/realRoc/skills/compare/main...$BRANCH_NAME${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    # 返回 main 分支
    git checkout main
  done
fi

# 完成
if [[ ${#NEW_SKILLS[@]} -eq 0 ]] && [[ ${#MODIFIED_SKILLS[@]} -eq 0 ]]; then
  echo -e "${GREEN}✅ All skills are up-to-date!${NC}"
else
  echo -e "\n${GREEN}✅ Sync complete!${NC}"
  echo -e "   New skills: ${#NEW_SKILLS[@]} (pushed to main)"
  echo -e "   Modified skills: ${#MODIFIED_SKILLS[@]} (branches created, PRs needed)"
fi
