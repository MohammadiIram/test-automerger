import os
import argparse
import json
import requests
import re
import time
import jwt

GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

# Get credentials from GitHub Actions secrets
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_APP_ID = os.getenv('APP_ID')
GITHUB_PRIVATE_KEY = os.getenv('APP_KEY')

# Token expiration
TOKEN_EXPIRATION_SECONDS = 600  # 10 minutes

def generate_github_jwt():
    """Generate a JWT for GitHub API."""
    if not GITHUB_PRIVATE_KEY or not GITHUB_APP_ID:
        print(f"Error: Missing APP_ID or APP_KEY.")
        exit(1)

    # If the private key is stored as a string (not file path), use it directly
    private_key = GITHUB_PRIVATE_KEY

    issued_at = int(time.time())
    payload = {
        'iat': issued_at,
        'exp': issued_at + TOKEN_EXPIRATION_SECONDS,
        'iss': GITHUB_APP_ID,
    }
    jwt_token = jwt.encode(payload, private_key, algorithm='RS256')
    
    print(f"Generated GitHub JWT (only for debugging purposes): {jwt_token}")
    
    return jwt_token
    #return jwt.encode(payload, private_key, algorithm='RS256')

def parse_arguments():
    parser = argparse.ArgumentParser(description="Process a specific PR based on PR ID.")
    parser.add_argument('--pr-id', required=True, type=int, help="The ID of the PR to process.")
    parser.add_argument('--repo', required=True, help="The name of the repository.")
    return parser.parse_args()

def load_config():
    try:
        with open('repos.json', 'r') as file:
            config = json.load(file)
        
        # Check if required keys are present
        required_keys = ["org", "components", "jira_server", "jira_project", "jira_priority"]
        for key in required_keys:
            if key not in config:
                raise KeyError(f"The '{key}' key is missing in 'repos.json'.")
        
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

    # Ensure title and body are strings
    title = str(title)
    body = str(body)

    jira_id_pattern = r'[A-Z]+-\d+'
    
   # Check the title for a JIRA ID
    jira_id_match = re.search(jira_id_pattern, title)
    if jira_id_match:
        return jira_id_match.group(0)  # Return the found JIRA ID

    # Check the body for a JIRA ID
    jira_id_match = re.search(jira_id_pattern, body)
    if jira_id_match:
        return jira_id_match.group(0)  # Return the found JIRA ID

    # Return a message if no JIRA ID was found
    #return "No JIRA ID found in PR"
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
            return jira_details
        except requests.exceptions.HTTPError as err:
            if response.status_code == 403:
                print(f"{RED}HTTP error 403: Forbidden for JIRA ID {jira_id}. Skipping.{RESET}")
                return None
            elif response.status_code == 404:
                print(f"{RED}JIRA issue {jira_id} not found. Skipping.{RESET}")
                return None
            else:
                print(f"{RED}HTTP error occurred: {err} for JIRA ID {jira_id}. Retrying ({attempt + 1}/{max_retries})...{RESET}")
                time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as err:
            print(f"{RED}Unexpected error: {err} for JIRA ID {jira_id}. Retrying ({attempt + 1}/{max_retries})...{RESET}")
            time.sleep(2 ** attempt)  # Exponential backoff

    print(f"{RED}Failed to retrieve JIRA details for ID {jira_id} after {max_retries} attempts.{RESET}")
    return None

def check_pr_mergeable(org, repo, pr_number):
    url = f'https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}'
    headers = {'Authorization': f'Bearer {generate_github_jwt()}'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get('mergeable', False)

def merge_pr(org, repo, pr, pr_number):
    url = f'https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}/merge'
    headers = {
        'Authorization': f'Bearer {generate_github_jwt()}',
        'Accept': 'application/vnd.github.v3+json'
    }
    data = {
        'commit_title': f'Merge PR #{pr_number}',
        'commit_message': 'Merged automatically because the linked JIRA issue has Blocker priority.'
    }

    response = requests.put(url, headers=headers, json=data)

    if response.status_code == 200:
        print(f"{GREEN}PR #{pr_number} in repo {repo} was successfully merged.{RESET}")

        # After merging, add a comment to the JIRA issue
        jira_id = get_jira_id_from_pr(pr)  # Obtain the JIRA ID from the PR details
        if jira_id:
            pr_link = f"https://github.com/{org}/{repo}/pull/{pr_number}"  # Construct the PR link
            comment_on_jira_issue(jira_id, "The associated pull request has been merged.", pr_link)
    else:
        print(f"{RED}Failed to merge PR #{pr_number} in repo {repo}. Response: {response.status_code} - {response.json()}{RESET}")

def comment_on_jira_issue(jira_id, comment, pr_link, max_retries=3):
    headers = {
        'Authorization': f'Bearer {JIRA_API_TOKEN}',
        'Content-Type': 'application/json'
    }
    url = f'{JIRA_SERVER}/rest/api/2/issue/{jira_id}/comment'
    # Comment with only the PR link on a new line
    full_comment = f"{comment}\n\n{pr_link}"
    data = {
        'body': full_comment
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            print(f"{GREEN}Comment added to JIRA issue {jira_id}.{RESET}")
            return
        except requests.exceptions.HTTPError as err:
            print(f"{RED}Failed to add comment to JIRA issue {jira_id}: {err}{RESET}")
            time.sleep(2 ** attempt)  
        except Exception as err:
            print(f"{RED}Unexpected error while commenting on JIRA issue {jira_id}: {err}{RESET}")
            time.sleep(2 ** attempt)  

    print(f"{RED}Failed to add comment to JIRA issue {jira_id} after {max_retries} attempts.{RESET}")


def is_user_in_org(org, username):
    """Check if a user is a member of the given GitHub organization."""
    url = f'https://api.github.com/orgs/{org}/members/{username}'
    headers = {'Authorization': f'Bearer {generate_github_jwt()}'}
    response = requests.get(url, headers=headers)
    # 204 No Content status code indicates membership
    return response.status_code == 204
  
def check_authors(org, pr):
    pr_author = pr['user']['login']
    
    # First, check if the PR is open (not merged or closed)
    if pr.get('state') != 'open':
        print(f"{GREEN}PR #{pr['number']} is not open. Skipping author check.{RESET}")
        return True  # If it's not open 
        
    # Now, proceed with organization membership check if the PR is still open
    if not is_user_in_org(org, pr_author):
        print(f"{RED}PR author '{pr_author}' not in '{org}' org. Merging not allowed. Stopping further checks.{RESET}")
        return False  # Stop here, do not proceed further if the author is not in the org

    print(f"{GREEN}PR author '{pr_author}' verified in org. Proceeding with merge.{RESET}")
    return True


def fetch_pr_details_by_id(org, repo, pr_id):
    headers = {'Authorization': f'Bearer {generate_github_jwt()}'}
    url = f'https://api.github.com/repos/{org}/{repo}/pulls/{pr_id}'
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        print(f"Error: PR #{pr_id} not found in the repository {org}/{repo}.")
        return None
    response.raise_for_status()
    return response.json()

  
if __name__ == "__main__":
    args = parse_arguments()
    pr_id = args.pr_id

    # Load configuration from repos.json
    config = load_config()
    org = config['org']
    JIRA_SERVER = config.get('jira_server', 'https://issues.redhat.com')

    # Iterate over each component and its repositories
    for component in config.get('components', []):
        for repo in component.get('rhds_repos', []):
            # Process the specific PR based on the passed PR ID
            pr_details = fetch_pr_details_by_id(org, repo, pr_id)
            if pr_details and check_authors(org, pr_details):
                jira_id = get_jira_id_from_pr(pr_details)
                if jira_id:
                    jira_details = get_jira_issue_details(jira_id)
                    if jira_details and jira_details.get('fields', {}).get('priority', {}).get('name') == 'Blocker':
                        print(f"{GREEN}Merging PR #{pr_details['number']} in repo {repo} because JIRA {jira_id} is a Blocker issue.{RESET}")
                        if check_pr_mergeable(org, repo, pr_details['number']):
                            merge_pr(org, repo, pr_details, pr_details['number'])
                        else:
                            print(f"{RED}PR #{pr_details['number']} is not mergeable.{RESET}")
                    else:
                        print(f"{RED}Skipping PR #{pr_details['number']} as the JIRA issue {jira_id} is not a Blocker.{RESET}")
                else:
                    print(f"{RED}No JIRA ID found in PR #{pr_details['number']}. Skipping.{RESET}")
