#!/usr/bin/python3
# -*- Coding: utf-8 -*-

import csv
import time
import datetime
from datetime import timedelta, datetime, timezone
import boto3
from boto3.session import Session
import pytz
import os

now = datetime.now(tz=timezone.utc)
tokyo = pytz.timezone('Asia/Tokyo')
jst_now = tokyo.normalize(now.astimezone(tokyo))

from_date = os.environ['start_date']
to_date = os.environ['end_date']
from_date_dt = tokyo.localize(datetime.strptime(from_date, '%Y-%m-%d %H:%M:%S'))
to_date_dt = tokyo.localize(datetime.strptime(to_date, '%Y-%m-%d %H:%M:%S'))

print('from: ' + str(from_date_dt))
print('to: ' + str(to_date_dt))

file_date = jst_now.strftime('%Y%m%d%H%M')
path_date = jst_now.strftime('%Y/%m%d')
timestamp = jst_now.strftime('%Y-%m-%d %H:%M:%S')

file_name = 'Glue-UsageReport-by-date-' + file_date + '.csv'
lambda_path = '/tmp/' + file_name
bucket_name = os.environ['s3_bucket_name']
s3_path = 'aws/usage/' + path_date + '/' + file_name
region = 'ap-northeast-1'

header = [
    'Account',
    'JobId',
    'JobName',
    'StartedOn',
    'CompletedOn',
    'ExecutionTime(s)',
    'ExecutionTimeRollup(s)',
    'MaxCapacity',
    'Cost',
    'Job_Type',
    'GlueVersion',
    'Timestamp'
]

account_list = os.environ['account_list'].split(',')
assume_role_name = os.environ['assume_role_name']

def sts_assume_role(account_id,role_name):
    """
    異なるAWSアカウント/ロールのクレデンシャル取得を実行する。
    Parameters
    ----------
    account_id : string
        AWSアカウントID
    role_name : string
        IAMロール名
    """
    role_arn = 'arn:aws:iam::' + account_id + ':role/' + role_name
    session_name = 'cross_lambda_session'

    client = boto3.client('sts')

    # AssumeRoleで一時クレデンシャルを取得
    response = client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )

    session = Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken'],
        region_name=region
    )

    return session

def get_job_run_list(job_name, next_token, id):
    """
    Glueジョブの実行履歴をcsvに出力する。
    NextTokenが入ってきたら繰り返し実行する。
    Parameters
    ----------
    job_name : string
        ジョブ名
    next_token : string
        NextToken
    id : string
        ID
    """
    session = sts_assume_role(id,assume_role_name)
    sts = session.client('sts')
    Account = sts.get_caller_identity()['Account']
    # print('AccountId: ' + Account)

    if next_token is not None and next_token != '':
        response = session.client('glue').get_job_runs(
            JobName = job_name,
            MaxResults = 200,
            NextToken = next_token
        )
    else:
        response = session.client('glue').get_job_runs(
            JobName = job_name,
            MaxResults = 200
        )
    job_info = session.client('glue').get_job(
        JobName = job_name
    )
    job_info_list = job_info.get('Job')
    Job_Type = job_info_list['Command']['Name']

    if 'JobRuns' in response:
        # yield from response['JobRuns']
        history = response['JobRuns']
        # print(job_name)
        for key in history:
            result = []
            ## 対象期間判定処理
            Started_On = key['StartedOn'].strftime('%Y-%m-%d %H:%M:%S')
            Started_On_dt = datetime.strptime(Started_On, '%Y-%m-%d %H:%M:%S')
            Started_On_JST = tokyo.normalize(Started_On_dt.astimezone(tokyo))
            if (Started_On_JST < from_date_dt) or (Started_On_JST > to_date_dt):
                # print(str(Started_On_JST))
                continue

            Job_Id = key['Id']
            Job_Name = key['JobName']
            if 'CompletedOn' in key:
                Completed_On = key['CompletedOn'].strftime('%Y-%m-%d %H:%M:%S')
                Completed_On_dt = datetime.strptime(Completed_On, '%Y-%m-%d %H:%M:%S')
                Completed_On_JST = tokyo.normalize(Completed_On_dt.astimezone(tokyo))
            else:
                Completed_On_JST = ''

            ## 最小課金単位処理
            if 'GlueVersion' in key:
                Glue_Version = key['GlueVersion']
            else:
                Glue_Version = '0.9'
            Execution_Time = key['ExecutionTime']
            ExecutionTime_Rollup = key['ExecutionTime']
            if Job_Type == 'pythonshell':
                if ExecutionTime_Rollup < 60:
                    ExecutionTime_Rollup = 60
            else: # glueetl
                if Glue_Version == '0.9' or Glue_Version == '1.0':
                    if ExecutionTime_Rollup < 600:
                        ExecutionTime_Rollup = 600
                else:
                    if ExecutionTime_Rollup < 60:
                        ExecutionTime_Rollup = 60

            Execution_Time_h = ExecutionTime_Rollup / 3600
            Max_Capacity = key['MaxCapacity']
            Cost = Max_Capacity * Execution_Time_h * 0.44

            result = [
                Account,
                Job_Id,
                Job_Name,
                Started_On_JST.strftime('%Y-%m-%d %H:%M:%S'),
                Completed_On_JST.strftime('%Y-%m-%d %H:%M:%S'),
                Execution_Time,
                ExecutionTime_Rollup,
                Max_Capacity,
                Cost,
                Job_Type,
                Glue_Version,
                timestamp
            ]

            ## csv出力
            with open(lambda_path, 'a') as f:
                writer = csv.writer(f)
                writer.writerow(result)

        if 'NextToken' in response:
            # print(response['NextToken'])
            yield from get_job_run_list(job_name, next_token=response['NextToken'], id=id)

def main(event, context):
    start_time = time.time()

    ## csv新規作成、ヘッダー付与
    with open(lambda_path, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(header)

    ## 各アカウント処理
    for id in account_list:
        session = sts_assume_role(id,assume_role_name)
        # sts = session.client('sts')
        # Account = sts.get_caller_identity()['Account']
        # # print('AccountId: ' + Account)

        ## Glueジョブ一覧取得
        job_list = session.client('glue').get_jobs()
        jobs = job_list.get('Jobs')

        ## 各ジョブの実行履歴取得
        for job in jobs:
            name = job['Name']
            next_token = None
            for job_run_list in get_job_run_list(job_name=name, next_token=None, id=id):
                # print(name)
                print(job_run_list)

    ## csvファイルをS3アップロード
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    bucket.upload_file(lambda_path, s3_path)

    script_exe_time = time.time() - start_time
    print('処理時間: ' + str(round(script_exe_time, 2)) + 's')
    print('出力先S3: ' + s3_path)

if __name__ == '__main__':
    main()