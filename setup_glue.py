import boto3
import sys

def setup_glue():
    glue = boto3.client('glue')
    iam = boto3.client('iam')
    
    db_name = "tn_dms_catalog"
    crawler_name = "tn_dms_pdf_crawler"
    s3_path = "s3://tn-dms-document-lake/"
    
    try:
        # 1. Create Glue Database
        print(f"Checking Glue Database: {db_name}")
        try:
            glue.get_database(Name=db_name)
            print(f"Database {db_name} already exists.")
        except glue.exceptions.EntityNotFoundException:
            print(f"Creating Glue Database: {db_name}")
            glue.create_database(DatabaseInput={'Name': db_name})
            print("Database created.")

        # 2. Get or Create IAM Role for Crawler
        role_name = "AWSGlueServiceRole-DMS"
        print(f"Checking IAM Role: {role_name}")
        try:
            role = iam.get_role(RoleName=role_name)
            role_arn = role['Role']['Arn']
            print(f"Role {role_name} already exists.")
        except iam.exceptions.NoSuchEntityException:
            print(f"Creating IAM Role: {role_name}")
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "glue.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }
            import json
            role = iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
            role_arn = role['Role']['Arn']
            # Attach recommended policy
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
            )
            # Add S3 access
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName="S3Access",
                PolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"], "Resource": ["arn:aws:s3:::tn-dms-document-lake", "arn:aws:s3:::tn-dms-document-lake/*"]}]
                })
            )
            print("Role created and policies attached.")

        # 3. Create Glue Crawler
        print(f"Checking Glue Crawler: {crawler_name}")
        try:
            glue.get_crawler(Name=crawler_name)
            print(f"Crawler {crawler_name} already exists.")
        except glue.exceptions.EntityNotFoundException:
            print(f"Creating Glue Crawler: {crawler_name}")
            glue.create_crawler(
                Name=crawler_name,
                Role=role_arn,
                DatabaseName=db_name,
                Targets={'S3Targets': [{'Path': s3_path}]},
                TablePrefix="doc_",
                SchemaChangePolicy={'UpdateBehavior': 'UPDATE_IN_DATABASE', 'DeleteBehavior': 'DEPRECATE_IN_DATABASE'}
            )
            print("Crawler created.")

    except Exception as e:
        print(f"Error setting up Glue: {e}")

if __name__ == "__main__":
    setup_glue()
