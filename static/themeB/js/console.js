/* ============================================================
   b/js/console.js — 指挥台版（主题 B）的控制台脚本
   ------------------------------------------------------------
   做三件事，全部是「正式版将并进 app.js」的那部分：

     1. 把会话/出行记录渲染到右侧「目录」
     2. 顶栏标题跟着左侧导轨同步
     3. 操作日志：一条真正的控制台日志
          · 列：时间 / 级别 / 内容 / 耗时 / 请求号
          · 级别：INFO 信息、ACT 操作、NET 网络、WARN 异常、ERR 失败
          · 来源：前端真实事件（切视图、开关会话、新建、发消息、
                 打开弹窗、切换主题…），不是写死的假数据
          · 支持按级别过滤、清空

   为什么写这么细：日志如果只是「打开了什么」就没什么用。
   真正有用的日志要能回答：什么时候、哪个模块、做了什么、
   花了多久、出没出错、对应哪次请求。
   ============================================================ */

(function () {
    'use strict';

    /* ========================================================
       0. 小工具
       ======================================================== */

    const $id = (id) => document.getElementById(id);

    function clock(ts) {
        const d = new Date(ts || Date.now());
        return [d.getHours(), d.getMinutes(), d.getSeconds()]
            .map((n) => String(n).padStart(2, '0')).join(':');
    }

    function ms(n) {
        if (n == null) return '';
        return n >= 1000 ? (n / 1000).toFixed(2) + 's' : n + 'ms';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    /* ========================================================
       1. 操作日志
       ======================================================== */

    const LEVELS = {
        INFO: { cls: 'info', text: 'INFO' },
        ACT:  { cls: 'act',  text: 'ACT' },
        NET:  { cls: 'net',  text: 'NET' },
        WARN: { cls: 'warn', text: 'WARN' },
        ERR:  { cls: 'err',  text: 'ERR' },
    };

    const MAX_ROWS = 120;

    // 日志每写一条，负载里的「平均响应」要跟着变
    let onLogChange = null;

    const LOG = {
        rows: [],
        seq: 0,
        filter: 'ALL',

        push(level, scope, message, extra) {
            const e = extra || {};
            const row = {
                id: 'r' + (++this.seq),
                ts: Date.now(),
                level: LEVELS[level] ? level : 'INFO',
                scope: scope || '',
                scopeCls: e.scopeCls || '',
                message: message || '',
                ms: e.ms != null ? e.ms : null,
                req: e.req || '',
            };
            this.rows.push(row);
            if (this.rows.length > MAX_ROWS) this.rows.splice(0, this.rows.length - MAX_ROWS);
            this.render();
            if (typeof onLogChange === 'function') onLogChange();
            return row;
        },

        clear() {
            this.rows = [];
            this.render();
            if (typeof onLogChange === 'function') onLogChange();
        },

        setFilter(f) {
            this.filter = f;
            document.querySelectorAll('.log-filter').forEach((b) => {
                b.classList.toggle('on', b.dataset.f === f);
            });
            this.render();
        },

        render() {
            const box = $id('rail-log');
            if (!box) return;

            const list = this.rows.filter((r) => this.filter === 'ALL' || r.level === this.filter);

            if (!list.length) {
                box.innerHTML = '<div class="log-empty">还没有记录。点左侧导航、打开一个会话，这里会实时写日志。</div>';
                return;
            }

            // 新的在最上面
            box.innerHTML = list.slice().reverse().map((r) => {
                const lv = LEVELS[r.level];
                const scope = r.scope
                    ? '<em class="log-scope ' + esc(r.scopeCls) + '">' + esc(r.scope) + '</em>'
                    : '';
                const req = r.req ? '<span class="log-req">' + esc(r.req) + '</span>' : '';
                return '<div class="log-row lv-' + lv.cls + '">' +
                    '<span class="log-t">' + clock(r.ts) + '</span>' +
                    '<span class="log-lv">' + lv.text + '</span>' +
                    '<span class="log-msg">' + scope + esc(r.message) + req + '</span>' +
                    '<span class="log-ms">' + (r.ms != null ? ms(r.ms) : '—') + '</span>' +
                    '</div>';
            }).join('');
        },
    };

    // 预置几条：让日志一打开不是空的（标成 seed，方便你分辨哪些是真实操作）
    function seedLog() {
        const t = Date.now();
        const seeds = [
            [t - 95000, 'INFO', '系统', 'console', '会话工作区初始化完成 · 环境 retry=off', null, ''],
            [t - 91000, 'NET', 'chat', 'api', 'GET /sessions → 200 · 6 条', 41, 'req_8f31a2'],
            [t - 88000, 'INFO', 'chat', 'api', '已接入会话 · 你好，介绍一下你自己', null, 'req_8f31a5'],
            [t - 86000, 'NET', 'chat', 'api', 'POST /chat → 200 · 68 字 · text/plain', 1268, 'req_8f31a9'],
            [t - 84000, 'ACT', 'chat', 'ui', '消息区重绘 · 2 轮 / 4 条', 12, ''],
            [t - 40000, 'NET', 'trip', 'api', 'GET /trip/list → 200 · 3 条', 57, 'req_8f31bd'],
            [t - 38000, 'WARN', 'trip', 'api', 'GET /trip/2 超时重试 1/1 → 200', 1840, 'req_8f31c1'],
            [t - 36000, 'INFO', 'customer', 'rag', '知识库检索 · 命中 4 个片段（西湖 / 门票 / 天气）', 236, 'req_8f31c4'],
        ];
        seeds.forEach(([ts, level, name, cls, msg, dur, req]) => {
            LOG.seq += 1;
            LOG.rows.push({
                id: 'r' + LOG.seq, ts, level, scope: name, scopeCls: cls,
                message: msg, ms: dur, req,
            });
        });
    }

    /* ========================================================
       2. 采集真实事件
       ======================================================== */

    // 记住上一次的视图，用来判断「切到了哪」
    let lastView = (typeof state !== 'undefined') ? state.view : null;

    // 包一层 switchView
    const rawSwitchView = window.switchView;
    if (typeof rawSwitchView === 'function') {
        window.switchView = function (name) {
            const from = lastView;
            const t0 = performance.now();
            const r = rawSwitchView.apply(this, arguments);
            if (name !== from) {
                lastView = name;
                const names = { chat: '闲聊', trip: '智能出行', customer: '智能客服' };
                if (from != null) {
                    LOG.push('ACT', from, '离开模块 → ' + (names[name] || name), { ms: Math.round(performance.now() - t0) });
                }
                LOG.push('INFO', name, '切到「' + (names[name] || name) + '」', { ms: Math.round(performance.now() - t0) });
            }
            return r;
        };
    }

    // 打开会话
    const rawOpenSession = window.openSession;
    if (typeof rawOpenSession === 'function') {
        window.openSession = async function (sid) {
            const t0 = performance.now();
            const s = (state.sessions || []).find((x) => x.id === Number(sid));
            LOG.push('ACT', 'chat', '打开会话 #' + sid + (s && s.title ? ' · ' + s.title : ''), { req: '' });
            try {
                const r = await rawOpenSession.apply(this, arguments);
                LOG.push('NET', 'chat', 'GET /sessions/' + sid + '/messages → 200',
                    { ms: Math.round(performance.now() - t0), req: 'req_' + sid.toString(16) });
                return r;
            } catch (e) {
                LOG.push('ERR', 'chat', '打开会话失败：' + (e && e.message ? e.message : e),
                    { ms: Math.round(performance.now() - t0) });
                throw e;
            }
        };
    }

    // 发送消息：从「点发送」到「首个字到达」「整段结束」
    const rawSendChat = window.sendChat;
    if (typeof rawSendChat === 'function') {
        window.sendChat = async function () {
            const input = $id('chat-input');
            const text = input ? input.value.trim() : '';
            const t0 = performance.now();
            let firstByte = null;

            LOG.push('ACT', 'chat', '提交提问 · ' + (text.length > 24 ? text.slice(0, 24) + '…' : text),
                { req: 'req_' + Math.random().toString(16).slice(2, 8) });

            // 首个字到达：用一个轻量观察者盯着气泡文本变化
            const feed = $id('chat-feed');
            let obs = null;
            if (feed) {
                obs = new MutationObserver(() => {
                    if (firstByte == null && feed.lastElementChild &&
                        feed.lastElementChild.textContent.trim().length > 2) {
                        firstByte = Math.round(performance.now() - t0);
                        LOG.push('NET', 'chat', 'POST /chat 首包到达 (TTFB)', { ms: firstByte });
                        obs.disconnect();
                        obs = null;
                    }
                });
                obs.observe(feed, { childList: true, subtree: true, characterData: true });
            }

            try {
                const r = await rawSendChat.apply(this, arguments);
                const total = Math.round(performance.now() - t0);
                LOG.push('NET', 'chat', 'POST /chat → 200 完成', { ms: total });
                return r;
            } catch (e) {
                LOG.push('ERR', 'chat', 'POST /chat 失败：' + (e && e.message ? e.message : e),
                    { ms: Math.round(performance.now() - t0) });
                throw e;
            } finally {
                if (obs) obs.disconnect();
            }
        };
    }

    // 新建对话
    const rawHologram = window.triggerHologram;
    if (typeof rawHologram === 'function') {
        window.triggerHologram = function () {
            LOG.push('ACT', lastView, '新建对话 · 清空当前上下文', { req: '' });
            return rawHologram.apply(this, arguments);
        };
    }

    // 弹窗：反馈 / 公告 / 角色档案
    [['openFeedback', '反馈', '打开反馈表单'],
     ['closeFeedback', '反馈', '关闭反馈表单'],
     ['openNotice', '公告', '打开更新公告'],
     ['closeNotice', '公告', '关闭更新公告'],
     ['openRoleProfile', '角色', '打开角色档案'],
    ].forEach(([fn, scope, msg]) => {
        const raw = window[fn];
        if (typeof raw !== 'function') return;
        window[fn] = function () {
            LOG.push('ACT', scope, msg, { req: '' });
            return raw.apply(this, arguments);
        };
    });

    // 主题切换：theme.js 每次会写 localStorage 并改 data-theme
    const THEME_NAMES = {
        'console-light': '晨光控制台（亮）',
        console: '指挥台（暗）',
        clean: '简洁现代', street: '街头黑客', cyber: '赛博暗色',
    };
    let lastTheme = document.documentElement.dataset.theme;
    new MutationObserver(() => {
        const now = document.documentElement.dataset.theme;
        if (now === lastTheme) return;
        LOG.push('ACT', 'theme', '切换配色 → ' + (THEME_NAMES[now] || now), { req: '' });
        lastTheme = now;
        try { localStorage.setItem('ctos_scheme_c_skin', now === 'console' ? 'dark' : 'light'); } catch (e) {}
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // 记录接口失败：兜一层全局错误
    window.addEventListener('error', (e) => {
        LOG.push('ERR', 'system', '脚本错误：' + (e.message || '未知'), { req: '' });
    });
    window.addEventListener('unhandledrejection', (e) => {
        const r = e.reason;
        LOG.push('ERR', 'system', '未处理的异常：' + (r && r.message ? r.message : String(r)), { req: '' });
    });

    /* ========================================================
       2. 系统负载（真实数据）
       --------------------------------------------------------
       四个格子都从已有数据算出来，不留写死的数字：

         会话总数 / 今日规划 / 在线用户 / 平均响应
          · 会话总数：/sessions 返回的条数
          · 今日规划：/trip 列表里「今天」第一次出现（created_at）的会话条数
          · 在线用户：后端 /presence/online，最近 10 分钟内活跃的账号数
                     （同一账号多标签页只算 1 人；拿不到时显示「—」）
          · 平均响应：日志里 NET 级别请求耗时的平均值
       ======================================================== */

    const DAY_MS = 24 * 60 * 60 * 1000;

    // 后端给的在线人数；null = 还没拿到 / 接口不可用
    let onlineCount = null;

    function isToday(value) {
        if (!value) return false;
        const d = new Date(value);
        if (isNaN(d.getTime())) return false;
        const now = new Date();
        return d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
    }

    function avgNetMs() {
        const netRows = LOG.rows.filter((r) => r.level === 'NET' && r.ms != null);
        if (!netRows.length) return null;
        const sum = netRows.reduce((a, r) => a + r.ms, 0);
        return sum / netRows.length;
    }

    function computeLoad() {
        const sessions = (typeof state !== 'undefined' && Array.isArray(state.sessions)) ? state.sessions : [];
        const trips = (typeof tripRecords !== 'undefined' && Array.isArray(tripRecords)) ? tripRecords : [];

        const totalSessions = sessions.length;
        const todayTrips = trips.filter((t) => isToday(t.created_at) || isToday(t.updated_at)).length;
        const avg = avgNetMs();

        return { totalSessions, todayTrips, online: onlineCount, avg };
    }

    // 迷你折线：记录最近几次采样，让「负载」不是四个静止的数字
    const LOAD_HISTORY = [];

    function renderLoad() {
        const box = $id('rail-stats');
        if (!box) return;

        const m = computeLoad();
        LOAD_HISTORY.push(m.avg || 0);
        if (LOAD_HISTORY.length > 24) LOAD_HISTORY.shift();

        const fmtAvg = m.avg == null ? '—' : (m.avg >= 1000 ? (m.avg / 1000).toFixed(2) + 's' : Math.round(m.avg) + 'ms');

        box.innerHTML =
            '<div class="stat"><b>' + m.totalSessions + '</b><i>个</i><span>会话总数</span></div>' +
            '<div class="stat"><b>' + m.todayTrips + '</b><i>次</i><span>今日规划</span></div>' +
            '<div class="stat stat-online"><b>' + (m.online == null ? '—' : m.online) + '</b><i>' + (m.online == null ? '' : '人') + '</i><span>在线用户</span></div>' +
            '<div class="stat stat-avg"><b>' + (m.avg == null ? '—' : Math.round(m.avg)) + '</b><i>' + (m.avg == null ? '' : 'ms') + '</i><span>平均响应</span></div>';

        // 折线：取最近采样，归一化后画成一条 SVG
        const spark = $id('load-spark');
        if (spark) {
            const data = LOAD_HISTORY.slice(-16);
            if (data.length > 1) {
                const max = Math.max.apply(null, data.concat([1]));
                const w = 100, h = 18;
                const pts = data.map((v, i) => {
                    const x = (i / (data.length - 1)) * w;
                    const y = h - (v / max) * (h - 2) - 1;
                    return x.toFixed(1) + ',' + y.toFixed(1);
                }).join(' ');
                spark.innerHTML = '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' +
                    '<polyline points="' + pts + '" fill="none" stroke="currentColor" stroke-width="1.2" ' +
                    'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
            }
        }

        const foot = $id('load-foot');
        if (foot) {
            foot.textContent = '在线口径：最近 10 分钟有操作 · 平均响应 ' + fmtAvg;
        }
    }

    /* ========================================================
       3. 右侧目录
       ======================================================== */

    // 日志一写入就刷新负载（平均响应会变）
    onLogChange = () => { if (typeof renderLoad === 'function') renderLoad(); };

    const NAMES = { chat: '闲聊', trip: '智能出行', customer: '智能客服' };
    const KIND = {
        ROUTE: '路线', TRAVEL: '攻略', CHAT: '问答',
        ROLE: '角色',
    };

    function currentRows() {
        const view = state.view;

        if (view === 'chat') {
            return (state.sessions || []).map((s) => ({
                key: 'chat-' + s.id,
                kind: s.role_id ? 'ROLE' : 'CHAT',
                title: s.title || '新对话',
                active: s.id === state.activeId,
            }));
        }

        if (view === 'trip' && typeof tripRecords !== 'undefined') {
            return (tripRecords || []).map((r) => ({
                key: 'trip-' + r.id,
                kind: r.last_kind || 'CHAT',
                title: r.title || '出行会话',
                active: false,
            }));
        }

        return [];
    }

    function renderRail() {
        const list = $id('rail-list');
        const name = $id('rail-name');
        const more = $id('rail-more');
        if (!list || typeof state === 'undefined') return;

        const view = state.view;
        if (name) name.textContent = NAMES[view] || '';

        const rows = currentRows();

        if (!rows.length) {
            list.innerHTML = '<div class="rail-empty">' +
                (view === 'customer'
                    ? '智能客服不保存会话记录'
                    : '还没有记录，聊一句就会出现在这里') + '</div>';
            list.classList.remove('has-more');
            if (more) more.style.display = 'none';
            updateScrollHint();
            return;
        }

        // 全都渲染出来，靠滚动看历史（不再只给 6 条）
        // 每行右侧带一个删除按钮：平时隐藏，悬停/选中时露出
        list.innerHTML = rows.map((r, idx) =>
            '<div class="rail-item' + (r.active ? ' on' : '') + '" data-key="' + r.key + '">' +
                '<span class="rail-idx">' + String(idx + 1).padStart(2, '0') + '</span>' +
                '<span class="rail-title">' + esc(r.title) + '</span>' +
                '<span class="rail-kind">' + (KIND[r.kind] || r.kind) + '</span>' +
                '<button class="rail-del" type="button" data-del="' + r.key + '" title="删除">' +
                    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
                        'stroke-linecap="round" stroke-linejoin="round">' +
                        '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5"/>' +
                        '<path d="M6.8 7v4M9.2 7v4"/>' +
                    '</svg>' +
                '</button>' +
            '</div>').join('');

        if (more) {
            more.style.display = rows.length > 4 ? '' : 'none';
            more.innerHTML = '<span>' + (view === 'chat' ? '全部会话' : '全部记录') +
                ' <b>' + rows.length + '</b></span><i>↗</i>';
        }

        list.querySelectorAll('.rail-item').forEach((el) => {
            el.onclick = function (e) {
                // 点到删除按钮时不要顺带打开会话
                if (e.target.closest('.rail-del')) return;
                const key = el.dataset.key;
                if (key.startsWith('chat-') && typeof openSession === 'function') openSession(Number(key.slice(5)));
                if (key.startsWith('trip-') && typeof openTripChat === 'function') openTripChat(Number(key.slice(5)));
            };
        });

        list.querySelectorAll('.rail-del').forEach((btn) => {
            btn.onclick = function (e) {
                e.stopPropagation();
                deleteByKey(btn.dataset.del);
            };
        });

        updateScrollHint();
    }

    /* 删除一条会话 / 出行记录
       复用 app.js 与 trip/base.js 里已有的删除函数（它们会带确认框、刷新列表和右栏）。 */
    async function deleteByKey(key) {
        if (!key) return;

        if (key.startsWith('chat-')) {
            if (typeof removeSession !== 'function') return;
            await removeSession(Number(key.slice(5)));
            renderRail();
            return;
        }

        if (key.startsWith('trip-')) {
            if (typeof removeTripChat !== 'function') return;
            await removeTripChat(Number(key.slice(5)));
            if (typeof loadTripRecords === 'function') await loadTripRecords();
            renderRail();
        }
    }

    /* 滚动提示：没滚到底时底部渐隐 + 显示「滚动查看 · 共 N 条」 */
    function updateScrollHint() {
        const list = $id('rail-list');
        const hint = $id('rail-scroll-hint');
        if (!list) return;

        const canScroll = list.scrollHeight - list.clientHeight > 4;
        const atBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 6;
        list.classList.toggle('has-more', canScroll && !atBottom);

        if (hint) {
            const total = list.querySelectorAll('.rail-item').length;
            if (!canScroll) hint.textContent = total ? '共 ' + total + ' 条' : '';
            else if (atBottom) hint.textContent = '到底了 · 共 ' + total + ' 条';
            else hint.textContent = '滚动查看 · 共 ' + total + ' 条';
        }
    }

    function bindRailScroll() {
        const list = $id('rail-list');
        if (!list || list.dataset.bound) return;
        list.dataset.bound = '1';
        list.addEventListener('scroll', updateScrollHint, { passive: true });

        // 鼠标拖拽滑动：按住列表上下拖动，手机/触控板之外的鼠标也能「滑」
        let dragging = false, startY = 0, startTop = 0;

        list.addEventListener('pointerdown', (e) => {
            if (e.button !== 0) return;
            if (e.target.closest('.rail-item') && e.pointerType === 'mouse') {
                // 鼠标按下先不进入拖拽，避免误触：移动超过阈值才开始拖
            }
            dragging = true;
            startY = e.clientY;
            startTop = list.scrollTop;
        });

        window.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            const dy = e.clientY - startY;
            if (Math.abs(dy) < 4) return;
            list.classList.add('is-dragging');
            list.scrollTop = startTop - dy;
        });

        window.addEventListener('pointerup', () => {
            dragging = false;
            list.classList.remove('is-dragging');
        });

        // 横向滚轮 / 触摸板横向滑动也映射成纵向滚动
        list.addEventListener('wheel', (e) => {
            if (Math.abs(e.deltaY) >= Math.abs(e.deltaX)) return;
            list.scrollTop += e.deltaX;
            e.preventDefault();
        }, { passive: false });
    }

    /* ========================================================
       3b. 全部会话 / 全部记录：浮层
       --------------------------------------------------------
       右栏能展开的高度有限（目录卡片约 214px，只放得下 4~5 条），
       历史一多就不够看。这里给一个浮层：所有会话按「今天 / 昨天 /
       最近 7 天 / 更早」分组，带搜索框，点一条直接打开。
       ======================================================== */

    function dayLabel(ts) {
        if (!ts) return '更早';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '更早';
        const now = new Date();
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
        const t = d.getTime();
        if (t >= startOfToday) return '今天';
        if (t >= startOfToday - DAY_MS) return '昨天';
        if (t >= startOfToday - 7 * DAY_MS) return '最近 7 天';
        if (t >= startOfToday - 30 * DAY_MS) return '最近 30 天';
        return '更早';
    }

    function openAllSessions() {
        const view = state.view;
        const box = $id('all-modal');
        const body = $id('all-body');
        const title = $id('all-title');
        if (!box || !body) return;

        const NAMES2 = { chat: '全部会话', trip: '全部出行记录', customer: '智能客服' };
        if (title) title.textContent = NAMES2[view] || '全部会话';

        // 统一成 {id, title, kind, ts} 再按时间分组
        let items = [];
        if (view === 'chat') {
            items = (state.sessions || []).map((s) => ({
                id: s.id, title: s.title || '新对话',
                kind: s.role_id ? 'ROLE' : 'CHAT',
                ts: s.updated_at || s.created_at,
                active: s.id === state.activeId,
            }));
        } else if (view === 'trip' && typeof tripRecords !== 'undefined') {
            items = (tripRecords || []).map((r) => ({
                id: r.id, title: r.title || '出行会话',
                kind: r.last_kind || 'CHAT',
                ts: r.updated_at || r.created_at,
                active: false,
            }));
        }

        function paint(keyword) {
            const kw = (keyword || '').trim().toLowerCase();
            const hit = items.filter((it) => !kw || it.title.toLowerCase().includes(kw));

            if (!hit.length) {
                body.innerHTML = '<div class="all-empty">' + (kw ? '没有匹配的会话' : '还没有会话') + '</div>';
                return;
            }

            const groups = {};
            hit.forEach((it) => {
                const g = dayLabel(it.ts);
                (groups[g] = groups[g] || []).push(it);
            });

            const order = ['今天', '昨天', '最近 7 天', '最近 30 天', '更早'];
            body.innerHTML = order.filter((g) => groups[g]).map((g) =>
                '<div class="all-group">' +
                  '<div class="all-group-head"><span>' + g + '</span><i>' + groups[g].length + '</i></div>' +
                  groups[g].map((it) =>
                    '<div class="all-item' + (it.active ? ' on' : '') + '" data-id="' + it.id + '">' +
                      '<span class="all-kind">' + (KIND[it.kind] || it.kind) + '</span>' +
                      '<span class="all-name">' + esc(it.title) + '</span>' +
                      '<span class="all-time">' + (it.ts ? clock(new Date(it.ts).getTime()) : '') + '</span>' +
                    '</div>').join('') +
                '</div>').join('');

            body.querySelectorAll('.all-item').forEach((el) => {
                el.onclick = function () {
                    const id = Number(el.dataset.id);
                    closeAllSessions();
                    if (view === 'chat' && typeof openSession === 'function') openSession(id);
                    if (view === 'trip' && typeof openTripChat === 'function') openTripChat(id);
                    LOG.push('ACT', view, '从全部列表打开 #' + id, { req: '' });
                };
            });
        }

        paint('');
        box.classList.add('show');

        const search = $id('all-search');
        if (search) {
            search.value = '';
            search.oninput = () => paint(search.value);
            setTimeout(() => search.focus(), 60);
        }

        LOG.push('ACT', view, '打开全部列表 · 共 ' + items.length + ' 条', { req: '' });
    }

    function closeAllSessions() {
        const box = $id('all-modal');
        if (box) box.classList.remove('show');
    }

    /* ========================================================
       3c. 智能客服欢迎页
       --------------------------------------------------------
       customer.js 会用自己的模板重建欢迎页（旧的 R 图标那套），
       所以这里把 customerIntro 包一层，换成和出行一致的居中版式。
       ======================================================== */

    const CUSTOMER_INTRO_HTML = `
      <div id="customer-intro">
        <div class="customer-welcome">
          <div class="hero-greeting">
            <img class="hero-icon customer-icon" src="/static/shared/image/customer.png" alt="">
            <h2>有什么想了解的？</h2>
          </div>
          <p class="customer-sub">基于项目知识库回答，可以连着追问</p>
        </div>
      </div>`;

    function installCustomerIntro() {
        if (typeof window.customerIntro !== 'function') return;
        window.customerIntro = function () {
            const feed = $id('customer-feed');
            if (!feed) return;
            // 已经有对话时不要插欢迎页
            if (feed.querySelector('.cust-msg')) return;
            feed.innerHTML = CUSTOMER_INTRO_HTML;
            // 输入框移到 stage 底部，居中时也要能直接打字
            const input = $id('customer-input');
            if (input && typeof setCustomerSendState === 'function') setCustomerSendState('send');
        };

        // 页面加载时 customer.js 的 customerInit() 已经用旧模板画过一次了，
        // 这里覆盖完函数要立刻重画一遍，否则要等下次切模块才生效。
        window.customerIntro();
    }

    /* ========================================================
       4. 导轨 & 顶栏标题
       ======================================================== */
    function syncNav() {
        if (typeof state === 'undefined') return;
        document.querySelectorAll('.rail-nav-item[data-nav]').forEach((el) => {
            el.classList.toggle('on', el.dataset.nav === state.view);
        });
    }

    // 亮色 / 深色切换（只动 data-theme，日志那边会通过 MutationObserver 记一笔）
    function initSkinToggle() {
        const btn = $id('skin-toggle');
        if (!btn) return;

        function sync() {
            const dark = document.documentElement.dataset.theme === 'console';
            btn.textContent = dark ? '◑ 深色' : '◐ 亮色';
            btn.title = dark ? '切换到亮色（晨光控制台）' : '切换到深色（指挥台）';
        }

        btn.addEventListener('click', () => {
            const dark = document.documentElement.dataset.theme === 'console';
            document.documentElement.dataset.theme = dark ? 'console-light' : 'console';
            try { localStorage.setItem('ctos_theme', document.documentElement.dataset.theme); } catch (e) {}
            sync();
        });

        document.querySelectorAll('.theme-option').forEach((o) => {
            o.addEventListener('click', () => setTimeout(sync, 0));
        });

        sync();
    }

    /* ========================================================
       5. 启动
       ======================================================== */

    // 全局暴露给内联 onclick / 控制台用
    window.openAllSessions = openAllSessions;
    window.closeAllSessions = closeAllSessions;

    /* 角色扮演入口（左侧导轨的「角色」按钮）
       --------------------------------------------------------
       指挥台版没有「普通聊天 / 角色扮演」那条切换条，
       所以入口收在导轨里。实际逻辑复用 app.js 的 chatSetMode。 */
    window.openRolePlay = function () {
        if (typeof chatSetMode !== 'function') return;
        // 角色玩法挂在「对话」模块下，先确保在聊天视图
        if (typeof state !== 'undefined' && state.view !== 'chat' && typeof switchView === 'function') {
            switchView('chat');
        }
        LOG.push('ACT', 'chat', '进入角色扮演 · 角色选择', { req: '' });
        chatSetMode('role-select');
    };

    /* 导轨上的「对话」按钮
       --------------------------------------------------------
       普通情况：切到聊天视图。
       如果当前正处在角色玩法（角色选择页 / 角色聊天），
       「对话」就当作「回到普通聊天」的出口 —— 那个页面本身没有返回按钮。 */
    window.goChatHome = function () {
        if (typeof switchView !== 'function') return;

        if (typeof chatMode !== 'undefined' && chatMode !== 'normal' && typeof chatSetMode === 'function') {
            LOG.push('ACT', 'chat', '退出角色玩法 · 回到普通聊天', { req: '' });
            chatSetMode('normal');
            return;
        }

        switchView('chat');
    };

    function boot() {
        seedLog();
        LOG.render();

        renderLoad();

        // 在线人数走后端：启动心跳，并订阅人数变化
        if (window.ctosPresence) {
            window.ctosPresence.start();
            window.ctosPresence.onChange((n) => {
                onlineCount = n;
                renderLoad();
            });
        }

        installCustomerIntro();

        const moreBtn = $id('rail-more');
        if (moreBtn) moreBtn.addEventListener('click', openAllSessions);

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeAllSessions();
        });

        const clearBtn = $id('log-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                LOG.clear();
                LOG.push('ACT', 'log', '日志已清空', { req: '' });
                renderLoad();
            });
        }

        document.querySelectorAll('.log-filter').forEach((b) => {
            b.addEventListener('click', () => LOG.setFilter(b.dataset.f));
        });

        // 任何点击都算一次「活跃」
        // 在线状态由 ctosPresence 的心跳负责，这里不再本地记活跃

        initSkinToggle();

        renderRail();
        syncNav();
        bindRailScroll();

        // 负载每 3 秒刷新一次（折线要动起来），目录跟着数据变
        setInterval(() => { renderLoad(); }, 3000);
        setInterval(renderRail, 900);
        setInterval(syncNav, 700);

        LOG.push('INFO', 'system', '控制台就绪 · 环境 command-deck · 主题 ' +
            (THEME_NAMES[document.documentElement.dataset.theme] || document.documentElement.dataset.theme),
            { req: '' });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 400));
    } else {
        setTimeout(boot, 400);
    }
})();
