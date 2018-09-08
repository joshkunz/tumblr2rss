# tumblr2RSS

Turns your tumblr dashboard into an RSS feed. An installation of this service
is currently running on my website at 
[tumblr2rss.obstack.net](http://tumblr2rss.obstack.net).
Just follow the instructions on that page and you will get a link
like `http://tumblr2rss.obstack.net/v2/dashboard/<random-junk>.rss`
which can be used in your feed reader of choice.

If you want to set up your own install follow the instructions listed here:

## Setup

As a step 0, you'll need to register a new "App" with tumblr and get
an OAuth consumer key and secret. This process is not particularly difficult,
but somewhat involved, so I will not detail it here. I'll assume you
already have them.

First, clone the repository:

    git clone https://github.com/Joshkunz/tumblr2rss.git

Then make a copy of the skeleton configuration file:

    cp config.yaml.skel config.yaml

and fill in all the necessary fields. Most important are the 
`consumer_key` and `consumer_secret` fields you got from tumblr. You'll need
some random data in the `secret_key` field of this config. You can use the
included `scripts/make-secret-key` script to generate a strong key for you.
I'm going to assume you used the defaults for the rest of this guide.

The next thing you'll want to do is create a sqlite database according
to the schema located in `user.schema`. Luckily, tumblr2rss comes with
a script that can do that for you:

    scripts/make-db

Finally, you'll need to build and run the server. Tumblr2RSS is built using
[Bazel][bazel], follow the instructions
[on the Bazel site](https://docs.bazel.build/versions/master/install.html) to
install bazel. Once you have bazel installed you can run:

    bazel run tumblr2rss -- --config <path/to/your/config.yml>

Which will start the server running on <http://127.0.0.1:8080>. You can
customize the server's host and port with the `--host` and `--port` flags.

## Distributing

As of writing, the easiest way to distribute tumblr2rss is by using Bazel's
`--build_python_zip`. Run:

    bazel build --build_python_zip tumblr2rss

Which should build a zip file like `bazel-bin/tumblr2rss/tumblr2rss.zip`. This
zip file can be run like a normal python file:

    python bazel-bin/tumblr2rss/tumblr2rss.zip --help

It can even be copied to another machine and run there, as long as it has a
compatible version of Python.

[bazel]: https://bazel.build/
