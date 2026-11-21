"""Regression tests for source-grounded ClassPilot assistant."""
import unittest

from course_ai import grading_answer, rank_syllabus_pages

GRADING_PAGE = """iClicker profile
Grading Policy
A total of 1000 points can be earned in this course.
Course Components and Point Distribution
Course Component Points Percentage of Overall Grade
Polling Exercises/Class
Participation 100 10%
Homework 100 10%
Quizzes 150 15%
Exam 1 200 20%
Exam 2 200 20%
Final Exam 250 25%
Total 1000 100%
Course letter grades will be assigned according to the scale below.
Grading Scale
A 900-1000 90%-100%
Page 6 of 18"""
PAGES = [
    "CHEM 107 syllabus. Meeting times: Monday, Wednesday, Friday.",
    "Learning outcomes and chemistry concepts.",
    "Textbooks and course materials.",
    "Homework and course policies.",
    "Exam 1 dates; Example: Exam 1 score 80%, Exam 2 score 60%, final score 80%.",
    GRADING_PAGE,
    "More details about the exam replacement policy.",
]


class GradingTests(unittest.TestCase):
    def test_final_weight(self):
        a = grading_answer(PAGES, "How much is my final worth?")
        self.assertIsNotNone(a)
        self.assertIn("25%", a["answer"])
        self.assertIn("250 points", a["answer"])
        self.assertEqual(a["sources"], ["Official Syllabus · page 6 · Grading Policy"])

    def test_exam_one_weight(self):
        a = grading_answer(PAGES, "How much is Exam 1 worth?")
        self.assertIn("20%", a["answer"])
        self.assertIn("200 points", a["answer"])

    def test_exam_two_weight(self):
        a = grading_answer(PAGES, "What percentage is Exam 2?")
        self.assertIn("20%", a["answer"])

    def test_missing_table_never_guesses(self):
        self.assertIsNone(grading_answer(PAGES[:5], "How much is my final worth?"))

    def test_misleading_examples_ignored(self):
        pages = ["Grading Policy\nCourse Components and Point Distribution\nExam 1 200 20%\nFinal Exam 250 25%"]
        a = grading_answer(pages, "How much is my final worth?")
        self.assertIn("25%", a["answer"])
        self.assertNotIn("20%", a["answer"])

    def test_search_ranks_grading_section_first(self):
        matches = rank_syllabus_pages(PAGES, "How much is my final worth?")
        self.assertEqual(matches[0][1]["title"], "Official Syllabus · page 6")

    def test_unrelated_question_does_not_trigger_grade_parser(self):
        self.assertIsNone(grading_answer(PAGES, "When does the final start?"))


if __name__ == "__main__":
    unittest.main()
