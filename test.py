import os
import json
import requests
import re
import subprocess
import argparse
import sys
import time
import yaml

# ANSI escape codes for color
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

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
        print(f"{RED}Error: 'repos.json' file not found.{RESET}")
        raise
    except json.JSONDecodeError:
        print(f"{RED}Error: 'repos.json' file is not a valid JSON.{RESET}")
        raise

def load_releases():
    try:
        with open('releases.yaml', 'r') as file:
            release_config = yaml.safe_load(file)
        return release_config.get('releases', [])
    except FileNotFoundError:
        print(f"{RED}Error: 'releases.yaml' file not found.{RESET}")
        raise
    except yaml.YAMLError:
        print(f"{RED}Error: 'releases.yaml' file is not a valid YAML.{RESET}")
        raise

def validate_branch(branch, allowed_releases):
    if branch not in allowed_releases:
        print(f"{RED}Branch '{branch}' is not in the list of allowed releases. Exiting.{RESET}")
        sys.exit(1)  # Exit with non-zero status if branch is not allowed
    else:
        print(f"{GREEN}Branch '{branch}' is valid and allowed to proceed.{RESET}")

def fetch_open_prs(org, repo, branch):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f'{GITHUB_API_URL}/repos/{org}/{repo}/pulls?state=open&base={branch}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    open_prs = response.json()
    return open_prs

# Remaining functions (e.g., get_jira_id_from_pr, get_jira_issue_details, etc.) remain the same
# ...

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process GitHub repositories and JIRA issues.')
    parser.add_argument('--branch', required=True, help='Branch name to check out and process')
    args = parser.parse_args()

    branch_name = args.branch

    # Load allowed releases and validate branch
    allowed_releases = load_releases()
    validate_branch(branch_name, allowed_releases)

    # Load main configuration and proceed if branch is valid
    config = load_config()
    org = config['org']
    all_prs_found = False

    for component in config['components']:
        for repo in component['rhds_repos']:
            checkout_branch(org, repo, branch_name)
            open_prs = fetch_open_prs(org, repo, branch_name)

            if not open_prs:
                print(f"{RED}No open PRs found for repo: {repo}.{RESET}")
                continue

            for pr in open_prs:
                if not check_authors(org, pr):
                    print(f"{RED}Skipping PR #{pr['number']} due to author checks.{RESET}")
                    continue

                jira_id = get_jira_id_from_pr(pr)
                if jira_id:
                    jira_details = get_jira_issue_details(jira_id)
                    if jira_details and jira_details.get('fields', {}).get('priority', {}).get('name') == 'Blocker':
                        print(f"{GREEN}Merging PR #{pr['number']} in repo {repo} because JIRA {jira_id} is a Blocker issue.{RESET}")
                        if check_pr_mergeable(org, repo, pr['number']):
                            merge_pr(org, repo, pr['number'])
                        else:
                            print(f"{RED}PR #{pr['number']} is not mergeable.{RESET}")
                    else:
                        print(f"{RED}Skipping PR #{pr['number']} as the JIRA issue {jira_id} is not a Blocker.{RESET}")
                else:
                    print(f"{RED}No JIRA ID found in PR #{pr['number']}. Skipping.{RESET}")
