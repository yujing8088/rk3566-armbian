#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 把整套移植文件推到 GitHub，并可顺手触发云端编译
#
# 准备：在 https://github.com/settings/tokens 生成 token
#   - Classic token：勾选 repo + workflow
#   - Fine-grained token：目标仓库的 Contents=Read/Write、Administration=Read/Write、
#     Actions=Read/Write（新建仓库还需要 account 级 Administration 权限）
#
# 用法：
#   GITHUB_TOKEN=ghp_xxx ./tools/push-to-github.sh <用户名> <仓库名> [private|public]
#
# 例：
#   GITHUB_TOKEN=ghp_xxx ./tools/push-to-github.sh zhang rk3566-armbian private
# ---------------------------------------------------------------------------
set -euo pipefail

OWNER="${1:-}"
REPO="${2:-rk3566-armbian}"
VISIBILITY="${3:-private}"
: "${GITHUB_TOKEN:?请先设置环境变量 GITHUB_TOKEN}"
[[ -n "${OWNER}" ]] || { echo "用法: GITHUB_TOKEN=xxx $0 <用户名> [仓库名] [private|public]" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="https://api.github.com"
AUTH=(-H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json")

echo "==> 校验 token"
LOGIN=$(curl -fsS "${AUTH[@]}" "$API/user" | python3 -c 'import json,sys;print(json.load(sys.stdin)["login"])') || {
	echo "!! token 无效或缺少权限" >&2; exit 1; }
echo "    登录账号: ${LOGIN}"

echo "==> 确认仓库 ${OWNER}/${REPO}"
if curl -fsS "${AUTH[@]}" "$API/repos/${OWNER}/${REPO}" >/dev/null 2>&1; then
	echo "    已存在，直接使用"
else
	echo "    不存在，创建中..."
	PRIVATE=false; [[ "${VISIBILITY}" == "private" ]] && PRIVATE=true
	curl -fsS -X POST "${AUTH[@]}" "$API/user/repos" \
		-d "{\"name\":\"${REPO}\",\"private\":${PRIVATE},\"description\":\"Armbian for RK3566 EVB2 LP4X V10\",\"has_issues\":false,\"has_wiki\":false}" >/dev/null
	echo "    创建完成"
fi

cd "${HERE}"
[[ -d .git ]] || { echo "!! ${HERE} 不是 git 仓库" >&2; exit 1; }

echo "==> 推送代码"
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${OWNER}/${REPO}.git"
# 用一次性 URL 推送，避免 token 被写进 .git/config
git push "https://x-access-token:${GITHUB_TOKEN}@github.com/${OWNER}/${REPO}.git" HEAD:main --force

echo "==> 触发云端编译（workflow_dispatch）"
if curl -fsS -X POST "${AUTH[@]}" \
	"$API/repos/${OWNER}/${REPO}/actions/workflows/build-armbian.yml/dispatches" \
	-d '{"ref":"main","inputs":{"release":"bookworm","branch":"current","minimal":true}}' >/dev/null 2>&1; then
	echo "    已触发"
else
	echo "    触发失败（token 可能缺 workflow 权限），到网页上点一次 Run workflow 即可"
fi

cat <<EOF

完成：
  仓库   https://github.com/${OWNER}/${REPO}
  构建   https://github.com/${OWNER}/${REPO}/actions
  约 40~90 分钟后在 Run 页面底部下载 artifact（含 .img 和 .img.xz）
EOF
