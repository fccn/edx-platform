"""
Views related to the transcript preferences feature
"""


import logging
import os

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from edxval.api import (
    create_or_update_video_transcript,
    delete_video_transcript,
    get_3rd_party_transcription_plans,
    get_available_transcript_languages,
    get_video_transcript_data,
    update_transcript_credentials_state_for_org
)
from opaque_keys.edx.keys import CourseKey

from contentstore.views.videos import TranscriptProvider
from openedx.core.djangoapps.video_config.models import VideoTranscriptEnabledFlag
from openedx.core.djangoapps.video_pipeline.config.waffle import (
    SAVE_CREDENTIALS_IN_VAL,
    waffle_flags
)
from openedx.core.djangoapps.video_pipeline.api import update_3rd_party_transcription_service_credentials
from student.auth import has_studio_write_access
from util.json_request import JsonResponse, expect_json
from xmodule.video_module.transcripts_utils import Transcript, TranscriptsGenerationException

__all__ = [
    'transcript_credentials_handler',
    'transcript_download_handler',
    'transcript_upload_handler',
    'transcript_delete_handler'
]

LOGGER = logging.getLogger(__name__)


class TranscriptionProviderErrorType:
    """
    Transcription provider's error types enumeration.
    """
    INVALID_CREDENTIALS = 1


def validate_transcript_credentials(provider, **credentials):
    """
    Validates transcript credentials.

    Validations:
        Providers must be either 3PlayMedia or Cielo24.
        In case of:
            3PlayMedia - 'api_key' and 'api_secret_key' are required.
            Cielo24 - 'api_key' and 'username' are required.

        It ignores any extra/unrelated parameters passed in credentials and
        only returns the validated ones.
    """
    error_message, validated_credentials = '', {}
    valid_providers = list(get_3rd_party_transcription_plans().keys())
    if provider in valid_providers:
        must_have_props = []
        if provider == TranscriptProvider.THREE_PLAY_MEDIA:
            must_have_props = ['api_key', 'api_secret_key']
        elif provider == TranscriptProvider.CIELO24:
            must_have_props = ['api_key', 'username']

        missing = [
            must_have_prop for must_have_prop in must_have_props if must_have_prop not in list(credentials.keys())
        ]
        if missing:
            error_message = u'{missing} must be specified.'.format(missing=' and '.join(missing))
            return error_message, validated_credentials

        validated_credentials.update({
            prop: credentials[prop] for prop in must_have_props
        })
    else:
        error_message = u'Invalid Provider {provider}.'.format(provider=provider)

    return error_message, validated_credentials


@expect_json
@login_required
@require_POST
def transcript_credentials_handler(request, course_key_string):
    """
    JSON view handler to update the transcript organization credentials.

    Arguments:
        request: WSGI request object
        course_key_string: A course identifier to extract the org.

    Returns:
        - A 200 response if credentials are valid and successfully updated in edx-video-pipeline.
        - A 404 response if transcript feature is not enabled for this course.
        - A 400 if credentials do not pass validations, hence not updated in edx-video-pipeline.
    """
    course_key = CourseKey.from_string(course_key_string)
    if not VideoTranscriptEnabledFlag.feature_enabled(course_key):
        return HttpResponseNotFound()

    provider = request.json.pop('provider')
    error_message, validated_credentials = validate_transcript_credentials(provider=provider, **request.json)
    if error_message:
        response = JsonResponse({'error': error_message}, status=400)
    else:
        # Send the validated credentials to edx-video-pipeline.
        credentials_payload = dict(validated_credentials, org=course_key.org, provider=provider)
        if waffle_flags()[SAVE_CREDENTIALS_IN_VAL].is_enabled(course_key):
            from edxval.api import create_or_update_transcript_credentials
            response = create_or_update_transcript_credentials(**credentials_payload)
            error_response, is_updated = response, not response.get('error_type')
        else:
            error_response, is_updated = update_3rd_party_transcription_service_credentials(**credentials_payload)
        # Send appropriate response based on whether credentials were updated or not.
        if is_updated:
            # Cache credentials state in edx-val.
            update_transcript_credentials_state_for_org(org=course_key.org, provider=provider, exists=is_updated)
            response = JsonResponse(status=200)
        else:
            # Error response would contain error types and the following
            # error type is received from edx-video-pipeline whenever we've
            # got invalid credentials for a provider. Its kept this way because
            # edx-video-pipeline doesn't support i18n translations yet.
            error_type = error_response.get('error_type')
            if error_type == TranscriptionProviderErrorType.INVALID_CREDENTIALS:
                error_message = _('The information you entered is incorrect.')

            response = JsonResponse({'error': error_message}, status=400)

    return response


@login_required
@require_GET
def transcript_download_handler(request):
    """
    JSON view handler to download a transcript.

    Arguments:
        request: WSGI request object

    Returns:
        - A 200 response with SRT transcript file attached.
        - A 400 if there is a validation error.
        - A 404 if there is no such transcript.
    """
    missing = [attr for attr in ['edx_video_id', 'language_code'] if attr not in request.GET]
    if missing:
        return JsonResponse(
            {'error': _(u'The following parameters are required: {missing}.').format(missing=', '.join(missing))},
            status=400
        )

    edx_video_id = request.GET['edx_video_id']
    language_code = request.GET['language_code']
    transcript = get_video_transcript_data(video_id=edx_video_id, language_code=language_code)
    if transcript:
        name_and_extension = os.path.splitext(transcript['file_name'])
        basename, file_format = name_and_extension[0], name_and_extension[1][1:]
        transcript_filename = '{base_name}.{ext}'.format(base_name=basename, ext=Transcript.SRT)
        transcript_content = Transcript.convert(
            content=transcript['content'],
            input_format=file_format,
            output_format=Transcript.SRT
        )
        # Construct an HTTP response
        response = HttpResponse(transcript_content, content_type=Transcript.mime_types[Transcript.SRT])
        response['Content-Disposition'] = u'attachment; filename="{filename}"'.format(filename=transcript_filename)
    else:
        response = HttpResponseNotFound()

    return response


def validate_transcript_upload_data(data, files):
    """
    Validates video transcript file.
    Arguments:
        data: A request's data part.
        files: A request's files part.
    Returns:
        None or String
        If there is error returns error message otherwise None.
    """
    error = None
    # Validate the must have attributes - this error is unlikely to be faced by common users.
    must_have_attrs = ['edx_video_id', 'language_code', 'new_language_code']
    missing = [attr for attr in must_have_attrs if attr not in data]
    if missing:
        error = _(u'The following parameters are required: {missing}.').format(missing=', '.join(missing))
    elif (
        data['language_code'] != data['new_language_code'] and
        data['new_language_code'] in get_available_transcript_languages(video_id=data['edx_video_id'])
    ):
        error = _(u'A transcript with the "{language_code}" language code already exists.'.format(
            language_code=data['new_language_code']
        ))
    elif 'file' not in files:
        error = _(u'A transcript file is required.')

    return error


@login_required
@require_POST
def transcript_upload_handler(request):
    """
    View to upload a transcript file.

    Arguments:
        request: A WSGI request object

    Transcript file, edx video id and transcript language are required.
    Transcript file should be in SRT(SubRip) format.

    Returns
        - A 400 if any of the validation fails
        - A 200 if transcript has been uploaded successfully
    """
    error = validate_transcript_upload_data(data=request.POST, files=request.FILES)
    if error:
        response = JsonResponse({'error': error}, status=400)
    else:
        edx_video_id = request.POST['edx_video_id']
        language_code = request.POST['language_code']
        new_language_code = request.POST['new_language_code']
        transcript_file = request.FILES['file']
        try:
            # Convert SRT transcript into an SJSON format
            # and upload it to S3.
            sjson_subs = Transcript.convert(
                content=transcript_file.read().decode('utf-8'),
                input_format=Transcript.SRT,
                output_format=Transcript.SJSON
            ).encode()
            create_or_update_video_transcript(
                video_id=edx_video_id,
                language_code=language_code,
                metadata={
                    'provider': TranscriptProvider.CUSTOM,
                    'file_format': Transcript.SJSON,
                    'language_code': new_language_code
                },
                file_data=ContentFile(sjson_subs),
            )
            response = JsonResponse(status=201)
        except (TranscriptsGenerationException, UnicodeDecodeError):
            response = JsonResponse(
                {'error': _(u'There is a problem with this transcript file. Try to upload a different file.')},
                status=400
            )

    return response


@login_required
@require_http_methods(["DELETE"])
def transcript_delete_handler(request, course_key_string, edx_video_id, language_code):
    """
    View to delete a transcript file.

    Arguments:
        request: A WSGI request object
        course_key_string: Course key identifying a course.
        edx_video_id: edX video identifier whose transcript need to be deleted.
        language_code: transcript's language code.

    Returns
        - A 404 if the user does not have required permisions
        - A 200 if transcript is deleted without any error(s)
    """
    # Check whether the feature is available for this course.
    course_key = CourseKey.from_string(course_key_string)
    # User needs to have studio write access for this course.
    if not has_studio_write_access(request.user, course_key):
        return HttpResponseNotFound()

    delete_video_transcript(video_id=edx_video_id, language_code=language_code)

    return JsonResponse(status=200)
