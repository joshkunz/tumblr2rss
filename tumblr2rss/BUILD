load("@rules_python//python:defs.bzl", "py_binary")
load("@pip_deps//:requirements.bzl", "requirement")

filegroup(
    name = "static",
    srcs = glob(["static/*"]),
)

filegroup(
    name = "templates",
    srcs = glob(["templates/*"]),
)

py_binary(
    name = "tumblr2rss",
    srcs = ["tumblr2rss.py"],
    srcs_version = "PY3",
    python_version = "PY3",
    data = [
        ":static",
        ":templates",
    ],
    deps = [
        requirement("Authlib"),
        requirement("Flask"),
        requirement("PyRSS2Gen"),
        requirement("PyYAML"),
        requirement("gunicorn"),
        requirement("requests"),
    ],
)
