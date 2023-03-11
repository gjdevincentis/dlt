import os

from dlt.common.configuration.specs import RunConfiguration
from dlt.common.typing import StrStr, StrAny, Literal, List
from dlt.common.utils import filter_env_vars
from dlt.version import __version__


TExecInfoNames = Literal["kubernetes", "docker", "codespaces", "github_actions", "airflow"]
# if one of these environment variables is set, we assume to be running in CI env
CI_ENVIRONMENT_TELL = [
    "bamboo.buildKey",
    "BUILD_ID",
    "BUILD_NUMBER",
    "BUILDKITE",
    "CI",
    "CIRCLECI",
    "CONTINUOUS_INTEGRATION",
    "GITHUB_ACTIONS",
    "HUDSON_URL",
    "JENKINS_URL",
    "TEAMCITY_VERSION",
    "TRAVIS",
    "CODEBUILD_BUILD_ARN",
    "CODEBUILD_BUILD_ID",
    "CODEBUILD_BATCH_BUILD_IDENTIFIER",
]


def exec_info_names() -> List[TExecInfoNames]:
    """Get names of execution environments"""
    names: List[TExecInfoNames] = []
    if kube_pod_info():
        names.append("kubernetes")
    if is_docker():
        names.append("docker")
    github = github_info()
    if github:
        if "github_user" in github:
            names.append("codespaces")
        if "github_actions" in github:
            names.append("github_actions")
    if airflow_info():
        names.append("airflow")
    return names


def airflow_info() -> StrAny:
    try:
        from airflow.operators.python import get_current_context
        get_current_context()
        return {"AIRFLOW_TASK": True}
    except Exception:
        return None


def dlt_version_info(config: RunConfiguration) -> StrStr:
    """Gets dlt version info including commit and image version available in docker"""
    version_info = {"dlt_version": __version__, "pipeline_name": config.pipeline_name}
    # extract envs with build info
    version_info.update(filter_env_vars(["COMMIT_SHA", "IMAGE_VERSION"]))

    return version_info


def kube_pod_info() -> StrStr:
    """Extracts information on pod name, namespace and node name if running on Kubernetes"""
    return filter_env_vars(["KUBE_NODE_NAME", "KUBE_POD_NAME", "KUBE_POD_NAMESPACE"])


def github_info() -> StrStr:
    """Extracts github info"""
    info = filter_env_vars(["GITHUB_USER", "GITHUB_REPOSITORY", "GITHUB_REPOSITORY_OWNER", "GITHUB_ACTIONS"])
    # set GITHUB_REPOSITORY_OWNER as github user if not present. GITHUB_REPOSITORY_OWNER is available in github action context
    if "github_user" not in info and "github_repository_owner" in info:
        info["github_user"] = info["github_repository_owner"]  # type: ignore
    return info


def in_continuous_integration() -> bool:
    """Returns `True` if currently running inside a continuous integration context."""
    return any(env in os.environ for env in CI_ENVIRONMENT_TELL)


def is_docker() -> bool:
    """Guess if we are running in docker environment.

    https://stackoverflow.com/questions/20010199/how-to-determine-if-a-process-runs-inside-lxc-docker

    Returns:
        `True` if we are running inside docker, `False` otherwise.
    """
    # first we try to use the env
    try:
        os.stat("/.dockerenv")
        return True
    except Exception:
        pass

    # if that didn't work, try to use proc information
    try:
        with open("/proc/self/cgroup", mode="r", encoding="utf-8") as f:
            return "docker" in f.read()
    except Exception:
        return False
