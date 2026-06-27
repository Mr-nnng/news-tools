# Detail Page Block Structure

每个 `page-detail` 块包含 1~2 个 repo-block。以下是一个完整的示例：

```html
<!-- PAGE N: #rank repo-name + #rank repo-name -->
<div class="page page-detail">
    <div class="repo-block">
        <div class="repo-number">#1</div>
        <div class="repo-header">
            <div class="repo-avatar"><img src="{{REPO_AVATAR_URL}}" alt="{{REPO_AUTHOR}}" loading="lazy"></div>
            <div class="repo-name">{{REPO_NAME}}<span class="author-name">{{REPO_AUTHOR}}</span></div>
        </div>
        <div class="repo-metrics">
            <div class="repo-metric"><span class="lang-dot" style="background:{{LANG_DOT_COLOR}}"></span><span class="lbl">{{LANG_NAME}}</span></div>
            <div class="repo-metric"><span class="val">{{STARS_COUNT}}</span><span class="lbl">Star</span></div>
            <div class="repo-metric"><span class="val" style="color:var(--near-black)">{{DAILY_STARS}}</span><span class="lbl">今日</span></div>
            <div class="repo-metric"><span class="val">{{FORKS_COUNT}}</span><span class="lbl">Fork</span></div>
        </div>
        <div class="repo-desc">{{REPO_DESC}}</div>
        <ul class="repo-features">
            <li>{{FEATURE_1}}</li>
            <li>{{FEATURE_2}}</li>
            <li>{{FEATURE_3}}</li>
        </ul>
        <div class="repo-audience"><strong>推荐：</strong>{{AUDIENCE}}</div>
        <div class="repo-url"><a href="{{REPO_URL}}" target="_blank">{{REPO_URL}}</a></div>
    </div>
    {{REPO_DIVIDER_OR_CLOSE}}
```

## 字段说明

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `{{REPO_RANK}}` | 排名编号，格式 `#N` | `#1` |
| `{{REPO_AVATAR_URL}}` | 作者头像 URL | `https://github.com/affaan-m.png` |
| `{{REPO_AUTHOR}}` | 作者 GitHub 用户名 | `affaan-m` |
| `{{REPO_NAME}}` | 仓库名称 | `ECC` |
| `{{LANG_DOT_COLOR}}` | 语言圆点颜色 hex | `#F1E05A` |
| `{{LANG_NAME}}` | 编程语言 | `JavaScript` |
| `{{STARS_COUNT}}` | 总 Star 数（格式化） | `199,730` |
| `{{DAILY_STARS}}` | 本周新增 Star | `+10,802` |
| `{{FORKS_COUNT}}` | Fork 数 | `30,661` |
| `{{REPO_DESC}}` | 仓库简介 | `Agent 性能优化系统` |
| `{{FEATURE_1..3}}` | 特点列表项 | `Skills / Instincts / Memory 一体化` |
| `{{AUDIENCE}}` | 推荐受众 | `AI 代理开发者` |
| `{{REPO_URL}}` | GitHub 仓库链接 | `https://github.com/affaan-m/ECC` |
| `{{PAGE_NUM}}` | 页码 | `02 / 11` |

## 重复规则

- 每页放 2 个 repo-block，中间用 `<hr class="divider">` 分隔
- 最后一个 repo-block 不需要 divider
- 页码的 `PAGE_NUM` 替换为 `{当前页} / {总页数}`
