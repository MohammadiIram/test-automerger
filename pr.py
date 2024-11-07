import os
import json
import requests
import re
import subprocess
import sys
import time
import yaml

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
    # Adjust to load the configuration from the GitHub Actions repository
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

def fetch_open_prs(org, repo):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls?state=open'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    open_prs = response.json()
    return open_prs

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

def checkout_branch(org, repo, branch):
    # Clone the target repo within the GitHub Actions environment
    try:
        subprocess.run(['git', 'clone', f'https://github.com/{org}/{repo}.git'], check=True)
        os.chdir(repo)
        subprocess.run(['git', 'checkout', branch], check=True)
    except subprocess.CalledProcessError as e:
        print(f"{RED}Error checking out branch '{branch}' in repo '{repo}': {e}{RESET}")
        sys.exit(1)

def is_user_in_org(org, username):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f'{GITHUB_API_URL}/orgs/{org}/members/{username}'
    response = requests.get(url, headers=headers)
    return response.status_code == 204

def check_authors(org, pr):
    pr_author = pr['user']['login']
    if not is_user_in_org(org, pr_author):
        print(f"{RED}PR author '{pr_author}' not in '{org}' org.{RESET}")
        return False
    print(f"{GREEN}PR author '{pr_author}' verified in org.{RESET}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process GitHub repositories and JIRA issues.')
    parser.add_argument('--branch', required=True, help='Branch name to check out and process')
    args = parser.parse_args()
    branch_name = args.branch

    allowed_releases = load_releases()
    validate_branch(branch_name, allowed_releases)

    # Load configuration from repos.json
    config = load_config()
    org = config['org']  # Get organization from repos.json
    repo = config['repos'][0]['name']  # Get the first repository name from repos.json (adjust if needed)

    for component in config['components']:
        for repo_name in component['rhds_repos']:
            checkout_branch(org, repo_name, branch_name)
            open_prs = fetch_open_prs(org, repo_name, branch_name)
            for pr in open_prs:
                if not check_authors(org, pr):
                    continue
                jira_id = get_jira_id_from_pr(pr)
                if jira_id:
                    jira_details = get_jira_issue_details(jira_id)
                    if jira_details and jira_details.get('fields', {}).get('priority', {}).get('name') == 'Blocker':
                        if check_pr_mergeable(org, repo_name, pr['number']):
                            merge_pr(org, repo_name, pr['number'])
                        else:
                            print(f"{RED}PR #{pr['number']} is not mergeable.{RESET}")
                    else:
                        print(f"{RED}Skipping PR #{pr['number']}: JIRA {jira_id} not a Blocker.{RESET}")
                else:
                    print(f"{RED}No JIRA ID found in PR #{pr['number']}. Skipping.{RESET}")
