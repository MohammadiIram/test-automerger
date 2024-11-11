import os
import json
import requests
import re
import subprocess
import sys
import time
import yaml
import argparse

# ANSI escape codes for color
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

def load_releases():
    try:
        with open('releases.yaml', 'r') as file:
            release_config = yaml.safe_load(file)
        return release_config.get('releases', [])
    except FileNotFoundError:
        print(f"{RED}Error: 'releases.yaml' file not found.{RESET}")
        raise
    except yaml.YAMLError:
        print(f"{RED}Error: 'releases.yaml' file is not valid YAML.{RESET}")
        raise

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

def validate_branch(branch, allowed_releases):
    if branch not in allowed_releases:
        print(f"{RED}Branch '{branch}' is not in the list of allowed releases. Exiting.{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}Branch '{branch}' is valid and allowed to proceed.{RESET}")

def get_pr_details(org, repo, pr_number):
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls/{pr_number}'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a GitHub pull request by ID.")
    parser.add_argument("--pr-id", type=int, required=True, help="The ID of the pull request to process.")
    args = parser.parse_args()

    pr_id = args.pr_id
    branch_name = os.getenv('GITHUB_REF').split('/')[-1]

    allowed_releases = load_releases()
    validate_branch(branch_name, allowed_releases)

    # Load configuration from repos.json
    config = load_config()
    org = config['org']  # Get organization from repos.json
    repo = config['repos'][0]['name'] 
    # Get PR details and process
    pr = get_pr_details(org, repo, pr_id)
    
    jira_id = get_jira_id_from_pr(pr)
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
