from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from types import SimpleNamespace
from .meeting_seating import audience_column_priority, stage_column_priority, participant_sort_key, auto_assign
from .models import Classroom, Meeting, MeetingParticipant, MeetingSeatAssignment, Participant, VenueSeatRole

class MeetingSeatingAlgorithmTests(SimpleTestCase):
    def test_audience_priorities(self):
        self.assertEqual(audience_column_priority(5), [2,1,3,0,4])
        self.assertEqual(audience_column_priority(6), [3,2,4,1,5,0])

    def test_stage_priorities_mirror(self):
        self.assertEqual(stage_column_priority(5), [2,3,1,4,0])

    def test_business_sort(self):
        level=SimpleNamespace(order=1); dept1=SimpleNamespace(order=1); dept2=SimpleNamespace(order=2)
        def p(i,cat,lo=100,ao=100,dept=None):
            return SimpleNamespace(id=i,category=cat,leader_order=lo,attendee_order=ao,personal_order=100,personnel_level=level,department=dept)
        people=[p(4,'department',dept=dept2),p(3,'department',dept=dept1),p(2,'attendee',ao=1),p(1,'bureau_leader',lo=1)]
        self.assertEqual([x.id for x in sorted(people,key=participant_sort_key)],[1,2,3,4])


class MeetingAutoAssignDatabaseTests(TestCase):
    def setUp(self):
        self.venue=Classroom.objects.create(name='测试会场',rows=1,cols=5)
        self.seats=list(self.venue.seats.order_by('col'))
        self.people=[Participant.objects.create(name=f'人员{i}',leader_order=i,category='bureau_leader') for i in range(1,7)]
        self.meeting=Meeting.objects.create(name='测试会议',venue=self.venue,use_stage=False)
        for person in self.people[:5]:
            MeetingParticipant.objects.create(meeting=self.meeting,participant=person)

    def test_locked_person_is_preserved_on_rerun(self):
        auto_assign(self.meeting)
        locked=self.meeting.assignments.exclude(participant=None).first()
        person_id=locked.participant_id
        seat_id=locked.seat_id
        locked.locked=True
        locked.save(update_fields=['locked'])
        auto_assign(self.meeting)
        locked.refresh_from_db()
        self.assertEqual(locked.seat_id,seat_id)
        self.assertEqual(locked.participant_id,person_id)

    def test_meeting_skip_does_not_consume_rank(self):
        skipped_seat=self.seats[2]
        MeetingSeatAssignment.objects.create(meeting=self.meeting,seat=skipped_seat,skipped=True)
        auto_assign(self.meeting)
        self.assertIsNone(self.meeting.assignments.get(seat=skipped_seat).participant)
        assigned=list(self.meeting.assignments.exclude(participant=None).values_list('participant_id',flat=True))
        self.assertEqual(len(assigned),4)
        self.assertEqual(len(set(assigned)),4)

    def test_auto_stage_capacity_excludes_meeting_skip(self):
        for seat in self.seats:
            seat.venue_role=VenueSeatRole.STAGE
            seat.save(update_fields=['venue_role'])
        self.meeting.use_stage=True
        self.meeting.stage_mode='auto'
        self.meeting.save(update_fields=['use_stage','stage_mode'])
        MeetingParticipant.objects.create(meeting=self.meeting,participant=self.people[5])
        MeetingSeatAssignment.objects.create(meeting=self.meeting,seat=self.seats[0],skipped=True)
        auto_assign(self.meeting)
        stage_assigned=self.meeting.assignments.filter(
            seat__venue_role=VenueSeatRole.STAGE,participant__isnull=False
        ).count()
        self.assertEqual(stage_assigned,4)
        self.assertIsNone(self.meeting.assignments.get(seat=self.seats[0]).participant)

    def test_rerun_keeps_unique_person_assignments(self):
        auto_assign(self.meeting)
        auto_assign(self.meeting)
        ids=list(self.meeting.assignments.exclude(participant=None).values_list('participant_id',flat=True))
        self.assertEqual(len(ids),len(set(ids)))


class MeetingSeatSwapViewTests(TestCase):
    def setUp(self):
        self.venue=Classroom.objects.create(name='交换测试会场',rows=1,cols=2)
        self.seats=list(self.venue.seats.order_by('col'))
        self.people=[Participant.objects.create(name='甲'),Participant.objects.create(name='乙')]
        self.meeting=Meeting.objects.create(name='交换测试会议',venue=self.venue)
        for p in self.people:
            MeetingParticipant.objects.create(meeting=self.meeting,participant=p)
        self.a=MeetingSeatAssignment.objects.create(meeting=self.meeting,seat=self.seats[0],participant=self.people[0])
        self.b=MeetingSeatAssignment.objects.create(meeting=self.meeting,seat=self.seats[1],participant=self.people[1])

    def swap(self):
        return self.client.post(reverse('meeting_swap_seats',args=[self.meeting.pk]),{
            'seat_a':self.seats[0].pk,'seat_b':self.seats[1].pk,
        })

    def test_swap_two_people(self):
        response=self.swap()
        self.assertEqual(response.status_code,200)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual(self.a.participant_id,self.people[1].pk)
        self.assertEqual(self.b.participant_id,self.people[0].pk)

    def test_locked_seat_rejects_swap_without_partial_change(self):
        self.a.locked=True; self.a.save(update_fields=['locked'])
        response=self.swap()
        self.assertEqual(response.status_code,400)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual(self.a.participant_id,self.people[0].pk)
        self.assertEqual(self.b.participant_id,self.people[1].pk)

    def test_swap_person_into_empty_seat(self):
        self.b.participant=None; self.b.save(update_fields=['participant'])
        response=self.swap()
        self.assertEqual(response.status_code,200)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertIsNone(self.a.participant_id)
        self.assertEqual(self.b.participant_id,self.people[0].pk)


class MeetingSeatStateGuardTests(TestCase):
    def setUp(self):
        self.venue=Classroom.objects.create(name='状态测试会场',rows=1,cols=2)
        self.seats=list(self.venue.seats.order_by('col'))
        self.person=Participant.objects.create(name='甲')
        self.meeting=Meeting.objects.create(name='状态测试会议',venue=self.venue)
        MeetingParticipant.objects.create(meeting=self.meeting,participant=self.person)
        self.a=MeetingSeatAssignment.objects.create(meeting=self.meeting,seat=self.seats[0],participant=self.person)
        self.b=MeetingSeatAssignment.objects.create(meeting=self.meeting,seat=self.seats[1],skipped=True)

    def test_skipped_seat_rejects_manual_swap(self):
        response=self.client.post(reverse('meeting_swap_seats',args=[self.meeting.pk]),{
            'seat_a':self.seats[0].pk,'seat_b':self.seats[1].pk,
        })
        self.assertEqual(response.status_code,400)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual(self.a.participant_id,self.person.pk)
        self.assertIsNone(self.b.participant_id)
        self.assertTrue(self.b.skipped)
