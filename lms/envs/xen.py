from .aws import *

################### CEPH

AWS_S3_HOST =  ENV_TOKENS.get('AWS_S3_HOST', 's3.amazonaws.com')

COURSE_DISCOVERY_MEANINGS = ENV_TOKENS.get('COURSE_DISCOVERY_MEANINGS', {})

ORA2_FILEUPLOAD_BACKEND = "django"

EDX_ORA_ALLOWED_FILE_TYPES = {
    'image/gif': '.gif',
    'image/jpeg': '.jpeg',
    'image/pjpeg': '.pjpeg',
    'image/png': '.png',
    'application/pdf': '.pdf',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'text/csv': '.csv',
    'application/vnd.ms-powerpoint': '.ppt',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
    'text/plain': '.txt',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
}
