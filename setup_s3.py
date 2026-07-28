import boto3
import sys

def setup_s3():
    try:
        s3 = boto3.client('s3')
        # Try to list buckets to verify connection
        response = s3.list_buckets()
        print("Successfully connected to AWS!")
        
        bucket_name = "tn-dms-document-lake"
        
        # Check if bucket exists
        existing_buckets = [b['Name'] for b in response['Buckets']]
        if bucket_name not in existing_buckets:
            print(f"Creating bucket: {bucket_name}")
            if s3.meta.region_name == 'us-east-1':
                s3.create_bucket(Bucket=bucket_name)
            else:
                s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': s3.meta.region_name}
                )
            print("Bucket created successfully.")
        else:
            print(f"Bucket {bucket_name} already exists.")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_s3()
