from django.shortcuts import render
from django.http import HttpResponseRedirect
# <HINT> Import any new Models here
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from .models import Choice, Course, Enrollment, Question, Submission
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
import logging
# Get an instance of a logger
logger = logging.getLogger(__name__)
# Create your views here.


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        # Check if user exists
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except:
            logger.error("New user")
        if not user_exist:
            user = User.objects.create_user(username=username, first_name=first_name, last_name=last_name,
                                            password=password)
            login(request, user)
            return redirect("onlinecourse:index")
        else:
            context['message'] = "User already exists."
            return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        else:
            context['message'] = "Invalid username or password."
            return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    else:
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    is_enrolled = False
    if user.id is not None:
        # Check if user enrolled
        num_results = Enrollment.objects.filter(user=user, course=course).count()
        if num_results > 0:
            is_enrolled = True
    return is_enrolled


# CourseListView
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_details_bootstrap.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lessons'] = self.object.lesson_set.order_by('order', 'pk')
        context['questions'] = exam_questions(self.object.pk)
        context['is_enrolled'] = check_if_enrolled(self.request.user, self.object)
        return context


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)
    if not is_enrolled and user.is_authenticated:
        # Create an enrollment
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))

def exam_questions(course_id):
    return Question.objects.filter(lesson__course_id=course_id).prefetch_related(
        'choice_set'
    ).order_by('lesson__order', 'lesson_id', 'pk')


@require_POST
@login_required(login_url='onlinecourse:login')
@transaction.atomic
def submit(request, course_id):
    enrollment = get_object_or_404(
        Enrollment, pk=Enrollment.objects.filter(user=request.user, course_id=course_id)
        .order_by('pk').values_list('pk', flat=True).first(),
    )
    if not exam_questions(course_id).exists():
        return HttpResponseBadRequest('This course has no exam.')
    try:
        selected_ids = {int(value) for value in request.POST.getlist('choices')}
    except ValueError:
        return HttpResponseBadRequest('Invalid choice.')
    choices = list(Choice.objects.filter(
        pk__in=selected_ids, question__lesson__course_id=course_id
    ))
    if len(choices) != len(selected_ids):
        return HttpResponseBadRequest('Invalid choice for this course.')
    submission = Submission.objects.create(enrollment=enrollment)
    submission.choices.set(choices)
    return redirect('onlinecourse:show_exam_result', course_id=course_id, submission_id=submission.pk)


@require_GET
@login_required(login_url='onlinecourse:login')
def show_exam_result(request, course_id, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related('enrollment__course'),
        pk=submission_id, enrollment__course_id=course_id, enrollment__user=request.user,
    )
    selected_ids = set(submission.choices.values_list('pk', flat=True))
    results = []
    earned = possible = 0
    for question in exam_questions(course_id):
        correct = question.is_get_score(selected_ids)
        possible += question.grade
        earned += question.grade if correct else 0
        results.append({'question': question, 'correct': correct, 'choices': [
            {'choice': choice, 'selected': choice.pk in selected_ids}
            for choice in question.choice_set.all()
        ]})
    score = round(100 * earned / possible) if possible else 0
    return render(request, 'onlinecourse/exam_result_bootstrap.html', {
        'course': submission.enrollment.course, 'results': results,
        'earned': earned, 'possible': possible, 'score': score,
        'passed': possible > 0 and 100 * earned >= 70 * possible,
    })
