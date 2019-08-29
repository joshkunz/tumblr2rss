load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

git_repository(
    name = "rules_python",
    remote = "https://github.com/bazelbuild/rules_python.git",
    commit = "9d68f24659e8ce8b736590ba1e4418af06ec2552",
)

load("@rules_python//python:pip.bzl", "pip_repositories")
pip_repositories()

load("@rules_python//python:pip.bzl", "pip_import")

# Required PIP packages for tumblr2rss
pip_import(
   name = "pip_deps",
   requirements = "//:requirements.txt",
)

# Actually load the required pip packages
load("@pip_deps//:requirements.bzl", "pip_install")
pip_install()
