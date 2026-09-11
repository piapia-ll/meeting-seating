from __future__ import annotations

from django.db.models import Q


class ClassroomPluginService:
    def __init__(self, ctx):
        self.ctx = ctx

    def current(self):
        self.ctx.require_permission('classroom.read')
        return self.ctx.classroom

    def get(self, classroom_id):
        self.ctx.require_permission('classroom.read')
        from .models import Classroom

        return Classroom.objects.get(pk=int(classroom_id))

    def serialize(self, classroom=None):
        self.ctx.require_permission('classroom.read')
        target = classroom or self.ctx.classroom
        if target is None:
            return None
        return {
            'id': target.pk,
            'name': target.name,
            'rows': target.rows,
            'cols': target.cols,
            'student_count': target.students.count(),
        }


class StudentPluginService:
    def __init__(self, ctx):
        self.ctx = ctx

    def _classroom(self, classroom=None):
        target = classroom or self.ctx.classroom
        if target is None:
            raise ValueError('缺少 classroom 上下文')
        return target

    @staticmethod
    def _serialize(student):
        seat = getattr(student, 'assigned_seat', None)
        group = getattr(seat, 'group', None) if seat else None
        return {
            'id': student.pk,
            'name': student.name,
            'student_id': student.student_id or '',
            'score': float(student.score or 0),
            'seat': {'row': seat.row, 'col': seat.col} if seat else None,
            'group': {'id': group.pk, 'name': group.name} if group else None,
        }

    def list(self, *, classroom=None, limit=100, offset=0):
        self.ctx.require_permission('students.read')
        target = self._classroom(classroom)
        limit_value = max(1, min(500, int(limit or 100)))
        offset_value = max(0, int(offset or 0))
        queryset = target.students.select_related('assigned_seat__group').order_by('name', 'pk')
        return [self._serialize(item) for item in queryset[offset_value:offset_value + limit_value]]

    def search(self, keyword='', *, classroom=None, limit=50):
        self.ctx.require_permission('students.read')
        target = self._classroom(classroom)
        text = str(keyword or '').strip()
        queryset = target.students.select_related('assigned_seat__group').order_by('name', 'pk')
        if text:
            queryset = queryset.filter(Q(name__icontains=text) | Q(student_id__icontains=text))
        return [self._serialize(item) for item in queryset[:max(1, min(100, int(limit or 50)))]]

    def get(self, student_id, *, classroom=None):
        self.ctx.require_permission('students.read')
        target = self._classroom(classroom)
        return self._serialize(target.students.select_related('assigned_seat__group').get(pk=int(student_id)))


class SeatPluginService:
    def __init__(self, ctx):
        self.ctx = ctx

    def locate(self, student_id, *, classroom=None):
        self.ctx.require_permission('students.read')
        target = classroom or self.ctx.classroom
        if target is None:
            raise ValueError('缺少 classroom 上下文')
        seat = target.seats.filter(student_id=int(student_id)).select_related('group').first()
        if seat is None:
            return None
        return {
            'student_id': int(student_id),
            'row': seat.row,
            'col': seat.col,
            'group': {'id': seat.group_id, 'name': seat.group.name} if seat.group_id else None,
        }


class PluginEventService:
    def __init__(self, ctx):
        self.ctx = ctx

    def emit(self, event, **payload):
        return self.ctx.registry.emit(event, source_plugin=self.ctx.plugin_id, **payload)


class PluginActionService:
    def __init__(self, ctx):
        self.ctx = ctx

    def run(self, action, payload=None, method='POST'):
        return self.ctx.registry.run_action(
            self.ctx.plugin_id,
            action,
            method=method,
            request=self.ctx.request,
            classroom=self.ctx.classroom,
            payload=payload or {},
        )


def local_plugin_service_factories():
    return {
        'classrooms': ClassroomPluginService,
        'students': StudentPluginService,
        'seats': SeatPluginService,
        'events': PluginEventService,
        'actions': PluginActionService,
    }
