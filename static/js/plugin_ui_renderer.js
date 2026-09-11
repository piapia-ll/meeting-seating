/* 插件动态 UI 渲染器：支持全部 19 种组件 + 统一 Action Runtime + JSON Fallback */
(function () {
    'use strict';

    var root = document.getElementById('plugin-ui-root');
    if (!root) return;

    var refreshBtn = document.getElementById('plugin-ui-refresh-btn');
    var feedback = document.getElementById('plugin-ui-feedback');
    var pluginId = root.dataset.pluginId || '';
    var uiName = root.dataset.uiName || '';
    var endpoint = root.dataset.uiEndpoint || '';

    if (!pluginId || !uiName || !endpoint) {
        root.innerHTML = '<div class="plugin-ui-error">缺少插件 UI 上下文，无法渲染。</div>';
        return;
    }

    var DEFAULT_SPANS = {
        metric: 3, text: 6, list: 6, actions: 12, table: 12, json: 12,
        progress: 6, divider: 12, section: 12, badge: 3, form: 12,
        input: 6, textarea: 6, select: 6, checkbox: 6, radio: 6,
        tabs: 12, alert: 12, button: 3, modal: 6
    };

    function resolveSpan(block) {
        if (block.span) return Math.min(12, Math.max(1, parseInt(block.span, 10) || 3));
        var t = String(block.type || 'json').toLowerCase();
        return DEFAULT_SPANS[t] || 6;
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var rows = (document.cookie || '').split(';');
        for (var i = 0; i < rows.length; i++) {
            var item = rows[i].trim();
            if (item.indexOf('csrftoken=') === 0) {
                return decodeURIComponent(item.substring('csrftoken='.length));
            }
        }
        return '';
    }

    function showFeedback(message, isError) {
        if (!feedback) return;
        feedback.hidden = false;
        feedback.textContent = message || '';
        feedback.className = 'plugin-ui-feedback' + (isError ? ' error' : '');
    }

    function hideFeedback() {
        if (!feedback) return;
        feedback.hidden = true;
        feedback.textContent = '';
        feedback.classList.remove('error');
    }

    function getClassroomIdFromQuery() {
        return new URLSearchParams(window.location.search).get('classroom_id') || null;
    }

    function parseJson(text) {
        try { return JSON.parse(text); } catch (e) { return null; }
    }

    function prettyJson(value) {
        try { return JSON.stringify(value, null, 2); } catch (e) { return String(value); }
    }

    function buildUiUrl() {
        var search = window.location.search || '';
        return search ? endpoint + search : endpoint;
    }

    function el(tag, cls, attrs) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (attrs) {
            for (var k in attrs) {
                if (attrs.hasOwnProperty(k)) node.setAttribute(k, attrs[k]);
            }
        }
        return node;
    }

    function renderSkeleton() {
        root.innerHTML = '';
        var wrap = el('div', 'plugin-ui-loading');
        wrap.textContent = '正在生成界面...';
        root.appendChild(wrap);
    }

    async function loadUi(extraParams) {
        hideFeedback();
        renderSkeleton();
        var url = buildUiUrl();
        if (extraParams) {
            var params = new URLSearchParams(extraParams);
            url += (url.indexOf('?') >= 0 ? '&' : '?') + params.toString();
        }
        var response;
        try {
            response = await fetch(url, {
                method: 'GET',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
        } catch (error) {
            root.innerHTML = '<div class="plugin-ui-error">请求失败：' + error + '</div>';
            return;
        }
        var text = await response.text();
        var payload = parseJson(text);
        if (!response.ok || !payload || payload.status !== 'success') {
            var msg = (payload && payload.message) ? payload.message : (text || '未知错误');
            root.innerHTML = '<div class="plugin-ui-error">生成失败：' + msg + '</div>';
            return;
        }
        renderUi(payload.ui);
    }

    function createCard(title, spanCols) {
        var card = el('article', 'plugin-ui-card');
        if (spanCols && spanCols !== 3) card.classList.add('span-' + spanCols);
        if (title) {
            var h = el('h3');
            h.textContent = title;
            card.appendChild(h);
        }
        return card;
    }

    /* ---------- 统一 Action Runtime ---------- */
    async function invokeAction(item, buttonRef, extraPayload) {
        var classroomId = getClassroomIdFromQuery();
        var method = String(item.method || 'POST').toUpperCase();
        var endpointUrl = item.call || (item.action
            ? '/plugins/' + encodeURIComponent(pluginId) + '/' + encodeURIComponent(item.action) + '/'
            : '');
        if (!endpointUrl) {
            showFeedback('动作缺少 call 或 action', true);
            return null;
        }
        var payload = Object.assign({}, item.payload || {}, extraPayload || {});
        if (classroomId && payload.classroom_id == null) payload.classroom_id = classroomId;

        if (buttonRef) { buttonRef.disabled = true; buttonRef.classList.add('is-busy'); }
        try {
            var response;
            if (method === 'GET') {
                var params = new URLSearchParams();
                Object.keys(payload).forEach(function (key) {
                    if (payload[key] != null) params.set(key, String(payload[key]));
                });
                var url = params.toString() ? endpointUrl + '?' + params.toString() : endpointUrl;
                response = await fetch(url, { method: 'GET', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            } else {
                response = await fetch(endpointUrl, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify(payload)
                });
            }
            var text = await response.text();
            var result = parseJson(text);
            if (!response.ok || !result || result.status !== 'success') {
                var errMsg = (result && result.message) ? result.message : text;
                showFeedback('执行失败：' + (errMsg || '未知错误'), true);
                return null;
            }
            showFeedback(item.success_message || '执行成功', false);
            if (item.refresh_ui !== false) await loadUi();
            return result;
        } catch (error) {
            showFeedback('执行失败：' + error, true);
            return null;
        } finally {
            if (buttonRef) { buttonRef.disabled = false; buttonRef.classList.remove('is-busy'); }
        }
    }

    /* ---------- 展示组件 ---------- */
    function renderMetric(block) {
        var card = createCard('', resolveSpan(block));
        var label = el('div', 'plugin-ui-metric-label');
        label.textContent = block.label || '指标';
        var value = el('div', 'plugin-ui-metric-value');
        value.textContent = block.value == null ? '-' : String(block.value);
        card.appendChild(label);
        card.appendChild(value);
        if (block.hint) {
            var hint = el('div', 'plugin-ui-metric-hint');
            hint.textContent = String(block.hint);
            card.appendChild(hint);
        }
        return card;
    }

    function renderText(block) {
        var card = createCard(block.title || '说明', resolveSpan(block));
        var body = el('div', 'plugin-ui-text-body');
        body.textContent = block.text || '';
        card.appendChild(body);
        return card;
    }

    function renderList(block) {
        var card = createCard(block.title || '列表', resolveSpan(block));
        var list = el('ul', 'plugin-ui-list');
        var items = Array.isArray(block.items) ? block.items : [];
        if (!items.length) items = [block.empty_text || '暂无数据'];
        items.forEach(function (item) {
            var li = el('li');
            li.textContent = item == null ? '' : String(item);
            list.appendChild(li);
        });
        card.appendChild(list);
        return card;
    }

    function renderTable(block) {
        var card = createCard(block.title || '表格', resolveSpan(block));
        var columns = Array.isArray(block.columns) ? block.columns : [];
        var rows = Array.isArray(block.rows) ? block.rows : [];
        var wrap = el('div', 'plugin-ui-table-wrap');
        var table = el('table', 'plugin-ui-table');
        if (columns.length) {
            var thead = el('thead');
            var tr = el('tr');
            columns.forEach(function (col) {
                var th = el('th');
                th.textContent = String((col && (col.label || col.key)) || '');
                tr.appendChild(th);
            });
            thead.appendChild(tr);
            table.appendChild(thead);
        }
        var tbody = el('tbody');
        if (rows.length) {
            rows.forEach(function (row) {
                var tr = el('tr');
                if (columns.length) {
                    columns.forEach(function (col) {
                        var td = el('td');
                        var key = col && col.key ? col.key : '';
                        var val = key && row && typeof row === 'object' ? row[key] : '';
                        td.textContent = val == null ? '' : String(val);
                        tr.appendChild(td);
                    });
                } else {
                    var td = el('td');
                    td.textContent = row == null ? '' : String(row);
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            });
        } else {
            var tr = el('tr');
            var td = el('td');
            td.textContent = block.empty_text || '暂无数据';
            if (columns.length) td.colSpan = columns.length;
            tr.appendChild(td);
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        wrap.appendChild(table);
        card.appendChild(wrap);
        return card;
    }

    function renderActions(block) {
        var card = createCard(block.title || '动作', resolveSpan(block));
        var wrap = el('div', 'plugin-ui-actions');
        var items = Array.isArray(block.items) ? block.items : [];
        items.forEach(function (item) {
            var button = el('button', 'plugin-ui-action-btn');
            button.type = 'button';
            if (item.variant === 'secondary') button.classList.add('secondary');
            button.textContent = item.label || item.action || '执行动作';
            button.addEventListener('click', function () { invokeAction(item, button); });
            wrap.appendChild(button);
        });
        card.appendChild(wrap);
        return card;
    }

    function renderProgress(block) {
        var card = createCard(block.title || '进度', resolveSpan(block));
        var wrap = el('div', 'plugin-ui-progress-wrap');
        var bar = el('div', 'plugin-ui-progress-bar');
        var fill = el('div', 'plugin-ui-progress-fill');
        var pct = Math.max(0, Math.min(100, parseFloat(block.value) || 0));
        fill.style.width = pct + '%';
        bar.appendChild(fill);
        wrap.appendChild(bar);
        var info = el('div', 'plugin-ui-progress-info');
        var labelEl = el('span');
        labelEl.textContent = block.label || '';
        var valEl = el('span');
        valEl.textContent = block.hint || (pct + '%');
        info.appendChild(labelEl);
        info.appendChild(valEl);
        wrap.appendChild(info);
        card.appendChild(wrap);
        return card;
    }

    function renderDivider() {
        return el('hr', 'plugin-ui-divider');
    }

    function renderSection(block) {
        var wrap = el('div', 'plugin-ui-section-header');
        var title = el('span', 'plugin-ui-section-title');
        title.textContent = block.title || '';
        wrap.appendChild(title);
        if (block.subtitle) {
            var sub = el('span', 'plugin-ui-section-subtitle');
            sub.textContent = block.subtitle;
            wrap.appendChild(sub);
        }
        return wrap;
    }

    function renderBadge(block) {
        var card = createCard('', resolveSpan(block));
        var badge = el('span', 'plugin-ui-badge');
        badge.classList.add('badge-' + (block.variant || 'primary'));
        badge.textContent = block.text || block.label || '';
        card.appendChild(badge);
        return card;
    }

    function renderJson(block) {
        var card = createCard(block.title || '数据', resolveSpan(block));
        var pre = el('pre', 'plugin-ui-json');
        pre.textContent = prettyJson(block.value == null ? block : block.value);
        card.appendChild(pre);
        return card;
    }

    /* ---------- 表单字段 ---------- */
    function applyCommonFieldAttrs(input, block) {
        if (block.name) input.name = block.name;
        if (block.placeholder) input.placeholder = block.placeholder;
        if (block.required) input.required = true;
        if (block.value != null && input.type !== 'checkbox' && input.type !== 'radio') {
            input.value = block.value;
        }
    }

    function fieldWrapper(block, control) {
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-field-card');
        if (block.label) {
            var lab = el('label', 'plugin-ui-field-label');
            lab.textContent = block.label + (block.required ? ' *' : '');
            card.appendChild(lab);
        }
        card.appendChild(control);
        if (block.hint || block.description) {
            var hint = el('div', 'plugin-ui-field-hint');
            hint.textContent = block.hint || block.description;
            card.appendChild(hint);
        }
        return card;
    }

    function renderInput(block) {
        var input = el('input', 'plugin-ui-input');
        input.type = block.input_type || 'text';
        applyCommonFieldAttrs(input, block);
        return fieldWrapper(block, input);
    }

    function renderTextarea(block) {
        var ta = el('textarea', 'plugin-ui-input');
        ta.rows = parseInt(block.rows, 10) || 3;
        applyCommonFieldAttrs(ta, block);
        return fieldWrapper(block, ta);
    }

    function renderSelect(block) {
        var sel = el('select', 'plugin-ui-input');
        applyCommonFieldAttrs(sel, block);
        var options = Array.isArray(block.options) ? block.options : [];
        options.forEach(function (opt) {
            var o = el('option');
            var val = (opt && typeof opt === 'object') ? opt.value : opt;
            var lab = (opt && typeof opt === 'object') ? (opt.label != null ? opt.label : opt.value) : opt;
            o.value = val == null ? '' : String(val);
            o.textContent = lab == null ? '' : String(lab);
            if (block.value != null && String(val) === String(block.value)) o.selected = true;
            sel.appendChild(o);
        });
        return fieldWrapper(block, sel);
    }

    function renderCheckbox(block) {
        var wrap = el('label', 'plugin-ui-check');
        var input = el('input');
        input.type = 'checkbox';
        if (block.name) input.name = block.name;
        if (block.value === true || block.checked === true) input.checked = true;
        var span = el('span');
        span.textContent = block.label || '';
        wrap.appendChild(input);
        wrap.appendChild(span);
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-field-card');
        card.appendChild(wrap);
        return card;
    }

    function renderRadio(block) {
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-field-card');
        if (block.label) {
            var lab = el('label', 'plugin-ui-field-label');
            lab.textContent = block.label;
            card.appendChild(lab);
        }
        var options = Array.isArray(block.options) ? block.options : [];
        options.forEach(function (opt) {
            var wrap = el('label', 'plugin-ui-check');
            var input = el('input');
            input.type = 'radio';
            if (block.name) input.name = block.name;
            var val = (opt && typeof opt === 'object') ? opt.value : opt;
            input.value = val == null ? '' : String(val);
            if (block.value != null && String(val) === String(block.value)) input.checked = true;
            var span = el('span');
            span.textContent = (opt && typeof opt === 'object') ? String(opt.label != null ? opt.label : opt.value) : String(opt);
            wrap.appendChild(input);
            wrap.appendChild(span);
            card.appendChild(wrap);
        });
        return card;
    }

    /* ---------- 交互容器 ---------- */
    function renderForm(block) {
        var card = createCard(block.title || '表单', resolveSpan(block));
        if (block.description) {
            var d = el('div', 'plugin-ui-field-hint');
            d.textContent = block.description;
            card.appendChild(d);
        }
        var form = el('form', 'plugin-ui-form');
        form.setAttribute('novalidate', 'novalidate');
        var grid = el('div', 'plugin-ui-blocks');
        var fields = Array.isArray(block.fields) ? block.fields : [];
        fields.forEach(function (field) {
            grid.appendChild(renderBlock(field));
        });
        form.appendChild(grid);
        var submit = el('button', 'plugin-ui-action-btn');
        submit.type = 'submit';
        submit.textContent = block.submit_label || '提交';
        form.appendChild(submit);

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var payload = {};
            var invalid = false;
            fields.forEach(function (field) {
                if (!field || !field.name) return;
                var node = form.querySelector('[name="' + field.name + '"]');
                if (!node) return;
                var val;
                if (node.type === 'checkbox') val = node.checked;
                else if (node.type === 'radio') {
                    var checked = form.querySelector('[name="' + field.name + '"]:checked');
                    val = checked ? checked.value : '';
                } else val = node.value;
                if (field.required && (val === '' || val == null)) {
                    invalid = true;
                    node.classList && node.classList.add('plugin-ui-input-invalid');
                } else {
                    node.classList && node.classList.remove('plugin-ui-input-invalid');
                }
                if (field.type === 'select' && val !== '' && !isNaN(Number(val)) && String(val).trim() !== '') {
                    val = Number(val);
                }
                payload[field.name] = val;
            });
            if (invalid) {
                showFeedback('请完整填写必填字段', true);
                return;
            }
            invokeAction({
                action: block.action,
                method: block.method || 'POST',
                payload: payload,
                success_message: block.success_message
            }, submit);
        });
        card.appendChild(form);
        return card;
    }

    function renderTabs(block) {
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-tabs-card');
        var items = Array.isArray(block.items) ? block.items : [];
        var nav = el('div', 'plugin-ui-tabs-nav');
        var body = el('div', 'plugin-ui-tabs-body');
        var activeId = block.active != null ? String(block.active) : (items[0] && items[0].id != null ? String(items[0].id) : '');
        items.forEach(function (item, idx) {
            var id = item && item.id != null ? String(item.id) : String(idx);
            var tabBtn = el('button', 'plugin-ui-tab-btn' + (id === activeId ? ' active' : ''));
            tabBtn.type = 'button';
            tabBtn.textContent = item.label || ('Tab ' + (idx + 1));
            tabBtn.dataset.tabId = id;
            var pane = el('div', 'plugin-ui-tab-pane' + (id === activeId ? ' active' : ''));
            pane.dataset.tabId = id;
            var inner = el('div', 'plugin-ui-blocks');
            (Array.isArray(item.blocks) ? item.blocks : []).forEach(function (b) {
                inner.appendChild(renderBlock(b));
            });
            pane.appendChild(inner);
            nav.appendChild(tabBtn);
            body.appendChild(pane);
        });
        nav.addEventListener('click', function (e) {
            var btn = e.target.closest('.plugin-ui-tab-btn');
            if (!btn) return;
            var id = btn.dataset.tabId;
            nav.querySelectorAll('.plugin-ui-tab-btn').forEach(function (b) {
                b.classList.toggle('active', b.dataset.tabId === id);
            });
            body.querySelectorAll('.plugin-ui-tab-pane').forEach(function (p) {
                p.classList.toggle('active', p.dataset.tabId === id);
            });
        });
        card.appendChild(nav);
        card.appendChild(body);
        return card;
    }

    function renderAlert(block) {
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-alert-card');
        var box = el('div', 'plugin-ui-alert alert-' + (block.variant || 'info'));
        if (block.title) {
            var t = el('div', 'plugin-ui-alert-title');
            t.textContent = block.title;
            box.appendChild(t);
        }
        var body = el('div', 'plugin-ui-alert-body');
        body.textContent = block.text || block.message || '';
        box.appendChild(body);
        card.appendChild(box);
        return card;
    }

    function renderButton(block) {
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-field-card');
        var btn = el('button', 'plugin-ui-action-btn');
        btn.type = 'button';
        if (block.variant === 'secondary') btn.classList.add('secondary');
        if (block.variant === 'danger') btn.classList.add('danger');
        btn.textContent = block.label || block.action || '执行';
        btn.addEventListener('click', function () {
            invokeAction({
                action: block.action,
                method: block.method || 'POST',
                payload: block.payload,
                success_message: block.success_message,
                refresh_ui: block.refresh_ui
            }, btn);
        });
        card.appendChild(btn);
        return card;
    }

    function renderModal(block) {
        var card = createCard('', resolveSpan(block));
        card.classList.add('plugin-ui-field-card');
        var trigger = el('button', 'plugin-ui-action-btn secondary');
        trigger.type = 'button';
        trigger.textContent = block.trigger_label || block.title || '打开';
        var overlay = el('div', 'plugin-ui-modal-overlay');
        overlay.setAttribute('hidden', 'hidden');
        var modal = el('div', 'plugin-ui-modal');
        var head = el('div', 'plugin-ui-modal-head');
        var t = el('h3');
        t.textContent = block.title || '';
        var close = el('button', 'plugin-ui-modal-close');
        close.type = 'button';
        close.textContent = '×';
        head.appendChild(t);
        head.appendChild(close);
        var inner = el('div', 'plugin-ui-blocks');
        (Array.isArray(block.blocks) ? block.blocks : []).forEach(function (b) {
            inner.appendChild(renderBlock(b));
        });
        modal.appendChild(head);
        modal.appendChild(inner);
        overlay.appendChild(modal);
        trigger.addEventListener('click', function () { overlay.removeAttribute('hidden'); });
        function dismiss() { overlay.setAttribute('hidden', 'hidden'); }
        close.addEventListener('click', dismiss);
        overlay.addEventListener('click', function (e) { if (e.target === overlay) dismiss(); });
        card.appendChild(trigger);
        card.appendChild(overlay);
        return card;
    }

    /* ---------- 分发 ---------- */
    function renderBlock(block) {
        var safeBlock = (block && typeof block === 'object') ? block : { type: 'json', value: block };
        var t = String(safeBlock.type || 'json').toLowerCase();
        switch (t) {
            case 'metric':   return renderMetric(safeBlock);
            case 'text':     return renderText(safeBlock);
            case 'list':     return renderList(safeBlock);
            case 'actions':  return renderActions(safeBlock);
            case 'table':    return renderTable(safeBlock);
            case 'progress': return renderProgress(safeBlock);
            case 'divider':  return renderDivider();
            case 'section':  return renderSection(safeBlock);
            case 'badge':    return renderBadge(safeBlock);
            case 'input':    return renderInput(safeBlock);
            case 'textarea': return renderTextarea(safeBlock);
            case 'select':   return renderSelect(safeBlock);
            case 'checkbox': return renderCheckbox(safeBlock);
            case 'radio':    return renderRadio(safeBlock);
            case 'form':     return renderForm(safeBlock);
            case 'tabs':     return renderTabs(safeBlock);
            case 'alert':    return renderAlert(safeBlock);
            case 'button':   return renderButton(safeBlock);
            case 'modal':    return renderModal(safeBlock);
            default:         return renderJson({ title: '未知组件 (' + t + ')', value: safeBlock });
        }
    }

    function renderUi(uiPayload) {
        if (uiPayload == null) {
            root.innerHTML = '<div class="plugin-ui-empty">插件未返回 UI 数据</div>';
            return;
        }
        var shell = el('section', 'plugin-ui-shell');
        if (uiPayload && typeof uiPayload === 'object' && !Array.isArray(uiPayload) && uiPayload.type === 'page') {
            if (uiPayload.theme && uiPayload.theme.primary) {
                document.documentElement.style.setProperty('--primary-color', String(uiPayload.theme.primary));
                document.documentElement.style.setProperty('--pui-primary', String(uiPayload.theme.primary));
            }
            var title = el('h2', 'plugin-ui-title');
            title.textContent = uiPayload.title || (pluginId + '/' + uiName);
            shell.appendChild(title);
            if (uiPayload.subtitle) {
                var subtitle = el('div', 'plugin-ui-subtitle');
                subtitle.textContent = String(uiPayload.subtitle);
                shell.appendChild(subtitle);
            }
            var blocksWrap = el('div', 'plugin-ui-blocks');
            (Array.isArray(uiPayload.blocks) ? uiPayload.blocks : []).forEach(function (block) {
                blocksWrap.appendChild(renderBlock(block));
            });
            shell.appendChild(blocksWrap);
        } else if (Array.isArray(uiPayload)) {
            var bw = el('div', 'plugin-ui-blocks');
            uiPayload.forEach(function (block) { bw.appendChild(renderBlock(block)); });
            shell.appendChild(bw);
        } else {
            var bw2 = el('div', 'plugin-ui-blocks');
            bw2.appendChild(renderJson({ title: 'UI 数据', value: uiPayload }));
            shell.appendChild(bw2);
        }
        root.innerHTML = '';
        root.appendChild(shell);
    }

    if (refreshBtn) refreshBtn.addEventListener('click', function () { loadUi(); });
    loadUi();
})();
