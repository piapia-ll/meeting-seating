PLUGIN_META = {
    'id': 'student_search_plugin',
    'name': '学生搜索插件',
    'version': '3.0.0',
    'description': '在工作界面快速搜索学生，并定位座位。',
    'author': '老三',
    'website': 'www.577622.xyz',
}


def _coerce_limit(raw_value, default=20, min_value=1, max_value=50):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, value))


def _search_students(context):
    payload = context.get('payload') or {}
    classroom = context.get('classroom')
    keyword = str(payload.get('query') or payload.get('keyword') or '').strip()
    limit = _coerce_limit(payload.get('limit'), default=20)

    if classroom is None:
        return {
            'query': keyword,
            'count': 0,
            'items': [],
            'message': '缺少 classroom 上下文，请在请求中附带 classroom_id。',
        }

    rows = context.students.search(keyword, classroom=classroom, limit=limit)

    return {
        'query': keyword,
        'count': len(rows),
        'items': rows,
        'limit': limit,
    }


STUDENT_SEARCH_UI_SCRIPT = """
payload_obj = payload if isinstance(payload, dict) else {}
query = str(payload_obj.get('query') or payload_obj.get('keyword') or '').strip()
limit_raw = payload_obj.get('limit', 20)
try:
    limit = int(limit_raw)
except Exception:
    limit = 20
if limit < 1:
    limit = 1
if limit > 50:
    limit = 50

students_data = ctx.students.search(query, limit=limit) if classroom else []
total_count = len(ctx.students.list(limit=500)) if classroom else 0

rows = []
if classroom:
    for student in students_data:
        seat = student.get('seat')
        seat_text = f"{seat.get('row')}-{seat.get('col')}" if seat else '未入座'
        rows.append({
            'name': student.get('name') or '',
            'student_id': student.get('student_id') or '无学号',
            'seat': seat_text,
            'score': float(student.get('score') or 0),
        })

list_rows = [f"{item['name']}（{item['student_id']}） · 座位 {item['seat']}" for item in rows]
hit_rate = round(len(rows) / total_count * 100, 1) if total_count > 0 else 0

status_variant = 'success' if classroom else 'danger'
status_text = '已连接班级' if classroom else '未连接班级'

ui = components.page(
    title='学生搜索',
    subtitle='支持按姓名或学号搜索，实时定位座位',
    theme={'primary': '#0a59f7', 'style': 'apple-like'},
    blocks=[
        components.badge(status_text, status_variant),
        components.badge(f"共 {total_count} 人", 'neutral'),
        components.badge(f"v3.0.0", 'primary'),
        components.badge('实时搜索', 'neutral'),

        components.divider(),

        components.section('搜索结果', f"关键词：{query or '（空）'}"),

        components.form(
            title='筛选学生',
            action='search_students',
            method='POST',
            submit_label='搜索',
            description='按姓名或学号筛选，结果可由 Seat Overlay Contribution 定位。',
            fields=[
                components.input('query', '姓名或学号', value=query, placeholder='输入关键词', input_type='search', span=8),
                components.select('limit', '返回数量', options=[10, 20, 30, 50], value=limit, span=4),
            ],
        ),

        components.metric('命中人数', len(rows), hint=f"关键词：{query or '（空）'}"),
        components.metric('学生总数', total_count, hint='当前班级'),
        components.metric('命中率', f"{hit_rate}%", hint='命中/总数'),
        components.metric('搜索上限', limit, hint='单次最多返回'),

        components.progress('命中率', hit_rate, label='搜索覆盖', hint=f"{len(rows)}/{total_count}"),

        components.text('使用说明',
            '工作页可授权注入搜索面板，支持无感快捷搜索与定位。'
            '快捷键 Ctrl+Shift+F 聚焦搜索框，Esc 清空高亮。'
            '点击搜索结果可自动滚动到对应座位并高亮显示。'),

        components.divider(),

        components.section('数据详情'),

        components.table(
            '搜索结果表格',
            columns=[
                {'key': 'name', 'label': '姓名'},
                {'key': 'student_id', 'label': '学号'},
                {'key': 'seat', 'label': '座位'},
                {'key': 'score', 'label': '分数'},
            ],
            rows=rows,
        ),

        components.list('搜索结果列表', list_rows, empty_text='暂无结果'),

        components.divider(),

        components.section('快捷操作'),

        components.actions('常用调用', items=[
            {
                'label': '搜索全部（前20）',
                'action': 'search_students',
                'method': 'POST',
                'payload': {'query': '', 'limit': 20},
            },
            {
                'label': '搜索前5名',
                'action': 'search_students',
                'method': 'POST',
                'payload': {'query': '', 'limit': 5},
                'variant': 'secondary',
            },
        ]),
    ],
)
""".strip()


def register(registry):
    registry.register_action(
        'search_students',
        _search_students,
        methods=('GET', 'POST'),
        description='按姓名或学号搜索学生',
    )
    registry.register_ui_script(
        'search_dashboard',
        STUDENT_SEARCH_UI_SCRIPT,
        methods=('GET', 'POST'),
        description='学生搜索脚本式 UI',
    )
    registry.register_command(
        'student.search',
        title='搜索学生',
        description='按姓名或学号搜索当前班级学生',
        shortcut='Ctrl+Shift+F',
        action='search_students',
        placements=('command_palette', 'workspace.toolbar'),
        permissions=('students.read',),
    )
    registry.contribute(
        'workspace.toolbar',
        {
            'id': 'student-search',
            'label': '搜索学生',
            'command': 'student.search',
            'icon': 'search',
        },
    )
    registry.register_workspace_panel(
        id='student-search-panel',
        title='学生搜索',
        placement='floating',
        command='student.search',
        ui='search_dashboard',
    )
    registry.register_seat_decorator(
        id='student-search-highlight',
        source='command-result',
        command='student.search',
        student_id_path='result.items[].id',
        variant='highlight',
    )
