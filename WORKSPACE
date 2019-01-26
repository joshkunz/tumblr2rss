load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

git_repository(
    name = "io_bazel_rules_python",
    remote = "https://github.com/bazelbuild/rules_python.git",
    commit = "ebd7adcbcafcc8abe3fd8e5b0e42e10ced1bfe27",
)

# Only needed for PIP support:
load("@io_bazel_rules_python//python:pip.bzl", "pip_repositories", "pip_import")

pip_repositories()

# Required PIP packages for tumblr2rss
pip_import(
   name = "pip_deps",
   requirements = "//:requirements.txt",
)

# Actually load the required pip packages
load("@pip_deps//:requirements.bzl", "pip_install")
pip_install()
