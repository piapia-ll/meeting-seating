(function () {
    'use strict';

    if (window.showConfirmModal && window.showPromptModal) return;

    var MODAL_ID = 'generic-dialog-modal';
    var _resolver = null;

    // 全局 modal 开关，供全站页面复用（与 classroom.js 内的实现行为一致）。
    if (typeof window.openModal !== 'function') {
        window.openModal = function (modalId) {
            if (!modalId) return;
            var modal = document.getElementById(modalId);
            if (!modal) return;
            modal.style.display = 'flex';
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    modal.classList.add('modal-visible');
                });
            });
        };
    }
    if (typeof window.closeModal !== 'function') {
        window.closeModal = function (modalId) {
            if (!modalId) return;
            var modal = document.getElementById(modalId);
            if (!modal) return;
            modal.classList.remove('modal-visible');
            var content = modal.querySelector('.modal-content');
            var onEnd = function (e) {
                if (e.target !== content) return;
                modal.style.display = 'none';
                modal.removeEventListener('transitionend', onEnd);
            };
            modal.addEventListener('transitionend', onEnd);
            // 兜底：无过渡动画时也能关闭。
            setTimeout(function () {
                if (!modal.classList.contains('modal-visible')) modal.style.display = 'none';
            }, 350);
        };
    }

    function ensureDom() {
        var modal = document.getElementById(MODAL_ID);
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = MODAL_ID;
        modal.className = 'modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'genericDialogTitle');
        modal.style.display = 'none';
        modal.innerHTML =
            '<div class="modal-content" style="max-width: 400px;">' +
                '<h3 id="genericDialogTitle" style="margin: 0 0 12px; font-size: 16px; font-weight: 600;"></h3>' +
                '<p id="genericDialogMessage" style="margin: 0 0 16px; font-size: 14px; color: var(--text-secondary); line-height: 1.5;"></p>' +
                '<input type="text" id="genericDialogInput" class="modal-field" style="display:none">' +
                '<div class="modal-actions">' +
                    '<button type="button" class="btn btn-secondary" id="genericDialogCancel">取消</button>' +
                    '<button type="button" class="btn btn-primary" id="genericDialogOk">确定</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(modal);
        return modal;
    }

    function freshButtons() {
        var ok = document.getElementById('genericDialogOk');
        var cancel = document.getElementById('genericDialogCancel');
        var input = document.getElementById('genericDialogInput');
        // 克隆重建以清除上一次的监听。
        ok.replaceWith(ok.cloneNode(true));
        cancel.replaceWith(cancel.cloneNode(true));
        input.replaceWith(input.cloneNode(true));
        return {
            ok: document.getElementById('genericDialogOk'),
            cancel: document.getElementById('genericDialogCancel'),
            input: document.getElementById('genericDialogInput')
        };
    }

    function closeDialog() {
        window.closeModal(MODAL_ID);
        _resolver = null;
    }

    function showConfirmModal(message, options) {
        options = options || {};
        var title = options.title || '确认操作';
        var okText = options.okText || '确定';
        var cancelText = options.cancelText || '取消';
        var danger = options.danger === true;
        return new Promise(function (resolve) {
            ensureDom();
            document.getElementById('genericDialogTitle').textContent = title;
            document.getElementById('genericDialogMessage').textContent = message;
            var refs = freshButtons();
            refs.input.style.display = 'none';
            refs.ok.textContent = okText;
            refs.cancel.textContent = cancelText;
            refs.ok.classList.toggle('btn-danger', danger);
            _resolver = resolve;
            refs.ok.addEventListener('click', function () { closeDialog(); resolve(true); });
            refs.cancel.addEventListener('click', function () { closeDialog(); resolve(false); });
            window.openModal(MODAL_ID);
        });
    }

    function showPromptModal(message, options) {
        options = options || {};
        var title = options.title || '请输入';
        var defaultValue = options.defaultValue || '';
        var okText = options.okText || '确定';
        var cancelText = options.cancelText || '取消';
        return new Promise(function (resolve) {
            ensureDom();
            document.getElementById('genericDialogTitle').textContent = title;
            document.getElementById('genericDialogMessage').textContent = message;
            var refs = freshButtons();
            refs.input.style.display = '';
            refs.input.value = defaultValue;
            refs.ok.textContent = okText;
            refs.cancel.textContent = cancelText;
            _resolver = resolve;
            var submit = function () { closeDialog(); resolve(refs.input.value); };
            refs.ok.addEventListener('click', submit);
            refs.input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') { e.preventDefault(); submit(); }
            });
            refs.cancel.addEventListener('click', function () { closeDialog(); resolve(null); });
            window.openModal(MODAL_ID);
            requestAnimationFrame(function () { refs.input.focus(); refs.input.select(); });
        });
    }

    // 云同步冲突等“二选一”场景：主按钮=本地，危险次按钮=云端，取消=中止。
    // resolve('local' | 'cloud' | 'cancel')
    function showChoiceModal(message, options) {
        options = options || {};
        var title = options.title || '请选择';
        var primaryText = options.primaryText || '保留本地版本';
        var altText = options.altText || '使用云端版本';
        var cancelText = options.cancelText || '取消';
        return new Promise(function (resolve) {
            ensureDom();
            document.getElementById('genericDialogTitle').textContent = title;
            document.getElementById('genericDialogMessage').textContent = message;
            var refs = freshButtons();
            refs.input.style.display = 'none';

            refs.ok.textContent = primaryText;
            refs.ok.classList.remove('btn-danger');

            // 复用 cancel 按钮位，额外插入一个“云端”按钮。
            refs.cancel.textContent = cancelText;
            var alt = document.createElement('button');
            alt.type = 'button';
            alt.className = 'btn btn-danger';
            alt.textContent = altText;
            refs.cancel.parentNode.insertBefore(alt, refs.cancel);

            var done = function (choice) {
                if (alt.parentNode) alt.parentNode.removeChild(alt);
                closeDialog();
                resolve(choice);
            };
            refs.ok.addEventListener('click', function () { done('local'); });
            alt.addEventListener('click', function () { done('cloud'); });
            refs.cancel.addEventListener('click', function () { done('cancel'); });
            window.openModal(MODAL_ID);
        });
    }

    window.showConfirmModal = showConfirmModal;
    window.showPromptModal = showPromptModal;
    window.showChoiceModal = showChoiceModal;
})();
