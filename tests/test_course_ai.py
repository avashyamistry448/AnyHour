"""Regression tests for source-grounded ClassPilot assistant."""
import unittest
from unittest.mock import patch
import io
import json

from course_ai import grading_answer, category_grading_answer, rank_syllabus_pages, rank_materials, keyword_answer, local_answer

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


class ConciseAndDocumentTests(unittest.TestCase):
    def test_category_exams_weight_is_collective(self):
        pages = ["Intro", "Grading breakdown\nModule Quizzes: 30%\nAssignments: 30%\nExams: 30%\nReflection Video: 10%"]
        result = category_grading_answer(pages, "How much is each exam worth?")
        self.assertEqual(result["answer"], "Together, exams account for 30% of your overall grade.")
        self.assertEqual(result["sources"], ["Official Syllabus · page 2"])

    def test_category_does_not_override_individual_exam(self):
        self.assertIsNone(category_grading_answer(["Exams: 30%"], "How much is Exam 1 worth?"))

    def test_keyword_answer_uses_retrieved_syllabus_line(self):
        matches = [{"title": "Official Syllabus · page 1",
                    "answer": "Office Hours: Tuesdays at 2 PM.\\nExtra course information.",
                    "kind": "official_syllabus"}]
        result = keyword_answer("When are office hours?", matches)
        self.assertIn("Tuesdays at 2 PM", result["answer"])
        self.assertEqual(result["sources"], ["Official Syllabus · page 1"])

    def test_keyword_answer_does_not_invent_absent_answer(self):
        matches = [{"title": "Unrelated notes", "answer": "Safety glasses required in labs.", "kind": "document"}]
        self.assertIsNone(keyword_answer("What is the exam weight?", matches))

    def test_documents_are_searched_beyond_first_2200_characters(self):
        rows = [{"title":"Lab handbook", "kind":"document", "body":"Unrelated material. " * 200 + "Lab reports are due each Friday at 5pm."}]
        results = rank_materials(rows, "When are lab reports due?")
        self.assertEqual(len(results), 1)
        self.assertIn("Friday at 5pm", results[0]["answer"])

    def test_document_search_scans_multiple_uploaded_documents(self):
        rows = [
            {"title":"Week 1 notes", "kind":"document", "body":"Foundations of financial planning."},
            {"title":"Project policies", "kind":"document", "body":"Projects are due Sunday at 11:59pm."}
        ]
        results = rank_materials(rows, "When are projects due?")
        self.assertTrue(any(item["title"] == "Project policies" for item in results))


class OllamaRecoveryTests(unittest.TestCase):
    def test_original_working_plain_text_is_returned(self):
        requests = []
        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return io.BytesIO(b'{"message":{"content":"Office hours are Tuesdays at 2 PM."}}')
        matches = [{"title": "Official Syllabus · page 1",
                    "answer": "Office Hours: Tuesdays at 2 PM.",
                    "kind": "official_syllabus"}]
        with patch("course_ai.urllib.request.urlopen", side_effect=fake_urlopen):
            result = local_answer("When are office hours?", matches)
        self.assertEqual(result["answer"], "Office hours are Tuesdays at 2 PM.")
        self.assertEqual(result["mode"], "ollama")
        self.assertEqual(len(requests), 1)
        self.assertNotIn("format", requests[0])

    def test_offline_keyword_fallback_still_answers(self):
        from urllib.error import URLError
        matches = [{"title": "Official Syllabus · page 1",
                    "answer": "Office Hours: Tuesdays at 2 PM.",
                    "kind": "official_syllabus"}]
        with patch("course_ai.urllib.request.urlopen", side_effect=URLError("service down")):
            result = local_answer("When are office hours?", matches)
        self.assertIn("Tuesdays at 2 PM", result["answer"])
        self.assertEqual(result["mode"], "keyword")
        self.assertEqual(result["sources"], ["Official Syllabus · page 1"])

    def test_no_match_does_not_make_up_course_details(self):
        from urllib.error import URLError
        matches = [{"title": "Notes", "answer": "A clean glass beaker is required.", "kind": "document"}]
        with patch("course_ai.urllib.request.urlopen", side_effect=URLError("service down")):
            result = local_answer("When is the final exam?", matches)
        self.assertEqual(result["mode"], "no_match")
        self.assertNotIn("beaker", result["answer"])



class CommonStudentQuestionTests(unittest.TestCase):
    def test_professor_synonym_retrieves_instructor(self):
        pages = ["Course overview", "Instructor: Dr. Rivera\nEmail: rivera@example.edu"]
        matches = rank_syllabus_pages(pages, "Who is my professor?")
        self.assertEqual(matches[0][1]["title"], "Official Syllabus · page 2")
        answer = keyword_answer("Who is my professor?", [matches[0][1]])
        self.assertIn("Dr. Rivera", answer["answer"])

    def test_textbook_synonym_retrieves_book(self):
        pages = ["Required Book: Fundamentals of Chemistry, ISBN 1234567890"]
        matches = rank_syllabus_pages(pages, "What textbook do we need?")
        self.assertTrue(matches)
        answer = keyword_answer("What textbook do we need?", [matches[0][1]])
        self.assertIn("Fundamentals of Chemistry", answer["answer"])

    def test_office_hours_are_extractable(self):
        materials = [{"title": "Course details", "body": "Instructor: Dr. Rivera\nOffice Hours: Tuesdays at 2 PM in Room 130.", "kind": "document"}]
        result = rank_materials(materials, "When can I meet my professor?")
        self.assertTrue(result)
        answer = keyword_answer("When are office hours?", result)
        self.assertIn("Tuesdays at 2 PM", answer["answer"])

    def test_deadline_paraphrase_retrieves_due_date(self):
        rows = [{"title": "Course calendar", "body": "Assignments must be submitted by Sunday 11:59 PM.", "kind": "document"}]
        matches = rank_materials(rows, "When is homework due?")
        self.assertTrue(matches)
        self.assertIn("Sunday", matches[0]["answer"])

    def test_across_sources_choose_relevant_line(self):
        matches = [
            {"title": "Other notes", "kind": "document", "answer": "The final exam will occur in December."},
            {"title": "Official Syllabus · page 2", "kind": "official_syllabus",
             "answer": "Exams are worth 30% of the total grade."},
        ]
        answer = keyword_answer("How much are exams worth?", matches)
        self.assertIn("30%", answer["answer"])

    def test_missing_private_contact_does_not_invent(self):
        matches = [{"title": "Syllabus", "kind": "official_syllabus",
                    "answer": "Instructor: Dr. Rivera\nCourse title: Chemistry."}]
        answer = keyword_answer("What is the professor's personal phone number?", matches)
        self.assertIsNone(answer)

    def test_missing_date_does_not_return_unrelated_course_line(self):
        matches = [{"title": "Notes", "kind": "document",
                    "answer": "Final exams are important learning milestones."}]
        answer = keyword_answer("When is the final exam due?", matches)
        self.assertIsNone(answer)

    def test_many_questions_have_relevant_keyword_matches(self):
        sample = [
            ("When are office hours?", "Office Hours: Mondays at 3 PM."),
            ("Who is my professor?", "Instructor: Dr. Rivera"),
            ("What textbook is required?", "Required Book: Chemistry Fundamentals"),
            ("Are late assignments accepted?", "Late assignments are accepted with a 10% penalty."),
            ("How much are exams worth?", "Exams: 30% of final grade."),
            ("Is attendance mandatory?", "Attendance is required in every lab."),
        ]
        for question, line in sample:
            with self.subTest(question=question):
                item = {"title": "Official Syllabus · page 1", "kind": "official_syllabus",
                        "answer": line}
                self.assertIsNotNone(keyword_answer(question, [item]))


if __name__ == "__main__":
    unittest.main()
