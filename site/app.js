/* ==================================================================
   News Tools · SPA 运行时
   路由、数据加载、渲染器、交互
   ================================================================== */

(function () {
  'use strict';

  // ══════════════════════════════════════════════════════════════
  // 配置
  // ══════════════════════════════════════════════════════════════

  var CONFIG = {
    dataRoot: 'data',
  };

  // ══════════════════════════════════════════════════════════════
  // 工具函数
  // ══════════════════════════════════════════════════════════════

  function formatDate(rd) {
    var parts = rd.split('-');
    if (parts.length === 3 && parts[0].length === 4) {
      return parts[0] + '年' + parseInt(parts[1], 10) + '月' + parseInt(parts[2], 10) + '日';
    }
    return rd;
  }

  function getMonthKey(rd) {
    var parts = rd.split('-');
    if (parts.length >= 2 && parts[0].length === 4) {
      return parts[0] + '年' + String(parseInt(parts[1], 10)).padStart(2, '0') + '月';
    }
    return '未知';
  }

  function monthSortKey(mk) {
    var m = mk.match(/(\d{4})年(\d{2})月/);
    if (m) return parseInt(m[1]) * 100 + parseInt(m[2]);
    return 0;
  }

  function fmtShort(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  function fmtComma(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function fmtWeekly(n) {
    return '+' + fmtComma(n);
  }

  function escapeHtml(s) {
    if (!s) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(s));
    return div.innerHTML;
  }

  function updateMeta(title, description) {
    document.title = title || 'News Tools';
    var desc = description || 'GitHub Trending 中文周报 · 华尔街见闻要闻 & 新闻联播文字摘要';
    var metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute('content', desc);
    var ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.setAttribute('content', title || 'News Tools');
    var ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.setAttribute('content', desc);
    var twitterTitle = document.querySelector('meta[name="twitter:title"]');
    if (twitterTitle) twitterTitle.setAttribute('content', title || 'News Tools');
    var twitterDesc = document.querySelector('meta[name="twitter:description"]');
    if (twitterDesc) twitterDesc.setAttribute('content', desc);
  }

  // ══════════════════════════════════════════════════════════════
  // 数据加载器
  // ══════════════════════════════════════════════════════════════

  var dataCache = {};

  function loadJSON(url) {
    if (dataCache[url]) return Promise.resolve(dataCache[url]);
    return fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status + ' ' + res.statusText);
        return res.json();
      })
      .then(function (data) {
        dataCache[url] = data;
        return data;
      });
  }

  // ══════════════════════════════════════════════════════════════
  // 渲染器
  // ══════════════════════════════════════════════════════════════

  var APP = document.getElementById('app');

  // ── 着陆页 ──────────────────────────────────────────────

  function renderLanding(data) {
    updateMeta('News Tools · GitHub Trending 周报 & 华尔街见闻 & 新闻联播');

    APP.className = '';
    APP.innerHTML =
      '<main class="page">\n' +
      renderHero(data) +
      renderTabBar() +
      renderGHPanel(data.gh) +
      renderXWLBPanel(data.xwlb) +
      renderWallstreetPanel(data.wallstreet) +
      renderFooter(false) +
      '\n</main>';

    // 初始化交互
    initTabSwitching();
    initMonthToggle('.tab-panel .month-toggle');
  }

  function renderHero(data) {
    var ghCount = data.gh ? data.gh.count : 0;
    var xwlbCount = data.xwlb ? data.xwlb.count : 0;
    var wsCount = data.wallstreet ? data.wallstreet.count : 0;
    return [
      '<header class="hero">',
      '  <div class="eyebrow">',
      '    <span>News Tools · <a class="version-link" href="https://github.com/Mr-nnng/news-tools">v2.0</a></span>',
      '    <span class="hero-links">',
      '      <a href="https://github.com/Mr-nnng/news-tools" target="_blank" rel="noopener">GitHub</a>',
      '    </span>',
      '  </div>',
      '  <h1>News Tools</h1>',
      '  <p class="tagline">GitHub Trending 周报 · 新闻联播 · 华尔街见闻</p>',
      '  <div class="hero-tokens">',
      '    <span><b>' + ghCount + '</b> 期 GitHub 周报</span>',
      '    <span><b>' + xwlbCount + '</b> 天新闻联播</span>',
      '    <span><b>' + wsCount + '</b> 天华尔街见闻</span>',
      '    <span><b>自动生成</b></span>',
      '    <span><b>中文摘要</b></span>',
      '  </div>',
      '  <div class="hero-cta">',
      '    <a class="btn-ghost" href="https://github.com/Mr-nnng/news-tools">GitHub 仓库</a>',
      '  </div>',
      '</header>',
    ].join('\n');
  }

  function renderTabBar() {
    return [
      '<div class="tab-bar" role="tablist">',
      '  <button class="tab-btn is-active" data-tab="github" role="tab"><span class="tab-icon">📂</span>GitHub 周报</button>',
      '  <button class="tab-btn" data-tab="xwlb" role="tab"><span class="tab-icon">📺</span>新闻联播</button>',
      '  <button class="tab-btn" data-tab="wallstreet" role="tab"><span class="tab-icon">💹</span>华尔街见闻</button>',
      '</div>',
    ].join('\n');
  }

  function renderWallstreetPanel(ws) {
    var monthsHtml = '';
    if (ws && ws.months) {
      var sorted = ws.months.slice().sort(function (a, b) {
        return monthSortKey(b.label) - monthSortKey(a.label);
      });
      sorted.forEach(function (m) {
        var cards = m.items
          .map(function (item) {
            return [
              '    <a href="#/wallstreet/' + item.date + '" class="report-card">',
              '      <p class="card-date">' + formatDate(item.date) + '</p>',
              '      <p class="card-meta">' + item.count + ' 个栏目</p>',
              '      <p class="card-desc">' + escapeHtml(item.summary) + '</p>',
              '    </a>',
            ].join('\n');
          })
          .join('\n');
        monthsHtml += [
          '  <div class="month-group">',
          '    <div class="month-toggle">',
          '      <span class="month-arrow">▾</span>',
          '      <span class="month-label">' + m.label + '</span>',
          '    </div>',
          '    <div class="report-grid">',
          cards,
          '    </div>',
          '  </div>',
        ].join('\n');
      });
    }
    return [
      '<section id="tab-wallstreet" class="tab-panel" role="tabpanel">',
      '  <div class="section-head">',
      '    <p class="section-num">03 · 华尔街见闻</p>',
      '    <h2 class="section-title">华尔街见闻要闻</h2>',
      '    <p class="section-lede">每日三档：华尔街见闻早餐 · 早间要闻汇总 · 美股盘前，捕捉全球市场重要动态。</p>',
      '  </div>',
      '  <div class="timeline">',
      monthsHtml,
      '  </div>',
      '</section>',
    ].join('\n');
  }

  function renderGHPanel(gh) {
    var monthsHtml = '';
    if (gh && gh.months) {
      var sorted = gh.months.slice().sort(function (a, b) {
        return monthSortKey(b.label) - monthSortKey(a.label);
      });
      sorted.forEach(function (m) {
        var cards = m.items
          .map(function (item) {
            return [
              '    <a href="#/github/' + item.date + '" class="report-card">',
              '      <p class="card-date">' + formatDate(item.date) + '</p>',
              '      <p class="card-meta">' + item.count + ' 个项目</p>',
              '      <p class="card-desc">' + escapeHtml(item.summary) + '</p>',
              '    </a>',
            ].join('\n');
          })
          .join('\n');
        monthsHtml += [
          '  <div class="month-group">',
          '    <div class="month-toggle">',
          '      <span class="month-arrow">▾</span>',
          '      <span class="month-label">' + m.label + '</span>',
          '    </div>',
          '    <div class="report-grid">',
          cards,
          '    </div>',
          '  </div>',
        ].join('\n');
      });
    }
    return [
      '<section id="tab-github" class="tab-panel is-active" role="tabpanel">',
      '  <div class="section-head">',
      '    <p class="section-num">01 · GitHub Trending</p>',
      '    <h2 class="section-title">GitHub 周报</h2>',
      '    <p class="section-lede">每周自动生成的中文开源趋势报告，涵盖 AI、安全、开发工具等领域的最热开源项目。</p>',
      '  </div>',
      '  <div class="timeline">',
      monthsHtml,
      '  </div>',
      '</section>',
    ].join('\n');
  }

  function renderXWLBPanel(xwlb) {
    var monthsHtml = '';
    if (xwlb && xwlb.months) {
      var sorted = xwlb.months.slice().sort(function (a, b) {
        return monthSortKey(b.label) - monthSortKey(a.label);
      });
      sorted.forEach(function (m) {
        var cards = m.items
          .map(function (item) {
            return [
              '    <a href="#/xwlb/' + item.date + '" class="report-card">',
              '      <p class="card-date">' + formatDate(item.date) + '</p>',
              '      <p class="card-meta">' + item.count + ' 条新闻</p>',
              '      <p class="card-desc">' + escapeHtml(item.summary) + '</p>',
              '    </a>',
            ].join('\n');
          })
          .join('\n');
        monthsHtml += [
          '  <div class="month-group">',
          '    <div class="month-toggle">',
          '      <span class="month-arrow">▾</span>',
          '      <span class="month-label">' + m.label + '</span>',
          '    </div>',
          '    <div class="report-grid">',
          cards,
          '    </div>',
          '  </div>',
        ].join('\n');
      });
    }
    return [
      '<section id="tab-xwlb" class="tab-panel" role="tabpanel">',
      '  <div class="section-head">',
      '    <p class="section-num">02 · 新闻联播</p>',
      '    <h2 class="section-title">每日新闻联播</h2>',
      '    <p class="section-lede">央视《新闻联播》文字摘要，每日自动更新，轻松了解天下大事。</p>',
      '  </div>',
      '  <div class="timeline">',
      monthsHtml,
      '  </div>',
      '</section>',
    ].join('\n');
  }

  // ── 详情页：GitHub 周报 ─────────────────────────────────

  function renderGHPage(date, data) {
    var title = 'GitHub Trending 周报 · ' + data.weekLabel;
    var desc = 'GitHub Trending 中文周报，' + data.weekLabel + '，共 ' + data.count + ' 个项目。';
    updateMeta(title, desc);

    APP.className = 'has-sidebar';

    // 构建内容
    var rankRows = '';
    var repos = data.repos || [];
    repos.slice(0, 10).forEach(function (r, i) {
      var lang = r.language || '—';
      var rank = i + 1;
      rankRows += [
        '                <tr>',
        '                    <td class="td-rank">' + rank + '</td>',
        '                    <td class="td-repo">' + escapeHtml(r.name) + '<span class="author"> / ' + escapeHtml(r.author) + '</span></td>',
        '                    <td>' + escapeHtml(lang) + '</td>',
        '                    <td class="td-stars">' + fmtShort(r.stars) + '</td>',
        '                    <td class="td-forks">' + fmtShort(r.forks) + '</td>',
        '                </tr>',
      ].join('\n');
    });

    // 解析摘要高亮
    var coverSummary = highlightSummary(data.coverSummary || '');

    // 构建 repo 列表
    var repoItems = '';
    repos.forEach(function (r, idx) {
      repoItems += buildRepoItem(r, idx + 1);
    });

    // 构建索引
    var indexItems = '';
    indexItems += '      <a class="index-item" href="#gh-cover"><span class="idx-num">✦</span> 排行榜</a>\n';
    indexItems += '      <div class="index-divider"></div>\n';
    repos.forEach(function (r, idx) {
      indexItems += '      <a class="index-item" href="#repo-' + pad2(idx + 1) + '"><span class="idx-num">#' + pad2(idx + 1) + '</span> ' + escapeHtml(r.name) + '</a>\n';
    });

    APP.innerHTML =
      renderSidebar('github', date) +
      renderIndexNav(indexItems) +
      [
        '<main class="page page-detail">',
        '  <header class="page-header">',
        '    <div class="eyebrow"><a href="#/">← 返回主页</a><span style="margin-left:12px;color:var(--stone)">News Tools</span></div>',
        '    <h1>GitHub Trending <span style="color:var(--brand)">周报</span></h1>',
        '    <div class="meta">',
        '      <span><span class="tag">GitHub Trending</span></span>',
        '      <span>' + data.count + ' 个项目</span>',
        '      <span>' + data.weekInfo + '</span>',
        '    </div>',
        '  </header>',
        '  <div class="cover-summary">' + coverSummary + '</div>',
        '  <section id="gh-cover">',
        '    <div class="section-head">',
        '      <p class="section-num">排行榜</p>',
        '      <h2 class="section-title">本周热门项目 Top 10</h2>',
        '    </div>',
        '    <table class="rank-table">',
        '      <thead><tr><th style="width:30px;text-align:center">#</th><th>仓库</th><th style="width:48px">语言</th><th style="width:64px;text-align:right">Star</th><th style="width:64px;text-align:right">Fork</th></tr></thead>',
        '      <tbody>' + rankRows + '</tbody>',
        '    </table>',
        '  </section>',
        '  <section class="repo-section">',
        '    <div class="section-head">',
        '      <p class="section-num">详细内容</p>',
        '      <h2 class="section-title">逐个项目介绍</h2>',
        '    </div>',
        repoItems,
        '  </section>',
        renderFooter(true),
        '</main>',
      ].join('\n');

    // 初始化交互
    initSidebarCollapse();
    initScrollTracking('.index-nav .index-item:not(.index-summary)');
  }

  function pad2(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  function buildRepoItem(r, rank) {
    var zhDesc = r.zhDesc || r.description || '';
    var features = r.features || [];
    var audience = r.audience || '';
    var lang = r.language || '';
    var langColor = r.langColor || '#888';
    var starsFmt = fmtComma(r.stars);
    var weeklyFmt = fmtWeekly(r.weeklyStars || r.starsToday || 0);
    var forksFmt = fmtComma(r.forks);
    var repoUrl = r.url;

    var featLines = '';
    features.slice(0, 3).forEach(function (f) {
      featLines += '            <li>' + escapeHtml(f) + '</li>\n';
    });

    var langMetric =
      '          <div class="repo-metric"><span class="lang-dot" style="background:' + langColor + '"></span><span class="lbl">' + escapeHtml(lang || '—') + '</span></div>\n';

    return [
      '    <div class="repo-item" id="repo-' + pad2(rank) + '">',
      '      <div class="repo-number">#' + rank + '</div>',
      '      <div class="repo-header">',
      '        <div class="repo-avatar"><img src="https://github.com/' + encodeURIComponent(r.author) + '.png" alt="' + escapeHtml(r.author) + '" loading="lazy" onerror="this.style.display=\'none\'"></div>',
      '        <div class="repo-name">' + escapeHtml(r.name) + '<span class="author-name">' + escapeHtml(r.author) + '</span></div>',
      '      </div>',
      '      <div class="repo-metrics">',
      langMetric + '        <div class="repo-metric"><span class="val">' + starsFmt + '</span><span class="lbl">Star</span></div>',
      '        <div class="repo-metric"><span class="val" style="color:var(--near-black)">' + weeklyFmt + '</span><span class="lbl">本周</span></div>',
      '        <div class="repo-metric"><span class="val">' + forksFmt + '</span><span class="lbl">Fork</span></div>',
      '      </div>',
      '      <div class="repo-desc">' + escapeHtml(zhDesc) + '</div>',
      '      <ul class="repo-features">',
      featLines + '      </ul>',
      '      <div class="repo-audience"><strong>推荐：</strong>' + escapeHtml(audience) + '</div>',
      '      <div class="repo-url"><a href="' + escapeHtml(repoUrl) + '" target="_blank">' + escapeHtml(repoUrl) + '</a></div>',
      '    </div>',
    ].join('\n');
  }

  function highlightSummary(text) {
    if (!text) return '';
    text = text.replace(/(\d+(?:\.\d+)?)(?=\s*(?:个|万|k|⭐|星))/g, '<span class="hl">$1</span>');
    text = text.replace(/(?<![.<>"])(\d+)(?![.\d]*<\/[^>]+>)(?!\s*\.\d)/g, '<span class="hl">$1</span>');
    text = text.replace(/(?<=涵盖\s)(.*?)(?=\s*等领域)/g, function (m) {
      return m.replace(/([^·\s][^·]*?)(?=·|$)/g, '<strong>$1</strong>');
    });
    return text;
  }

  // ── 详情页：新闻联播 ──────────────────────────────────

  function renderXWLBPage(date, data) {
    var title = data.title + ' · 新闻联播文字摘要';
    var desc = data.title + ' 新闻联播文字摘要，共 ' + data.count + ' 条新闻。';
    updateMeta(title, desc);

    APP.className = 'has-sidebar';

    var summaryHtml = buildXWLBSummary(data.summary || '');
    var itemsHtml = buildXWLBItems(data.items || []);
    var indexHtml = buildXWLBIndex(data.items || []);

    APP.innerHTML =
      renderSidebar('xwlb', date) +
      renderIndexNav(indexHtml) +
      [
        '<main class="page page-detail">',
        '  <header class="page-header">',
        '    <div class="eyebrow"><a href="#/">← 返回主页</a><span style="margin-left:12px;color:var(--stone)">News Tools</span></div>',
        '    <h1>' + escapeHtml(data.title) + '</h1>',
        '    <div class="meta">',
        '      <span><span class="tag">新闻联播</span></span>',
        '      <span>' + data.count + ' 条新闻</span>',
        '      <span>来源：<a href="' + escapeHtml(data.url) + '" target="_blank" rel="noopener">央视网</a></span>',
        '      <span>' + data.date + '</span>',
        '    </div>',
        '  </header>',
        '  <section id="xwlb-summary">',
        '    <div class="section-head">',
        '      <p class="section-num">摘要</p>',
        '      <h2 class="section-title">本期要闻</h2>',
        '    </div>',
        '    <ol class="summary-list">' + summaryHtml + '</ol>',
        '  </section>',
        '  <section class="news-section">',
        '    <div class="section-head">',
        '      <p class="section-num">详细内容</p>',
        '      <h2 class="section-title">逐条新闻</h2>',
        '    </div>',
        itemsHtml,
        '  </section>',
        renderFooter(true),
        '</main>',
      ].join('\n');

    initSidebarCollapse();
    initScrollTracking('.index-nav .index-item:not(.index-summary)');
  }

  // ── 详情页：华尔街见闻 ──────────────────────────────────

  var WALLSTREET_SECTIONS = [
    { key: 'breakfast', label: '华尔街见闻早餐', icon: '☕', anchor: 'ws-breakfast' },
    { key: 'morning', label: '早间要闻汇总', icon: '🌅', anchor: 'ws-morning' },
    { key: 'premarket', label: '美股盘前', icon: '📈', anchor: 'ws-premarket' }
  ];

  function renderWallstreetPage(date, data) {
    var title = '华尔街见闻 · ' + formatDate(date);
    var desc = '华尔街见闻要闻 ' + formatDate(date) + '，收录 ' + data.count + ' 个栏目。';
    updateMeta(title, desc);

    APP.className = 'has-sidebar';

    var sectionsHtml = '';
    var indexHtml = '';
    var sectionCount = 0;
    WALLSTREET_SECTIONS.forEach(function (sec, i) {
      var secData = data.sections ? data.sections[sec.key] : null;
      indexHtml +=
        '      <a class="index-item" href="#' + sec.anchor + '">' +
        '<span class="idx-num">' + (i + 1) + '</span> ' + sec.label + '</a>\n';

      if (secData) {
        sectionCount++;
        sectionsHtml += buildWallstreetSection(sec, secData, date);
      } else {
        sectionsHtml += buildWallstreetEmpty(sec);
      }
    });

    APP.innerHTML =
      renderSidebar('wallstreet', date) +
      renderIndexNav(indexHtml) +
      [
        '<main class="page page-detail">',
        '  <header class="page-header">',
        '    <div class="eyebrow"><a href="#/">← 返回主页</a><span style="margin-left:12px;color:var(--stone)">News Tools</span></div>',
        '    <h1>华尔街见闻 <span style="color:var(--brand)">要闻</span></h1>',
        '    <div class="meta">',
        '      <span><span class="tag">华尔街见闻</span></span>',
        '      <span>' + sectionCount + ' 个栏目</span>',
        '      <span>来源：<a href="https://wallstreetcn.com/" target="_blank" rel="noopener">华尔街见闻</a></span>',
        '      <span>' + date + '</span>',
        '    </div>',
        '  </header>',
        '  <div class="wallstreet-summary">' +
        '    <p>每日三档栏目 · 早餐 07:25 · 早间汇总 12:30 · 美股盘前 21:30</p>' +
        '  </div>',
        sectionsHtml,
        renderFooter(true),
        '</main>',
      ].join('\n');

    initSidebarCollapse();
    initScrollTracking('.index-nav .index-item:not(.index-summary)');
  }

  function buildWallstreetSection(sec, secData, date) {
    var coverHtml = '';
    var article = secData.article;
    if (article && article.image && article.image.uri) {
      coverHtml = [
        '  <div class="wallstreet-cover">',
        '    <img src="' + escapeHtml(article.image.uri) + '" alt="' + escapeHtml(sec.label) + '" loading="lazy">',
        '  </div>',
      ].join('\n');
    }

    var pointsHtml = '';
    var points = secData.points || [];
    if (points.length) {
      var lis = points
        .map(function (p) { return '      <li>' + escapeHtml(p) + '</li>'; })
        .join('\n');
      pointsHtml = '    <ol class="wallstreet-list">\n' + lis + '\n    </ol>';
    } else {
      pointsHtml = '    <p class="wallstreet-empty-note">（暂无内容）</p>';
    }

    var sourceLink = '';
    if (secData.uri) {
      sourceLink = '<a class="wallstreet-source" href="' + escapeHtml(secData.uri) + '" target="_blank" rel="noopener">原文快讯 ↗</a>';
    }
    if (article && article.uri) {
      sourceLink = '<a class="wallstreet-source" href="' + escapeHtml(article.uri) + '" target="_blank" rel="noopener">阅读全文 ↗</a>';
    }

    return [
      '  <section class="wallstreet-section" id="' + sec.anchor + '">',
      '    <div class="section-head">',
      '      <p class="section-num">' + sec.icon + ' ' + sec.label + '</p>',
      '      <h2 class="section-title">' + escapeHtml(secData.title || sec.label) + '</h2>',
      '    </div>',
      coverHtml,
      pointsHtml,
      '    <div class="wallstreet-foot">' + sourceLink +
      '      <span class="wallstreet-time">抓取于 ' + escapeHtml((secData.fetched_at || '').slice(0, 16).replace('T', ' ')) + '</span>' +
      '    </div>',
      '  </section>',
    ].join('\n');
  }

  function buildWallstreetEmpty(sec) {
    return [
      '  <section class="wallstreet-section wallstreet-empty" id="' + sec.anchor + '">',
      '    <div class="section-head">',
      '      <p class="section-num">' + sec.icon + ' ' + sec.label + '</p>',
      '      <h2 class="section-title">' + sec.label + '</h2>',
      '    </div>',
      '    <p class="wallstreet-empty-note">本栏目今日未更新，稍后再来看看吧。</p>',
      '  </section>',
    ].join('\n');
  }

  // ══════════════════════════════════════════════════════════════
  // XWLB 构建函数（从 build_xwlb_html.py 翻译）
  // ══════════════════════════════════════════════════════════════

  function cleanXWLBText(text) {
    if (!text) return '';
    return text
      .replace(/^央视网消息\s*（新闻联播）\s*：\s*/, '')
      .replace(/\n*\[[^\]]*\]\([^)]*\)\s*$/, '')
      .replace(/\n*编辑：.*?责任编辑：.*$/s, '')
      .trim();
  }

  function cleanItemTitle(rawTitle) {
    if (!rawTitle) return '';
    var firstLine = rawTitle.split('\n')[0].trim();
    var m = firstLine.match(/[（\(]\d+[）\)]|^\d+\./);
    if (m) {
      return firstLine.substring(0, m.index).replace(/[：:。，,\s]+$/, '') || firstLine;
    }
    return firstLine;
  }

  function extractSubTitles(title) {
    if (!title || (title.indexOf('联播快讯') === -1 && title.indexOf('快讯') === -1)) return [];
    var parts = title.split(/[（\(]\d+[）\)]/);
    var subs = [];
    for (var i = 1; i < parts.length; i++) {
      var t = parts[i].replace(/[；;。，,\s]+$/, '').trim();
      if (t) subs.push(t);
    }
    return subs;
  }

  function buildXWLBSummary(summaryText) {
    if (!summaryText) return '';
    var lines = summaryText.replace(/\r\n/g, '\n').split('\n');
    var parts = [];
    lines.forEach(function (line) {
      var s = line.trim();
      if (!s) return;
      if (s.indexOf('本期节目主要内容') === 0) {
        parts.push('<div class="summary-label">' + escapeHtml(s) + '</div>');
      } else if (s.indexOf('联播快讯') !== -1) {
        var cleaned = s.replace(/^\d+[.、]\s*/, '');
        parts.push('<div class="summary-label">' + escapeHtml(cleaned) + '</div>');
      } else if (s.indexOf('（《新闻联播》') === 0 || s.indexOf('(《新闻联播》') === 0) {
        // skip
      } else if (s.indexOf('（') === 0 || s.indexOf('(') === 0) {
        parts.push('<li class="summary-subitem">' + escapeHtml(s) + '</li>');
      } else {
        var cleaned = s.replace(/^\d+[.、]\s*/, '');
        parts.push('<li>' + escapeHtml(cleaned) + '</li>');
      }
    });
    return parts.join('\n');
  }

  function buildXWLBItems(items) {
    var parts = [];
    items.forEach(function (item, i) {
      var idx = i + 1;
      var rawTitle = item.title || '';
      var url = item.url || '';
      var content = item.content || '';
      var cleanTitle = cleanItemTitle(rawTitle);
      var subTitles = extractSubTitles(rawTitle);
      var contentHtml = renderContentAsHtml(content, subTitles);
      if (!contentHtml) contentHtml = '<p>（暂无详细文字内容）</p>';
      var titleHtml = url
        ? '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' + escapeHtml(cleanTitle) + '</a>'
        : escapeHtml(cleanTitle);
      parts.push([
        '    <div class="news-item" id="item-' + pad2(idx) + '">',
        '      <div class="item-number">第 ' + pad2(idx) + ' 条</div>',
        '      <h3 class="item-title">' + titleHtml + '</h3>',
        '      <div class="item-content">',
        contentHtml,
        '      </div>',
        '    </div>',
      ].join('\n'));
    });
    return parts.join('\n');
  }

  function renderContentAsHtml(content, subTitles) {
    var cleaned = cleanXWLBText(content);
    if (!cleaned) return '';

    if (subTitles && subTitles.length > 0) {
      return renderExpressAsHtml(cleaned, subTitles);
    }

    var lines = cleaned.split('\n');
    var htmlParts = [];
    lines.forEach(function (line) {
      var s = line.trim();
      if (s) htmlParts.push('<p>' + escapeHtml(s) + '</p>');
    });
    return htmlParts.join('\n');
  }

  function renderExpressAsHtml(text, subTitles) {
    var cleanTitles = subTitles
      .map(function (t) { return t.replace(/[；;。，,\s]+$/, '').trim(); })
      .filter(function (t) { return t; });

    var lines = text.split('\n');
    var htmlParts = [];
    var currentTitle = null;
    var currentBodies = [];

    function flush() {
      if (currentTitle) {
        var bodyHtml = '';
        currentBodies.forEach(function (b) {
          if (b.trim()) bodyHtml += '<div class="express-body">' + escapeHtml(b.trim()) + '</div>\n';
        });
        if (bodyHtml) {
          htmlParts.push('<p><span class="express-title">' + escapeHtml(currentTitle) + '</span></p>\n' + bodyHtml);
        } else {
          htmlParts.push('<p><span class="express-title">' + escapeHtml(currentTitle) + '</span></p>');
        }
        currentTitle = null;
        currentBodies = [];
      }
    }

    lines.forEach(function (rawLine) {
      var s = rawLine.trim();
      if (!s) return;
      var matched = null;
      for (var j = 0; j < cleanTitles.length; j++) {
        var t = cleanTitles[j];
        if (s === t || s.indexOf(t) === 0) {
          matched = t;
          break;
        }
        var noNum = s.replace(/^[（\(]?\d+[）\)]\s*/, '');
        if (noNum === t || noNum.indexOf(t) === 0) {
          matched = t;
          break;
        }
      }
      if (matched) {
        flush();
        currentTitle = matched;
        var rest = s.substring(matched.length).replace(/^[。：:\s]+/, '');
        if (rest) currentBodies.push(rest);
      } else {
        if (currentTitle) {
          currentBodies.push(s);
        } else {
          htmlParts.push('<p>' + escapeHtml(s) + '</p>');
        }
      }
    });
    flush();
    return htmlParts.join('\n');
  }

  function buildXWLBIndex(items) {
    var parts = [];
    parts.push('      <a class="index-item index-summary" href="#xwlb-summary"><span class="idx-num">◈</span> 摘要</a>');
    parts.push('      <div class="index-divider"></div>');
    items.forEach(function (item, i) {
      var cleanTitle = cleanItemTitle(item.title || '');
      var display = cleanTitle.length > 60 ? cleanTitle.substring(0, 58) + '…' : cleanTitle;
      parts.push(
        '      <a class="index-item" href="#item-' + pad2(i + 1) + '">' +
        '<span class="idx-num">' + pad2(i + 1) + '</span> ' + escapeHtml(display) + '</a>'
      );
    });
    return parts.join('\n');
  }

  // ── 共享：Sidebar ───────────────────────────────────────

  function renderSidebar(type, currentDate) {
    // 着陆页数据需要加载 index.json 来获取所有日期
    // 我们用同步方式传入了 allDates —— 实际上这里需要从 data/index.json
    // 但为了不重新 fetch，我们在渲染侧边栏时不要求所有数据都准备好
    // 侧边栏将在数据加载完成后由 initDetailPage 触发重建
    // 这里我们简单渲染一个带有返回主页链接的骨架
    return [
      '<nav class="sidebar" id="sidebar">',
      '  <a class="sidebar-home" href="#/"><span class="icon">🏠</span> 返回主页</a>',
      '  <div class="sidebar-section" id="sidebar-section"></div>',
      '  <div class="sidebar-footer">',
      '    <a href="https://github.com/Mr-nnng/news-tools" target="_blank" rel="noopener"><span class="icon">📂</span> GitHub</a>',
      '  </div>',
      '</nav>',
    ].join('\n');
    // 侧边栏内容稍后通过 loadSidebarData 动态填充
  }

  function loadSidebarData(type, currentDate) {
    var section = document.getElementById('sidebar-section');
    if (!section) return;

    // 从 index.json 获取日期数据
    loadJSON(CONFIG.dataRoot + '/index.json').then(function (indexData) {
      var data;
      if (type === 'github') data = indexData.gh;
      else if (type === 'wallstreet') data = indexData.wallstreet;
      else data = indexData.xwlb;
      if (!data || !data.months) return;

      var sortedMonths = data.months.slice().sort(function (a, b) {
        return monthSortKey(b.label) - monthSortKey(a.label);
      });

      var sectionsHtml = '';
      sortedMonths.forEach(function (m) {
        var items = m.items.slice().sort(function (a, b) {
          return b.date.localeCompare(a.date);
        });
        var itemsHtml = items
          .map(function (item) {
            var displayDate = formatDate(item.date);
            var activeClass = item.date === currentDate ? ' is-active' : '';
            var link;
            if (type === 'github') link = '#/github/' + item.date;
            else if (type === 'wallstreet') link = '#/wallstreet/' + item.date;
            else link = '#/xwlb/' + item.date;
            return '<a href="' + link + '" class="sidebar-item' + activeClass + '">' + displayDate + '</a>';
          })
          .join('\n');
        sectionsHtml += [
          '<div class="sidebar-month-group">',
          '  <div class="sidebar-month-toggle">',
          '    <span class="arrow">▾</span> ' + m.label,
          '  </div>',
          '  <div class="sidebar-month-items">',
          itemsHtml,
          '  </div>',
          '</div>',
        ].join('\n');
      });

      section.innerHTML = sectionsHtml;
      initSidebarCollapse();
    })['catch'](function () {
      section.innerHTML = '<div style="padding:12px;color:var(--stone);font-size:13px;">加载失败</div>';
    });
  }

  // ── 共享：Index Nav ─────────────────────────────────────

  function renderIndexNav(itemsHtml) {
    return [
      '<nav class="index-nav">',
      '  <div class="index-head">本页导航</div>',
      itemsHtml,
      '</nav>',
    ].join('\n');
  }

  // ── 共享：Footer ────────────────────────────────────────

  function renderFooter(isDetail) {
    var cls = 'foot' + (isDetail ? ' foot-detail' : '');
    var markCls = isDetail ? 'mark mark-simple' : 'mark';
    var line = isDetail ? 'GitHub Trending 中文周报 · 华尔街见闻 · 新闻联播' : 'GitHub Trending 中文周报 · 华尔街见闻 · 新闻联播';
    var ethos = isDetail
      ? '每周发现开源好项目，每日捕捉全球市场动态与天下大事'
      : '每周发现开源好项目，每日捕捉全球市场动态与天下大事';

    return [
      '<footer class="' + cls + '">',
      '  <div class="' + markCls + '">',
      '    <span class="wm-name">News Tools</span>',
      '    <span class="wm-line">' + line + '</span>',
      '  </div>',
      '  <div class="colophon">',
      '    <div class="links">',
      '      <a href="https://github.com/Mr-nnng/news-tools" target="_blank" rel="noopener">GitHub</a> ·',
      '      <a href="https://github.com/Mr-nnng/news-tools/blob/main/LICENSE" target="_blank" rel="noopener">MIT License</a>',
      '    </div>',
      '    <p class="ethos">' + ethos + '</p>',
      '  </div>',
      '</footer>',
    ].join('\n');
  }

  // ══════════════════════════════════════════════════════════════
  // 交互初始化
  // ══════════════════════════════════════════════════════════════

  function initTabSwitching() {
    var btns = document.querySelectorAll('.tab-btn');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tabId = btn.getAttribute('data-tab');
        btns.forEach(function (b) { b.classList.toggle('is-active', b === btn); });
        document.querySelectorAll('.tab-panel').forEach(function (p) {
          p.classList.toggle('is-active', p.id === 'tab-' + tabId);
        });
      });
    });
  }

  function initMonthToggle(selector) {
    var toggles = document.querySelectorAll(selector);
    toggles.forEach(function (t) {
      t.addEventListener('click', function () {
        t.parentElement.classList.toggle('is-collapsed');
      });
    });
  }

  function initSidebarCollapse() {
    var toggles = document.querySelectorAll('.sidebar-month-toggle');
    toggles.forEach(function (t) {
      t.addEventListener('click', function () {
        t.parentElement.classList.toggle('is-collapsed');
      });
    });
  }

  function initScrollTracking(itemSelector) {
    var indexItems = document.querySelectorAll(itemSelector);
    if (!indexItems.length) return;

    var sections = [];
    indexItems.forEach(function (item) {
      var href = item.getAttribute('href');
      if (href && href.charAt(0) === '#') {
        var el = document.getElementById(href.substring(1));
        if (el) sections.push({ el: el, link: item });
      }
    });
    if (!sections.length) return;

    function updateActive() {
      var bestIdx = -1;
      var bestDist = Infinity;
      for (var i = 0; i < sections.length; i++) {
        var rect = sections[i].el.getBoundingClientRect();
        var dist = Math.abs(rect.top - 100);
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = i;
        }
      }
      if (bestIdx >= 0) {
        var activeId = sections[bestIdx].el.id;
        indexItems.forEach(function (item) {
          item.classList.toggle('is-active', item.getAttribute('href') === '#' + activeId);
        });
      }
    }

    var ticking = false;
    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(function () {
          updateActive();
          ticking = false;
        });
        ticking = true;
      }
    });
    updateActive();
  }

  // ══════════════════════════════════════════════════════════════
  // 加载状态 / 错误
  // ══════════════════════════════════════════════════════════════

  function showLoading() {
    APP.className = '';
    APP.innerHTML = '<div class="loading-spinner">加载中</div>';
  }

  function showError(msg) {
    APP.className = '';
    APP.innerHTML = '<div class="error-message">' + escapeHtml(msg || '加载失败') + '</div>';
  }

  // ══════════════════════════════════════════════════════════════
  // 路由
  // ══════════════════════════════════════════════════════════════

  function parseHash() {
    var hash = window.location.hash.replace(/^#\//, '') || '';
    var parts = hash.split('/');
    if (!hash || hash === '') return { route: 'landing' };
    if (parts[0] === 'github' && parts[1]) return { route: 'github', date: parts[1] };
    if (parts[0] === 'wallstreet' && parts[1]) return { route: 'wallstreet', date: parts[1] };
    if (parts[0] === 'xwlb' && parts[1]) return { route: 'xwlb', date: parts[1] };
    return { route: 'landing' };
  }

  function navigate() {
    // 如果 hash 存在但不是 #/ 开头的路由（如 #repo-01 等内部锚点），
    // 交给浏览器原生锚点滚动处理，不触发路由切换
    var rawHash = window.location.hash;
    if (rawHash && rawHash.indexOf('#/') !== 0) {
      return;
    }

    var parsed = parseHash();

    if (parsed.route === 'landing') {
      showLoading();
      loadJSON(CONFIG.dataRoot + '/index.json')
        .then(function (data) {
          renderLanding(data);
          window.scrollTo(0, 0);
        })
        ['catch'](function (err) {
          showError('无法加载数据，请稍后重试。');
          console.error('Landing load error:', err);
        });
      return;
    }

    if (parsed.route === 'github') {
      showLoading();
      var dataUrl = CONFIG.dataRoot + '/github/' + parsed.date + '.json';
      loadJSON(dataUrl)
        .then(function (data) {
          renderGHPage(parsed.date, data);
          loadSidebarData('github', parsed.date);
          window.scrollTo(0, 0);
        })
        ['catch'](function (err) {
          showError('无法加载 GitHub 周报数据 (日期: ' + parsed.date + ')。');
          console.error('GH page load error:', err);
        });
      return;
    }

    if (parsed.route === 'wallstreet') {
      showLoading();
      var dataUrl = CONFIG.dataRoot + '/wallstreet/' + parsed.date + '.json';
      loadJSON(dataUrl)
        .then(function (data) {
          renderWallstreetPage(parsed.date, data);
          loadSidebarData('wallstreet', parsed.date);
          window.scrollTo(0, 0);
        })
        ['catch'](function (err) {
          showError('无法加载华尔街见闻数据 (日期: ' + parsed.date + ')。');
          console.error('Wallstreet page load error:', err);
        });
      return;
    }

    if (parsed.route === 'xwlb') {
      showLoading();
      var dataUrl = CONFIG.dataRoot + '/xwlb/' + parsed.date + '.json';
      loadJSON(dataUrl)
        .then(function (data) {
          renderXWLBPage(parsed.date, data);
          loadSidebarData('xwlb', parsed.date);
          window.scrollTo(0, 0);
        })
        ['catch'](function (err) {
          showError('无法加载新闻联播数据 (日期: ' + parsed.date + ')。');
          console.error('XWLB page load error:', err);
        });
      return;
    }
  }

  // ══════════════════════════════════════════════════════════════
  // 启动
  // ══════════════════════════════════════════════════════════════

  window.addEventListener('hashchange', navigate);
  navigate();

})();
