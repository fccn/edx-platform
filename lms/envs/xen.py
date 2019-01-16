from .aws import *

################### CEPH

AWS_S3_HOST =  ENV_TOKENS.get('AWS_S3_HOST', 's3.amazonaws.com')

COURSE_DISCOVERY_MEANINGS = ENV_TOKENS.get('COURSE_DISCOVERY_MEANINGS', {})

ORA2_FILEUPLOAD_BACKEND = "django"
