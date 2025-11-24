"""
search.py

This module is used to register search/filter views methods
"""

import json
from urllib.parse import parse_qs

from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import render

from base.methods import get_key_instances, get_pagination, sortby
from horilla.decorators import (
    hx_request_required,
    is_recruitment_manager,
    login_required,
    permission_required,
)
from horilla.group_by import group_by_queryset
from horilla.group_by import group_by_queryset as general_group_by
from recruitment.filters import (
    CandidateFilter,
    RecruitmentFilter,
    StageFilter,
)
from recruitment.models import (
    Candidate,
    Recruitment,
    Stage,
)
from recruitment.views.paginator_qry import paginator_qry


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_recruitment")
def recruitment_search(request):
    """
    This method is used to search recruitment
    """
    if not request.GET:
        request.GET.copy().update({"is_active": "on"})
    queryset = Recruitment.objects.all()
    if not request.GET.get("is_active"):
        queryset = Recruitment.objects.filter(is_active=True)
    filter_obj = RecruitmentFilter(request.GET, queryset)
    previous_data = request.GET.urlencode()
    recruitment_obj = sortby(request, filter_obj.qs, "orderby")
    data_dict = parse_qs(previous_data)
    get_key_instances(Recruitment, data_dict)

    return render(
        request,
        "recruitment/recruitment_component.html",
        {
            "data": paginator_qry(recruitment_obj, request.GET.get("page")),
            "pd": previous_data,
            "filter_dict": data_dict,
        },
    )


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_stage")
def stage_search(request):
    """
    This method is used to search stage
    """
    queryset = Stage.objects.filter(recruitment_id__is_active=True)
    stages = StageFilter(request.GET, queryset).qs
    previous_data = request.GET.urlencode()
    stages = sortby(request, stages, "orderby")
    data_dict = parse_qs(previous_data)
    get_key_instances(Stage, data_dict)
    recruitments = group_by_queryset(
        stages, "recruitment_id", request.GET.get("rpage"), "rpage"
    )

    return render(
        request,
        "stage/stage_group.html",
        {
            "data": paginator_qry(stages, request.GET.get("page")),
            "recruitments": recruitments,
            "pd": previous_data,
            "filter_dict": data_dict,
        },
    )


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_candidate")
def candidate_search(request):
    """
    This method is used to search candidate model and return matching objects
    """
    previous_data = request.GET.urlencode()
    search = request.GET.get("search")
    if search is None:
        search = ""
    candidates = Candidate.objects.filter(name__icontains=search)
    candidates = CandidateFilter(request.GET, queryset=candidates).qs
    data_dict = []
    if not request.GET.get("dashboard"):
        data_dict = parse_qs(previous_data)
        get_key_instances(Candidate, data_dict)

    template = "candidate/candidate_card.html"
    if request.GET.get("view") == "list":
        template = "candidate/candidate_list.html"
    candidates = sortby(request, candidates, "orderby")

    field = request.GET.get("field")
    if field != "" and field is not None:
        candidates = general_group_by(
            candidates, field, request.GET.get("page"), "page"
        )
        template = "candidate/group_by.html"
    else:
        # Store the Candidates in the session
        request.session["filtered_candidates"] = [
            candidate.id for candidate in candidates
        ]

    candidates = paginator_qry(candidates, request.GET.get("page"))

    mails = list(Candidate.objects.values_list("email", flat=True))
    # Query the User model to check if any email is present
    existing_emails = list(
        User.objects.filter(username__in=mails).values_list("email", flat=True)
    )

    return render(
        request,
        template,
        {
            "data": candidates,
            "pd": previous_data,
            "filter_dict": data_dict,
            "field": field,
            "emp_list": existing_emails,
        },
    )


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_candidate")
def candidate_filter_view(request):
    """
    This method is used for filter,pagination and search candidate.
    """
    candidates = Candidate.objects.filter(is_active=True)
    template = "candidate/candidate_card.html"
    if request.GET.get("view") == "list":
        template = "candidate/candidate_list.html"

    previous_data = request.GET.urlencode()
    filter_obj = CandidateFilter(request.GET, queryset=candidates)
    paginator = Paginator(filter_obj.qs, 24)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        template,
        {"data": page_obj, "pd": previous_data},
    )



