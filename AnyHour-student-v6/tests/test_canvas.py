"""Canvas connector unit checks; does not contact a real Canvas server."""
import sys,unittest,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import canvas_api

class FakeHandler:
    headers={}

class ConnectorTests(unittest.TestCase):
    def test_unconfigured_connector_fails_cleanly(self):
        if not canvas_api.ENABLED:
            with self.assertRaisesRegex(ValueError,'not configured'):
                canvas_api.connect(FakeHandler())

    def test_browser_session_is_random_and_isolated(self):
        sid1,d1,_=canvas_api.session(FakeHandler())
        sid2,d2,_=canvas_api.session(FakeHandler())
        self.assertNotEqual(sid1,sid2)
        self.assertIsNot(d1,d2)
        self.assertIn('HttpOnly',canvas_api.session_cookie(sid1))

    def test_course_restriction_and_assignment_mapping(self):
        fakecourses=[{'id':'20','name':'Calculus','code':'MATH 152','url':'https://canvas.example.edu/courses/20'}]
        assignments=[{'id':'4','name':'Homework 8','due_at':'2026-11-28T23:59:00Z','url':'https://canvas.example.edu/courses/20/assignments/4'}]
        with patch.object(canvas_api,'courses',return_value=fakecourses),patch.object(canvas_api,'fetch_paginated',return_value=[{'id':4,'name':'Homework 8','due_at':'2026-11-28T23:59:00Z','html_url':'https://canvas.example.edu/courses/20/assignments/4','published':True}]),patch.object(canvas_api,'BASE','https://canvas.example.edu'):
            result=canvas_api.assignments({'access_token':'fake'},'20')
            self.assertEqual(result[0]['name'],'Homework 8')
            self.assertEqual(result[0]['due_at'],assignments[0]['due_at'])
            with self.assertRaisesRegex(ValueError,'not available'):
                canvas_api.assignments({'access_token':'fake'},'999')

    def test_token_disconnect(self):
        data={'access_token':'sample','refresh_token':'refresh','expires':time.time()+100,'user':'Test'}
        canvas_api.disconnect(data)
        self.assertIsNone(data['access_token'])
        self.assertIsNone(data['refresh_token'])

if __name__=='__main__':unittest.main()
