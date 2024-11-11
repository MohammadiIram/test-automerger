import os
import argparse
import json
import requests
import re
import subprocess
import sys
import time
import yaml

GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

# Get credentials from GitHub Actions secrets
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# Hard-coded JIRA server URL
JIRA_SERVER = 'https://issues.redhat.com'

# GitHub API base URL
GITHUB_API_URL = 'https://api.github.com'

def parse_arguments():
    parser = argparse.ArgumentParser(description="Process a specific PR based on PR ID.")
    parser.add_argument('--pr-id', required=True, type=int, help="The ID of the PR to process.")
    return parser.parse_args()

def load_config():
    try:
        with open('repos.json', 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        print(f"{RED}Error: 'repos.json' file not found in the GitHub Actions repository.{RESET}")
        raise
    except json.JSONDecodeError:
        print(f"{RED}Error: 'repos.json' file is not valid JSON.{RESET}")
        raise

def get_jira_id_from_pr(pr):
    title = pr.get('title', '')
    body = pr.get('body', '')

    jira_id_pattern = r'[A-Z]+-\d+'
    jira_id_match = re.search(jira_id_pattern, title) or re.search(jira_id_pattern, body)
    return jira_id_match.group(0) if jira_id_match else None

def get_jira_issue_details(jira_id, max_retries=3):
    headers = {'Authorization': f'Bearer {JIRA_API_TOKEN}'}
    url = f'{JIRA_SERVER}/rest/api/2/issue/{jira_id}'

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            if response.status_code in {403, 404}:
                print(f"{RED}Error {response.status_code}: {jira_id} - {err}{RESET}")
                return None
            print(f"{RED}HTTP error: {err}. Retrying ({attempt + 1}/{max_retries})...{RESET}")
            time.sleep(2 ** attempt)
    return None

def check_pr_mergeable(org, repo, pr_number):
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get('mergeable', False)

def merge_pr(org, repo, pr_number):
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}/merge'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    data = {
        'commit_title': f'Merge PR #{pr_number}',
        'commit_message': 'Auto-merged due to Blocker priority JIRA issue.'
    }
    response = requests.put(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"{GREEN}PR #{pr_number} merged successfully.{RESET}")
    else:
        print(f"{RED}Failed to merge PR #{pr_number}. Response: {response.status_code} - {response.json()}{RESET}")

def check_authors(org, pr):
    pr_author = pr['user']['login']
    if not is_user_in_org(org, pr_author):
        print(f"{RED}PR author '{pr_author}' not in '{org}' org.{RESET}")
        return False
    print(f"{GREEN}PR author '{pr_author}' verified in org.{RESET}")
    return True

def fetch_pr_details_by_id(org, repo, pr_id):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_id}'
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        print(f"Error: PR #{pr_id} not found in the repository {org}/{repo}.")
        return None
    response.raise_for_status()  # Raise error for other HTTP errors
    pr_details = response.json()
    return pr_details



if __name__ == "__main__":
    args = parse_arguments()
    pr_id = args.pr_id

    # Load configuration from repos.json
    config = load_config()
    org = config['org']
    repo = config['repos'][0]['name']  

    branch_name = os.getenv('GITHUB_REF').split('/')[-1]

    # Process the specific PR based on the passed PR ID
    pr_details = fetch_pr_details_by_id(org, repo, pr_id)  
    if pr_details and check_authors(org, pr_details):
        jira_id = get_jira_id_from_pr(pr_details)
        if jira_id:
            jira_details = get_jira_issue_details(jira_id)
            if jira_details and jira_details.get('fields', {}).get('priority', {}).get('name') == 'Blocker':
                if check_pr_mergeable(org, repo, pr_id):
                    merge_pr(org, repo, pr_id)
                else:
                    print(f"{RED}PR #{pr_id} is not mergeable.{RESET}")
            else:
                print(f"{RED}Skipping PR #{pr_id}: JIRA {jira_id} not a Blocker.{RESET}")
        else:
            print(f"{RED}No JIRA ID found in PR #{pr_id}. Skipping.{RESET}")

