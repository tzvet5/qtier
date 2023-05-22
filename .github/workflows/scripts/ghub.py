import os

from github import Github


def get_env(name: str) -> str:
    return os.environ[name]


g = Github(login_or_token=get_env("__BOT_TOKEN__"), base_url="https://github.com/api/v3")
qtgql = g.get_repo("qtgql/qtgql")


def get_current_pr():
    return qtgql.get_pull(int(get_env("__PR_NUMBER__")))