"""会场排排座：行政会议排序与座位优先级。"""
from .models import ParticipantCategory

def participant_sort_key(p):
    """局领导 > 列席 > 警种部门；普通人员先行政级别、同级再警种排序。"""
    if p.category == ParticipantCategory.BUREAU_LEADER:
        return (0, p.leader_order, p.personal_order, p.id)
    if p.category == ParticipantCategory.ATTENDEE:
        return (1, p.attendee_order, p.personal_order, p.id)
    level = p.personnel_level.order if p.personnel_level else 999999
    dept = p.department.order if p.department else 999999
    return (2, level, dept, p.personal_order, p.id)

def audience_column_priority(cols):
    """返回列下标（0-based）。5席=>[2,1,3,0,4]，显示序号42135。"""
    if cols <= 0: return []
    if cols % 2:
        center=cols//2; out=[center]
        for d in range(1, center+1): out += [center-d, center+d]
        return out
    right=cols//2; left=right-1; out=[]
    for d in range(cols//2): out += [right-1-d, right+d]
    return out

def stage_column_priority(cols):
    """主席台面向观众，方向与普通席镜像。5席=>中、观众视角右、左...，显示53124。"""
    return [cols-1-i for i in audience_column_priority(cols)]

def ordered_seats(seats, stage=False):
    rows={}
    for s in seats:
        if s.cell_type != 'seat' or s.meeting_status == 'skip': continue
        rows.setdefault(s.row, []).append(s)
    result=[]
    for row in sorted(rows):
        row_seats=sorted(rows[row], key=lambda x:x.col)
        index={s.col:s for s in row_seats}
        cols=sorted(index)
        priorities=stage_column_priority(len(cols)) if stage else audience_column_priority(len(cols))
        result.extend(index[cols[i]] for i in priorities)
    return result
