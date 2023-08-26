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

Finally you can create a virtual environment:

    python3 -m virtualenv venv
    source ./venv/bin/activate
    pip3 install -r requirements.lock

Then you can run the server:

    python3 tumblr2rss.py --config ./config.yaml --host 0.0.0.0 --port 8080

Change the host and port based on your hosting environment.
