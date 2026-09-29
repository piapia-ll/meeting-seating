from django.test import SimpleTestCase
from types import SimpleNamespace
from .meeting_seating import audience_column_priority, stage_column_priority, participant_sort_key

class MeetingSeatingAlgorithmTests(SimpleTestCase):
    def test_audience_priorities(self):
        self.assertEqual(audience_column_priority(5), [2,1,3,0,4])
        self.assertEqual(audience_column_priority(6), [2,3,1,4,0,5])

    def test_stage_priorities_mirror(self):
        self.assertEqual(stage_column_priority(5), [2,3,1,4,0])

    def test_business_sort(self):
        level=SimpleNamespace(order=1); dept1=SimpleNamespace(order=1); dept2=SimpleNamespace(order=2)
        def p(i,cat,lo=100,ao=100,dept=None):
            return SimpleNamespace(id=i,category=cat,leader_order=lo,attendee_order=ao,personal_order=100,personnel_level=level,department=dept)
        people=[p(4,'department',dept=dept2),p(3,'department',dept=dept1),p(2,'attendee',ao=1),p(1,'bureau_leader',lo=1)]
        self.assertEqual([x.id for x in sorted(people,key=participant_sort_key)],[1,2,3,4])
