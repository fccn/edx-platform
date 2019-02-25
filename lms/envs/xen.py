from .aws import *

################### CEPH

AWS_S3_HOST =  ENV_TOKENS.get('AWS_S3_HOST', 's3.amazonaws.com')

ORA2_FILEUPLOAD_BACKEND = "django"

