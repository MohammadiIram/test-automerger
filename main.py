# import os
# import json
# import requests
# import re
# import time

# # Get credentials from environment variables set in GitHub Actions
# JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
# GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# # Hard-coded JIRA server URL
# JIRA_SERVER = 'https://issues.redhat.com'

# # GitHub API base URL
# GITHUB_API_URL = 'https://api.github.com'

# def load_config():
#     with open('repos.json', 'r') as file:
#         config = json.load(file)
#     return config

# def fetch_open_prs(org, repo, branch=None):
#     headers = {'Authorization': f'token {GITHUB_TOKEN}'}
#     url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls?state=open'
    
#     if branch:
#         url += f'&base={branch}'
        
#     response = requests.get(url, headers=headers)
#     response.raise_for_status()
#     open_prs = response.json()
#     print(f"Fetched {len(open_prs)} open PRs for repo: {repo} on branch: {branch if branch else 'all branches'}")
#     return open_prs

# def get_jira_id_from_pr(pr):
#     title = pr.get('title', '')
#     body = pr.get('body', '')

#     jira_id_pattern = r'[A-Z]+-\d+'
    
#     jira_id_match = re.search(jira_id_pattern, title)
#     if jira_id_match:
#         jira_id = jira_id_match.group(0)
#         print(f"Extracted JIRA ID from PR {pr['number']} title: {jira_id}")
#         return jira_id

#     jira_id_match = re.search(jira_id_pattern, body)
#     if jira_id_match:
#         jira_id = jira_id_match.group(0)
#         print(f"Extracted JIRA ID from PR {pr['number']} body: {jira_id}")
#         return jira_id

#     print(f"No JIRA ID found in PR {pr['number']} title or body.")
#     return None

# def get_jira_issue_details(jira_id, max_retries=3):
#     headers = {
#         'Authorization': f'Bearer {JIRA_API_TOKEN}'
#     }
#     url = f'{JIRA_SERVER}/rest/api/2/issue/{jira_id}'

#     for attempt in range(max_retries):
#         try:
#             response = requests.get(url, headers=headers)
#             response.raise_for_status()
#             jira_details = response.json()
#             print(f"Retrieved JIRA details for ID {jira_id}: Issue type - {jira_details.get('fields', {}).get('issuetype', {}).get('name', '')}, Priority - {jira_details.get('fields', {}).get('priority', {}).get('name', '')}")
#             return jira_details
#         except requests.exceptions.HTTPError as err:
#             if response.status_code == 403:
#                 print(f"HTTP error 403: Forbidden for JIRA ID {jira_id}. Skipping.")
#                 return None
#             elif response.status_code == 404:
#                 print(f"JIRA issue {jira_id} not found. Skipping.")
#                 return None
#             else:
#                 print(f"HTTP error occurred: {err} for JIRA ID {jira_id}. Retrying ({attempt + 1}/{max_retries})...")
#                 time.sleep(2 ** attempt)  # Exponential backoff
#         except Exception as err:
#             print(f"Unexpected error: {err} for JIRA ID {jira_id}. Retrying ({attempt + 1}/{max_retries})...")
#             time.sleep(2 ** attempt)  # Exponential backoff

#     print(f"Failed to retrieve JIRA details for ID {jira_id} after {max_retries} attempts.")
#     return None

# def check_pr_mergeable(org, repo, pr_number):
#     url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}'
#     headers = {'Authorization': f'token {GITHUB_TOKEN}'}
#     response = requests.get(url, headers=headers)
#     response.raise_for_status()
#     pr_details = response.json()
#     return pr_details.get('mergeable', False)

# def merge_pr(org, repo, pr_number):
#     url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}/merge'
#     headers = {
#         'Authorization': f'token {GITHUB_TOKEN}',
#         'Accept': 'application/vnd.github.v3+json'
#     }
#     data = {
#         'commit_title': f'Merge PR #{pr_number}',
#         'commit_message': 'Merged automatically because the linked JIRA issue has Blocker priority.'
#     }

#     response = requests.put(url, headers=headers, json=data)
    
#     if response.status_code == 200:
#         print(f"PR #{pr_number} in repo {repo} was successfully merged.")
#     else:
#         print(f"Failed to merge PR #{pr_number} in repo {repo}. Response: {response.status_code} - {response.json()}")

# if __name__ == "__main__":
#     config = load_config()
#     org = config['org']

#     for component in config['components']:
#         for repo in component['rhds_repos']:
#             open_prs = fetch_open_prs(org, repo)
#             for pr in open_prs:
#                 jira_id = get_jira_id_from_pr(pr)
#                 if jira_id:
#                     jira_details = get_jira_issue_details(jira_id)
#                     if jira_details:
#                         priority = jira_details.get('fields', {}).get('priority', {}).get('name', '')
#                         if priority == "Blocker":
#                             mergeable = check_pr_mergeable(org, repo, pr['number'])
#                             if mergeable:
#                                 merge_pr(org, repo, pr['number'])
#                             else:
#                                 print(f"PR #{pr['number']} in repo {repo} is not mergeable.")

import os
import json
import requests
import re
import time

# Get credentials from environment variables
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# Hard-coded JIRA server URL
JIRA_SERVER = 'https://issues.redhat.com'

# GitHub API base URL
GITHUB_API_URL = 'https://api.github.com'

def load_config():
    try:
        with open('repos.json', 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        print("Error: 'repos.json' file not found.")
        raise
    except json.JSONDecodeError:
        print("Error: 'repos.json' file is not a valid JSON.")
        raise

def fetch_open_prs(org, repo, branch=None):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls?state=open'
    
    if branch:
        url += f'&base={branch}'
        
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    open_prs = response.json()
    print(f"Fetched {len(open_prs)} open PRs for repo: {repo} on branch: {branch if branch else 'all branches'}")
    return open_prs

def get_jira_id_from_pr(pr):
    title = pr.get('title', '')
    body = pr.get('body', '')

    jira_id_pattern = r'[A-Z]+-\d+'
    
    jira_id_match = re.search(jira_id_pattern, title)
    if jira_id_match:
        jira_id = jira_id_match.group(0)
        print(f"Extracted JIRA ID from PR {pr['number']} title: {jira_id}")
        return jira_id

    jira_id_match = re.search(jira_id_pattern, body)
    if jira_id_match:
        jira_id = jira_id_match.group(0)
        print(f"Extracted JIRA ID from PR {pr['number']} body: {jira_id}")
        return jira_id

    print(f"No JIRA ID found in PR {pr['number']} title or body.")
    return None

def get_jira_issue_details(jira_id, max_retries=3):
    headers = {
        'Authorization': f'Bearer {JIRA_API_TOKEN}'
    }
    url = f'{JIRA_SERVER}/rest/api/2/issue/{jira_id}'

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            jira_details = response.json()
            print(f"Retrieved JIRA details for ID {jira_id}: Issue type - {jira_details.get('fields', {}).get('issuetype', {}).get('name', '')}, Priority - {jira_details.get('fields', {}).get('priority', {}).get('name', '')}")
            return jira_details
        except requests.exceptions.HTTPError as err:
            if response.status_code == 403:
                print(f"HTTP error 403: Forbidden for JIRA ID {jira_id}. Skipping.")
                return None
            elif response.status_code == 404:
                print(f"JIRA issue {jira_id} not found. Skipping.")
                return None
            else:
                print(f"HTTP error occurred: {err} for JIRA ID {jira_id}. Retrying ({attempt + 1}/{max_retries})...")
                time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as err:
            print(f"Unexpected error: {err} for JIRA ID {jira_id}. Retrying ({attempt + 1}/{max_retries})...")
            time.sleep(2 ** attempt)  # Exponential backoff

    print(f"Failed to retrieve JIRA details for ID {jira_id} after {max_retries} attempts.")
    return None

def check_pr_mergeable(org, repo, pr_number):
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    pr_details = response.json()
    return pr_details.get('mergeable', False)

def merge_pr(org, repo, pr_number):
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}/merge'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    data = {
        'commit_title': f'Merge PR #{pr_number}',
        'commit_message': 'Merged automatically because the linked JIRA issue has Blocker priority.'
    }

    response = requests.put(url, headers=headers, json=data)
    
    if response.status_code == 200:
        print(f"PR #{pr_number} in repo {repo} was successfully merged.")
    else:
        print(f"Failed to merge PR #{pr_number} in repo {repo}. Response: {response.status_code} - {response.json()}")

if __name__ == "__main__":
    try:
        config = load_config()
        org = config['org']

        for component in config['components']:
            for repo in component['rhds_repos']:
                open_prs = fetch_open_prs(org, repo)
                for pr in open_prs:
                    jira_id = get_jira_id_from_pr(pr)
                    if jira_id:
                        jira_details = get_jira_issue_details(jira_id)
                        if jira_details:
                            priority = jira_details.get('fields', {}).get('priority', {}).get('name', '')
                            if priority == "Blocker":
                                mergeable = check_pr_mergeable(org, repo, pr['number'])
                                if mergeable:
                                    merge_pr(org, repo, pr['number'])
                                else:
                                    print(f"PR #{pr['number']} in repo {repo} is not mergeable.")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise


