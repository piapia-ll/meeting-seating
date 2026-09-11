from __future__ import annotations


class CloudAccountPluginService:
    def __init__(self, ctx):
        self.ctx = ctx

    def current(self):
        self.ctx.require_permission('cloud.account')
        user = self.ctx.user
        if user is None:
            return None
        return {
            'uid': user.uid,
            'nickname': user.nickname,
            'subscription_tier': user.subscription_tier,
        }


class CloudClassroomPluginService:
    def __init__(self, ctx):
        self.ctx = ctx

    def _user(self):
        self.ctx.require_permission('cloud.account')
        if self.ctx.user is None:
            raise ValueError('此服务需要云端登录态')
        return self.ctx.user

    @staticmethod
    def _serialize(classroom):
        return {
            'uuid': str(classroom.uuid),
            'name': classroom.name,
            'rows': classroom.rows,
            'cols': classroom.cols,
            'version': classroom.version,
            'is_deleted': classroom.is_deleted,
            'updated_at': classroom.updated_at.isoformat() if classroom.updated_at else None,
        }

    def list(self, *, include_deleted=False, limit=100):
        from .models import CloudClassroom

        queryset = CloudClassroom.objects.filter(user=self._user()).order_by('-updated_at', 'pk')
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        return [self._serialize(item) for item in queryset[:max(1, min(500, int(limit or 100)))]]

    def get(self, classroom_uuid):
        from .models import CloudClassroom

        classroom = CloudClassroom.objects.get(user=self._user(), uuid=classroom_uuid)
        return self._serialize(classroom)


class CloudPluginEventService:
    def __init__(self, ctx):
        self.ctx = ctx

    def emit(self, event, **payload):
        return self.ctx.registry.emit(event, source_plugin=self.ctx.plugin_id, **payload)


def cloud_plugin_service_factories():
    return {
        'accounts': CloudAccountPluginService,
        'cloud_classrooms': CloudClassroomPluginService,
        'events': CloudPluginEventService,
    }
