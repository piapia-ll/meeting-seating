from django.contrib import admin

from .models import StudentTag, StudentTagMembership, StudentTagRule, PersonnelLevel, PoliceDepartment, Participant, Meeting, MeetingParticipant, MeetingSeatAssignment


@admin.register(StudentTag)
class StudentTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'classroom', 'color', 'sort_order', 'created_at')
    list_filter = ('classroom',)
    search_fields = ('name', 'description')


@admin.register(StudentTagMembership)
class StudentTagMembershipAdmin(admin.ModelAdmin):
    list_display = ('student', 'tag', 'classroom', 'created_at')
    list_filter = ('classroom', 'tag')
    search_fields = ('student__name', 'student__student_id', 'tag__name')


@admin.register(StudentTagRule)
class StudentTagRuleAdmin(admin.ModelAdmin):
    list_display = ('tag', 'rule_type', 'classroom', 'enabled', 'priority')
    list_filter = ('classroom', 'rule_type', 'enabled')
    search_fields = ('tag__name', 'note')


@admin.register(PersonnelLevel)
class PersonnelLevelAdmin(admin.ModelAdmin):
    list_display=('name','order','active')
    list_editable=('order','active')

@admin.register(PoliceDepartment)
class PoliceDepartmentAdmin(admin.ModelAdmin):
    list_display=('name','short_name','order','active')
    list_editable=('short_name','order','active')

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display=('name','category','department','personnel_level','position','active')
    list_filter=('category','personnel_level','department','active')
    search_fields=('name','department__name','position')

class MeetingParticipantInline(admin.TabularInline):
    model=MeetingParticipant
    extra=0

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display=('name','meeting_date','venue','use_stage')
    inlines=(MeetingParticipantInline,)

@admin.register(MeetingSeatAssignment)
class MeetingSeatAssignmentAdmin(admin.ModelAdmin):
    list_display=('meeting','seat','participant','locked','skipped','sort_order')
