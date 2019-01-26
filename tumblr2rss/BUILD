load("@pip_deps//:requirements.bzl", "all_requirements")

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
    default_python_version = "PY3",
    data = [
        ":static",
        ":templates",
    ],
    deps = all_requirements,
)
