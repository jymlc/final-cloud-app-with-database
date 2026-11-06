# OnlineCourse Assessment

Django course app with lessons, an enrollment-only mock exam, and a results page that explains which choices were correct. An attempt passes at 70%. Only its owner can view it.

## Run locally

Use Python 3.12 or newer.

```sh
pip install -r requirements.txt
python manage.py makemigrations onlinecourse
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/admin/` to manage courses, lessons, questions, and choices. The learner view is at `http://127.0.0.1:8000/onlinecourse/`.

The GitHub Actions workflow runs validation against an isolated database and captures both required screenshots from the running application. Download the `django-assessment-screenshots` artifact from a successful run.
