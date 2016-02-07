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

Then, optionally (but recommended) make a virtualenv:

    virtualenv tumblr2rss-virtualenv
    source tumblr2rss-virtualenv/bin/activate

Next, install the required packages:

    pip install -r requirements.txt

Then make a copy of the skeleton configuration file:

    cp config.py.skel config.py

and fill in all the necessary fields. Most important are the 
`CONSUMER_KEY` and `CONSUMER_SECRET` fields you got from tumblr.
I'm going to assume you used the defaults for the rest of this guide.

The next thing you'll want to do is create a sqlite database according
to the schema located in `user.schema`. Luckily, tumblr2rss comes with
a script that can do that for you:

    scripts/make-db

You'll also need some random data in your configured secret key file.
There's a simple script to generate this as well:

    scripts/make-secret-key

At this point you should be ready to go. Just run the following command to
start the test server:

    scripts/serve

It's not recommended that you use this development server for a "real"
deployment. <http://tumblr2rss.obstack.net> uses `gunicorn` with the
supplied `gunicorn.conf` configuration.

## Migrating

Recently I've made changes that anonymize Dashboard feed URLs. Unfortunately,
this required a table schema change. The code should be backwards compatible,
but if you would like to use the new schema, you'll have to convert your old
database using `scripts/v1tov2-migrate-db`.
