"""Seed an isolated demo and capture evidence from the running Django application."""
import os
import sys
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from onlinecourse.models import Choice, Course, Enrollment, Lesson, Question, Submission

PASSWORD = 'local-ci-demo-password'
BASE = 'http://127.0.0.1:8000'


def seed():
    users = get_user_model().objects
    users.create_superuser('demo_admin', 'admin@example.test', PASSWORD)
    student = users.create_user('demo_student', password=PASSWORD)
    stranger = users.create_user('demo_other', password=PASSWORD)
    course = Course.objects.create(
        name='Database Foundations',
        description='Learn relational databases, Django models, and how to check what you learned.',
        image='course_images/demo.png',
    )
    Enrollment.objects.create(course=course, user=student)
    examples = [
        ('Relational databases', 'Tables organize rows and columns around related data.',
         'Which language is used to query a relational database?', 'SQL', 'HTML'),
        ('Django models', 'A model defines the fields and behavior of stored data.',
         'What identifies a row uniquely?', 'Primary key', 'Display title'),
        ('Working with data', 'The ORM translates model operations into database queries.',
         'Which tool maps Python model objects to database rows?', 'Django ORM', 'CSS'),
    ]
    for order, (title, content, prompt, right, wrong) in enumerate(examples, start=1):
        lesson = Lesson.objects.create(course=course, order=order, title=title, content=content)
        question = Question.objects.create(lesson=lesson, question_text=prompt)
        Choice.objects.create(question=question, choice_text=right, is_correct=True)
        Choice.objects.create(question=question, choice_text=wrong)

    client = Client(HTTP_HOST='localhost')
    submit_url = f'/onlinecourse/{course.pk}/submit/'
    assert client.post(submit_url).status_code == 302
    client.force_login(student)
    assert client.get(submit_url).status_code == 405
    assert client.post(submit_url, {'choices': ['invalid']}).status_code == 400
    assert client.post(submit_url, {'choices': [999999]}).status_code == 400
    first_question = Question.objects.order_by('pk').first()
    both = list(first_question.choice_set.values_list('pk', flat=True))
    attempt = client.post(submit_url, {'choices': both}, follow=True)
    assert attempt.status_code == 200 and b'Score: 0%' in attempt.content
    submission = Submission.objects.latest('pk')
    client.force_login(stranger)
    assert client.get(f'/onlinecourse/{course.pk}/results/{submission.pk}/').status_code == 404
    assert client.post(submit_url).status_code == 404
    print('Verified authentication, enrollment, invalid answers, exact scoring, and private results.')


def capture():
    from playwright.sync_api import expect, sync_playwright

    output = Path('screenshots')
    output.mkdir(exist_ok=True)
    course = Course.objects.get(name='Database Foundations')
    lessons = list(course.lesson_set.all())
    correct_choices = list(Choice.objects.filter(question__lesson__course=course, is_correct=True))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        admin = browser.new_page(viewport={'width': 1360, 'height': 900})
        admin.goto(f'{BASE}/admin/', wait_until='domcontentloaded')
        admin.locator('#id_username').fill('demo_admin')
        admin.locator('#id_password').fill(PASSWORD)
        admin.get_by_role('button', name='Log in').click()
        expect(admin.get_by_text('Authentication and Authorization', exact=True)).to_be_visible()
        expect(admin.get_by_text('OnlineCourse', exact=True)).to_be_visible()
        admin.screenshot(path=output / '03-admin-site.png', full_page=True)

        student = browser.new_page(viewport={'width': 1360, 'height': 900})
        student.goto(f'{BASE}/onlinecourse/login/', wait_until='domcontentloaded')
        student.locator('#username').fill('demo_student')
        student.locator('#psw').fill(PASSWORD)
        student.locator('form').filter(has=student.locator('#username')).get_by_role('button', name='Login').click()
        student.goto(f'{BASE}/onlinecourse/{course.pk}/', wait_until='domcontentloaded')
        for lesson in lessons:
            expect(student.get_by_role('heading', name=f'Lesson {lesson.order} · {lesson.title}')).to_be_visible()
        for choice in correct_choices:
            student.get_by_role('checkbox', name=choice.choice_text, exact=True).check()
        student.get_by_role('button', name='Submit exam').click()
        expect(student.get_by_role('heading', name='Congratulations!')).to_be_visible()
        expect(student.get_by_text('Score: 100% (3 / 3 points)', exact=True)).to_be_visible()
        expect(student.get_by_text('Your answer', exact=False)).to_have_count(3)
        student.screenshot(path=output / '07-final.png', full_page=True)
        browser.close()


if __name__ == '__main__':
    {'seed': seed, 'capture': capture}[sys.argv[1]]()
