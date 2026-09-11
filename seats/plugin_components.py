from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


ComponentFactory = Callable[[dict[str, Any]], dict[str, Any]]


class PluginComponentLibrary:
    def __init__(self):
        self._components: dict[str, ComponentFactory] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register('metric', self._build_metric)
        self.register('text', self._build_text)
        self.register('list', self._build_list)
        self.register('actions', self._build_actions)
        self.register('table', self._build_table)
        self.register('progress', self._build_progress)
        self.register('divider', self._build_divider)
        self.register('section', self._build_section)
        self.register('badge', self._build_badge)
        self.register('input', self._build_input)
        self.register('textarea', self._build_textarea)
        self.register('select', self._build_select)
        self.register('checkbox', self._build_checkbox)
        self.register('radio', self._build_radio)
        self.register('form', self._build_form)
        self.register('tabs', self._build_tabs)
        self.register('alert', self._build_alert)
        self.register('button', self._build_button)
        self.register('modal', self._build_modal)

    def register(self, name: str, factory: ComponentFactory):
        key = str(name or '').strip()
        if not key:
            raise ValueError('组件名称不能为空')
        if not callable(factory):
            raise ValueError('组件工厂必须是可调用对象')
        self._components[key] = factory

    def names(self) -> list[str]:
        return sorted(self._components.keys())

    def exists(self, name: str) -> bool:
        return str(name or '').strip() in self._components

    def call(self, component_name: str, **props):
        key = str(component_name or '').strip()
        if key not in self._components:
            raise ValueError(f'组件不存在：{key}')
        result = self._components[key](dict(props))
        if not isinstance(result, dict):
            raise ValueError('组件返回值必须是 dict')
        return deepcopy(result)

    def page(self, *, title: str, subtitle: str = '', blocks: list[dict[str, Any]] | None = None, theme=None):
        payload = {
            'type': 'page',
            'title': str(title or ''),
            'blocks': list(blocks or []),
        }
        if subtitle:
            payload['subtitle'] = str(subtitle)
        if isinstance(theme, dict) and theme:
            payload['theme'] = deepcopy(theme)
        return payload

    def metric(self, label: str, value: Any, hint: str = '', span: int | None = None):
        props: dict[str, Any] = {'label': label, 'value': value}
        if hint:
            props['hint'] = hint
        if span is not None:
            props['span'] = span
        return self.call('metric', **props)

    def text(self, title: str, text: str, span: int | None = None):
        props: dict[str, Any] = {'title': title, 'text': text}
        if span is not None:
            props['span'] = span
        return self.call('text', **props)

    def list(self, title: str, items: list[Any] | None = None, empty_text: str = '暂无数据', span: int | None = None):
        props: dict[str, Any] = {'title': title, 'items': items or [], 'empty_text': empty_text}
        if span is not None:
            props['span'] = span
        return self.call('list', **props)

    def actions(self, title: str, items: list[dict[str, Any]] | None = None, span: int | None = None):
        props: dict[str, Any] = {'title': title, 'items': items or []}
        if span is not None:
            props['span'] = span
        return self.call('actions', **props)

    def table(self, title: str, columns: list[dict[str, Any]] | None = None, rows: list[dict[str, Any]] | None = None, span: int | None = None):
        props: dict[str, Any] = {'title': title, 'columns': columns or [], 'rows': rows or []}
        if span is not None:
            props['span'] = span
        return self.call('table', **props)

    def progress(self, title: str, value: float, label: str = '', hint: str = '', span: int | None = None):
        props: dict[str, Any] = {'title': title, 'value': value}
        if label:
            props['label'] = label
        if hint:
            props['hint'] = hint
        if span is not None:
            props['span'] = span
        return self.call('progress', **props)

    def divider(self):
        return self.call('divider')

    def section(self, title: str, subtitle: str = ''):
        props: dict[str, Any] = {'title': title}
        if subtitle:
            props['subtitle'] = subtitle
        return self.call('section', **props)

    def badge(self, text: str, variant: str = 'primary', span: int | None = None):
        props: dict[str, Any] = {'text': text, 'variant': variant}
        if span is not None:
            props['span'] = span
        return self.call('badge', **props)

    def input(self, name: str, label: str, value: Any = '', placeholder: str = '', input_type: str = 'text', required: bool = False, span: int | None = None):
        return self.call(
            'input', name=name, label=label, value=value, placeholder=placeholder,
            input_type=input_type, required=required, span=span,
        )

    def textarea(self, name: str, label: str, value: Any = '', placeholder: str = '', rows: int = 4, required: bool = False, span: int | None = None):
        return self.call(
            'textarea', name=name, label=label, value=value, placeholder=placeholder,
            rows=rows, required=required, span=span,
        )

    def select(self, name: str, label: str, options=None, value: Any = '', required: bool = False, multiple: bool = False, span: int | None = None):
        return self.call(
            'select', name=name, label=label, options=options or [], value=value,
            required=required, multiple=multiple, span=span,
        )

    def checkbox(self, name: str, label: str, checked: bool = False, value: Any = True, span: int | None = None):
        return self.call('checkbox', name=name, label=label, checked=checked, value=value, span=span)

    def radio(self, name: str, label: str, options=None, value: Any = '', required: bool = False, span: int | None = None):
        return self.call(
            'radio', name=name, label=label, options=options or [], value=value,
            required=required, span=span,
        )

    def form(self, title: str, action: str, fields=None, method: str = 'POST', submit_label: str = '提交', description: str = '', span: int | None = None):
        return self.call(
            'form', title=title, action=action, fields=fields or [], method=method,
            submit_label=submit_label, description=description, span=span,
        )

    def tabs(self, items=None, active: str = '', span: int | None = None):
        return self.call('tabs', items=items or [], active=active, span=span)

    def alert(self, title: str, message: str, variant: str = 'info', span: int | None = None):
        return self.call('alert', title=title, message=message, variant=variant, span=span)

    def button(self, label: str, action: str = '', method: str = 'POST', payload=None, variant: str = 'primary', span: int | None = None):
        return self.call(
            'button', label=label, action=action, method=method, payload=payload or {},
            variant=variant, span=span,
        )

    def modal(self, modal_id: str, title: str, blocks=None, trigger_label: str = '', span: int | None = None):
        return self.call(
            'modal', modal_id=modal_id, title=title, blocks=blocks or [],
            trigger_label=trigger_label, span=span,
        )

    @staticmethod
    def _apply_span(result: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
        span = props.get('span')
        if span is not None:
            result['span'] = max(1, min(12, int(span)))
        return result

    @staticmethod
    def _build_metric(props: dict[str, Any]):
        result = {
            'type': 'metric',
            'label': str(props.get('label') or '指标'),
            'value': props.get('value'),
        }
        if props.get('hint') not in (None, ''):
            result['hint'] = str(props.get('hint'))
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_text(props: dict[str, Any]):
        result = {
            'type': 'text',
            'title': str(props.get('title') or '说明'),
            'text': str(props.get('text') or ''),
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_list(props: dict[str, Any]):
        items = props.get('items')
        if not isinstance(items, list):
            items = []
        if not items:
            empty_text = str(props.get('empty_text') or '暂无数据')
            items = [empty_text]
        result = {
            'type': 'list',
            'title': str(props.get('title') or '列表'),
            'items': items,
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_actions(props: dict[str, Any]):
        items = props.get('items')
        if not isinstance(items, list):
            items = []
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            row = {
                'label': str(item.get('label') or '执行动作'),
            }
            for key in ('action', 'call', 'method', 'variant', 'success_message'):
                if key in item and item.get(key) not in (None, ''):
                    row[key] = item.get(key)
            payload = item.get('payload')
            if isinstance(payload, dict):
                row['payload'] = payload
            if item.get('refresh_ui') is False:
                row['refresh_ui'] = False
            normalized.append(row)

        result = {
            'type': 'actions',
            'title': str(props.get('title') or '动作'),
            'items': normalized,
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_table(props: dict[str, Any]):
        columns = props.get('columns')
        rows = props.get('rows')
        if not isinstance(columns, list):
            columns = []
        if not isinstance(rows, list):
            rows = []
        result = {
            'type': 'table',
            'title': str(props.get('title') or '表格'),
            'columns': columns,
            'rows': rows,
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_progress(props: dict[str, Any]):
        value = props.get('value', 0)
        try:
            value = max(0, min(100, float(value)))
        except (TypeError, ValueError):
            value = 0
        result = {
            'type': 'progress',
            'title': str(props.get('title') or '进度'),
            'value': value,
        }
        if props.get('label') not in (None, ''):
            result['label'] = str(props.get('label'))
        if props.get('hint') not in (None, ''):
            result['hint'] = str(props.get('hint'))
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_divider(props: dict[str, Any]):
        return {'type': 'divider'}

    @staticmethod
    def _build_section(props: dict[str, Any]):
        result = {
            'type': 'section',
            'title': str(props.get('title') or ''),
        }
        if props.get('subtitle') not in (None, ''):
            result['subtitle'] = str(props.get('subtitle'))
        return result

    @staticmethod
    def _build_badge(props: dict[str, Any]):
        result = {
            'type': 'badge',
            'text': str(props.get('text') or ''),
            'variant': str(props.get('variant') or 'primary'),
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _field_base(component_type: str, props: dict[str, Any]):
        name = str(props.get('name') or '').strip()
        if not name:
            raise ValueError(f'{component_type} 组件缺少 name')
        result = {
            'type': component_type,
            'name': name,
            'label': str(props.get('label') or name),
        }
        if props.get('value') is not None:
            result['value'] = deepcopy(props.get('value'))
        if props.get('placeholder') not in (None, ''):
            result['placeholder'] = str(props.get('placeholder'))
        if props.get('required'):
            result['required'] = True
        if props.get('help_text') not in (None, ''):
            result['help_text'] = str(props.get('help_text'))
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _normalize_options(options):
        rows = []
        for item in options if isinstance(options, list) else []:
            if isinstance(item, dict):
                value = item.get('value')
                rows.append({
                    'value': value,
                    'label': str(item.get('label') if item.get('label') is not None else value),
                    **({'disabled': True} if item.get('disabled') else {}),
                })
            else:
                rows.append({'value': item, 'label': str(item)})
        return rows

    @staticmethod
    def _build_input(props: dict[str, Any]):
        result = PluginComponentLibrary._field_base('input', props)
        input_type = str(props.get('input_type') or props.get('inputType') or 'text').strip().lower()
        allowed = {'text', 'search', 'number', 'email', 'url', 'password', 'date', 'time'}
        result['input_type'] = input_type if input_type in allowed else 'text'
        for key in ('min', 'max', 'step', 'max_length'):
            if props.get(key) is not None:
                result[key] = props.get(key)
        return result

    @staticmethod
    def _build_textarea(props: dict[str, Any]):
        result = PluginComponentLibrary._field_base('textarea', props)
        try:
            result['rows'] = max(2, min(20, int(props.get('rows') or 4)))
        except (TypeError, ValueError):
            result['rows'] = 4
        return result

    @staticmethod
    def _build_select(props: dict[str, Any]):
        result = PluginComponentLibrary._field_base('select', props)
        result['options'] = PluginComponentLibrary._normalize_options(props.get('options'))
        if props.get('multiple'):
            result['multiple'] = True
        return result

    @staticmethod
    def _build_checkbox(props: dict[str, Any]):
        result = PluginComponentLibrary._field_base('checkbox', props)
        result['checked'] = bool(props.get('checked'))
        return result

    @staticmethod
    def _build_radio(props: dict[str, Any]):
        result = PluginComponentLibrary._field_base('radio', props)
        result['options'] = PluginComponentLibrary._normalize_options(props.get('options'))
        return result

    @staticmethod
    def _build_form(props: dict[str, Any]):
        fields = props.get('fields') if isinstance(props.get('fields'), list) else []
        allowed_fields = {'input', 'textarea', 'select', 'checkbox', 'radio'}
        normalized_fields = [deepcopy(item) for item in fields if isinstance(item, dict) and item.get('type') in allowed_fields]
        action = str(props.get('action') or '').strip()
        if not action:
            raise ValueError('form 组件缺少 action')
        result = {
            'type': 'form',
            'title': str(props.get('title') or '表单'),
            'action': action,
            'method': str(props.get('method') or 'POST').upper(),
            'submit_label': str(props.get('submit_label') or '提交'),
            'fields': normalized_fields,
        }
        if props.get('description'):
            result['description'] = str(props.get('description'))
        if props.get('success_message'):
            result['success_message'] = str(props.get('success_message'))
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_tabs(props: dict[str, Any]):
        rows = []
        for index, item in enumerate(props.get('items') if isinstance(props.get('items'), list) else []):
            if not isinstance(item, dict):
                continue
            tab_id = str(item.get('id') or f'tab-{index + 1}')
            rows.append({
                'id': tab_id,
                'label': str(item.get('label') or tab_id),
                'blocks': [deepcopy(block) for block in (item.get('blocks') or []) if isinstance(block, dict)],
            })
        result = {'type': 'tabs', 'items': rows}
        result['active'] = str(props.get('active') or (rows[0]['id'] if rows else ''))
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_alert(props: dict[str, Any]):
        variant = str(props.get('variant') or 'info').lower()
        if variant not in {'info', 'success', 'warning', 'danger'}:
            variant = 'info'
        result = {
            'type': 'alert',
            'title': str(props.get('title') or ''),
            'message': str(props.get('message') or ''),
            'variant': variant,
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_button(props: dict[str, Any]):
        result = {
            'type': 'button',
            'label': str(props.get('label') or '执行'),
            'action': str(props.get('action') or ''),
            'method': str(props.get('method') or 'POST').upper(),
            'variant': str(props.get('variant') or 'primary'),
            'payload': deepcopy(props.get('payload')) if isinstance(props.get('payload'), dict) else {},
        }
        return PluginComponentLibrary._apply_span(result, props)

    @staticmethod
    def _build_modal(props: dict[str, Any]):
        modal_id = str(props.get('modal_id') or '').strip()
        if not modal_id:
            raise ValueError('modal 组件缺少 modal_id')
        result = {
            'type': 'modal',
            'id': modal_id,
            'title': str(props.get('title') or ''),
            'blocks': [deepcopy(block) for block in (props.get('blocks') or []) if isinstance(block, dict)],
        }
        if props.get('trigger_label'):
            result['trigger_label'] = str(props.get('trigger_label'))
        return PluginComponentLibrary._apply_span(result, props)


@dataclass
class PluginComponentScope:
    plugin_id: str
    library: PluginComponentLibrary

    def names(self):
        return self.library.names()

    def exists(self, name: str):
        return self.library.exists(name)

    def call(self, component_name: str, **props):
        return self.library.call(component_name, **props)

    def page(self, **kwargs):
        return self.library.page(**kwargs)

    def metric(self, label, value, hint='', span=None):
        return self.library.metric(label, value, hint, span)

    def text(self, title, text, span=None):
        return self.library.text(title, text, span)

    def list(self, title, items=None, empty_text='暂无数据', span=None):
        return self.library.list(title, items or [], empty_text, span)

    def actions(self, title, items=None, span=None):
        return self.library.actions(title, items or [], span)

    def table(self, title, columns=None, rows=None, span=None):
        return self.library.table(title, columns or [], rows or [], span)

    def progress(self, title, value, label='', hint='', span=None):
        return self.library.progress(title, value, label, hint, span)

    def divider(self):
        return self.library.divider()

    def section(self, title, subtitle=''):
        return self.library.section(title, subtitle)

    def badge(self, text, variant='primary', span=None):
        return self.library.badge(text, variant, span)

    def input(self, name, label, value='', placeholder='', input_type='text', required=False, span=None):
        return self.library.input(name, label, value, placeholder, input_type, required, span)

    def textarea(self, name, label, value='', placeholder='', rows=4, required=False, span=None):
        return self.library.textarea(name, label, value, placeholder, rows, required, span)

    def select(self, name, label, options=None, value='', required=False, multiple=False, span=None):
        return self.library.select(name, label, options or [], value, required, multiple, span)

    def checkbox(self, name, label, checked=False, value=True, span=None):
        return self.library.checkbox(name, label, checked, value, span)

    def radio(self, name, label, options=None, value='', required=False, span=None):
        return self.library.radio(name, label, options or [], value, required, span)

    def form(self, title, action, fields=None, method='POST', submit_label='提交', description='', span=None):
        return self.library.form(title, action, fields or [], method, submit_label, description, span)

    def tabs(self, items=None, active='', span=None):
        return self.library.tabs(items or [], active, span)

    def alert(self, title, message, variant='info', span=None):
        return self.library.alert(title, message, variant, span)

    def button(self, label, action='', method='POST', payload=None, variant='primary', span=None):
        return self.library.button(label, action, method, payload or {}, variant, span)

    def modal(self, modal_id, title, blocks=None, trigger_label='', span=None):
        return self.library.modal(modal_id, title, blocks or [], trigger_label, span)


plugin_component_library = PluginComponentLibrary()


def get_component_scope(plugin_id: str):
    return PluginComponentScope(plugin_id=str(plugin_id or ''), library=plugin_component_library)
